import json
from typing import Dict, Any, Callable, List

from agent.sandbox import DockerSandbox

class ToolRegistry:
    def __init__(self, sandbox: DockerSandbox):
        self.sandbox = sandbox
        self.tools: Dict[str, Dict[str, Any]] = {}
        self._register_default_tools()

    def register(self, name: str, description: str, parameters: Dict[str, Any], func: Callable):
        self.tools[name] = {
            "definition": {
                "type": "function",
                "function": {
                    "name": name,
                    "description": description,
                    "parameters": parameters,
                }
            },
            "func": func
        }

    def get_tool_definitions(self) -> List[Dict[str, Any]]:
        return [tool["definition"] for tool in self.tools.values()]

    def execute(self, name: str, arguments: str) -> str:
        if name not in self.tools:
            return f"Error: Tool '{name}' not found."

        try:
            args = json.loads(arguments)
        except json.JSONDecodeError:
            return f"Error: Invalid JSON arguments: {arguments}"

        try:
            return self.tools[name]["func"](**args)
        except Exception as e:
            return f"Error executing {name}: {str(e)}"

    def _register_default_tools(self):
        # 1. list_files
        self.register(
            name="list_files",
            description="List all files in a given directory.",
            parameters={
                "type": "object",
                "properties": {
                    "directory": {"type": "string", "description": "The directory to list, relative to workspace root. Default is '.'"}
                }
            },
            func=self._tool_list_files
        )

        # 2. read_file
        self.register(
            name="read_file",
            description="Read the contents of a file.",
            parameters={
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "The path to the file."}
                },
                "required": ["file_path"]
            },
            func=self._tool_read_file
        )

        # 3. write_file
        self.register(
            name="write_file",
            description="Write content to a file, overwriting it entirely.",
            parameters={
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "The path to the file."},
                    "content": {"type": "string", "description": "The full content to write."}
                },
                "required": ["file_path", "content"]
            },
            func=self._tool_write_file
        )

        # 4. run_shell
        self.register(
            name="run_shell",
            description="Run a shell command in the sandbox.",
            parameters={
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "The bash command to run."}
                },
                "required": ["command"]
            },
            func=self._tool_run_shell
        )

        # 5. apply_patch
        self.register(
            name="apply_patch",
            description="Apply a unified diff patch to the workspace.",
            parameters={
                "type": "object",
                "properties": {
                    "patch_content": {"type": "string", "description": "The content of the patch file."}
                },
                "required": ["patch_content"]
            },
            func=self._tool_apply_patch
        )

        # 6. git_diff
        self.register(
            name="git_diff",
            description="Show changes between commits, commit and working tree, etc.",
            parameters={
                "type": "object",
                "properties": {}
            },
            func=self._tool_git_diff
        )

        # 7. git_status
        self.register(
            name="git_status",
            description="Show the working tree status.",
            parameters={
                "type": "object",
                "properties": {}
            },
            func=self._tool_git_status
        )

    # Tool Implementations
    def _tool_list_files(self, directory: str = ".") -> str:
        return self.sandbox.list_files(directory)

    def _tool_read_file(self, file_path: str) -> str:
        return self.sandbox.read_file(file_path)

    def _tool_write_file(self, file_path: str, content: str) -> str:
        self.sandbox.write_file(file_path, content)
        return f"Successfully wrote to {file_path}"

    def _tool_run_shell(self, command: str) -> str:
        code, output = self.sandbox.run_command(command)
        return f"Exit Code: {code}\nOutput:\n{output}"

    def _tool_apply_patch(self, patch_content: str) -> str:
        self.sandbox.write_file("temp.patch", patch_content)
        code, output = self.sandbox.run_command("patch -p1 < temp.patch")
        self.sandbox.run_command("rm temp.patch")
        return f"Exit Code: {code}\nOutput:\n{output}"

    def _tool_git_diff(self) -> str:
        code, output = self.sandbox.run_command("git diff")
        if code != 0:
             # fallback to check what's going on
             code_st, output_st = self.sandbox.run_command("git status")
             return f"git diff failed (code {code}). Output: {output}\ngit status: {output_st}"
        return output

    def _tool_git_status(self) -> str:
        code, output = self.sandbox.run_command("git status")
        return output
