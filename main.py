# FILE: main.py
import sys
import os
# Import the path helper first
from utils.path_helper import load_env_file
# Load environment variables (API keys) immediately on startup
load_env_file()

# Absolute imports from our packages
from database.table_generator import create_tables
from managers.user_manager import get_active_user, register_user
from managers.conversation_manager import compile_llm_context  
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
    configure_provider_flow,
    model_selection_flow,
    provider_management_flow
)
from managers.conversation_manager import start_new_conversation
from utils import config_manager

def cli_tool_approval_callback(tool_name: str, arguments: dict) -> bool:
    """Passed to the Engine to handle terminal user authorization."""
    print(f"\n 📝 [AI Requests Tool Run] -> {tool_name}")
    print(f" Parameters: {arguments}")
    choice = input("👉 Allow this action? (y/n): ").strip().lower()
    return choice == "y"

def cli_status_callback(message: str) -> None:
    """Prints system-level status and retry updates to the console."""
    print(f"⚙️ [System Status] {message}")

def pick_conversation(user: dict) -> int | None:
    """ Shows the main menu (new / resume / rename / exit) on a loop until the user lands on a conversation_id to chat in, or chooses to exit. """
    while True:
        choice = main_menu(user["name"])
        if choice == "new":
            title = input("📝 Title for this conversation (blank = 'New Conversation'): ").strip()
            session = start_new_conversation(
                user_id=user["id"], title=title or "New Conversation",
            )
            print(f"\n ✔️ Started new conversation (id={session['id']}).")
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
        # --- NEW CATCH FOR PROVIDER CONFIGURATION ---
        if choice == "config":
            provider_management_flow()
            continue
        if choice == "exit":
            return None
        print("⚠️ Invalid choice, please pick 1-5.")

IN_CHAT_HELP = """ Available commands:
exit / quit - close the session
menu        - go back to the conversation menu (switch / rename / new)
history     - reprint the full transcript of this conversation
tools       - show just the tool calls made in this conversation
/models     - switch active models/providers on the fly
/thinking   - adjust reasoning/thinking budget
help        - show this list again
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

    # First-launch configuration setup verification
    if not config_manager.has_any_provider_configured():
        print("\n⚠️  Welcome! No LLM providers have been configured yet.")
        print("Let's set up your first API key before getting started.")
        configure_provider_flow()
        # Verify if they completed the setup or exited early
        if not config_manager.has_any_provider_configured():
            print("\n❌ An active LLM provider API key is required to run the agent. Exiting.")
            sys.exit(1)

    # Read active provider and model preferences from config manager
    provider_choice = config_manager.get_default_provider()
    model_choice = config_manager.get_active_model(provider_choice)

    # Read overrides from command-line if provided (preserves CLI override capabilities)
    if len(sys.argv) > 1:
        provider_choice = sys.argv[1].strip().lower()
    if len(sys.argv) > 2:
        model_choice = sys.argv[2].strip()

    # Ensure key is present for the chosen provider
    resolved_key = config_manager.get_provider_api_key(provider_choice)
    if not resolved_key:
        print(f"\n⚠️  API Key not configured for: {provider_choice.upper()}")
        configure_provider_flow(provider_choice)
        resolved_key = config_manager.get_provider_api_key(provider_choice)
        if not resolved_key:
            print(f"❌ Cannot proceed without an API Key for {provider_choice.upper()}. Exiting.")
            sys.exit(1)

    # Instantiate our Agent Engine dynamically
    try:
        print(f"\n--- Booting Assistant ---")
        print(f"Provider: [{provider_choice.upper()}]")
        print(f"Model:    [{model_choice}]")
        print(f"-------------------------\n")
        engine = AgentEngine(provider_name=provider_choice, model_name=model_choice, api_key=resolved_key, autonomous=False)
    except Exception as e:
        print(f"Initialization Error: {e}")
        print("Please check your configuration or local credentials.")
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

                # Intercept slash commands
                if lowered == "/models":
                    selection = model_selection_flow()
                    if selection:
                        provider_choice, model_choice = selection
                        resolved_key = config_manager.get_provider_api_key(provider_choice)
                        print("\n🔄 Re-booting Assistant with new model...")
                        engine = AgentEngine(
                            provider_name=provider_choice, 
                            model_name=model_choice, 
                            api_key=resolved_key, 
                            autonomous=False
                        )
                        print(f"🎯 Assistant is now running: [{provider_choice.upper()}] - {model_choice}\n")
                    continue

                if lowered == "/thinking":
                    from engine.thinking_configure import supports_thinking
                    if not supports_thinking(model_choice):
                        print(f"\n⚠️ The current model [{model_choice}] does not support dynamic thinking/reasoning modes.\n")
                        continue
                    
                    print(f"\n🧠 Current thinking level: {config_manager.get_thinking_level().upper()}")
                    print("Select a new reasoning/thinking budget:")
                    print("  [1] Off")
                    print("  [2] Low")
                    print("  [3] Medium")
                    print("  [4] High")
                    level_choice = input("👉 Choose level (1-4): ").strip()
                    level_map = {"1": "off", "2": "low", "3": "medium", "4": "high"}
                    selected_level = level_map.get(level_choice)
                    if selected_level:
                        config_manager.set_thinking_level(selected_level)
                        print(f"✅ Thinking level updated to: {selected_level.upper()}\n")
                    else:
                        print("⚠️ Invalid choice. Thinking level unchanged.\n")
                    continue

                print("🤖 Assistant is thinking...")
                response_text = engine.send_message(
                    conversation_id=conversation_id, 
                    user_text=user_input, 
                    approval_callback=cli_tool_approval_callback, 
                    status_callback=cli_status_callback, 
                )
                print(f"\n 🤖 Assistant: {response_text}\n")
            except KeyboardInterrupt:
                print("\nSession interrupted. Goodbye!")
                return
            except Exception as e:
                print(f"\n ❌ Error encountered: {e}\n")

if __name__ == "__main__":
    run_assistant_cli()