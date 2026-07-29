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
    It isolates processes by restricting command execution to the workspace directory
    and enforcing a local Python virtual environment.
    """
    def __init__(self, sandbox_root: str):
        self.sandbox_root = os.path.abspath(sandbox_root)
        self.venv_dir = os.path.join(self.sandbox_root, ".venv")
        self._ensure_venv()

    def _ensure_venv(self):
        """Creates a virtual environment if it doesn't exist to protect the host machine."""
        os.makedirs(self.sandbox_root, exist_ok=True)
        if not os.path.exists(self.venv_dir):
            # Create venv with pip installed
            venv.create(self.venv_dir, with_pip=True)

    def _get_venv_executable(self, executable_name: str) -> str:
        """Resolves the correct path for venv executables across Windows and Unix."""
        if sys.platform == "win32":
            return os.path.join(self.venv_dir, "Scripts", f"{executable_name}.exe")
        return os.path.join(self.venv_dir, "bin", executable_name)

    def run_command(self, command: list[str], timeout_seconds: int = None) -> dict:
        """
        Backend utility to run hardcoded commands.
        Intercepts 'python' and 'pip' to route them through the workspace .venv.
        """
        if not command:
            return {"status": "error", "output": "Empty command provided."}

        if timeout_seconds is None:
            timeout_seconds = 15

        self._ensure_venv()  # Ensure it wasn't deleted mid-session

        # Intercept Python and Pip to force venv usage
        if command[0] in ["python", "python3"]:
            command[0] = self._get_venv_executable("python")
        elif command[0] in ["pip", "pip3"]:
            command[0] = self._get_venv_executable("pip")

        # Prepare environment variables to ensure nested subprocesses respect the venv
        env = os.environ.copy()
        env["VIRTUAL_ENV"] = self.venv_dir
        bin_dir = os.path.dirname(self._get_venv_executable("python"))
        env["PATH"] = f"{bin_dir}{os.pathsep}{env.get('PATH', '')}"

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
                env=env,  # Pass the modified environment
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
        """Mock cleanup for compatibility with Docker interface."""
        return True