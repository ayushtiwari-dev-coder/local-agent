# engine/handle_permissions.py
import json
from tools.registry import execute_tool
from managers.conversation_manager import log_tool_run

def _detect_tool_error(tool_name: str, tool_output: any) -> bool:
    """
    Determines if a tool execution failed.

    Priority order:
    1. If tool_output follows the structured {"status": ..., "output": ...} contract
       (e.g. run_terminal_command), trust the status field directly — no guessing.
    2. If tool_output is a dict with an explicit top-level "error" key, treat as failure.
    3. For read_files/write_files, check per-path values for the "Error:" prefix.
    4. For flat string outputs, fall back to prefix checking (legacy tools only).
    """
    if isinstance(tool_output, dict):
        # 1. Structured status contract: trust it directly.
        if tool_output.get("status") in ("success", "error"):
            return tool_output["status"] == "error"

        # 2. Check if the tool returned an explicit top-level error payload
        if "error" in tool_output:
            return True

        if tool_name in ["read_files", "write_files"]:
            return any(
                isinstance(v, str) and v.strip().startswith("Error:")
                for v in tool_output.values()
            )

    # 4. For flat string outputs (legacy tools like memory_tools), check prefix
    if isinstance(tool_output, str):
        return tool_output.strip().startswith("Error:")

    return False


def _extract_display_output(tool_output: any) -> any:
    """
    Produces a clean, LLM-facing representation of a tool's output.

    Tools using the structured {"status": ..., "output": ...} contract get
    unwrapped to just their output text, so the model sees readable content
    instead of a raw Python dict repr. All other output shapes (read_files/
    write_files dicts, plain strings) pass through unchanged.
    """
    if isinstance(tool_output, dict) and set(tool_output.keys()) == {"status", "output"}:
        return tool_output["output"]
    return tool_output


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

    # 3. Check for Errors in the Output (structured contract first, then legacy checks)
    has_error = _detect_tool_error(tool_name, tool_output)
    status = "error" if has_error else "success"

    # 4. Log the Execution Details (raw structured output preserved in the DB)
    log_tool_run(
        conversation_id,
        tool_name,
        json.dumps(tool_args),
        status,
        output=tool_output
    )

    # 5. Return a clean display value to the caller (agent_engine.py), not the raw dict
    display_output = _extract_display_output(tool_output)
    return display_output, status