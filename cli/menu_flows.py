# cli/menu_flows.py
import sys
from rich.console import Console
from rich.panel import Panel
from cli.constants import SEPARATOR, SUPPORTED_MODELS
from cli.callbacks import validate_api_key
from cli.chat_loop import enter_chat_session
from managers.user_manager import get_active_user, register_user
from queries.conversation_queries import get_all_conversations, update_conversation_title, delete_conversation
from managers.conversation_manager import start_new_conversation
from utils import config_manager

console = Console()

def display_conversation_list() -> list[dict]:
    """Prints conversations chronologically: oldest on top, latest/newest on bottom."""
    conversations = get_all_conversations()
    chronological_convs = list(reversed(conversations))
    print(SEPARATOR)
    if not chronological_convs:
        print(" No conversations yet. You'll start a fresh one.")
        print(SEPARATOR)
        return chronological_convs
    print(" Your Conversations (Chronological):\n")
    for idx, conv in enumerate(chronological_convs, start=1):
        created = conv.get("created_at", "unknown time")
        print(f" [{idx}] (id={conv['id']}) \"{conv['title']}\" - created {created}")
    print(SEPARATOR)
    return chronological_convs

def prompt_pick_conversation(conversations: list[dict]) -> dict | None:
    """Prompts selection of a conversation index."""
    if not conversations:
        return None
    raw = input(" Enter the [number] of the conversation: ").strip()
    if not raw.isdigit():
        print(" Please enter a valid number.")
        return None
    index = int(raw) - 1
    if index < 0 or index >= len(conversations):
        print(" That number isn't in the list.")
        return None
    return conversations[index]

def main_menu(user_name: str) -> str:
    """Primary routing screen."""
    print(SEPARATOR)
    print(f"=== Hello, {user_name}! What would you like to do? ===")
    print(" [1] Start a NEW conversation")
    print(" [2] Resume an EXISTING conversation")
    print(" [3] Rename a conversation")
    print(" [4] Delete a conversation")
    print(" [5] Manage Providers & API Keys")
    print(" [6] Exit")
    print(SEPARATOR)
    choice = input(" Choose an option (1-6): ").strip()
    return {
        "1": "new",
        "2": "resume",
        "3": "rename",
        "4": "delete",
        "5": "config",
        "6": "exit"
    }.get(choice, "invalid")

def rename_conversation_flow() -> None:
    """Interactively modifies titles."""
    convs = display_conversation_list()
    if not convs:
        return
    target = prompt_pick_conversation(convs)
    if not target:
        return
    new_title = input(f" New title for \"{target['title']}\": ").strip()
    if not new_title:
        print(" Title cannot be empty. Cancelled.")
        return
    try:
        updated = update_conversation_title(target["id"], new_title)
        print(f" Renamed to \"{updated['title']}\".")
    except ValueError as e:
        print(f" Error: {e}")

def delete_conversation_flow() -> None:
    """Safely removes conversations using standard cascading rules."""
    convs = display_conversation_list()
    if not convs:
        return
    target = prompt_pick_conversation(convs)
    if not target:
        return
    print(SEPARATOR)
    confirm = input(f" Are you absolutely sure you want to delete '{target['title']}'? (y/n): ").strip().lower()
    if confirm == "y":
        try:
            delete_conversation(target["id"])
            console.print(f"[bold red] Successfully deleted Conversation ID {target['id']}.[/bold red]\n")
        except Exception as e:
            print(f" Error during deletion execution: {e}")
    else:
        print(" Deletion cancelled safely.")

def configure_provider_flow(provider_name: str = None) -> bool:
    """Configures credentials."""
    available_providers = list(SUPPORTED_MODELS.keys())
    if not provider_name:
        print(SEPARATOR)
        print(" Configure Provider API Key")
        for idx, prov in enumerate(available_providers, start=1):
            print(f" [{idx}] {prov.capitalize()}")
        print(SEPARATOR)
        choice = input(f" Select provider (1-{len(available_providers)}): ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(available_providers):
            provider_name = available_providers[int(choice) - 1]
        else:
            print(" Invalid selection. Returning.")
            return False
    
    print(SEPARATOR)
    print(f" Setting up API key for: [{provider_name.upper()}]")
    key_input = input(" Paste your API key: ").strip()
    if not key_input:
        print(" API Key cannot be blank.")
        return False
    
    is_valid = validate_api_key(provider_name, key_input)
    if is_valid:
        print(" API key verified successfully!")
    else:
        allow = input(" Key validation failed. Allow saving this key anyway? (y/n): ").strip().lower()
        if allow != "y":
            print(" Setup cancelled. Key not saved.")
            return False
    
    config_manager.set_provider_api_key(provider_name, key_input)
    print(f" Successfully configured {provider_name.upper()}!")
    return True

def provider_management_flow() -> None:
    """API key sub-menu router."""
    while True:
        print(SEPARATOR)
        print(" Provider & API Key Management Menu")
        gemini_status = "Configured" if config_manager.is_provider_configured("gemini") else "Not Set"
        groq_status = "Configured" if config_manager.is_provider_configured("groq") else "Not Set"
        active_default = config_manager.get_default_provider()
        
        print(f" [1] View Configured Status (Gemini: {gemini_status} | Groq: {groq_status})")
        print(" [2] Add / Edit a Provider API Key")
        print(f" [3] Change Default Active Provider (Current: {active_default.upper()})")
        print(" [4] Back to Main Menu")
        print(SEPARATOR)
        choice = input(" Choose option (1-4): ").strip()
        if choice == "1":
            print(SEPARATOR)
            print(" Current Configured Status:")
            print(f" - GEMINI: {gemini_status} (Active Model: {config_manager.get_active_model('gemini')})")
            print(f" - GROQ: {groq_status} (Active Model: {config_manager.get_active_model('groq')})")
            print(f" - DEFAULT PROVIDER: {active_default.upper()}")
            input("\n Press Enter to continue...")
        elif choice == "2":
            configure_provider_flow()
        elif choice == "3":
            print(SEPARATOR)
            print(f" Set Default Provider (Current: {active_default.upper()})")
            for idx, prov in enumerate(SUPPORTED_MODELS.keys(), start=1):
                print(f" [{idx}] {prov.upper()}")
            sub_choice = input(" Choose default (1-2): ").strip()
            if sub_choice.isdigit() and 1 <= int(sub_choice) <= len(SUPPORTED_MODELS):
                target_default = list(SUPPORTED_MODELS.keys())[int(sub_choice) - 1]
                config_manager.set_default_provider(target_default)
                print(f" Default provider changed to {target_default.upper()}.")
        elif choice == "4":
            break

def run_main_app_loop() -> None:
    """The central profile checking and loop routing container."""
    user = get_active_user()
    if user is None:
        print("\n--- Welcome to Local Workflow Agent! ---")
        print("Let's set up your local profile first.")
        while True:
            try:
                name = input("Enter your Display Name (e.g. Ayush): ").strip()
                username = input("Enter your unique Username (e.g. ayush_tiwari): ").strip()
                user = register_user(name, username)
                print(f"\nSuccess: Profile created for {user['name']} (@{user['username']})!")
                break
            except ValueError as e:
                print(f"Validation Error: {e}. Please try again.\n")
    
    if not config_manager.has_any_provider_configured():
        print("\n Welcome! No LLM providers have been configured yet.")
        print(" Let's set up your first API key before getting started.")
        configure_provider_flow()
    
    if not config_manager.has_any_provider_configured():
        print("\n An active LLM provider API key is required to run the agent. Exiting.")
        sys.exit(1)
    
    while True:
        choice = main_menu(user["name"])
        if choice == "exit":
            print("Goodbye!")
            break
        elif choice == "new":
            title = input(" Title for this conversation (blank = 'New Conversation'): ").strip()
            session = start_new_conversation(user_id=user["id"], title=title or "New Conversation")
            print(f"\n Started new conversation (id={session['id']}).")
            enter_chat_session(session["id"])
        elif choice == "resume":
            convs = display_conversation_list()
            target = prompt_pick_conversation(convs)
            if target:
                enter_chat_session(target["id"])
        elif choice == "rename":
            rename_conversation_flow()
        elif choice == "delete":
            delete_conversation_flow()
        elif choice == "config":
            provider_management_flow()