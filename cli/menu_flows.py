# cli/menu_flows.py
import sys
import os
import time
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt, IntPrompt, FloatPrompt, Confirm
from rich.align import Align

from cli.constants import SEPARATOR, SUPPORTED_MODELS, SUPPORTED_EMBEDDING_MODELS, APP_BANNER
from database.table_generator import create_tables
from queries.conversation_queries import (
    get_all_conversations,
    create_conversation,
    update_conversation_title,
    delete_conversation,
)
from managers.user_manager import get_active_user, register_user
from cli.chat_loop import enter_chat_session
import utils.config_manager as config_manager
import config_configure.out_chat_config as out_chat_config
import config_configure.in_chat_config as in_chat_config

console = Console()

def clear_screen():
    """Clears the terminal screen for a clean UI dashboard feel."""
    os.system('cls' if os.name == 'nt' else 'clear')

def display_conversation_list() -> list[dict]:
    """Retrieves and lists conversations chronologically using a Rich Table."""
    conversations = get_all_conversations()
    chronological_convs = list(reversed(conversations))

    if not chronological_convs:
        console.print(Panel("[dim]No active conversations found. Start a new session.[/dim]", border_style="yellow"))
        return chronological_convs

    table = Table(title="Your Conversations", show_header=True, header_style="bold cyan", expand=True)
    table.add_column("ID", style="dim", width=5)
    table.add_column("Title", style="bold white")
    table.add_column("Created At", style="green", justify="right")

    for idx, conv in enumerate(chronological_convs, start=1):
        created = conv.get("created_at", "unknown time")
        table.add_row(f"[{idx}]", conv['title'], created)

    console.print(table)
    return chronological_convs

def prompt_pick_conversation(conversations: list[dict]) -> dict | None:
    """Prompts selection of a conversation index."""
    if not conversations:
        return None
    
    index = IntPrompt.ask("\nSelect the [cyan]ID[/cyan] of the conversation", default=1) - 1
    
    if index < 0 or index >= len(conversations):
        console.print("[bold red]Invalid selection. That number isn't in the list.[/bold red]")
        return None
    return conversations[index]

def main_menu(user_name: str) -> str:
    clear_screen()
    console.print(Align.center(APP_BANNER))
    
    menu_text = (
        "[1] Start a [bold green]NEW[/bold green] conversation\n"
        "[2] Resume an [bold yellow]EXISTING[/bold yellow] conversation\n"
        "[3] Rename a conversation\n"
        "[4] Delete a conversation\n"
        "[5] Settings & API Keys\n"
        "[6] Exit"
    )
    
    console.print(Panel(menu_text, title=f"Welcome, [bold cyan]{user_name}[/bold cyan]!", border_style="blue", expand=False))
    
    choice = Prompt.ask("Choose an option", choices=["1", "2", "3", "4", "5", "6"], default="1")
    
    return {
        "1": "new",
        "2": "resume",
        "3": "rename",
        "4": "delete",
        "5": "config",
        "6": "exit",
    }.get(choice, "invalid")

def rename_conversation_flow() -> None:
    """Interactively modifies titles."""
    clear_screen()
    console.print("[bold yellow]Rename Conversation[/bold yellow]")
    convs = display_conversation_list()
    if not convs:
        Prompt.ask("Press Enter to return")
        return

    target = prompt_pick_conversation(convs)
    if not target:
        return

    new_title = Prompt.ask(f"New title for [bold cyan]\"{target['title']}\"[/bold cyan]")
    if not new_title.strip():
        console.print("[yellow]Title cannot be blank. Cancelled.[/yellow]")
        time.sleep(1)
        return

    try:
        updated = update_conversation_title(target["id"], new_title.strip())
        console.print(f"[bold green]✔ Renamed to \"{updated['title']}\".[/bold green]")
    except ValueError as e:
        console.print(f"[bold red]Error: {e}[/bold red]")
    Prompt.ask("Press Enter to return")

def delete_conversation_flow() -> None:
    """Safely removes conversations using standard cascading rules."""
    clear_screen()
    console.print("[bold red]Delete Conversation[/bold red]")
    convs = display_conversation_list()
    if not convs:
        Prompt.ask("Press Enter to return")
        return

    target = prompt_pick_conversation(convs)
    if not target:
        return

    confirm = Confirm.ask(f"Are you sure you want to delete [bold red]'{target['title']}'[/bold red]?")
    if confirm:
        try:
            delete_conversation(target["id"])
            console.print(f"[bold green]✔ Successfully deleted Conversation.[/bold green]")
        except Exception as e:
            console.print(f"[bold red]Error during deletion execution: {e}[/bold red]")
    else:
        console.print("[dim]Deletion cancelled safely.[/dim]")
    Prompt.ask("Press Enter to return")

def configure_provider_flow(provider_name: str = None) -> bool:
    """Configures credentials."""
    clear_screen()
    available_providers = list(SUPPORTED_MODELS.keys())
    
    if not provider_name:
        table = Table(title="Configure Provider API Key", show_header=True, header_style="bold magenta")
        table.add_column("ID", style="dim", width=5)
        table.add_column("Provider", style="bold white")
        
        for idx, prov in enumerate(available_providers, start=1):
            table.add_row(f"[{idx}]", prov.capitalize())
            
        console.print(table)
        
        choice = IntPrompt.ask("Select provider", choices=[str(i) for i in range(1, len(available_providers) + 1)])
        provider_name = available_providers[choice - 1]

    console.print(f"\n[bold cyan]Setting up API key for: {provider_name.upper()}[/bold cyan]")
    key_input = Prompt.ask("Paste your API key", password=True)
    
    if not key_input:
        console.print("[bold red]API Key cannot be blank.[/bold red]")
        time.sleep(1)
        return False

    with console.status("[bold yellow]Validating API key... Please wait...[/bold yellow]"):
        res = out_chat_config.validate_and_set_api_key(provider_name, key_input)

    if res["status"] == "success":
        console.print(f"[bold green]✔ {res['message']}[/bold green]")
        time.sleep(1)
        return True
    else:
        console.print(f"[bold red]✖ {res['message']}[/bold red]")
        if res.get("requires_force"):
            allow = Confirm.ask("Key validation failed. Allow saving this key anyway?")
            if allow:
                force_res = out_chat_config.validate_and_set_api_key(
                    provider_name, key_input, force_save=True
                )
                console.print(f"[bold green]{force_res['message']}[/bold green]")
                time.sleep(1)
                return True
            else:
                console.print("[yellow]Setup cancelled. Key not saved.[/yellow]")
                time.sleep(1)
        return False

def models_configuration_flow() -> None:
    """Dedicated menu for Models and Embeddings."""
    while True:
        clear_screen()
        main_prov = config_manager.get_default_provider()
        main_mod = config_manager.get_active_model(main_prov)
        emb_prov = config_manager.get_default_embedding_provider()
        emb_mod = config_manager.get_embedding_model(emb_prov)

        menu_text = (
            f"[1] Set Main Chat Model      [dim](Current: {main_prov.upper()} - {main_mod})[/dim]\n"
            f"[2] Set Embedding Model      [dim](Current: {emb_prov.upper()} - {emb_mod})[/dim]\n"
            f"[3] Set API Keys\n"
            f"[4] Back to Menu"
        )
        console.print(Panel(menu_text, title="🤖 Model & Embedding Configuration", border_style="magenta", expand=False))

        choice = Prompt.ask("Select option", choices=["1", "2", "3", "4"], default="4")

        if choice == "1":
            try:
                prov = Prompt.ask("Provider", choices=["gemini", "groq"], default=main_prov)
                if prov in SUPPORTED_MODELS:
                    # FIX: Corrected method name to set_active_default_provider
                    res_prov = out_chat_config.set_active_default_provider(prov)
                    if isinstance(res_prov, dict) and res_prov.get("status") == "error":
                        console.print(f"[bold red]Error: {res_prov.get('message')}[/bold red]")
                        time.sleep(2)
                        continue
                    
                    table = Table(title=f"Available Models for {prov.upper()}", show_header=True, header_style="bold cyan")
                    table.add_column("ID", style="dim", width=5)
                    table.add_column("Model", style="bold white")
                    table.add_column("Description", style="dim")
                    
                    for idx, m in enumerate(SUPPORTED_MODELS[prov], 1):
                        table.add_row(f"[{idx}]", m['model'], m['desc'])
                    console.print(table)
                    
                    mod_idx = IntPrompt.ask("Select model number", choices=[str(i) for i in range(1, len(SUPPORTED_MODELS[prov]) + 1)])
                    selected = SUPPORTED_MODELS[prov][mod_idx - 1]["model"]
                    
                    res_mod = in_chat_config.switch_active_model(prov, selected)
                    if isinstance(res_mod, dict) and res_mod.get("status") == "error":
                        console.print(f"[bold red]Error: {res_mod.get('message')}[/bold red]")
                    else:
                        console.print(f"[bold green]✔ Main model updated to {selected}[/bold green]")
                    time.sleep(1)
            except Exception as e:
                console.print(f"[bold red]An unexpected error occurred: {e}[/bold red]")
                time.sleep(2)

        elif choice == "2":
            try:
                prov = Prompt.ask("Embedding Provider", choices=["gemini", "groq"], default=emb_prov)
                if prov in SUPPORTED_EMBEDDING_MODELS:
                    res_emb_prov = out_chat_config.set_default_embedding_provider(prov)
                    if isinstance(res_emb_prov, dict) and res_emb_prov.get("status") == "error":
                        console.print(f"[bold red]Error: {res_emb_prov.get('message')}[/bold red]")
                        time.sleep(2)
                        continue
                    
                    table = Table(title=f"Available Embeddings for {prov.upper()}", show_header=True, header_style="bold cyan")
                    table.add_column("ID", style="dim", width=5)
                    table.add_column("Model", style="bold white")
                    
                    for idx, m in enumerate(SUPPORTED_EMBEDDING_MODELS[prov], 1):
                        table.add_row(f"[{idx}]", m['model'])
                    console.print(table)
                    
                    mod_idx = IntPrompt.ask("Select model number", choices=[str(i) for i in range(1, len(SUPPORTED_EMBEDDING_MODELS[prov]) + 1)])
                    selected = SUPPORTED_EMBEDDING_MODELS[prov][mod_idx - 1]["model"]
                    
                    res_emb_mod = out_chat_config.update_embedding_model(prov, selected)
                    if isinstance(res_emb_mod, dict) and res_emb_mod.get("status") == "error":
                        console.print(f"[bold red]Error: {res_emb_mod.get('message')}[/bold red]")
                    else:
                        console.print(f"[bold green]✔ Embedding model updated to {selected}[/bold green]")
                    time.sleep(1)
            except Exception as e:
                console.print(f"[bold red]An unexpected error occurred: {e}[/bold red]")
                time.sleep(2)

        elif choice == "3":
            configure_provider_flow()
        elif choice == "4":
            break

def advanced_settings_flow() -> None:
    """Interactive Advanced Settings Terminal Flow."""
    while True:
        clear_screen()
        menu_text = (
            f"[1] Edit System Prompt        [dim](Overrides default behavior)[/dim]\n"
            f"[2] Set Max ReAct Loops       [dim](Current: {config_manager.get_max_turns()})[/dim]\n"
            f"[3] Set Context Window Size   [dim](Current: {config_manager.get_max_context_tokens()} tokens)[/dim]\n"
            f"[4] Set Thinking Level        [dim](Current: {config_manager.get_thinking_level().upper()})[/dim]\n"
            f"[5] Configure Loop Guard      [dim](Prevents infinite loops)[/dim]\n"
            f"[6] Set Summary Threshold     [dim](Current: {config_manager.get_summary_trigger_count()} messages)[/dim]\n"
            f"[7] Set Memory Match Score    [dim](Current: {config_manager.get_memory_similarity_threshold()})[/dim]\n"
            f"[8] Configure Network Retry\n"
            f"[9] Change Workspace Path     [dim](Current: {config_manager.get_workspace_path()})[/dim]\n"
            f"[10] Back"
        )
        
        console.print(Panel(menu_text, title="鈿 欙 笍 Advanced Agent Settings", border_style="yellow", expand=False))
        
        # UPDATE: Change range to (1, 11) and default to "10"
        choice = Prompt.ask("Select option", choices=[str(i) for i in range(1, 11)], default="10")

        if choice == "1":
            console.print("\n[dim]Type 'CLEAR' to revert to default.[/dim]")
            val = Prompt.ask("New System Prompt")
            out_chat_config.update_system_instruction(val)
            console.print("[bold green]✔ System prompt updated.[/bold green]")
            time.sleep(1)
            
        elif choice == "2":
            val = IntPrompt.ask("Enter max execution steps", default=15)
            out_chat_config.update_max_turns(val)
            console.print("[bold green]✔ Max loops updated.[/bold green]")
            time.sleep(1)
            
        elif choice == "3":
            val = IntPrompt.ask("Enter max context tokens", default=100000)
            out_chat_config.update_max_context_tokens(val)
            console.print("[bold green]✔ Context window updated.[/bold green]")
            time.sleep(1)
            
        elif choice == "4":
            val = Prompt.ask("Thinking level", choices=["off", "low", "medium", "high"], default="high")
            config_manager.set_thinking_level(val)
            console.print(f"[bold green]✔ Thinking level set to {val}.[/bold green]")
            time.sleep(1)
            
        elif choice == "5":
            f = IntPrompt.ask("Max consecutive failures allowed", default=3)
            s = IntPrompt.ask("Max consecutive successes allowed", default=2)
            out_chat_config.update_loop_guard(f, s)
            console.print("[bold green]✔ Loop guard updated.[/bold green]")
            time.sleep(1)
            
        elif choice == "6":
            val = IntPrompt.ask("Enter trigger count", default=30)
            out_chat_config.update_summary_trigger_count(val)
            console.print("[bold green]✔ Summary threshold updated.[/bold green]")
            time.sleep(1)
            
        elif choice == "7":
            val = FloatPrompt.ask("Enter clustering similarity score (0.0 to 1.0)", default=0.8)
            try:
                out_chat_config.update_memory_similarity_threshold(val)
                console.print("[bold green]✔ Memory threshold updated.[/bold green]")
            except ValueError:
                console.print("[bold red]Invalid input.[/bold red]")
            time.sleep(1)
            
        elif choice == "8":
            retry = config_manager.get_api_retry_settings()
            attempts = IntPrompt.ask("Enter max retry attempts", default=retry['max_attempts'])
            delay = FloatPrompt.ask("Enter base delay in seconds", default=retry['base_delay'])
            try:
                out_chat_config.update_api_retry_settings(attempts, delay)
                console.print("[bold green]✔ Network retry bounds updated.[/bold green]")
            except ValueError:
                console.print("[bold red]Invalid base delay format.[/bold red]")
            time.sleep(1)
            
        elif choice == "9":
            console.print("\n[dim]Enter the absolute path to the new workspace directory.[/dim]")
            val = Prompt.ask("New Workspace Path").strip()
            if val:
                res = out_chat_config.update_workspace_path(val)
                if res.get("status") == "success":
                    console.print(f"[bold green]鉁 {res['message']}[/bold green]")
                else:
                    console.print(f"[bold red]鉂 {res.get('message', 'Failed to update workspace.')}[/bold red]")
                time.sleep(1.5)
            else:
                console.print("[yellow]Workspace update cancelled.[/yellow]")
                time.sleep(1)

        elif choice == "10":
            break

def telegram_configuration_flow() -> None:
    """Interactive menu for managing Telegram Bot settings."""
    while True:
        clear_screen()
        res = out_chat_config.get_telegram_settings()
        data = res["data"]
        
        info_text = (
            f"[bold white]Current Bot Token:[/bold white] {data['bot_token_masked']}\n"
            f"[bold white]Allowed User IDs:[/bold white] {data['allowed_user_ids']}"
        )
        console.print(Panel(info_text, title="📱 Telegram Bot Configuration", border_style="blue", expand=False))
        
        menu_text = (
            "[1] Update Bot Token\n"
            "[2] Update Allowed User IDs (Whitelist)\n"
            "[3] Remove Bot Token (Disable Telegram)\n"
            "[4] Back"
        )
        console.print(Panel(menu_text, border_style="dim", expand=False))

        choice = Prompt.ask("Choose option", choices=["1", "2", "3", "4"], default="4")
        
        if choice == "1":
            new_token = Prompt.ask("Enter new Telegram Bot Token", password=True)
            if new_token:
                res = out_chat_config.update_telegram_settings(bot_token=new_token)
                console.print(f"\n[bold green]✔ {res['message']}[/bold green]")
                time.sleep(1)
                
        elif choice == "2":
            console.print("\n[dim]Enter allowed Telegram User IDs separated by commas (e.g., 123456, 987654).[/dim]")
            console.print("[bold yellow]WARNING: Leave completely blank to clear the list (Nobody will be able to use the bot).[/bold yellow]")
            new_users = Prompt.ask("User IDs")
            res = out_chat_config.update_telegram_settings(allowed_users_str=new_users)
            console.print(f"\n[bold green]✔ {res['message']}[/bold green]")
            time.sleep(1)
            
        elif choice == "3":
            confirm = Confirm.ask("Are you sure you want to remove the Telegram token?")
            if confirm:
                res = out_chat_config.update_telegram_settings(bot_token="")
                console.print("\n[bold yellow]Telegram bot disabled.[/bold yellow]")
                time.sleep(1)
                
        elif choice == "4":
            break

def run_main_app_loop() -> None:
    """The central profile checking and loop routing container."""
    user = get_active_user()
    
    if user is None:
        clear_screen()
        console.print(Align.center(APP_BANNER))
        console.print(Align.center("[bold yellow]--- Welcome to Local Workflow Agent! ---[/bold yellow]"))
        console.print(Align.center("Let's set up your local profile first.\n"))
        while True:
            try:
                name = Prompt.ask("Enter your Display Name (e.g. Ayush)")
                username = Prompt.ask("Enter your unique Username (e.g. ayush_tiwari)")
                user = register_user(name, username)
                console.print(f"\n[bold green]✔ Success: Profile created for {user['name']} (@{user['username']})![/bold green]")
                time.sleep(1.5)
                break
            except ValueError as e:
                console.print(f"[bold red]Validation Error: {e}. Please try again.[/bold red]\n")

    if not config_manager.has_any_provider_configured():
        clear_screen()
        console.print(Panel("[bold yellow]No LLM providers have been configured yet.\nLet's set up your first API key before getting started.[/bold yellow]", border_style="yellow"))
        configure_provider_flow()

    if not config_manager.has_any_provider_configured():
        console.print("\n[bold red]An active LLM provider API key is required to run the agent. Exiting.[/bold red]")
        sys.exit(1)

    while True:
        choice = main_menu(user["name"])
        
        if choice == "new":
            title = Prompt.ask("Title for this conversation", default="New Conversation")
            session = create_conversation(user_id=user["id"], title=title)
            console.print(f"\n[bold green]Started new conversation (id={session['id']}).[/bold green]")
            enter_chat_session(session["id"])
            
        elif choice == "resume":
            clear_screen()
            console.print("[bold yellow]Resume Conversation[/bold yellow]")
            convs = display_conversation_list()
            selected = prompt_pick_conversation(convs)
            if selected:
                enter_chat_session(selected["id"])
                
        elif choice == "rename":
            rename_conversation_flow()
            
        elif choice == "delete":
            delete_conversation_flow()
            
        elif choice == "config":
            while True:
                clear_screen()
                menu_text = (
                    "[1] Models & Embeddings\n"
                    "[2] Advanced Agent Settings\n"
                    "[3] Telegram Bot Settings\n"
                    "[4] Back to Main Menu"
                )
                console.print(Panel(menu_text, title="⚙️ Settings & Configuration", border_style="white", expand=False))
                
                sub = Prompt.ask("Select option", choices=["1", "2", "3", "4"], default="4")
                
                if sub == "1":
                    models_configuration_flow()
                elif sub == "2":
                    advanced_settings_flow()
                elif sub == "3":
                    telegram_configuration_flow()
                elif sub == "4":
                    break
                    
        elif choice == "exit":
            console.print("[bold green]Goodbye![/bold green]")
            break