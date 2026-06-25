import json
from tools.registry import execute_tool
from managers.conversation_manager import log_tool_run

def determine_and_execute_tool(
    tool_name: str,
    tool_args: dict,
    conversation_id: int,
    autonomous: bool,
    approval_callback=None
) -> tuple[str, str]:
    """
    Handles autonomous vs. supervised permission checks, executes the requested 
    tool, and logs the execution output.
    
    Returns:
        tool_output (str): The output of the tool execution or a permission error.
        status (str): "success" or "error" reflecting the execution state.
    """
    # 1. Handle Supervised Permission Check
    if not autonomous:
        if approval_callback is None:
            raise ValueError("Engine is in supervised mode, but no approval_callback was provided.")
        
        approved = approval_callback(tool_name, tool_args)
        if not approved:
            tool_output = f"Error: Permission Denied. User refused execution of '{tool_name}'."
            log_tool_run(
                conversation_id, tool_name,
                json.dumps(tool_args), "error", error_message="User denied permission."
            )
            return tool_output, "error"
            
    # 2. Execute the Tool (if autonomous, or if approved)
    tool_output = execute_tool(tool_name, tool_args)
    
    # 3. Check for Errors in the Output
    if isinstance(tool_output, dict):
        has_error = any("Error:" in str(v) for v in tool_output.values())
    else:
        has_error = "Error:" in str(tool_output)
        
    status = "error" if has_error else "success"
    
    # 4. Log the Execution Details
    log_tool_run(
        conversation_id, tool_name, 
        json.dumps(tool_args), status, output=tool_output
    )
    
    return tool_output, status