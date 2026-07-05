import os
import logging
import shlex  # Safe shell escaping from the standard library
import docker
from tools.security_guard import check_command_safety
import utils.config_manager as config_manager       

logger = logging.getLogger("tools.sandbox_executor")

class DockerSandboxExecutor:
    def __init__(self, sandbox_root: str, fallback_approval_callback=None):
        self.sandbox_root = os.path.abspath(sandbox_root)
        self._docker_available = None
        self.fallback_approval_callback = fallback_approval_callback

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

    def run_command(self, command: str, timeout_seconds: int = None) -> dict:
        """
        Executes shell commands inside an isolated Docker container with strict resource
        limits, falling back to local subprocess execution if Docker is unavailable.

        Returns a structured result instead of a bare string:
            {"status": "success" | "error", "output": str}
        Success/failure is determined from the actual exit code of the process
        (or the Docker container error), never by inspecting the text of the output.
        """
        sandbox_config = config_manager.get_sandbox_settings()
        docker_image = config_manager.get_docker_image()
        workspace_path = config_manager.get_workspace_path()
        if timeout_seconds is None:
            timeout_seconds = sandbox_config.get("timeout_seconds", 15)
        if not self._check_docker():
            return self._run_local_fallback(command, timeout_seconds)

        try:
            client = docker.from_env()
            # Quote and isolate execution strings safely using shlex
            execution_cmd = f"sh -c {shlex.quote(command)}"

            container = client.containers.run(
                image=docker_image,
                command=execution_cmd,
                volumes={workspace_path: {"bind": "/workspace", "mode": "rw"}},
                working_dir="/workspace",
                network_disabled=True,          # Cuts off internet access within the container
                mem_limit=sandbox_config.get("mem_limit", "512m"),      # Restrict memory usage
                nano_cpus=sandbox_config.get("nano_cpus", 1000000000),  # Limits to 1 CPU core
                timeout=timeout_seconds,
                remove=True,
                stdout=True,
                stderr=True
            )
            output_text = container.decode("utf-8").strip() or "[Command executed with no output]"
            return {"status": "success", "output": output_text}
        except docker.errors.ContainerError as e:
            error_text = f"Error: Process failed with exit code {e.exit_status}. Output: {e.stderr.decode('utf-8').strip()}"
            return {"status": "error", "output": error_text}
        except Exception as e:
            return {"status": "error", "output": f"Sandbox execution failure: {str(e)}"}

    def _run_local_fallback(self, command: str, timeout_seconds: int) -> dict:
        """
        Subprocess execution boundary fallback if Docker is offline.

        Returns a structured result: {"status": "success" | "error", "output": str}.
        Status is set from the process's real returncode, not from string content.
        """
        import subprocess

        is_safe, warning_reason = check_command_safety(command)
        if not is_safe:
            if not self.fallback_approval_callback:
                return {
                    "status": "error",
                    "output": f"Error: Execution blocked. Destructive command flagged: {warning_reason}."
                }

            # Delegate validation directly to the presentation callback
            approved = self.fallback_approval_callback(command, warning_reason)
            if not approved:
                return {
                    "status": "error",
                    "output": f"Error: Execution blocked by user. Reason: Failed safety check ({warning_reason})."
                }

        try:
            result = subprocess.run(
                command, shell=True, cwd=self.sandbox_root, capture_output=True,
                text=True, timeout=timeout_seconds
            )
            output = "\n".join(filter(None, [result.stdout, result.stderr])).strip()
            output = output or "[Command executed with no output]"
            status = "success" if result.returncode == 0 else "error"
            return {"status": status, "output": output}
        except subprocess.TimeoutExpired:
            return {
                "status": "error",
                "output": f"Error: Command execution timed out (exceeded {timeout_seconds} seconds)."
            }
        except Exception as e:
            return {"status": "error", "output": f"Error executing native command: {e}"}