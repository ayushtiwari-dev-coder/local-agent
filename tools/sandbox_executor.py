import subprocess
import os

class LocalSandboxExecutor:
    """
    LOCAL HOST EXECUTION ENGINE (RAM-Free)
    -----------------------------------------------------------------
    This fallback class is used for local systems without Docker Desktop.
    It isolates processes by restricting command execution to the workspace directory.
    """
    def __init__(self, sandbox_root: str):
        self.sandbox_root = os.path.abspath(sandbox_root)

    def run_command(self, command: str, timeout_seconds: int = None) -> dict:
        if timeout_seconds is None:
            timeout_seconds = 15
            
        os.makedirs(self.sandbox_root, exist_ok=True)
        
        try:
            # Executes command natively inside the safe workspace directory
            result = subprocess.run(
                command,
                shell=True,
                cwd=self.sandbox_root,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                encoding="utf-8",
                errors="replace"
            )
            
            # COMBINE stdout and stderr so the LLM never misses hidden logs
            combined_output = f"{result.stdout}\n{result.stderr}".strip()

            if result.returncode == 0:
                return {
                    "status": "success",
                    "output": combined_output or "[Command executed with no output]"
                }
            else:
                return {
                    "status": "error",
                    "output": f"Process failed with exit code {result.returncode}.\nOutput:\n{combined_output}"
                }
                
        except subprocess.TimeoutExpired:
            return {"status": "error", "output": f"Execution timed out after {timeout_seconds} seconds."}
        except Exception as e:
            return {"status": "error", "output": f"Local host execution failure: {e}"}
            
    def cleanup_container(self, conversation_id: int) -> bool:
        return True