# cli/menu_flows.py
import sys
from cli.constants import SEPARATOR, SUPPORTED_MODELS
from database.table_generator import create_tables
from queries.conversation_queries import get_all_conversations, create_conversation
from managers.user_manager import get_active_user, register_user
from cli.callbacks import validate_api_key
from cli.chat_loop import enter_chat_session
import utils.config_manager as config_manager

def display_conversation_list() -> list[dict]:
    """Retrieves and lists conversations chronologically: oldest on top, latest/newest on bottom."""
    conversations = get_all_conversations() # Returns newest first from DB query
    
    # Reverse so that the latest/newest conversation is at the bottom of the list
    chronological_convs = list(reversed(conversations))
    
    print(SEPARATOR)
    if not chronological_convs:
        print(" (No active conversations found. Choose option [1] to start a new session.)")
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
        print(" Title cannot be blank. Cancelled.")
        return
    try:
        from queries.conversation_queries import update_conversation_title
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
    confirm = input(f" Are you sure you want to delete '{target['title']}'? (y/n): ").strip().lower()
    if confirm == "y":
        try:
            from queries.conversation_queries import delete_conversation
            delete_conversation(target["id"])
            from rich.console import Console
            Console().print(f"[bold red] Successfully deleted Conversation ID {target['id']}.[/bold red]\n")
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
        print(" [4] Edit Advanced Agent Settings (Max Turns, Sandbox, etc.)")
        print(" [5] Back to Main Menu")
        print(SEPARATOR)
        
        choice = input(" Choose option (1-5): ").strip()
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
            advanced_settings_flow()
        elif choice == "5":
            break

# Inside advanced_settings_flow() in cli/menu_flows.py [14, 15]
def advanced_settings_flow() -> None:
    while True:
        print(SEPARATOR)
        print(" Advanced Agent System Configuration Settings")
        print(SEPARATOR)
        print(f" [1] Adjust ReAct Loop Maximum Turns (Current: {config_manager.get_max_turns()})")
        print(f" [2] Set Sliding Window Context Size (Current: {config_manager.get_max_context_tokens()} tokens)")
        print(f" [3] Modify Background Summary Threshold (Current: {config_manager.get_summary_trigger_count()} messages)")
        print(f" [4] Configure Safe Sandbox Limits (Current: {config_manager.get_sandbox_settings()['memory_limit']} RAM)")
        print(f" [5] Set Local Log Truncation length (Current: {config_manager.get_cli_log_truncation_limit()} chars)")
        print(f" [6] Set Memory Category Similarity Match (Current: {config_manager.get_memory_similarity_threshold()})")
        print(f" [7] Configure Network Retry Bounds (Current: {config_manager.get_api_retry_settings()['max_attempts']} tries)")
        
        # Resolve currently configured loop guard settings
        lg = config_manager.get_loop_guard()
        failed_val = lg.get("max_failed_attempts")
        success_val = lg.get("max_success_attempts")
        failed_display = failed_val if (failed_val is not None and failed_val > 0) else "Default Fallback (3)"
        success_display = success_val if (success_val is not None and success_val > 0) else "Default Fallback (2)"
        
        print(f" [8] Configure Loop Guard Thresholds (Current: Failed={failed_display}, Success={success_display})")
        print(" [9] Back to Settings Menu")
        print(SEPARATOR)

        choice = input(" Select option (1-9): ").strip()
        
        if choice == "1":
            val = input(" Enter maximum execution steps (e.g. 10 to 30): ").strip()
            if val.isdigit():
                config_manager.set_max_turns(int(val))
                print(f" Max turns successfully updated to {config_manager.get_max_turns()}!")
            else:
                print(" Invalid input.")
                
        elif choice == "2":
            val = input(" Enter max context window size (e.g., 8192 to 200000): ").strip()
            if val.isdigit():
                config_manager.set_max_context_tokens(int(val))
                print(f" Max tokens successfully updated to {config_manager.get_max_context_tokens()}!")
            else:
                print(" Invalid input.")
                
        elif choice == "3":
            val = input(" Enter trigger count of un-summarized messages (e.g., 10 to 50): ").strip()
            if val.isdigit():
                config_manager.set_summary_trigger_count(int(val))
                print(f" Trigger count successfully updated to {config_manager.get_summary_trigger_count()}!")
            else:
                print(" Invalid input.")
                
        elif choice == "4":
            sandbox = config_manager.get_sandbox_settings()
            mem = input(f" Enter Docker container RAM limit (e.g. 512m, 1g, 2g) [Current: {sandbox['memory_limit']}]: ").strip()
            timeout = input(f" Enter execution timeout in seconds (e.g. 15, 30, 60) [Current: {sandbox['timeout_seconds']}]: ").strip()
            if timeout.isdigit() and mem:
                config_manager.set_sandbox_settings(
                    memory_limit=mem, 
                    cpu_limit=sandbox["cpu_limit"], 
                    timeout_seconds=int(timeout)
                )
                print(" Sandbox safety bounds updated successfully!")
            else:
                print(" Invalid inputs.")
                
        elif choice == "5":
            val = input(" Enter max characters displayed for logs (e.g. 200 to 2000): ").strip()
            if val.isdigit():
                config_manager.set_cli_log_truncation_limit(int(val))
                print(f" Truncation limit successfully updated to {config_manager.get_cli_log_truncation_limit()} characters!")
            else:
                print(" Invalid input.")
                
        elif choice == "6":
            val = input(" Enter clustering similarity score (0.0 to 1.0) [e.g. 0.80]: ").strip()
            try:
                score = float(val)
                if 0.0 <= score <= 1.0:
                    config_manager.set_memory_similarity_threshold(score)
                    print(f" Memory matching threshold successfully updated to {config_manager.get_memory_similarity_threshold()}!")
                else:
                    print(" Out of range. Value must be between 0.0 and 1.0.")
            except ValueError:
                print(" Invalid input.")
                
        elif choice == "7":
            retry = config_manager.get_api_retry_settings()
            attempts = input(f" Enter maximum retry attempts (e.g. 3, 5) [Current: {retry['max_attempts']}]: ").strip()
            delay = input(f" Enter base delay in seconds (e.g. 2.0, 5.0) [Current: {retry['base_delay']}]: ").strip()
            if attempts.isdigit():
                try:
                    config_manager.set_api_retry_settings(
                        max_attempts=int(attempts), 
                        base_delay=float(delay)
                    )
                    print(" Network API retry bounds successfully updated!")
                except ValueError:
                    print(" Invalid base delay format.")
            else:
                print(" Invalid attempts format.")
                
        elif choice == "8":
            print("\n--- Loop Guard Threshold Configuration ---")
            print("Leave blank, enter 0, or type 'none' to reset back to template default limits.")
            
            failed_in = input("Enter max consecutive failures allowed: ").strip().lower()
            success_in = input("Enter max consecutive successes allowed: ").strip().lower()
            
            # Process failures: map 0/none/blank to None (representing template fallback)
            if failed_in in ("", "0", "none", "null"):
                max_failed = None
            else:
                try:
                    max_failed = int(failed_in)
                    if max_failed <= 0:
                        max_failed = None
                except ValueError:
                    print("Invalid input for failures. Resorting to Default Fallback.")
                    max_failed = None
                    
            # Process successes: map 0/none/blank to None (representing template fallback)
            if success_in in ("", "0", "none", "null"):
                max_success = None
            else:
                try:
                    max_success = int(success_in)
                    if max_success <= 0:
                        max_success = None
                except ValueError:
                    print("Invalid input for successes. Resorting to Default Fallback.")
                    max_success = None
                    
            config_manager.set_loop_guard(max_failed, max_success)
            print("\n[Success] Loop Guard thresholds updated successfully!")
            
        elif choice == "9":
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
        if choice == "new":
            title = input(" Title for this conversation (blank = 'New Conversation'): ").strip()
            session = create_conversation(user_id=user["id"], title=title or "New Conversation")
            print(f"\n Started new conversation (id={session['id']}).")
            enter_chat_session(session["id"])
        elif choice == "resume":
            convs = display_conversation_list()
            selected = prompt_pick_conversation(convs)
            if selected:
                enter_chat_session(selected["id"])
        elif choice == "rename":
            rename_conversation_flow()
        elif choice == "delete":
            delete_conversation_flow()
        elif choice == "config":
            provider_management_flow()
        elif choice == "exit":
            print("Goodbye!")
            break
