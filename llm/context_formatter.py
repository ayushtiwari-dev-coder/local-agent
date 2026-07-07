import utils.config_manager as config_manager

DEFAULT_SYSTEM_INSTRUCTION = (
    "You are an elite, highly efficient local AI assistant. Your primary goal is to solve the user's request in the ABSOLUTE MINIMUM number of API turns.\n\n"
    "CRITICAL REASONING PROTOCOL:\n"
    "You MUST think step-by-step inside <thought> tags before calling tools or answering.\n"
    "Inside <thought>, explicitly plan how to batch your tool calls to save turns.\n\n"
    "STRICT BATCHING & TOOL RULES (MANDATORY):\n"
    "1. PARALLEL TOOL CALLING IS REQUIRED: You can and MUST call multiple tools in a single turn if they don't depend on each other's immediate output. \n"
    "   - Example: If you need to write a script and run it, call `write_files` AND `run_terminal_command` in the EXACT SAME TURN.\n"
    "   - Example: If you need to write a report and finish, call `write_files` and provide your final text response to the user in the EXACT SAME TURN.\n"
    "2. WRITE PRODUCTION-READY CODE: Double-check your Python code for syntax errors, missing imports, or attribute errors before writing it. Get it right on the first try.\n"
    "3. NO PARANOID VERIFICATION: If a command succeeds silently (no output), DO NOT run `ls`, `cat`, or `verify` commands. Trust the system.\n"
    "4. SMART ERROR RECOVERY: If a command fails, read the traceback in your <thought>, fix the code using `write_files`, and re-run it using `run_terminal_command` IN THE SAME TURN.\n"
    "5. ENVIRONMENT: You are on a Windows system. ALWAYS use `python` instead of `python3`.\n"
    "6. STOP WHEN DONE: The moment the objective is met, give your final response. Do not add unnecessary steps."
)


def format_context(db_messages: list[dict]) -> tuple[str, list[dict]]:
    """
    Extracts base instructions, handles system summaries, and formats the raw database
    messages into a clean, universal standard that any LLM provider can easily map.
    """
    custom_system_instruction = config_manager.get_system_instruction()
    base_instructions = (
        custom_system_instruction
        if custom_system_instruction
        else DEFAULT_SYSTEM_INSTRUCTION
    )

    system_instruction = base_instructions
    standardized_messages = []

    for msg in db_messages:
        role = msg.get("role")
        content = msg.get("content", "")

        if role == "system":
            system_instruction += f"\n\n[Previous Conversation Summary]\n{content}"
        else:
            # Create a clean universal dictionary for user, assistant, or tool roles
            clean_msg = {"role": role, "content": content}
            # Carry over any tool data if it exists
            if "tool_name" in msg:
                clean_msg["tool_name"] = msg["tool_name"]
            if "tool_calls" in msg:
                clean_msg["tool_calls"] = msg["tool_calls"]

            standardized_messages.append(clean_msg)

    return system_instruction, standardized_messages
