# engine/handle_permissions.py

import json
from tools.registry import execute_tool
from managers.conversation_manager import log_tool_run

def _detect_tool_error(tool_name: str, tool_output: any) -> bool:
    """
    Systematically determines if a tool execution failed by checking structures 
    and prefixes, preventing false positives from contents containing 'Error:'.
    """
    if isinstance(tool_output, dict):
        # 1. Check if the tool returned an explicit top-level error payload
        if "error" in tool_output:
            return True
            
        if tool_name in ["read_files", "write_files"]:
            return any(
                isinstance(v, str) and v.strip().startswith("Error:") 
                for v in tool_output.values()
            )
            
    # 3. For flat string outputs (like run_terminal_command failures), check prefix
    if isinstance(tool_output, str):
        return tool_output.strip().startswith("Error:")
        
    return False

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
    """
    # 1. Handle Supervised Permission Check
    if not autonomous:
        if approval_callback is None:
            raise ValueError("Engine is in supervised mode, but no approval_callback was provided.")
        approved = approval_callback(tool_name, tool_args)
        if not approved:
            tool_output = f"Error: Permission Denied. User refused execution of '{tool_name}'."
            log_tool_run(
                conversation_id, 
                tool_name,
                json.dumps(tool_args), 
                "error", 
                error_message="User denied permission."
            )
            return tool_output, "error"

    # 2. Execute the Tool
    tool_output = execute_tool(tool_name, tool_args, conversation_id)

    # 3. Check for Errors in the Output (Using the structured detector helper)
    has_error = _detect_tool_error(tool_name, tool_output)
    status = "error" if has_error else "success"

    # 4. Log the Execution Details
    log_tool_run(
        conversation_id, 
        tool_name,
        json.dumps(tool_args), 
        status, 
        output=tool_output
    )

    return tool_output, status