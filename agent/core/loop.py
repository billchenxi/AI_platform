import json
import os
import datetime
from typing import List, Dict, Any, Callable

from agent.llm import LLMProvider
from agent.sandbox import DockerSandbox
from agent.tools import ToolRegistry


class Agent:
    def __init__(self, provider: LLMProvider, sandbox: DockerSandbox, registry: ToolRegistry):
        self.provider = provider
        self.sandbox = sandbox
        self.registry = registry

        # Internal state
        self.messages: List[Dict[str, Any]] = []
        self.tool_calls_log: List[Dict[str, Any]] = []
        self.run_dir = ""

        self.max_steps = 15

    def setup_run_dir(self, task: str):
        timestamp = datetime.datetime.now().strftime("%Y-%m-%dT%H%M%S")
        self.run_dir = os.path.join(".runs", timestamp)
        os.makedirs(self.run_dir, exist_ok=True)

        with open(os.path.join(self.run_dir, "task.json"), "w") as f:
            json.dump({"task": task, "timestamp": timestamp}, f, indent=2)

    def log_tool_call(self, tool_call: Dict[str, Any], result: str):
        entry = {
            "timestamp": datetime.datetime.now().isoformat(),
            "call": tool_call,
            "result": result
        }
        self.tool_calls_log.append(entry)

        # Append to JSONL
        if self.run_dir:
            with open(os.path.join(self.run_dir, "tool_calls.jsonl"), "a") as f:
                f.write(json.dumps(entry) + "\n")

    def log_plan(self, plan: str):
        if self.run_dir:
            with open(os.path.join(self.run_dir, "plan.md"), "w") as f:
                f.write(plan)

    def log_summary(self, summary: str):
        if self.run_dir:
            with open(os.path.join(self.run_dir, "final_summary.md"), "w") as f:
                f.write(summary)

    def save_diff(self):
        if self.run_dir:
            code, diff = self.sandbox.run_command("git diff")
            if diff:
                with open(os.path.join(self.run_dir, "diff.patch"), "w") as f:
                    f.write(diff)

    def ask_approval(self, message: str) -> bool:
        """CLI hook for user approval"""
        print(f"\n[APPROVAL REQUIRED] {message}")
        while True:
            resp = input("Approve? [y/N]: ").strip().lower()
            if resp in ['y', 'yes']:
                return True
            if resp in ['n', 'no', '']:
                return False

    def run(self, task: str):
        self.setup_run_dir(task)

        print(f"Starting task: {task}")
        self.sandbox.start()

        try:
            # 1. System Prompt & Task
            system_prompt = (
                "You are an AI coding agent. You have access to tools to inspect and modify a codebase in a secure sandbox. "
                "Your goal is to complete the user's task.\n"
                "First, inspect the repository to understand it.\n"
                "Then, create a plan and use the tools to execute it.\n"
                "When you are finished and have verified your changes with tests (if applicable), call a tool or output 'FINISHED_TASK' at the end of your response."
            )

            self.messages.append({"role": "system", "content": system_prompt})
            self.messages.append({"role": "user", "content": f"Task: {task}"})

            # Initial plan tracking
            has_planned = False
            approved = False

            for step in range(self.max_steps):
                print(f"\n--- Step {step + 1} ---")

                # Call LLM
                response = self.provider.complete(
                    messages=self.messages,
                    tools=self.registry.get_tool_definitions()
                )

                content = response.get("content", "")
                if content:
                    print(f"Agent:\n{content}\n")
                    self.messages.append({"role": "assistant", "content": content})

                    # Extract a plan if we haven't yet and it looks like one
                    if not has_planned and "plan" in content.lower() and len(content) > 50:
                        self.log_plan(content)
                        has_planned = True
                        approved = self.ask_approval("The agent has proposed a plan. Do you approve?")
                        if not approved:
                            print("Plan rejected. Exiting.")
                            break

                    if "FINISHED_TASK" in content:
                        print("Agent signaled completion.")
                        break

                # Execute Tool Calls
                tool_calls = response.get("tool_calls", [])

                if not tool_calls and not content:
                    print("Empty response from LLM, stopping.")
                    break

                if tool_calls:
                    # Assistant message containing tool calls
                    assistant_msg = {"role": "assistant", "content": None, "tool_calls": []}
                    for tc in tool_calls:
                        assistant_msg["tool_calls"].append({
                            "id": tc["id"],
                            "type": "function",
                            "function": {"name": tc["name"], "arguments": tc["arguments"]}
                        })

                    # If we added a pure content message just before, we might need to handle the API strictness.
                    # Usually better to append a single message with both content and tool_calls, but keeping it simple.
                    if content:
                        # Modify the last message to include tool calls
                        self.messages[-1]["tool_calls"] = assistant_msg["tool_calls"]
                    else:
                        self.messages.append(assistant_msg)

                    for tc in tool_calls:
                        name = tc["name"]
                        args = tc["arguments"]

                        print(f"Tool Call: {name}({args})")

                        # High risk tool approval
                        if name in ["write_file", "apply_patch", "run_shell"] and not approved:
                            # If plan wasn't explicitly approved yet, ask now before modification
                            approved = self.ask_approval(f"Approve execution of {name}?")
                            if not approved:
                                print("Action rejected. Exiting.")
                                return

                        if name == "run_shell":
                            # Check for installs and ask specifically
                            try:
                                args_dict = json.loads(args)
                                cmd = args_dict.get("cmd", args_dict.get("command", ""))
                                if "install" in cmd or "pip" in cmd or "npm" in cmd:
                                    if not self.ask_approval(f"Approve install command: {cmd}?"):
                                        print("Install rejected.")
                                        # Let the agent know it was rejected
                                        self.messages.append({
                                            "role": "tool",
                                            "tool_call_id": tc["id"],
                                            "name": name,
                                            "content": "User rejected this command."
                                        })
                                        self.log_tool_call(tc, "Rejected by user")
                                        continue
                            except Exception:
                                pass

                        result = self.registry.execute(name, args)
                        print(f"Tool Result (truncated): {result[:200]}...")

                        self.log_tool_call(tc, result)

                        self.messages.append({
                            "role": "tool",
                            "tool_call_id": tc["id"],
                            "name": name,
                            "content": result
                        })

            print("\n--- Run Complete ---")

            # Generate Final Summary
            summary_msg = {"role": "user", "content": "The run is complete. Please provide a brief summary of what you did."}
            self.messages.append(summary_msg)
            summary_resp = self.provider.complete(messages=self.messages)
            summary = summary_resp.get("content", "No summary provided.")
            print(f"\nFinal Summary:\n{summary}")

            self.log_summary(summary)
            self.save_diff()

            print(f"\nAudit logs and diff saved to: {self.run_dir}")

        finally:
            self.sandbox.stop(keep_sandbox=False)
