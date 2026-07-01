# cli/conversation_ui.py
import json
import textwrap
from queries.conversation_queries import (
    get_all_conversations, get_conversation_by_id, update_conversation_title,
)
from queries.message_queries import get_messages_by_conversation
from queries.tool_log_queries import get_tool_logs_by_conversation
from managers.conversation_manager import start_new_conversation

SEPARATOR = "—" * 60
ROLE_ICONS = {
    "user": "👤 You",
    "assistant": "🤖 Assistant",
    "system": "⚙️ System",
}

# Supported models with informational metadata
SUPPORTED_MODELS = {
    "gemini": [
        {"model": "gemini-3.1-flash-lite", "desc": "Gemini 3.1 Flashlight (Ultra-low latency, supports thinking)"},
        {"model": "gemini-2.5-flash-lite", "desc": "Gemini 2.5 Flashlight (Fast, cost-efficient, stable)"},
        {"model": "gemini-2.5-flash", "desc": "Gemini 2.5 Flash (State-of-the-art workhorse model)"},
        {"model": "gemini-3-flash", "desc": "Gemini 3 Flash (Advanced reasoning combined with Flash speed)"},
        {"model": "gemini-3.5-flash", "desc": "Gemini 3.5 Flash (Frontier-class performance with agentic capabilities)"},
        {"model": "gemma-4-26b-a4b-it", "desc": "Gemma 4 26B (Mixture-of-Experts reasoning open model)"},
        {"model": "gemma-4-31b-it", "desc": "Gemma 4 31B (Flagship dense open reasoning model)"}
    ],
    "groq": [
        {"model": "llama-3.3-70b-versatile", "desc": "Llama 3.3 70B Versatile (Stable, high intelligence Meta production standard)"},
        {"model": "openai/gpt-oss-120b", "desc": "GPT-OSS 120B (OpenAI's flagship 120B open-weights model with native reasoning)"},
        {"model": "openai/gpt-oss-20b", "desc": "GPT-OSS 20B (OpenAI's highly efficient 20B open-weights reasoning model)"},
        {"model": "llama-3.1-8b-instant", "desc": "Llama 3.1 8B Instant (Extremely fast, ultra-low latency model)"}
    ]
}

def print_separator() -> None:
    print(SEPARATOR)

def _truncate(text: str, width: int = 100) -> str:
    text = text.replace("\n", " ")
    return text if len(text) <= width else text[:width - 3] + "..."

def _format_timestamp(created_at: str) -> str:
    return created_at if created_at else "unknown time"

def display_conversation_list() -> list[dict]:
    """Prints a numbered list of all conversations. Returns the list used."""
    conversations = get_all_conversations()
    print_separator()
    if not conversations:
        print("No conversations yet. You'll start a fresh one.")
        print_separator()
        return conversations
    print(" Your Conversations:\n")
    for idx, conv in enumerate(conversations, start=1):
        print(f" [{idx}] (id={conv['id']}) \"{conv['title']}\" - created {_format_timestamp(conv['created_at'])}")
    print_separator()
    return conversations

def main_menu(user_name: str) -> str:
    """Top-level menu. Returns one of the mapped command actions."""
    print_separator()
    print(f"=== Hello, {user_name}! What would you like to do? ===")
    print(" [1] Start a NEW conversation")
    print(" [2] Resume an EXISTING conversation")
    print(" [3] Rename a conversation")
    print(" [4] Delete a conversation")
    print(" [5] Configure dynamic agent routing (Planner / Executor)")
    print(" [6] Manage Providers & API Keys")
    print(" [7] Exit")
    print_separator()
    choice = input(" Choose an option (1-7): ").strip()
    return {
        "1": "new",
        "2": "resume",
        "3": "rename",
        "4": "delete",
        "5": "routing",
        "6": "config",
        "7": "exit"
    }.get(choice, "invalid")

def prompt_pick_conversation(conversations: list[dict]) -> dict | None:
    """Given a displayed list, ask the user to pick one by number. Returns the row or None."""
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

def render_conversation_history(conversation_id: int) -> None:
    """Prints the full transcript of a conversation."""
    messages = get_messages_by_conversation(conversation_id)
    tool_logs = get_tool_logs_by_conversation(conversation_id)
    timeline = []
    for m in messages:
        timeline.append((m["created_at"], m["id"], "message", m))
    for t in tool_logs:
        timeline.append((t["created_at"], t["id"], "tool", t))
    timeline.sort(key=lambda row: (row[0], row[1]))
    print_separator()
    print(f" Conversation History (id={conversation_id})")
    print_separator()
    if not timeline:
        print("(No messages yet - this conversation is empty.)")
        print_separator()
        return
    for _, _, kind, row in timeline:
        if kind == "message":
            icon = ROLE_ICONS.get(row["role"], row["role"])
            print(f"\n{icon} [{_format_timestamp(row['created_at'])}]")
            print(textwrap.fill(row["content"], width=90, initial_indent="  ", subsequent_indent="  "))
        else:
            status_icon = "✔️" if row["status"] == "success" else "❌"
            print(f"\n  {status_icon} Tool Run: {row['tool_name']} [{_format_timestamp(row['created_at'])}]")
            print(f"    args: {_truncate(row['arguments'], 90)}")
            if row.get("output"):
                print(f"    output: {_truncate(str(row['output']), 90)}")
            if row.get("error_message"):
                print(f"    error: {row['error_message']}")
    print()
    print_separator()

def show_tool_calls_only(conversation_id: int) -> None:
    """Quick view: just the tool execution log for the current conversation."""
    tool_logs = get_tool_logs_by_conversation(conversation_id)
    print_separator()
    print(f" Tool Calls for Conversation {conversation_id}")
    print_separator()
    if not tool_logs:
        print("(No tools have been run in this conversation yet.)")
    for t in tool_logs:
        status_icon = "✔️" if t["status"] == "success" else "❌"
        print(f"\n{status_icon} {t['tool_name']} [{_format_timestamp(t['created_at'])}]")
        print(f"  args: {_truncate(t['arguments'], 90)}")
        if t.get("output"):
            print(f"  output: {_truncate(str(t['output']), 90)}")
        if t.get("error_message"):
            print(f"  error: {t['error_message']}")
    print()
    print_separator()

def rename_conversation_flow() -> None:
    conversations = display_conversation_list()
    if not conversations:
        return
    target = prompt_pick_conversation(conversations)
    if target is None:
        return
    new_title = input(f" New title for \"{target['title']}\": ").strip()
    if not new_title:
        print(" Title cannot be empty. Cancelled.")
        return
    try:
        updated = update_conversation_title(target["id"], new_title)
        print(f" Renamed to \"{updated['title']}\".")
    except ValueError as e:
        print(f" {e}")

def delete_conversation_flow() -> None:
    """Interactively select and delete a conversation thread using the native SQL wrapper."""
    from queries.conversation_queries import delete_conversation
    conversations = display_conversation_list()
    if not conversations:
        return
    target = prompt_pick_conversation(conversations)
    if target is None:
        return
    print_separator()
    confirm = input(f"⚠️ Are you absolutely sure you want to delete '{target['title']}'? (y/n): ").strip().lower()
    if confirm == "y":
        try:
            delete_conversation(target["id"])
            print(f"\n Successfully deleted Conversation ID {target['id']}.\n")
        except Exception as e:
            print(f"Error during deletion execution: {e}")
    else:
        print("Deletion cancelled safely.")

def save_orchestra_route_config(role: str, provider: str, model: str) -> None:
    """Internal helper to safely update agent model routes in config.json."""
    from utils.config_manager import load_config, save_config
    config = load_config()
    if "orchestra" not in config:
        config["orchestra"] = {}
    config["orchestra"][role] = {"provider": provider, "model": model}
    save_config(config)

def agent_routing_flow() -> None:
    """Interactively configure Planner, Executor, and Base Coordinator routing configurations."""
    from utils import config_manager
    roles = ["manager", "planner", "executor"]
    providers = list(SUPPORTED_MODELS.keys())
    
    print_separator()
    print("⚙️ Configure Custom Agent Role Routing")
    print("Select customized AI models to handle specific task execution roles.")
    print_separator()
    for idx, role in enumerate(roles, start=1):
        route = config_manager.get_orchestra_route(role)
        print(f" [{idx}] {role.upper()} -> Provider: {route['provider'].upper()} | Model: {route['model']}")
    print_separator()
    
    role_choice = input("Select an Agent Role to modify (1-3) or press Enter to cancel: ").strip()
    if role_choice not in ["1", "2", "3"]:
        return
    selected_role = roles[int(role_choice) - 1]
    
    print(f"\nSelect a Provider for {selected_role.upper()}:")
    for idx, prov in enumerate(providers, start=1):
        print(f" [{idx}] {prov.upper()}")
        
    prov_choice = input(f"Choose Provider (1-{len(providers)}): ").strip()
    if not prov_choice.isdigit() or not (1 <= int(prov_choice) <= len(providers)):
        return
    selected_prov = providers[int(prov_choice) - 1]
    
    models = SUPPORTED_MODELS[selected_prov]
    print(f"\nSelect a Model from {selected_prov.upper()}:")
    for idx, m in enumerate(models, start=1):
        print(f" [{idx}] {m['model']}")
        print(f"     Description: {m['desc']}")
        
    model_choice = input(f"Choose Model (1-{len(models)}): ").strip()
    if not model_choice.isdigit() or not (1 <= int(model_choice) <= len(models)):
        return
    selected_model = models[int(model_choice) - 1]["model"]
    
    save_orchestra_route_config(selected_role, selected_prov, selected_model)
    print(f"\n Successfully mapped {selected_role.upper()} role to {selected_model} ({selected_prov.upper()})!\n")

def search_memories_flow() -> None:
    """Interactively executes keyword-based searches against saved database memories."""
    from queries.memory_queries import search_memories
    query = input("\nEnter keyword search term to query memories: ").strip()
    if not query:
        return
    results = search_memories(query)
    if not results:
        print("No matching database memories found.")
        return
    print_separator()
    print(f"Memory Search Results for '{query}':")
    print_separator()
    for row in results:
        category = row.get("category", "general").upper()
        content = row.get("content", "")
        created_at = row.get("created_at", "")[:10]
        print(f" [{category}] {content} (Logged: {created_at})")
    print_separator()

def validate_api_key(provider: str, key: str) -> bool:
    """Attempts a quick, lightweight request using the SDK client to validate key permissions."""
    print("\n Validating API key... Please wait.")
    try:
        if provider == "gemini":
            from google import genai
            client = genai.Client(api_key=key)
            client.models.generate_content(
                model="gemini-3.1-flash-lite", contents="test validation key"
            )
            return True
        elif provider == "groq":
            from groq import Groq
            client = Groq(api_key=key)
            client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": "test validation key"}],
                max_tokens=1
            )
            return True
    except Exception as e:
        print(f"\n Validation failed: {e}")
        return False
    return False

def configure_provider_flow(provider_name: str = None) -> bool:
    """Interactively configure or modify the API key for a specified provider dynamically."""
    from utils import config_manager
    available_providers = list(SUPPORTED_MODELS.keys())
    
    if not provider_name:
        print_separator()
        print(" Configure Provider API Key")
        for idx, prov in enumerate(available_providers, start=1):
            print(f" [{idx}] {prov.capitalize()}")
        print_separator()
        choice = input(f"Select provider (1-{len(available_providers)}): ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(available_providers):
            provider_name = available_providers[int(choice) - 1]
        else:
            print(" Invalid selection. Returning.")
            return False
            
    print_separator()
    print(f" Setting up API key for: [{provider_name.upper()}]")
    key_input = input(" Paste your API key: ").strip()
    if not key_input:
        print(" API Key cannot be blank.")
        return False
    # Validate key
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
    """Terminal sub-menu to manage provider configurations dynamically."""
    from utils import config_manager
    while True:
        print_separator()
        print(" Provider & API Key Management Menu")
        available_providers = list(SUPPORTED_MODELS.keys())
        gemini_status = "Configured" if config_manager.is_provider_configured("gemini") else "Not Set"
        groq_status = "Configured" if config_manager.is_provider_configured("groq") else "Not Set"
        active_default = config_manager.get_default_provider()
        
        print(f" [1] View Configured Providers (Gemini: {gemini_status} | Groq: {groq_status})")
        print(" [2] Add / Edit a Provider API Key")
        print(" [3] Remove a Provider API Key")
        print(f" [4] Change Default Active Provider (Current: {active_default.upper()})")
        print(" [5] Back to Main Menu")
        print_separator()
        choice = input(" Choose option (1-5): ").strip()
        if choice == "1":
            print_separator()
            print(" Current Configured Status:")
            print(f"  - GEMINI: {gemini_status}")
            print(f"    Active Model: {config_manager.get_active_model('gemini')}")
            print(f"  - GROQ: {groq_status}")
            print(f"    Active Model: {config_manager.get_active_model('groq')}")
            print(f"  - DEFAULT PROVIDER: {active_default.upper()}")
            print_separator()
            input("Press Enter to continue...")
        elif choice == "2":
            configure_provider_flow()
        elif choice == "3":
            print_separator()
            print(" Remove Provider Key")
            for idx, prov in enumerate(available_providers, start=1):
                print(f" [{idx}] Remove {prov.capitalize()} key")
            sub_choice = input(f"Select target (1-{len(available_providers)}): ").strip()
            if sub_choice.isdigit() and 1 <= int(sub_choice) <= len(available_providers):
                target_prov = available_providers[int(sub_choice) - 1]
                config_manager.set_provider_api_key(target_prov, None)
                print(f" {target_prov.capitalize()} key removed.")
        elif choice == "4":
            print_separator()
            print(f" Set Default Provider (Current: {active_default.upper()})")
            for idx, prov in enumerate(available_providers, start=1):
                print(f" [{idx}] {prov.upper()}")
            sub_choice = input(f"Choose target default (1-{len(available_providers)}): ").strip()
            if sub_choice.isdigit() and 1 <= int(sub_choice) <= len(available_providers):
                target_default = available_providers[int(sub_choice) - 1]
                config_manager.set_default_provider(target_default)
                print(f" Default provider changed to {target_default.upper()}.")
        elif choice == "5":
            break
        else:
            print(" Invalid option, please choose 1-5.")

def model_selection_flow() -> tuple[str, str] | None:
    """Prompts selection of provider and model, returning (provider, model_name) or None."""
    from utils import config_manager
    print_separator()
    print(" Model Selection Selector")
    available_providers = list(SUPPORTED_MODELS.keys())
    for idx, prov in enumerate(available_providers, start=1):
        print(f" [{idx}] {prov.capitalize()}")
    print_separator()
    choice = input(f"Choose Provider (1-{len(available_providers)}): ").strip()
    if choice.isdigit() and 1 <= int(choice) <= len(available_providers):
        provider = available_providers[int(choice) - 1]
    else:
        print(" Invalid choice.")
        return None
        
    if not config_manager.is_provider_configured(provider):
        print(f"\n {provider.upper()} has no API key configured.")
        setup = input("Would you like to configure it now? (y/n): ").strip().lower()
        if setup == "y":
            if not configure_provider_flow(provider):
                return None
        else:
            return None
            
    models = SUPPORTED_MODELS[provider]
    print_separator()
    print(f" Models available for [{provider.upper()}]:")
    for idx, m in enumerate(models, start=1):
        print(f" [{idx}] {m['model']}")
        print(f"     Description: {m['desc']}")
    print_separator()
    pick = input(f" Select model (1-{len(models)}): ").strip()
    if not pick.isdigit():
        print(" Selection must be a valid number.")
        return None
    pick_idx = int(pick) - 1
    if pick_idx < 0 or pick_idx >= len(models):
        print(" Number out of range.")
        return None
    selected_model = models[pick_idx]["model"]
    config_manager.set_active_model(provider, selected_model)
    config_manager.set_default_provider(provider)
    print(f"\n Configured system to use: {selected_model} via {provider.upper()}!")
    return provider, selected_model