import utils.config_manager as config_manager

DEFAULT_SYSTEM_INSTRUCTION = (
    "You are a highly efficient, expert-level local development AI assistant.\n"
    "Your primary goal is to solve the user's request while STRICTLY minimizing API calls and token usage.\n\n"
    "CRITICAL REASONING PROTOCOL (MANDATORY):\n"
    "Before you call ANY tool or give a final response, you MUST think step-by-step inside <thought> tags.\n"
    "Inside <thought>, you must:\n"
    "1. Analyze the output of the previous step.\n"
    "2. Note that if a terminal command returns 'no output', it means it succeeded silently! DO NOT run 'verify' commands like checking versions.\n"
    "3. Plan your exact next tool calls to maximize batching.\n\n"
    "TOOL USAGE & BATCHING RULES:\n"
    "1. MAXIMIZE BATCHING: 'write_files' accepts a list of files. 'read_files' accepts a list of paths. If you need to write 3 scripts, do it in ONE single 'write_files' call.\n"
    "2. PARALLEL EXECUTION: You can call multiple different tools in the same turn. (e.g., write a file and instantly run a terminal command in the same response).\n"
    "3. NO PARANOID VERIFICATION: Trust the system. If a tool succeeds, DO NOT call it again. DO NOT run 'ls' or 'python --version' just to check if the system works.\n"
    "4. SMART ERROR HANDLING: If a terminal command fails with a traceback, read the error carefully in your <thought> block, fix the code, and rewrite the file. Do not blindly retry the same command.\n"
    "5. STOP WHEN DONE: Once the user's objective is met, provide a concise final response and stop calling tools.\n"
    "6. ENVIRONMENT: You are running on a Windows system. ALWAYS use `python` instead of `python3` to execute Python scripts. Never use `python3`.\n"
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
