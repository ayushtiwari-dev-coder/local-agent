# FILE: main.py
import sys

# Import the path helper first
from utils.path_helper import load_env_file

# Load environment variables (API keys) immediately on startup
load_env_file()

# Absolute imports from our packages
from database.table_generator import create_tables
from managers.user_manager import get_active_user, register_user
from managers.conversation_manager import compile_llm_context  # noqa: F401 (kept for parity)

# --> Engine <--
from engine.agent_engine import AgentEngine

# --> New CLI UI layer <--
from cli.conversation_ui import (
    main_menu,
    display_conversation_list,
    prompt_pick_conversation,
    render_conversation_history,
    show_tool_calls_only,
    rename_conversation_flow,
)
from managers.conversation_manager import start_new_conversation


def cli_tool_approval_callback(tool_name: str, arguments: dict) -> bool:
    """Passed to the Engine to handle terminal user authorization."""
    print(f"\n📝 [AI Requests Tool Run] -> {tool_name}")
    print(f"   Parameters: {arguments}")
    choice = input("👉 Allow this action? (y/n): ").strip().lower()
    return choice == "y"


def cli_status_callback(message: str) -> None:
    """Prints system-level status and retry updates to the console."""
    print(f"⚙️ [System Status] {message}")



def pick_conversation(user: dict) -> int | None:
    """
    Shows the main menu (new / resume / rename / exit) on a loop until
    the user lands on a conversation_id to chat in, or chooses to exit.
    """
    while True:
        choice = main_menu(user["name"])

        if choice == "new":
            title = input("📝 Title for this conversation (blank = 'New Conversation'): ").strip()
            session = start_new_conversation(
                user_id=user["id"],
                title=title or "New Conversation",
            )
            print(f"\n✅ Started new conversation (id={session['id']}).")
            return session["id"]

        if choice == "resume":
            conversations = display_conversation_list()
            target = prompt_pick_conversation(conversations)
            if target is None:
                continue
            render_conversation_history(target["id"])
            return target["id"]

        if choice == "rename":
            rename_conversation_flow()
            continue

        if choice == "exit":
            return None

        print("⚠️  Invalid choice, please pick 1-4.")




IN_CHAT_HELP = """
Available commands:
  exit / quit   - close the session
  menu          - go back to the conversation menu (switch / rename / new)
  history       - reprint the full transcript of this conversation
  tools         - show just the tool calls made in this conversation
  help          - show this list again
""".strip()


def run_assistant_cli() -> None:
    """The main CLI loop that boots the system."""
    print("Initializing local assistant database...")
    try:
        create_tables()
    except Exception as e:
        print(f"Fatal: Database setup failed: {e}")
        sys.exit(1)

    # Verify or Register Active User
    user = get_active_user()
    if user is None:
        print("\n--- Welcome to Local Workflow Agent! ---")
        print("Let's set up your local profile first.")
        while True:
            try:
                name = input("Enter your Display Name (e.g. Ayush): ")
                username = input("Enter your unique Username (e.g. ayush_tiwari): ")
                user = register_user(name, username)
                print(f"\nSuccess: Profile created for {user['name']} (@{user['username']})!")
                break
            except ValueError as e:
                print(f"Validation Error: {e}. Please try again.\n")

    # Instantiate our Agent Engine
    try:
        # Default provider is Gemini, but architecture supports others now
        engine = AgentEngine(provider_name="gemini", autonomous=False)
    except Exception as e:
        print(f"Initialization Error: {e}")
        print("Please make sure you have set the GEMINI_API_KEY inside your .env file.")
        sys.exit(1)

    # Outer loop: lets the user bounce between conversations without restarting the app
    while True:
        conversation_id = pick_conversation(user)
        if conversation_id is None:
            print("Goodbye!")
            return

        print(f"\n=== You're in conversation {conversation_id}. Type 'help' for commands. ===\n")

        # Inner loop: the actual chat for the selected conversation
        while True:
            try:
                user_input = input("👤 You: ").strip()
                if not user_input:
                    continue

                lowered = user_input.lower()

                if lowered in {"exit", "quit"}:
                    print("Goodbye!")
                    return

                if lowered == "menu":
                    break  # back to outer loop -> pick_conversation again

                if lowered == "history":
                    render_conversation_history(conversation_id)
                    continue

                if lowered == "tools":
                    show_tool_calls_only(conversation_id)
                    continue

                if lowered == "help":
                    print(IN_CHAT_HELP)
                    continue

                print("🤖 Assistant is thinking...")
                response_text = engine.send_message(
                    conversation_id=conversation_id,
                    user_text=user_input,
                    approval_callback=cli_tool_approval_callback,
                    status_callback=cli_status_callback,
                )
                print(f"\n🤖 Assistant: {response_text}\n")

            except KeyboardInterrupt:
                print("\nSession interrupted. Goodbye!")
                return
            except Exception as e:
                print(f"\n❌ Error encountered: {e}\n")
                raise


if __name__ == "__main__":
    run_assistant_cli()