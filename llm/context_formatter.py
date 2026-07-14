# llm/context_formatter.py
import json
import utils.config_manager as config_manager
from tools.skeleton_parser import generate_file_skeleton

DEFAULT_SYSTEM_INSTRUCTION = (
    "# CORE IDENTITY & OBJECTIVE\n"
    "You are a highly capable, efficient, and autonomous Local System Agent. Your objective is to assist the user with a wide variety of tasks—ranging from general research and writing to targeted scripting and file manipulation.\n"
    "You operate in a continuous ReAct (Reason + Act) loop. Your primary success metric is solving the user's request accurately while minimizing the number of API turns.\n\n"
    "# THINKING & PLANNING\n"
    "- Before executing any tools, you MUST use `<thought> ... </thought>` tags to analyze the current state, reflect on previous tool outputs, and formulate a clear, step-by-step plan.\n"
    "- Think ahead. Anticipate what information you need and fetch it proactively.\n\n"
    "# TOOL HIERARCHY & USAGE (CRITICAL)\n"
    "You have access to a suite of native Python tools and a terminal. You MUST strictly prioritize native tools over terminal commands.\n"
    "- NATIVE TOOLS FIRST: Always use `read_files`, `write_files`, `get_file_skeleton`, `read_file_chunk`, and `search_inside_file` for workspace operations.\n"
    "- TERMINAL RESTRICTIONS: The `run_terminal_command` tool is strictly reserved for EXECUTING scripts (e.g., `python script.py`), compiling, or running specific programs.\n"
    "- NO TERMINAL STUPIDITY: NEVER use the terminal to read, write, or search files. Do NOT use `cat`, `head`, `tail`, `ls`, `dir`, `grep`, `echo`, or redirection (`>`, `>>`). Use your native tools instead.\n"
    "- SECURITY GUARD ACTIVE: Your terminal commands are monitored by a strict static analyzer. Malicious, obfuscated, or chained commands (using `&&`, `|`, `;`) will be instantly blocked. Keep terminal commands simple and direct.\n\n"
    "# EFFICIENCY & BATCHING\n"
    "- PARALLEL BATCHING: You must issue multiple independent tool calls in a single turn whenever possible. For example, if you write a script and need to run it, call `write_files` and `run_terminal_command` in the SAME turn. Do not wait for a new turn just to run code you just wrote.\n"
    "- NO PARANOID VERIFICATION: Do not run exploratory directory listings or verify if files exist before interacting with them. If a file path is known or mentioned, immediately act on it.\n\n"
    "# MEMORY & TRUNCATION STRATEGY\n"
    "- RAW DATA TRUNCATION: Massive tool outputs (like large file reads or long terminal logs) will be dynamically truncated in your history in the very next turn to save context memory.\n"
    "- SKELETON MAPS: When a file is truncated, a line-numbered 'Skeleton' remains in your history. Use those line numbers to surgically read exactly what you need using `read_file_chunk`.\n"
    "- THE SCRATCHPAD METAGAME: If you read a massive dataset or document and need to remember specific metrics or facts for later, you MUST immediately write those insights to a small `scratchpad.md` file using `write_files` in the exact same turn, before the raw data is truncated.\n\n"
    "# ENVIRONMENT SPECIFICATIONS\n"
    "- Operating System: Windows.\n"
    "- Python Execution: Always use the `python` command to run scripts. NEVER use `python3`.\n"
)


def _truncate_single_string(content: str, tool_name: str, filename: str = None) -> str:
    """Core logic to truncate a single massive string into Head/Tail + Skeleton."""
    lines = content.splitlines()
    total_lines = len(lines)

    if total_lines < 10:
        head = content[:500]
        tail = content[-500:]
        return (
            f"[RAW OUTPUT TRUNCATED]\nTool: {tool_name}\nSize: ~{len(content)} chars (Minified)\n"
            f"--- HEAD ---\n{head}\n...\n--- TAIL ---\n{tail}\n\n"
            f"System Note: Use search_file to extract specific keys."
        )

    head_lines = "\n".join(lines[:5])
    tail_lines = "\n".join(lines[-5:])

    skeleton_block = ""
    if filename:
        # CALL THE ORCHESTRATOR
        skeleton = generate_file_skeleton(content, filename)
        if skeleton:
            skeleton_block = f"--- FILE SKELETON ---\n{skeleton}\n\n"

    return (
        f"[RAW OUTPUT TRUNCATED]\nTool: {tool_name}\nSize: {total_lines} lines\n"
        f"--- HEAD (First 5 lines) ---\n{head_lines}\n...\n"
        f"--- TAIL (Last 5 lines) ---\n{tail_lines}\n\n{skeleton_block}"
        f"System Note: Use read_file_chunk or search_file to query this data."
    )


def smart_truncate_tool_output(
    content: str, tool_name: str, threshold_chars: int = 2000
) -> str:
    """Dynamically truncates tool outputs, handling both raw strings and JSON dicts."""
    if not content or len(content) <= threshold_chars:
        return content

    try:
        parsed_content = json.loads(content)
        if isinstance(parsed_content, dict):
            truncated_dict = {}
            for key, val in parsed_content.items():
                if isinstance(val, str) and len(val) > threshold_chars:
                    truncated_dict[key] = _truncate_single_string(
                        val, tool_name, filename=key
                    )
                else:
                    truncated_dict[key] = val
            return json.dumps(truncated_dict, ensure_ascii=False)
    except (json.JSONDecodeError, TypeError):
        pass

    return _truncate_single_string(content, tool_name)


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
    total_msgs = len(db_messages)

    for i, msg in enumerate(db_messages):
        role = msg.get("role")
        content = msg.get("content", "")

        if role == "system":
            system_instruction += f"\n\n[Previous Conversation Summary]\n{content}"
        else:
            # THE ONE-TURN RULE: Truncate old tool outputs
            if role == "tool" and i < total_msgs - 1:
                tool_name = msg.get("tool_name", "unknown")
                content = smart_truncate_tool_output(content, tool_name)

            clean_msg = {"role": role, "content": content}
            if "tool_name" in msg:
                clean_msg["tool_name"] = msg["tool_name"]
            if "tool_calls" in msg:
                clean_msg["tool_calls"] = msg["tool_calls"]

            standardized_messages.append(clean_msg)

    return system_instruction, standardized_messages
