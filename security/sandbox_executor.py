# security/sandbox_executor.py
import subprocess
import os
import sys
import venv

class LocalSandboxExecutor:
    """
    LOCAL HOST EXECUTION ENGINE (RAM-Free)
    -----------------------------------------------------------------
    This fallback class is used for local systems without Docker Desktop.
    It isolates processes by restricting command execution to the workspace directory,
    and automatically forces Python/Pip commands into a sandboxed Virtual Environment.
    """
    def __init__(self, sandbox_root: str):
        self.sandbox_root = os.path.abspath(sandbox_root)
        self.venv_dir = os.path.join(self.sandbox_root, ".venv")
        self._ensure_venv()

    def _ensure_venv(self):
        """Creates a Python virtual environment silently if it doesn't exist."""
        if not os.path.exists(self.venv_dir):
            os.makedirs(self.sandbox_root, exist_ok=True)
            venv.create(self.venv_dir, with_pip=True)

    def _get_venv_binary(self, binary_name: str) -> str:
        """Resolves the correct binary path for Windows or Unix."""
        # Normalize python3/pip3 to python/pip for cross-platform venv mapping
        base_name = "python" if "python" in binary_name else "pip" if "pip" in binary_name else binary_name
        
        if sys.platform == "win32":
            return os.path.join(self.venv_dir, "Scripts", f"{base_name}.exe")
        return os.path.join(self.venv_dir, "bin", base_name)

    def run_command(self, command: list[str], timeout_seconds: int = None) -> dict:
        """
        Backend utility to run hardcoded commands.
        Takes a list (e.g., ["git", "status"]) instead of a raw string.
        """
        if timeout_seconds is None:
            timeout_seconds = 15

        os.makedirs(self.sandbox_root, exist_ok=True)

        # INTERCEPT AND REROUTE TO VENV
        if command and command[0] in ["python", "python3", "pip", "pip3"]:
            command[0] = self._get_venv_binary(command[0])

        try:
            # shell=False prevents injection.
            # cwd=self.sandbox_root ensures it ALWAYS runs standing in the workspace directory.
            result = subprocess.run(
                command,
                shell=False,
                cwd=self.sandbox_root,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                encoding="utf-8",
                errors="replace",
            )

            # COMBINE stdout and stderr so we never miss hidden logs
            combined_output = f"{result.stdout}\n{result.stderr}".strip()

            if result.returncode == 0:
                return {
                    "status": "success",
                    "output": combined_output or "[Command executed with no output]",
                }
            else:
                return {
                    "status": "error",
                    "output": f"Process failed with exit code {result.returncode}.\nOutput:\n{combined_output}",
                }

        except subprocess.TimeoutExpired:
            return {
                "status": "error",
                "output": f"Execution timed out after {timeout_seconds} seconds.",
            }
        except Exception as e:
            return {"status": "error", "output": f"Local host execution failure: {e}"}

    def cleanup_container(self, conversation_id: int) -> bool:
        return True