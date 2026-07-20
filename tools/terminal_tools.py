# tools/terminal_tools.py

from tools.core import agent_tool
from tools.file_tools import _sandbox  # Reuse the existing sandbox executor

@agent_tool
def run_script(language: str, filepath: str, args: list[str] = None) -> dict:
    """
    Executes a Python or Node.js script inside the workspace.
    Use this to run code you have written to test it or execute a workflow.
    
    Args:
        language: MUST be either 'python' or 'node'.
        filepath: The name or relative path of the file (e.g., 'main.py' or 'app.js').
        args: Optional list of command-line arguments to pass to the script.
    """
    if language not in ["python", "node"]:
        return {"status": "error", "output": "Language must be 'python' or 'node'."}
    
    # Safely construct the command as a list
    command = [language, filepath]
    if args and isinstance(args, list):
        command.extend(args)
        
    return _sandbox.run_command(command)

@agent_tool
def manage_dependencies(manager: str, action: str, packages: list[str] = None) -> dict:
    """
    Installs or uninstalls project dependencies via pip or npm.
    
    Args:
        manager: MUST be either 'pip' or 'npm'.
        action: MUST be either 'install' or 'uninstall'.
        packages: A list of package names (e.g., ["requests", "numpy"]). 
                  Leave empty if running a general 'npm install' or 'pip install -r requirements.txt'.
    """
    if manager not in ["pip", "npm"]:
        return {"status": "error", "output": "Manager must be 'pip' or 'npm'."}
        
    if action not in ["install", "uninstall"]:
        return {"status": "error", "output": "Action must be 'install' or 'uninstall'."}

    # Base command
    command = [manager, action]
    
    # Handle specific package installations
    if packages and isinstance(packages, list):
        command.extend(packages)
    else:
        # If no packages provided, handle default bulk installs
        if manager == "pip" and action == "install":
            command.extend(["-r", "requirements.txt"])
            
    return _sandbox.run_command(command)

@agent_tool
def run_tests(framework: str, target: str = "") -> dict:
    """
    Runs test suites using pytest or npm.
    
    Args:
        framework: MUST be either 'pytest' or 'npm'.
        target: Optional. The specific test file or directory to run (e.g., 'tests/test_api.py').
                If using 'npm', this is ignored and 'npm test' is run.
    """
    if framework not in ["pytest", "npm"]:
        return {"status": "error", "output": "Framework must be 'pytest' or 'npm'."}
    
    if framework == "pytest":
        command = ["pytest"]
        if target:
            command.append(target)
    elif framework == "npm":
        command = ["npm", "test"]
        
    return _sandbox.run_command(command)