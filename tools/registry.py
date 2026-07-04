import inspect
from tools.file_tools import read_files, write_files, run_terminal_command
from tools.memory_tools import remember_user_preference, search_user_history


TOOL_REGISTRY = {
    "read_files": read_files,
    "write_files": write_files,
    "run_terminal_command": run_terminal_command,
    "remember_user_preference": remember_user_preference,
    "search_user_history": search_user_history,
}

def get_all_tools() -> list:
    """Returns a list of all callable tool functions for the LLM schema."""
    return list(TOOL_REGISTRY.values())

def execute_tool(tool_name: str, arguments: dict, conversation_id: int = None) -> str:
    """
    Executes a tool by name with arguments. Dynamically injects context variables
    (like conversation_id) if the underlying function expects them.
    """
    tool_func = TOOL_REGISTRY.get(tool_name)
    if not tool_func:
        return f"Error: Tool '{tool_name}' is not registered."
        
    sig = inspect.signature(tool_func)
    
    # Dynamically inject conversation_id if the tool requires it
    if "conversation_id" in sig.parameters and conversation_id is not None:
        arguments["conversation_id"] = conversation_id
        
    # Validate that all required arguments are present
    for param_name, param in sig.parameters.items():
        if param.default == inspect.Parameter.empty and param_name not in arguments:
            return f"Error: Missing required parameter '{param_name}' for tool '{tool_name}'."
            
    try:
        return tool_func(**arguments)
    except Exception as e:
        return f"Error: Failed to execute tool '{tool_name}': {e}"