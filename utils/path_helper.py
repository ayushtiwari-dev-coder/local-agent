import os

def get_project_root() -> str:
    """
    Resolves the absolute path to the root directory of this project.
    """
    # This file lives in local_workflow_agent/utils/path_helper.py
    current_dir = os.path.dirname(os.path.abspath(__file__))
    # Go up one level to get to local_workflow_agent/
    return os.path.dirname(current_dir)


def resolve_absolute_path(relative_path: str) -> str:
    """
    Converts any relative project path into a secure, absolute path 
    starting from the project root directory.
    """
    root_dir = get_project_root()
    return os.path.abspath(os.path.join(root_dir, relative_path))


def load_env_file() -> None:
    """
    Locates the .env file in the project root, parses its content,
    and populates os.environ safely.
    """
    env_path = resolve_absolute_path(".env")
    
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                # Skip blank lines and comment lines
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    # Clean up spaces and quote marks
                    clean_val = val.strip().strip('"').strip("'")
                    os.environ[key.strip()] = clean_val