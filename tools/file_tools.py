# FILE: tools/file_tools.py
import os
import json
import subprocess
from tools.sandbox_executor import DockerSandboxExecutor    

SANDBOX_ROOT = os.path.abspath(
    os.path.join(os.path.expanduser("~"), ".local_workflow_agent", "workspace")
)
os.makedirs(SANDBOX_ROOT, exist_ok=True)

def _resolve_safe_path(path: str) -> str | None:
    full_path = os.path.abspath(os.path.join(SANDBOX_ROOT, path))
    if os.path.commonpath([full_path, SANDBOX_ROOT]) != SANDBOX_ROOT:
        return None
    return full_path

def read_files(paths: list[str]) -> dict:
    """
    Safely reads multiple files from the sandboxed workspace in a single turn.

    Args:
        paths: A list of file paths, e.g. ["file1.txt", "src/main.py"]
    """
    if not isinstance(paths, list):
        return {"error": "Expected a list of paths."}
    # everything below this is unchanged — no json.loads needed
    unique_paths = []
    for p in paths:
        if p and p not in unique_paths:
            unique_paths.append(p)

    results = {}
    for path in unique_paths:
        safe_path = _resolve_safe_path(path)
        if safe_path is None:
            results[path] = f"Error: Path '{path}' is outside the allowed workspace."
            continue
        try:
            if not os.path.exists(safe_path):
                results[path] = "Error: File not found."
            elif os.path.isdir(safe_path):
                results[path] = "Error: Path is a directory, not a file."
            else:
                with open(safe_path, 'r', encoding='utf-8', errors='replace') as f:
                    results[path] = f.read()

        except Exception as e:
            results[path] = f"Error: Failed to read file: {e}"
            
    return results

def write_files(files: list[dict]) -> dict:
    """
    Safely writes multiple files to disk inside the sandboxed workspace.

    Args:
        files: A list of objects, each with 'path' and 'content' keys.
               e.g. [{"path": "hello.txt", "content": "print('hi')"}]
    """
    if not isinstance(files, list):
        return {"error": "Expected a list of file objects."}
    
    unique_files = {}
    for file_info in files:
        if not isinstance(file_info, dict):
            continue
        path = file_info.get("path")
        content = file_info.get("content", "")
        if path:
            unique_files[path] = content

    results = {}
    for path, content in unique_files.items():
        safe_path = _resolve_safe_path(path)
        if safe_path is None:
            results[path] = f"Error: Path '{path}' is outside the allowed workspace."
            continue
        try:
            parent_dir = os.path.dirname(safe_path)
            if parent_dir and not os.path.exists(parent_dir):
                os.makedirs(parent_dir, exist_ok=True)
            with open(safe_path, 'w', encoding='utf-8') as f:
                f.write(content)
            results[path] = "Success: File written successfully."
        except Exception as e:
            results[path] = f"Error: Failed to write file: {e}"
            
    return results


_sandbox=DockerSandboxExecutor(SANDBOX_ROOT)
def run_terminal_command(command: str) -> str:
    """Executes a shell command safely using the configured sandbox architecture."""
    # Delegate execution entirely to your secure Sandbox Executor
    return _sandbox.run_command(command)