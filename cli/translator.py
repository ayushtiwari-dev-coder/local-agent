# cli/translator.py

import json
from tools.security_guard import check_command_safety
from engine.handle_permissions import execute_and_format_tool
from managers.conversation_manager import log_tool_run

def cli_translator_layer(tool_name: str, tool_args: dict, conversation_id: int) -> tuple[str, str]:
    """
    Handles Layer 1 (Security Guard) and Layer 2 (User Approval) for the CLI.
    Delegates actual execution back to the unified execution layer.
    """

    if tool_name == "run_terminal_command":
        command = tool_args.get("command") or tool_args.get("cmd", "")
        is_safe, warning_reason = check_command_safety(command)

        if not is_safe:
            print(f"\n [SECURITY INTERCEPT] Command blocked automatically.")
            print(f" Command: {command}")
            print(f" Reason: {warning_reason}")
            
            error_msg = f"Error: Security Guard blocked this command. Reason: {warning_reason}. Please fix your command and use allowed tools only."
            log_tool_run(conversation_id, tool_name, json.dumps(tool_args), "error", output=error_msg)
            return error_msg, "error"

    print(f"\n [CRUCIAL ACTION REQUESTED] -> {tool_name}")
    print(f" Parameters: {json.dumps(tool_args, indent=2)}")
    choice = input(" Allow this action? (y/n): ").strip().lower()

    if choice != "y":
        error_msg = f"Error: Permission Denied. User refused execution of '{tool_name}'."
        log_tool_run(conversation_id, tool_name, json.dumps(tool_args), "error", output=error_msg)
        return error_msg, "error"

    # --- DELEGATE TO UNIFIED EXECUTION LAYER ---
    print(f" [Executing {tool_name} ...]")
    return execute_and_format_tool(tool_name, tool_args, conversation_id)