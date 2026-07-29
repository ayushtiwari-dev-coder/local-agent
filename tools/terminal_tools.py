# tools/terminal_tools.py

from tools.core import agent_tool
from tools.file_tools import get_sandbox  # FIXED: Import get_sandbox instead of _sandbox

@agent_tool
def run_script(language: str, filepath: str, args: list[str] = None) -> dict:
    if language not in ["python", "node"]:
        return {"status": "error", "output": "Language must be 'python' or 'node'."}

    command = [language, filepath]
    if args and isinstance(args, list):
        command.extend(args)

    return get_sandbox().run_command(command, timeout_seconds=60)


@agent_tool
def manage_dependencies(manager: str, action: str, packages: list[str] = None) -> dict:
    if manager not in ["pip", "npm"]:
        return {"status": "error", "output": "Manager must be 'pip' or 'npm'."}

    if action not in ["install", "uninstall"]:
        return {"status": "error", "output": "Action must be 'install' or 'uninstall'."}

    command = [manager, action]

    if packages and isinstance(packages, list):
        command.extend(packages)
    else:
        if manager == "pip" and action == "install":
            command.extend(["-r", "requirements.txt"])

    return get_sandbox().run_command(command, timeout_seconds=120)


@agent_tool
def run_tests(framework: str, target: str = "") -> dict:
    """
    Runs test suites using pytest or npm inside the workspace.
    """
    if framework not in ["pytest", "npm"]:
        return {"status": "error", "output": "Framework must be 'pytest' or 'npm'."}

    if framework == "pytest":
        command = ["python", "-m", "pytest"]
        if target:
            command.append(target)

        res = get_sandbox().run_command(command, timeout_seconds=60)

        # CRITICAL FIX: Pytest returns Exit Code 1 when 1+ tests fail.
        # This is NOT a tool crash; it is a valid test report.
        # Mark as 'success' so the LLM receives the failure traceback and fixes the code!
        if res.get("status") == "error" and "exit code 1" in res.get("output", ""):
            res["status"] = "success"

        return res

    elif framework == "npm":
        return get_sandbox().run_command(["npm", "test"], timeout_seconds=60)