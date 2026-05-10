import argparse
import os
import sys

from agent.llm import OpenAICompatibleProvider
from agent.sandbox import DockerSandbox
from agent.tools import ToolRegistry
from agent.core import Agent

def main():
    parser = argparse.ArgumentParser(description="Local AI Coding Agent")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run the agent on a task")
    run_parser.add_argument("--repo", required=True, help="Path to the local repository")
    run_parser.add_argument("--task", required=True, help="Natural language task description")
    run_parser.add_argument("--model", default="gpt-4o", help="Model name to use")
    run_parser.add_argument("--base-url", default=None, help="Base URL for OpenAI-compatible API (e.g., Ollama)")

    args = parser.parse_args()

    if args.command == "run":
        if not os.path.exists(args.repo) or not os.path.isdir(args.repo):
            print(f"Error: Repository path '{args.repo}' does not exist or is not a directory.")
            sys.exit(1)

        print(f"Initializing agent...")
        provider = OpenAICompatibleProvider(model=args.model, base_url=args.base_url)

        print(f"Preparing sandbox for '{args.repo}'...")
        sandbox = DockerSandbox(source_repo_path=args.repo)

        registry = ToolRegistry(sandbox=sandbox)

        agent = Agent(provider=provider, sandbox=sandbox, registry=registry)

        agent.run(task=args.task)

if __name__ == "__main__":
    main()
