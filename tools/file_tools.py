import os
import json  # Import json to parse inputs

SANDBOX_ROOT = os.path.abspath(
    os.path.join(os.path.expanduser("~"), ".local_workflow_agent", "workspace")
)
os.makedirs(SANDBOX_ROOT, exist_ok=True)

def _resolve_safe_path(path: str) -> str | None:
    full_path = os.path.abspath(os.path.join(SANDBOX_ROOT, path))
    if os.path.commonpath([full_path, SANDBOX_ROOT]) != SANDBOX_ROOT:
        return None
    return full_path

def read_files(paths_json: str) -> dict:
    """
    Safely reads multiple files from the sandboxed workspace in a single turn.

    Args:
        paths_json: A JSON string representing a list of file paths to read.
                    Example: '["file1.txt", "subfolder/file2.py"]'
    """
    try:
        paths = json.loads(paths_json)
    except Exception as e:
        return {"error": f"Invalid JSON format for paths_json: {e}"}

    results = {}
    for path in paths:
        safe_path = _resolve_safe_path(path)
        if safe_path is None:
            results[path] = f"Error: Path '{path}' is outside the allowed workspace."
            continue

        try:
            if not os.path.exists(safe_path):
                results[path] = f"Error: File not found."
            elif os.path.isdir(safe_path):
                results[path] = f"Error: Path is a directory, not a file."
            else:
                with open(safe_path, 'r', encoding='utf-8', errors='replace') as f:
                    results[path] = f.read()
        except Exception as e:
            results[path] = f"Error: Failed to read file: {e}"
            
    return results

def write_files(files_json: str) -> dict:
    """
    Safely writes multiple files to disk inside the sandboxed workspace.

    Args:
        files_json: A JSON string representing a list of file dictionaries containing 'path' and 'content'.
                    Example: '[{"path": "notes.txt", "content": "My notes"}, {"path": "script.py", "content": "print(1)"}]'
    """
    try:
        files = json.loads(files_json)
    except Exception as e:
        return {"error": f"Invalid JSON format for files_json: {e}"}

    results = {}
    for file_info in files:
        path = file_info.get("path")
        content = file_info.get("content", "")
        if not path:
            continue

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
            results[path] = f"Success: File written successfully."
        except Exception as e:
            results[path] = f"Error: Failed to write file: {e}"

    return results