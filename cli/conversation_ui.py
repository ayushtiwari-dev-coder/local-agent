
import json
import textwrap

from queries.conversation_queries import (
    get_all_conversations,
    get_conversation_by_id,
    update_conversation_title,
)
from queries.message_queries import get_messages_by_conversation
from queries.tool_log_queries import get_tool_logs_by_conversation
from managers.conversation_manager import start_new_conversation


SEPARATOR = "─" * 60

ROLE_ICONS = {
    "user": "👤 You",
    "assistant": "🤖 Assistant",
    "system": "🗒️  System",
}


def print_separator() -> None:
    print(SEPARATOR)


def _truncate(text: str, width: int = 100) -> str:
    text = text.replace("\n", " ")
    return text if len(text) <= width else text[: width - 3] + "..."


def _format_timestamp(created_at: str) -> str:
    # created_at comes from SQLite as "YYYY-MM-DD HH:MM:SS"
    return created_at if created_at else "unknown time"




def display_conversation_list() -> list[dict]:
    """Prints a numbered list of all conversations. Returns the list used."""
    conversations = get_all_conversations()
    print_separator()
    if not conversations:
        print("No conversations yet. You'll start a fresh one.")
        print_separator()
        return conversations

    print("📂 Your Conversations:\n")
    for idx, conv in enumerate(conversations, start=1):
        print(f"  [{idx}] (id={conv['id']}) \"{conv['title']}\"  "
              f"— created {_format_timestamp(conv['created_at'])}")
    print_separator()
    return conversations


def main_menu(user_name: str) -> str:
    """Top-level menu. Returns one of: 'new', 'resume', 'rename', 'exit'."""
    print_separator()
    print(f"=== Hello, {user_name}! What would you like to do? ===")
    print("  [1] Start a NEW conversation")
    print("  [2] Resume an EXISTING conversation")
    print("  [3] Rename a conversation")
    print("  [4] Exit")
    print_separator()

    choice = input("👉 Choose an option (1-4): ").strip()
    return {
        "1": "new",
        "2": "resume",
        "3": "rename",
        "4": "exit",
    }.get(choice, "invalid")


def prompt_pick_conversation(conversations: list[dict]) -> dict | None:
    """Given a displayed list, ask the user to pick one by number. Returns the row or None."""
    if not conversations:
        return None
    raw = input("👉 Enter the [number] of the conversation: ").strip()
    if not raw.isdigit():
        print("⚠️  Please enter a valid number.")
        return None
    index = int(raw) - 1
    if index < 0 or index >= len(conversations):
        print("⚠️  That number isn't in the list.")
        return None
    return conversations[index]




def render_conversation_history(conversation_id: int) -> None:
    """
    Prints the full transcript of a conversation: user/assistant messages
    AND tool executions, interleaved in chronological order — so tool
    calls show up inline exactly where they happened, no separate log view needed.
    """
    messages = get_messages_by_conversation(conversation_id)
    tool_logs = get_tool_logs_by_conversation(conversation_id)

    # Merge both streams into one timeline, sorted by created_at then id
    # (id is a stable tiebreaker for same-second timestamps)
    timeline = []
    for m in messages:
        timeline.append((m["created_at"], m["id"], "message", m))
    for t in tool_logs:
        timeline.append((t["created_at"], t["id"], "tool", t))
    timeline.sort(key=lambda row: (row[0], row[1]))

    print_separator()
    print(f"📜 Conversation History (id={conversation_id})")
    print_separator()

    if not timeline:
        print("(No messages yet — this conversation is empty.)")
        print_separator()
        return

    for _, _, kind, row in timeline:
        if kind == "message":
            icon = ROLE_ICONS.get(row["role"], row["role"])
            print(f"\n{icon}  [{_format_timestamp(row['created_at'])}]")
            print(textwrap.fill(row["content"], width=90, initial_indent="  ", subsequent_indent="  "))
        else:
            status_icon = "✅" if row["status"] == "success" else "❌"
            print(f"\n  {status_icon} ⚙️  Tool: {row['tool_name']}  [{_format_timestamp(row['created_at'])}]")
            print(f"     args:   {_truncate(row['arguments'], 90)}")
            if row.get("output"):
                print(f"     output: {_truncate(str(row['output']), 90)}")
            if row.get("error_message"):
                print(f"     error:  {row['error_message']}")

    print()
    print_separator()


def show_tool_calls_only(conversation_id: int) -> None:
    """Quick view: just the tool execution log for the current conversation, no chat text."""
    tool_logs = get_tool_logs_by_conversation(conversation_id)
    print_separator()
    print(f"⚙️  Tool Calls for Conversation {conversation_id}")
    print_separator()
    if not tool_logs:
        print("(No tools have been run in this conversation yet.)")
    for t in tool_logs:
        status_icon = "✅" if t["status"] == "success" else "❌"
        print(f"\n{status_icon} {t['tool_name']}  [{_format_timestamp(t['created_at'])}]")
        print(f"   args:   {_truncate(t['arguments'], 90)}")
        if t.get("output"):
            print(f"   output: {_truncate(str(t['output']), 90)}")
        if t.get("error_message"):
            print(f"   error:  {t['error_message']}")
    print()
    print_separator()




def rename_conversation_flow() -> None:
    conversations = display_conversation_list()
    if not conversations:
        return
    target = prompt_pick_conversation(conversations)
    if target is None:
        return
    new_title = input(f"✏️  New title for \"{target['title']}\": ").strip()
    if not new_title:
        print("⚠️  Title cannot be empty. Cancelled.")
        return
    try:
        updated = update_conversation_title(target["id"], new_title)
        print(f"✅ Renamed to \"{updated['title']}\".")
    except ValueError as e:
        print(f"⚠️  {e}")




def choose_or_create_conversation(user_id: int) -> int | None:
    """
    Drives the full menu loop until the user picks a conversation to chat in
    (new or resumed) or chooses to exit.

    Returns:
        conversation_id (int) to start chatting in, or None if the user chose to exit.
    """
    while True:
        action = main_menu_dispatch(user_id)
        if action is not None:
            return action


def main_menu_dispatch(user_id: int):
    """Single pass through the menu. Returns conversation_id, None (exit), or False (loop again)."""
    # Need the user's display name for the greeting — caller already has it,
    # but to keep this function self-contained we just use a generic greeting.
    choice = main_menu("there")

    if choice == "new":
        session = start_new_conversation(user_id=user_id, title="New Conversation")
        print(f"\n✅ Started new conversation (id={session['id']}).")
        return session["id"]

    if choice == "resume":
        conversations = display_conversation_list()
        target = prompt_pick_conversation(conversations)
        if target is None:
            return False
        render_conversation_history(target["id"])
        return target["id"]

    if choice == "rename":
        rename_conversation_flow()
        return False

    if choice == "exit":
        return None

    print("⚠️  Invalid choice, please pick 1-4.")
    return False