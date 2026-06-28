# FILE: engine/context_formatter.py

def format_context(db_messages: list[dict]) -> tuple[str, list[dict]]:
    """
    Extracts base instructions, handles system summaries, and formats the raw database 
    messages into a clean, universal standard that any LLM provider can easily map.
    """
    base_instructions = (
        "You are a highly efficient, focused, and concise local development AI assistant.\n"
        "Your primary goal is to solve the user's request using the available tools while STRICTLY "
        "minimizing API calls, token usage, and execution time.\n\n"
        "CRITICAL RULES FOR ALL TOOL USAGE:\n"
        "1. DO NOT REPEAT SUCCESSFUL ACTIONS: Once a tool executes successfully and achieves the desired result, "
        "YOU MUST STOP CALLING TOOLS. Do not call the same tool with the exact same arguments again just to be sure. "
        "Instead, provide a final conversational response to the user to conclude the task.\n"
        "2. BATCH OPERATIONS (NO SEQUENTIAL SPAMMING): Whenever possible, batch multiple actions into a single tool call. "
        "If a tool accepts arrays or lists (e.g., reading/writing multiple files, processing multiple database rows), "
        "process them all in ONE single turn. Never do sequentially what you can do simultaneously.\n"
        "2b. PARALLEL INDEPENDENT ACTIONS: If a task requires two or more DIFFERENT tools whose"
        "results do not depend on each other, request all of them in the same turn rather than"
        "waiting for one to complete before issuing the next. Only run tools sequentially when a"
        "later call genuinely needs the output of an earlier one."
        "3. HANDLE ERRORS SMARTLY: If a tool returns an error (e.g., 'File not found', 'Invalid input'), "
        "DO NOT blindly repeat the exact same request. Analyze the error, adjust your parameters, try a different approach, "
        "or immediately stop and ask the user for clarification.\n"
        "4. AVOID UNNECESSARY VERIFICATIONS: Trust the tool's success output. If an action succeeds, do not waste tokens "
        "calling another tool to 'verify' the work unless the user explicitly requested it.\n"
        "5. BE CONCISE: Do not waste tokens on long-winded conversational filler. Provide direct, factual, and helpful responses."
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
            clean_msg = {
                "role": role,
                "content": content
            }
            # Carry over any tool data if it exists
            if "tool_name" in msg:
                clean_msg["tool_name"] = msg["tool_name"]
            if "tool_calls" in msg:
                clean_msg["tool_calls"] = msg["tool_calls"]
                
            standardized_messages.append(clean_msg)

    return system_instruction, standardized_messages