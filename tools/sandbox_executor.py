import os
import logging
import shlex  # Safe shell escaping from the standard library
import docker
from tools.security_guard import check_command_safety

logger = logging.getLogger("tools.sandbox_executor")

class DockerSandboxExecutor:
    def __init__(self, sandbox_root: str):
        self.sandbox_root = os.path.abspath(sandbox_root)
        self._docker_available = None

    def _check_docker(self) -> bool:
        """Verifies if the Docker engine is running locally."""
        if self._docker_available is not None:
            return self._docker_available
        try:
            client = docker.from_env()
            client.ping()
            self._docker_available = True
        except Exception:
            logger.warning("Docker is offline. Defaulting to local subprocess execution.")
            self._docker_available = False
        return self._docker_available

    def run_command(self, command: str, timeout_seconds: int = 15) -> str:
        """Executes shell commands inside an isolated Docker container with strict resource limits."""
        if not self._check_docker():
            return self._run_local_fallback(command, timeout_seconds)

        try:
            client = docker.from_env()
            # Quote and isolate execution strings safely using shlex
            execution_cmd = f"sh -c {shlex.quote(command)}"
            
            container = client.containers.run(
                image="python:3.11-slim",
                command=execution_cmd,
                volumes={self.sandbox_root: {"bind": "/workspace", "mode": "rw"}},
                working_dir="/workspace",
                network_disabled=True,            # Cuts off internet access within the container
                mem_limit="512m",                 # Limits memory consumption
                nano_cpus=1000000000,             # Limits to 1 CPU core
                timeout=timeout_seconds,
                remove=True,                     
                stdout=True,
                stderr=True
            )
            return container.decode("utf-8").strip() or "[Command executed with no output]"
        except docker.errors.ContainerError as e:
            return f"Error: Process failed with exit code {e.exit_status}. Output: {e.stderr.decode('utf-8').strip()}"
        except Exception as e:
            return f"Sandbox execution failure: {str(e)}"


    def _run_local_fallback(self, command: str, timeout_seconds: int) -> str:
        """Subprocess execution boundary fallback if Docker is offline."""
        import subprocess

        is_safe, warning_reason = check_command_safety(command)
        if not is_safe:
            print("\n" + "=" * 60)
            print("⚠️  [SECURITY WARNING] Potential Destructive Command Detected!")
            print(f"Command: {command}")
            print(f"Flagged as: {warning_reason}")
            print("=" * 60)
            

            confirm = input("Do you want to allow this command to run? (y/n): ").strip().lower()
            if confirm != 'y':
                return f"Error: Execution blocked by user. Reason: Failed safety check ({warning_reason})."
        
        try:
            result = subprocess.run(
                command, shell=True, cwd=self.sandbox_root, capture_output=True, text=True, timeout=timeout_seconds
            )
            output = "\n".join(filter(None, [result.stdout, result.stderr])).strip()
            return output or "[Command executed with no output]"
        except subprocess.TimeoutExpired:
            return f"Error: Execution timed out (exceeded {timeout_seconds} seconds)."
        except Exception as e:
            return f"Error executing native command: {e}"