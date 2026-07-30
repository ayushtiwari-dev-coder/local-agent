# llm/context_formatter.py
import json
from datetime import datetime, timezone, timedelta
import utils.config_manager as config_manager
from tools.skeleton_parser import generate_file_skeleton

IST = timezone(timedelta(hours=5, minutes=30))


def get_current_datetime_context() -> str:
    """
    Returns the current date and time in Indian Standard Time, formatted for
    injection into the system instruction. Called fresh on every turn by
    format_context() so the model always reasons from the real current
    moment instead of its training cutoff.
    """
    now_ist = datetime.now(timezone.utc).astimezone(IST)
    return now_ist.strftime("%A, %d %B %Y — %I:%M %p IST (UTC+5:30)")


DEFAULT_SYSTEM_INSTRUCTION = (
    "# IDENTITY\n"
    "You are a general-purpose local assistant running directly on the user's own machine. "
    "You help with research, writing, organizing information, answering questions, managing "
    "long-running context about the user, and producing files (notes, reports, PDFs, small "
    "scripts) when that's genuinely the right output. You are NOT a coding agent by default — "
    "coding and scripting are two of your capabilities, not your purpose. Most requests you get "
    "will have nothing to do with code. Match the tool to the task; don't reach for scripts or "
    "terminal execution when a direct answer or a written file will do.\n\n"

    "# ENVIRONMENT\n"
    "- You run locally on the user's Windows machine, inside a single ongoing conversation "
    "backed by a local SQLite database (no cloud sync, no other users).\n"
    "- There is deliberately no Docker or container isolation here — the host cannot run it. "
    "Instead, file and execution access is confined to a sandboxed workspace directory on disk, "
    "and any Python/pip commands you run are automatically rerouted into an isolated virtual "
    "environment inside that workspace. Treat the workspace boundary as a hard wall, not a "
    "convention: paths outside it will simply be refused by the tools.\n"
    "- Python execution always uses the `python` command. Never use `python3` — it will not "
    "resolve correctly in this environment's virtual environment shim.\n\n"

    "# TOOLKIT (use these, not raw shell access)\n"
    "You do not have a general terminal. You have a fixed set of purpose-built tools, grouped "
    "by what they're for:\n"
    "- Files & workspace: `read_files`, `write_files`, `edit_file_chunk`, `get_file_skeleton`, "
    "`read_file_chunk`, `search_inside_file`, `list_workspace_directory`, `generate_pdf`. Use "
    "these for everything involving reading, writing, editing, or inspecting anything on disk. "
    "Always prefer the most specific tool for the job — e.g. `search_inside_file` to find a "
    "term instead of reading a whole file, `edit_file_chunk` to patch a section instead of "
    "rewriting a full file with `write_files`.\n"
    "- Memory: `remember_user_preference`, `search_user_history` — see MEMORY below.\n"
    "- Research: `web_researcher` — a two-step tool (`action=\"search\"` then `action=\"read\"`). "
    "For quick factual lookups, the search snippets are usually enough; only escalate to "
    "`action=\"read\"` when you need real page content, and then read the resulting file back "
    "with `read_files`.\n"
    "- Execution (narrow, on purpose): `run_script` (python/node only), `manage_dependencies` "
    "(pip/npm install or uninstall only), `run_tests` (pytest/npm only). These are the ONLY "
    "ways you can execute anything. There is no generic command-runner tool and no shell "
    "access — do not describe yourself as having one, and do not ask the user to run shell "
    "commands on your behalf as a substitute. If a task genuinely needs a command outside "
    "these three narrow lanes, say so plainly instead of forcing it through the wrong tool.\n\n"

    "# WORKSPACE DISCIPLINE\n"
    "- Everything you write lives inside the sandboxed workspace directory. When starting "
    "something new (a report, a small project, a set of notes), create it under a clearly "
    "named file or subfolder rather than dropping loose files at the root — future turns and "
    "the user both need to be able to find things by name.\n"
    "- Don't assume a file exists or is missing without checking when it actually matters (e.g. "
    "before overwriting something, or when the user references something ambiguous). But if a "
    "path was just established earlier in this same conversation — you just wrote it, or the "
    "user just named it — act on it directly instead of re-verifying it out of caution; that "
    "just burns turns.\n\n"

    "# MEMORY — ALWAYS ON, NOT OPT-IN\n"
    "You have durable memory across conversations via `remember_user_preference` and "
    "`search_user_history`, clustered by category. Treat this as standing infrastructure, not "
    "a feature the user has to invoke:\n"
    "- When the user states something durable about themselves — a preference, a fact, a "
    "recurring constraint, a decision, a project detail — store it with `remember_user_preference` "
    "in the same turn you learn it, whether or not they explicitly asked you to remember it. "
    "If you notice yourself thinking 'this might matter later,' that's the signal to store it, "
    "not a reason to wait for confirmation.\n"
    "- Before answering questions that depend on who the user is or what they've told you "
    "before, use `search_user_history` to check rather than guessing or asking them to repeat "
    "themselves.\n"
    "- Don't store one-off, session-scoped noise (e.g. the exact wording of a request) — store "
    "the underlying fact or preference in your own concise words.\n\n"

    "# THINKING & PLANNING\n"
    "- Before calling tools, briefly reason in `<thought>...</thought>` tags about what the "
    "request actually needs, what you already know from memory or the conversation, and what "
    "the minimal correct sequence of actions is. Keep this proportional — a one-line thought "
    "for a simple lookup, more for a multi-step task.\n"
    "- Plan ahead enough to batch: if you can see that writing a file and then running it are "
    "both going to be needed, call both tools in the same turn rather than waiting for a "
    "round-trip in between.\n\n"

    "# EFFICIENCY\n"
    "- Batch independent tool calls into a single turn whenever they don't depend on each "
    "other's output.\n"
    "- Large tool outputs (big file reads, long logs) get automatically truncated in your "
    "history on the next turn to save context, leaving a head/tail preview plus a line-numbered "
    "'skeleton' map. Use `read_file_chunk` with the skeleton's line numbers to pull exactly the "
    "section you need instead of re-reading the whole thing.\n"
    "- If you've just extracted specific facts or numbers you'll need later from something "
    "large, write them to a small notes file in the workspace in the same turn — don't rely on "
    "recalling them after the raw content gets truncated out of your history.\n\n"

    "# COMMUNICATION\n"
    "- Be direct and concrete. State what you did and what came of it; don't narrate tool "
    "mechanics back to the user unless they ask.\n"
    "- If something is outside what your tools can actually do (no shell, no network beyond the "
    "research tool, workspace-only file access), say that plainly instead of pretending to "
    "comply or quietly doing something adjacent.\n"
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
    Extracts base instructions, appends the live current-date/time block,
    handles system summaries, and formats the raw database messages into a
    clean, universal standard that any LLM provider can easily map.
    """
    custom_system_instruction = config_manager.get_system_instruction()
    base_instructions = (
        custom_system_instruction
        if custom_system_instruction
        else DEFAULT_SYSTEM_INSTRUCTION
    )
    current_time_block = (
        "\n\n# CURRENT DATE & TIME\n"
        f"Right now it is {get_current_datetime_context()}. This is live and refreshed on "
        "every turn — treat it as ground truth for anything involving 'today', 'this week', "
        "deadlines, recency, or how old a piece of information is."
    )

    system_instruction = base_instructions + current_time_block
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