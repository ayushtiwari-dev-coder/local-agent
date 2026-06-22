import os

# 1. Define our secure sandbox boundary
# All file reads/writes must stay inside: ~/.local_workflow_agent/workspace/
SANDBOX_ROOT = os.path.abspath(
    os.path.join(os.path.expanduser("~"), ".local_workflow_agent", "workspace")
)
# Ensure this folder physically exists on your drive
os.makedirs(SANDBOX_ROOT, exist_ok=True)


def _resolve_safe_path(path: str) -> str | None:
    """
    Resolves a user-provided path and verifies it remains strictly inside SANDBOX_ROOT.
    Returns the resolved absolute path if safe, or None if it escapes the boundary.
    """
    # Join the root with the target path and resolve it absolutely (cleans up any '..')
    full_path = os.path.abspath(os.path.join(SANDBOX_ROOT, path))
    
    # Verify the sandbox root is the common parent directory
    if os.path.commonpath([full_path, SANDBOX_ROOT]) != SANDBOX_ROOT:
        return None
    return full_path


def read_file(path: str) -> str:
    """
    Safely reads a local file inside the sandboxed workspace.
    """
    safe_path = _resolve_safe_path(path)
    if safe_path is None:
        return f"Error: Path '{path}' is outside the allowed workspace."

    try:
        if not os.path.exists(safe_path):
            return f"Error: File not found at path '{path}'."
        if os.path.isdir(safe_path):
            return f"Error: Path '{path}' is a directory, not a file."
            
        with open(safe_path, 'r', encoding='utf-8', errors='replace') as f:
            return f.read()
    except Exception as e:
        return f"Error: Failed to read file: {e}"


def write_file(path: str, content: str) -> str:
    """
    Safely writes content to a local file inside the sandboxed workspace.
    """
    safe_path = _resolve_safe_path(path)
    if safe_path is None:
        return f"Error: Path '{path}' is outside the allowed workspace."

    try:
        parent_dir = os.path.dirname(safe_path)
        if parent_dir and not os.path.exists(parent_dir):
            os.makedirs(parent_dir, exist_ok=True)
            
        with open(safe_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return f"Success: File written successfully to '{path}'."
    except Exception as e:
        return f"Error: Failed to write file: {e}"