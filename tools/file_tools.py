import os

def read_file(path: str) -> str:
    """
    Safely reads a local file and returns its content.
    Returns an error description if the file doesn't exist or cannot be read.
    """
    try:
        if not os.path.exists(path):
            return f"Error: File not found at path '{path}'."
        if os.path.isdir(path):
            return f"Error: Path '{path}' is a directory, not a file."
            
        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            return f.read()
    except Exception as e:
        return f"Error: Failed to read file: {e}"


def write_file(path: str, content: str) -> str:
    """
    Safely writes content to a local file on disk.
    Creates parent directories automatically if they do not exist.
    """
    try:
        # Automatically make directories if the path is nested (e.g., 'subfolder/app.py')
        parent_dir = os.path.dirname(path)
        if parent_dir and not os.path.exists(parent_dir):
            os.makedirs(parent_dir, exist_ok=True)
            
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        return f"Success: File written successfully to '{path}'."
    except Exception as e:
        return f"Error: Failed to write file: {e}"