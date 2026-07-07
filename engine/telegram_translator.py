# engine/telegram_translator.py
import json
import threading
from engine.handle_permissions import execute_and_format_tool
from managers.conversation_manager import log_tool_run
from tools.security_guard import check_command_safety  # <-- ADDED IMPORT

# Global dictionary to hold events for async approvals
# Maps: conversation_id -> {"event": threading.Event, "approved": bool}
active_approvals = {}

def telegram_translator_layer(
    tool_name: str,
    tool_args: dict,
    conversation_id: int,
    send_message_callback=None,
    **kwargs,
) -> tuple[str, str]:
    """
    Freezes the engine thread waiting for a Telegram webhook response.
    """
    
    # --- 1. LAYER 1: STRICT SECURITY GUARD CHECK ---
    if tool_name == "run_terminal_command":
        command = tool_args.get("command") or tool_args.get("cmd", "")
        is_safe, warning_reason = check_command_safety(command)

        if not is_safe:
            error_msg = f"Error: Security Guard blocked this command. Reason: {warning_reason}. Please fix your command and use allowed tools only."
            
            # Log the blocked execution to the database
            log_tool_run(
                conversation_id,
                tool_name,
                json.dumps(tool_args),
                "error",
                output=error_msg,
            )
            
            # Alert the user on Telegram that a malicious command was intercepted
            if send_message_callback:
                alert_msg = (
                    f"🛡️ *SECURITY INTERCEPT*\n"
                    f"Command blocked automatically.\n"
                    f"*Command:* `{command}`\n"
                    f"*Reason:* {warning_reason}"
                )
                send_message_callback(conversation_id, alert_msg)
                
            # Return immediately to the LLM, do NOT freeze the thread
            return error_msg, "error"
    # -----------------------------------------------

    # 2. Trigger the Telegram bot to ask the user for approval
    if send_message_callback:
        prompt_msg = (
            f"🚨 *Action Required*\n"
            f"Approve execution of `{tool_name}`?\n\n"
            f"Arguments:\n```json\n{json.dumps(tool_args, indent=2)}\n```"
        )
        send_message_callback(conversation_id, prompt_msg)

    # 3. Create an event and freeze this specific thread
    event = threading.Event()
    active_approvals[conversation_id] = {"event": event, "approved": False}

    # Wait for up to 5 minutes (300 seconds). If no reply, it unfreezes automatically.
    event_triggered = event.wait(timeout=300)

    # 4. Retrieve the user's decision
    approval_data = active_approvals.pop(conversation_id, None)

    if not event_triggered:
        error_msg = f"Error: Approval timed out for '{tool_name}'. Execution cancelled."
        log_tool_run(
            conversation_id, tool_name, json.dumps(tool_args), "error", output=error_msg
        )
        return error_msg, "error"

    if approval_data and approval_data.get("approved"):
        # User clicked YES -> Execute the tool safely
        return execute_and_format_tool(tool_name, tool_args, conversation_id)
    else:
        # User clicked NO -> Deny execution
        error_msg = (
            f"Error: Permission Denied. User refused execution of '{tool_name}'."
        )
        log_tool_run(
            conversation_id, tool_name, json.dumps(tool_args), "error", output=error_msg
        )
        return error_msg, "error"


def resolve_telegram_approval(conversation_id: int, approved: bool) -> bool:
    """
    Called by your future Telegram Webhook to unfreeze the engine thread.
    Returns True if a thread was successfully unfrozen, False otherwise.
    """
    if conversation_id in active_approvals:
        active_approvals[conversation_id]["approved"] = approved
        active_approvals[conversation_id]["event"].set()  # Unfreezes the thread!
        return True
    return False