# cli/chat_loop.py
import json
import textwrap
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from cli.constants import SEPARATOR, IN_CHAT_HELP, SUPPORTED_MODELS
from cli.callbacks import (
    reset_execution_counters,
    cli_tool_approval_callback,
    cli_status_callback
)
from engine.agent_engine import AgentEngine
from engine.thinking_configure import supports_thinking
from queries.message_queries import get_messages_by_conversation
from queries.tool_log_queries import get_tool_logs_by_conversation
from queries.memory_queries import search_memories
from queries.conversation_queries import delete_conversation
from utils import config_manager

console = Console()

def render_conversation_history(conversation_id: int) -> None:
    """Reprints the chronological dialog transcript."""
    from cli.constants import ROLE_ICONS
    messages = get_messages_by_conversation(conversation_id)
    tool_logs = get_tool_logs_by_conversation(conversation_id)
    timeline = []
    for m in messages:
        timeline.append((m["created_at"], m["id"], "message", m))
    for t in tool_logs:
        timeline.append((t["created_at"], t["id"], "tool", t))
    timeline.sort(key=lambda row: (row[0], row[1]))
    
    print(SEPARATOR)
    print(f" Conversation History (id={conversation_id})")
    print(SEPARATOR)
    if not timeline:
        print(" (No messages yet - this conversation is empty.)")
        print(SEPARATOR)
        return

    import textwrap
    for _, _, kind, row in timeline:
        if kind == "message":
            icon = ROLE_ICONS.get(row["role"], row["role"])
            print(f"\n{icon} [{row['created_at']}]")
            print(textwrap.fill(row["content"], width=90, initial_indent=" ", subsequent_indent=" "))
        else:
            status_icon = "✓" if row["status"] == "success" else "✗"
            print(f"\n {status_icon} Tool Run: {row['tool_name']} [{row['created_at']}]")
            print(f" args: {row['arguments']}")
            if row.get("output"):
                print(f" output: {row['output']}")
            if row.get("error_message"):
                print(f" error: {row['error_message']}")
    print()
    print(SEPARATOR)

def show_tool_calls_only(conversation_id: int) -> None:
    """Prints tool metrics and logs alone."""
    tool_logs = get_tool_logs_by_conversation(conversation_id)
    print(SEPARATOR)
    print(f" Tool Calls for Conversation {conversation_id}")
    print(SEPARATOR)
    if not tool_logs:
        print(" (No tools have been run in this conversation yet.)")
        return
    for t in tool_logs:
        status_icon = "✓" if t["status"] == "success" else "✗"
        print(f"\n{status_icon} {t['tool_name']} [{t['created_at']}]")
        print(f" args: {t['arguments']}")
        if t.get("output"):
            print(f" output: {t['output']}")
        if t.get("error_message"):
            print(f" error: {t['error_message']}")
    print()
    print(SEPARATOR)

def search_memories_flow() -> None:
    """Conducts keyword-based searches and displays results."""
    query = input("\nEnter keyword search term to query memories: ").strip()
    if not query:
        return
    results = search_memories(query)
    if not results:
        console.print("[yellow]No matching database memories found.[/yellow]")
        return
    table = Table(title=f"Memory Search Results for '{query}'", show_header=True, header_style="bold cyan")
    table.add_column("Category", style="green", width=15)
    table.add_column("Memory Details", style="white")
    table.add_column("Logged Date", style="dim", width=15)
    for row in results:
        category = row.get("category", "general").upper()
        content = row.get("content", "")
        created = row.get("created_at", "")[:10]
        table.add_row(category, content, created)
    console.print(table)

def enter_chat_session(conversation_id: int) -> None:
    """The central in-chat interactive shell parsing prompt commands."""
    provider_choice = config_manager.get_default_provider()
    model_choice = config_manager.get_active_model(provider_choice)
    resolved_key = config_manager.get_provider_api_key(provider_choice)
    try:
        engine = AgentEngine(
            provider_name=provider_choice,
            model_name=model_choice,
            api_key=resolved_key,
            autonomous=False
        )
    except Exception as e:
        print(f"Initialization Error: {e}")
        return
    
    print(f"\n=== You're in conversation {conversation_id}. Type 'help' for commands. ===\n")
    
    while True:
        try:
            user_input = input("You: ").strip()
            if not user_input:
                continue
            lowered = user_input.lower()
            if lowered in {"exit", "quit"}:
                print("Goodbye!")
                return
            elif lowered == "menu":
                break
            elif lowered == "history":
                render_conversation_history(conversation_id)
                continue
            elif lowered == "tools":
                show_tool_calls_only(conversation_id)
                continue
            elif lowered == "help":
                print(IN_CHAT_HELP)
                continue
            elif lowered == "/search":
                search_memories_flow()
                continue
            elif lowered == "/delete":
                confirm = input("Delete current session and exit back to menu? (y/n): ").strip().lower()
                if confirm == "y":
                    delete_conversation(conversation_id)
                    print("Conversation deleted successfully.")
                    break
                continue
            elif lowered == "/models":
                print(SEPARATOR)
                print(" Model Selection Selector")
                available_providers = list(SUPPORTED_MODELS.keys())
                for idx, prov in enumerate(available_providers, start=1):
                    print(f" [{idx}] {prov.capitalize()}")
                print(SEPARATOR)
                choice = input(" Choose Provider (1-2): ").strip()
                if choice.isdigit() and 1 <= int(choice) <= len(available_providers):
                    provider_choice = available_providers[int(choice) - 1]
                    models = SUPPORTED_MODELS[provider_choice]
                    print(SEPARATOR)
                    print(f" Models available for [{provider_choice.upper()}]:")
                    for idx, m in enumerate(models, start=1):
                        print(f" [{idx}] {m['model']} ({m['desc']})")
                    print(SEPARATOR)
                    pick = input(f" Select model (1-{len(models)}): ").strip()
                    if pick.isdigit() and 1 <= int(pick) <= len(models):
                        model_choice = models[int(pick) - 1]["model"]
                        config_manager.set_active_model(provider_choice, model_choice)
                        config_manager.set_default_provider(provider_choice)
                        resolved_key = config_manager.get_provider_api_key(provider_choice)
                        
                        # Rebuild local Agent Engine instance
                        print("\nRe-booting Assistant with new model...")
                        engine = AgentEngine(
                            provider_name=provider_choice,
                            model_name=model_choice,
                            api_key=resolved_key,
                            autonomous=False
                        )
                        print(f"Assistant is now running: [{provider_choice.upper()}] - {model_choice}\n")
                continue
            elif lowered == "/thinking":
                if not supports_thinking(model_choice):
                    print(f"\nThe current model [{model_choice}] does not support thinking budget levels.\n")
                    continue
                print(f"\nCurrent thinking level: {config_manager.get_thinking_level().upper()}")
                print("Select a new reasoning/thinking budget:")
                print(" [1] Off")
                print(" [2] Low")
                print(" [3] Medium")
                print(" [4] High")
                level_choice = input(" Choose level (1-4): ").strip()
                level_map = {"1": "off", "2": "low", "3": "medium", "4": "high"}
                selected_level = level_map.get(level_choice)
                if selected_level:
                    config_manager.set_thinking_level(selected_level)
                    print(f"Thinking level updated to: {selected_level.upper()}\n")
                else:
                    print("Invalid choice. Thinking level unchanged.\n")
                continue
            
            reset_execution_counters()
            response_text = engine.send_message(
                conversation_id=conversation_id,
                user_text=user_input,
                approval_callback=cli_tool_approval_callback,
                status_callback=cli_status_callback
            )
            print(f"\n Assistant: {response_text}\n")
        except KeyboardInterrupt:
            print("\nSession interrupted. Returning to main menu.")
            break
        except Exception as e:
            print(f"\nError encountered: {e}\n")