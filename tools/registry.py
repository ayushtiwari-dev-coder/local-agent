import inspect
from tools.file_tools import read_files, write_files

TOOL_REGISTRY = {
    "read_files": read_files,
    "write_files": write_files
}

def get_all_tools() -> list:
    return list(TOOL_REGISTRY.values())


def execute_tool(tool_name: str, arguments: dict) -> str:
    tool_func = TOOL_REGISTRY.get(tool_name)
    if not tool_func:
        return f"Error: Tool '{tool_name}' is not registered."
        
    sig = inspect.signature(tool_func)
    for param_name, param in sig.parameters.items():
        if param.default == inspect.Parameter.empty and param_name not in arguments:
            return f"Error: Missing required parameter '{param_name}' for tool '{tool_name}'."
            
    try:
        return tool_func(**arguments)
    except Exception as e:
        return f"Error: Failed to execute tool '{tool_name}': {e}"