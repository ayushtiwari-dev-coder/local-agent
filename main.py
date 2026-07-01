# FILE: main.py
import sys
import os
import time

# Import the path helper first to load environment variables [1]
from utils.path_helper import load_env_file
# Load environment variables (API keys) immediately on startup [1]
load_env_file()

# Absolute imports from your packages [1]
from database.table_generator import create_tables
from managers.user_manager import get_active_user, register_user
from managers.conversation_manager import compile_llm_context, start_new_conversation
from queries.task_queries import get_orchestra_status_summary
from managers.recovery_manager import ExecutionRecoveryManager
from tools.orchestra_tools import register_orchestra_status_callback

# --> Engine <-- [1]
from engine.agent_engine import AgentEngine

# --> CLI UI layer <-- [1]
from cli.conversation_ui import (
    main_menu, display_conversation_list, # Unmodified, original UI functions preserved
    prompt_pick_conversation, render_conversation_history, show_tool_calls_only, rename_conversation_flow, configure_provider_flow, model_selection_flow, provider_management_flow
)
from utils import config_manager

_request_counter = 0

def reset_request_counter() -> None:
    """Resets the live API turn counter for a brand new prompt thread."""
    global _request_counter
    _request_counter = 0

def cli_tool_approval_callback(tool_name: str, arguments: dict) -> bool:
    """Passed to the Engine to handle terminal user authorization."""
    print(f"\n 🔑 [AI Requests Tool Run] -> {tool_name}")
    print(f" Parameters: {arguments}")
    choice = input("👉 Allow this action? (y/n): ").strip().lower()
    return choice == "y"

def cli_status_callback(message: str) -> None:
    """Handles CLI progress feedback, tracking, and the 4-second observation delay."""
    global _request_counter
    # If starting a new reasoning turn, increment count and throttle for readability [18]
    if "Generating thoughts" in message:
        _request_counter += 1
        print(f"\n 🧠 [Request #{_request_counter}] {message}")
        print("🔔 Delaying 4 seconds to observe process flow...")
        time.sleep(4.0)
    # If running a local tool, print with an execution icon [18, 56]
    elif "Executing tool" in message:
        print(f"🛠️ [Orchestra Tool Run] {message}")
    elif "finished with status" in message:
        print(f"✔️ [Orchestra Tool Output] {message}")
    # Fallback output for standard updates or retry errors [25]
    else:
        print(f"🛠️ [System Status] {message}")

def pick_conversation(user: dict) -> int | None:
    """Shows the main menu on a loop until the user lands on a conversation_id."""
    while True:
        choice = main_menu(user["name"])
        if choice == "new":
            title = input("📝 Title for this conversation (blank = 'New Conversation'): ").strip()
            session = start_new_conversation(
                user_id=user["id"], title=title or "New Conversation"
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
        if choice == "config":
            provider_management_flow()
            continue
        if choice == "exit":
            return None
        print("⚠️ Invalid choice, please pick 1-5.")

IN_CHAT_HELP = """ Available commands:
exit / quit - close the session
menu - go back to the conversation menu (switch / rename / new)
history - reprint the full transcript of this conversation
tools - show just the tool calls made in this conversation
/models - switch active models/providers on the fly
/thinking - adjust reasoning/thinking budget
/status - see what the background Planner/Executor are working on right now
help - show this list again
""".strip()

def run_assistant_cli() -> None:
    """The main CLI loop that boots the system."""
    print("Initializing local assistant database...")
    try:
        create_tables()
        # Recover orphaned database tasks on startup
        ExecutionRecoveryManager.recover_orphaned_tasks()
        
        # Define how the UI layer (main.py) wants to render background progress updates
        def display_background_status(message: str) -> None:
            print(f"📡 [Background Orchestra] {message}")
            
        # Register the printer delegate inside the background orchestrator
        register_orchestra_status_callback(display_background_status)
    except Exception as e:
        print(f"Fatal: Database setup failed: {e}")
        sys.exit(1)

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

    if not config_manager.has_any_provider_configured():
        print("\n ⚠️ Welcome! No LLM providers have been configured yet.")
        print("Let's set up your first API key before getting started.")
        configure_provider_flow()

    if not config_manager.has_any_provider_configured():
        print("\n ❌ An active LLM provider API key is required to run the agent. Exiting.")
        sys.exit(1)

    provider_choice = config_manager.get_default_provider()
    model_choice = config_manager.get_active_model(provider_choice)

    if len(sys.argv) > 1:
        provider_choice = sys.argv[1].strip().lower()
    if len(sys.argv) > 2:
        model_choice = sys.argv[2].strip()

    resolved_key = config_manager.get_provider_api_key(provider_choice)
    if not resolved_key:
        print(f"\n ⚠️ API Key not configured for: {provider_choice.upper()}")
        configure_provider_flow(provider_choice)
        resolved_key = config_manager.get_provider_api_key(provider_choice)
        if not resolved_key:
            print(f"❌ Cannot proceed without an API Key for {provider_choice.upper()}. Exiting.")
            sys.exit(1)

    try:
        print(f"\n--- Booting Assistant ---")
        print(f"Provider: [{provider_choice.upper()}]")
        print(f"Model: [{model_choice}]")
        print(f"-------------------------\n")
        engine = AgentEngine(
            provider_name=provider_choice, model_name=model_choice, api_key=resolved_key, autonomous=False
        )
    except Exception as e:
        print(f"Initialization Error: {e}")
        print("Please check your configuration or local credentials.")
        sys.exit(1)

    while True:
        conversation_id = pick_conversation(user)
        if conversation_id is None:
            print("Goodbye!")
            return
        print(f"\n=== You're in conversation {conversation_id}. Type 'help' for commands. ===\n")
        
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
                    break
                if lowered == "history":
                    render_conversation_history(conversation_id)
                    continue
                if lowered == "tools":
                    show_tool_calls_only(conversation_id)
                    continue
                if lowered == "help":
                    print(IN_CHAT_HELP)
                    continue
                if lowered == "/models":
                    selection = model_selection_flow()
                    if selection:
                        provider_choice, model_choice = selection
                        resolved_key = config_manager.get_provider_api_key(provider_choice)
                        print("\n 🔄 Re-booting Assistant with new model...")
                        engine = AgentEngine(
                            provider_name=provider_choice, model_name=model_choice, api_key=resolved_key, autonomous=False
                        )
                        print(f"🚀 Assistant is now running: [{provider_choice.upper()}] - {model_choice}\n")
                        continue
                if lowered == "/thinking":
                    from engine.thinking_configure import supports_thinking
                    if not supports_thinking(model_choice):
                        print(f"\n ⚠️ The current model [{model_choice}] does not support dynamic thinking/reasoning modes.\n")
                        continue
                    print(f"\n Current thinking level: {config_manager.get_thinking_level().upper()}")
                    print("Select a new reasoning/thinking budget:")
                    print(" [1] Off")
                    print(" [2] Low")
                    print(" [3] Medium")
                    print(" [4] High")
                    level_choice = input("👉 Choose level (1-4): ").strip()
                    level_map = {"1": "off", "2": "low", "3": "medium", "4": "high"}
                    selected_level = level_map.get(level_choice)
                    if selected_level:
                        config_manager.set_thinking_level(selected_level)
                        print(f"Thinking level updated to: {selected_level.upper()}\n")
                    else:
                        print("⚠️ Invalid choice. Thinking level unchanged.\n")
                    continue
                if lowered in {"/status", "/background"}:
                    status_summary = get_orchestra_status_summary()
                    if not status_summary:
                        print("\n [System] No active background agent tasks are currently remaining.\n")
                        continue
                    print("\n================ ACTIVE ORCHESTRA STATUS ================")
                    for task in status_summary:
                        task_icon = "🔄" if task["status"] == "in_progress" else "⏸️"
                        print(f" [{task_icon}] {task['title'].upper()} ({task['status'].upper()})")
                        for sub in task.get("sub_tasks", []):
                            sub_icon = "🔄" if sub["status"] == "in_progress" else "⏸️"
                            print(f"  [{sub_icon}] {sub['description']}")
                    print("=========================================================\n")
                    continue
                    
                if "use agent" in lowered or "use agents" in lowered:
                    from tools.orchestra_tools import trigger_multi_agent_workflow
                    print("\n [System Status] Manual multi-agent trigger detected. Spawning background orchestra...")
                    reset_request_counter()
                    response_text = trigger_multi_agent_workflow(conversation_id, user_input)
                    print(f"\n Assistant: {response_text}\n")
                    continue
                    
                reset_request_counter()
                response_text = engine.send_message(
                    conversation_id=conversation_id,
                    user_text=user_input,
                    approval_callback=cli_tool_approval_callback,
                    status_callback=cli_status_callback
                )
                print(f"\n Assistant: {response_text}\n")
                
            except KeyboardInterrupt:
                print("\nSession interrupted. Goodbye!")
                return
            except Exception as e:
                print(f"\n ❌ Error encountered: {e}\n")

if __name__ == "__main__":
    run_assistant_cli()