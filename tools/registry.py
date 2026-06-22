import inspect
from tools.file_tools import read_file, write_file

# The central directory that maps tool names to their raw Python functions
TOOL_REGISTRY = {
    "read_file": read_file,
    "write_file": write_file
}

def get_all_tools() -> list:
    """
    Returns a list of all raw Python functions registered as tools.
    Used by the Gemini SDK to auto-build API schemas.
    """
    return list(TOOL_REGISTRY.values())


def execute_tool(tool_name: str, arguments: dict) -> str:
    """
    Looks up a tool, validates its required parameters, and executes it.
    Returns the string output or a descriptive validation/runtime error.
    """
    tool_func = TOOL_REGISTRY.get(tool_name)
    if not tool_func:
        return f"Error: Tool '{tool_name}' is not registered in this system."
        
    # Inspect the Python function's signature
    sig = inspect.signature(tool_func)
    for param_name, param in sig.parameters.items():
        # If the parameter has no default value, it is strictly required
        if param.default == inspect.Parameter.empty and param_name not in arguments:
            return f"Error: Missing required parameter '{param_name}' for tool '{tool_name}'."
            
    try:
        # Execute using argument unpacking (e.g., read_file(**{"path": "app.py"}))
        return tool_func(**arguments)
    except Exception as e:
        return f"Error: Failed to execute tool '{tool_name}': {e}"