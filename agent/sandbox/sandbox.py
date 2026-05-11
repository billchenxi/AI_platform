import os
import shutil
import tempfile
import docker
import time
from typing import Tuple, Optional

class DockerSandbox:
    def __init__(self, source_repo_path: str, image: str = "public.ecr.aws/docker/library/python:3.10-slim", network_disabled: bool = True):
        self.client = docker.from_env()
        self.source_repo_path = os.path.abspath(source_repo_path)
        self.image = image
        self.network_disabled = network_disabled

        # Create a temporary directory to act as the sandbox workspace
        self.sandbox_dir = tempfile.mkdtemp(prefix="agent_sandbox_")
        self.workspace_dir = os.path.join(self.sandbox_dir, "workspace")

        # Copy the source repo to the workspace
        shutil.copytree(self.source_repo_path, self.workspace_dir)

        self.container = None

    def start(self):
        """Starts the sandbox container."""
        # Ensure the image is available
        try:
            self.client.images.get(self.image)
        except docker.errors.ImageNotFound:
            print(f"Pulling image {self.image}...")
            self.client.images.pull(self.image)

        # Start the container
        self.container = self.client.containers.run(
            self.image,
            command="sh -c 'apt-get update && apt-get install -y git patch && tail -f /dev/null'",  # Install git, patch, keep container running
            detach=True,
            volumes={
                self.workspace_dir: {"bind": "/workspace", "mode": "rw"}
            },
            working_dir="/workspace",
            network_disabled=self.network_disabled,
            # Basic security constraints
            pids_limit=100,
            mem_limit="1g"
        )
        # Give it a moment to start
        time.sleep(1)

    def stop(self, keep_sandbox: bool = False):
        """Stops the container and cleans up."""
        if self.container:
            try:
                self.container.stop(timeout=2)
                self.container.remove()
            except Exception as e:
                print(f"Warning: Failed to stop/remove container: {e}")
            self.container = None

        if not keep_sandbox:
            shutil.rmtree(self.sandbox_dir, ignore_errors=True)

    def run_command(self, command: str, timeout: int = 30) -> Tuple[int, str]:
        """Runs a shell command inside the sandbox."""
        if not self.container:
            raise RuntimeError("Sandbox container is not running.")

        # Basic check for obviously dangerous commands (though docker provides isolation)
        dangerous = ["rm -rf /", "sudo ", "/var/run/docker.sock"]
        for d in dangerous:
            if d in command:
                return 1, f"Command rejected for security reasons: contains '{d}'"

        try:
            # We run the command via sh -c to support pipes, etc.
            exit_code, output = self.container.exec_run(
                cmd=["sh", "-c", command],
                workdir="/workspace"
            )
            return exit_code, output.decode('utf-8', errors='replace')
        except Exception as e:
            return 1, f"Error executing command: {str(e)}"

    def read_file(self, file_path: str) -> str:
        """Reads a file from the sandbox workspace."""
        full_path = self._resolve_path(file_path)
        with open(full_path, 'r', encoding='utf-8') as f:
            return f.read()

    def write_file(self, file_path: str, content: str):
        """Writes content to a file in the sandbox workspace."""
        full_path = self._resolve_path(file_path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, 'w', encoding='utf-8') as f:
            f.write(content)

    def list_files(self, directory: str = ".") -> str:
        """Lists files in the sandbox workspace."""
        full_path = self._resolve_path(directory)
        result = []
        for root, dirs, files in os.walk(full_path):
            rel_path = os.path.relpath(root, self.workspace_dir)
            if rel_path == '.':
                rel_path = ''
            for d in dirs:
                result.append(os.path.join(rel_path, d) + "/")
            for f in files:
                result.append(os.path.join(rel_path, f))
        return "\n".join(sorted(result))

    def _resolve_path(self, file_path: str) -> str:
        """Safely resolves a path relative to the workspace dir to prevent directory traversal."""
        # Normalize and make it absolute relative to workspace
        # Remove leading slashes so os.path.join doesn't treat it as absolute root
        safe_path = file_path.lstrip('/')
        full_path = os.path.abspath(os.path.join(self.workspace_dir, safe_path))

        # Verify it's still inside the workspace
        if not full_path.startswith(self.workspace_dir):
            raise ValueError(f"Path traversal detected: {file_path}")

        return full_path
