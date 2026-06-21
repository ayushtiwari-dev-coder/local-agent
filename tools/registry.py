from tools.file_tools import read_file, write_file

# 1. The central directory that maps tool names to their raw Python functions
TOOL_REGISTRY = {
    "read_file": read_file,
    "write_file": write_file
}

def get_all_tools() -> list:
    """
    Returns a list of all raw Python functions registered as tools.
    The official Google Generative AI SDK accepts this list directly 
    and automatically builds the API function schemas for Gemini.
    """
    return list(TOOL_REGISTRY.values())


def execute_tool(tool_name: str, arguments: dict) -> str:
    """
    Looks up a tool by its name and executes it with the provided arguments.
    Returns the string output of the tool run, or an error if the tool doesn't exist.
    """
    tool_func = TOOL_REGISTRY.get(tool_name)
    if not tool_func:
        return f"Error: Tool '{tool_name}' is not registered in this system."
        
    try:
        # Execute the function using Python keyword argument unpacking (e.g., **{"path": "app.py"})
        return tool_func(**arguments)
    except Exception as e:
        return f"Error: Failed to execute tool '{tool_name}': {e}"