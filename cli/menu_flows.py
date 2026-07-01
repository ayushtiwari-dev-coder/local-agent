# cli/menu_flows.py
import sys
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from cli.conversation_ui import print_separator, SUPPORTED_MODELS

console = Console()

def delete_conversation_flow() -> None:
    """Executes a clean, interactive conversation deletion flow using existing SQL helpers."""
    from cli.conversation_ui import display_conversation_list, prompt_pick_conversation
    from queries.conversation_queries import delete_conversation
    
    conversations = display_conversation_list()
    if not conversations:
        return
        
    target = prompt_pick_conversation(conversations)
    if target is None:
        return
        
    confirm = input(f"\n⚠️ Are you absolutely sure you want to delete '{target['title']}'? (y/n): ").strip().lower()
    if confirm == "y":
        try:
            delete_conversation(target["id"])
            console.print(f"[bold red]🗑️ Successfully deleted Conversation ID {target['id']}.[/bold red]\n")
        except Exception as e:
            console.print(f"[bold red]Error deleting conversation: {e}[/bold red]")
    else:
        console.print("[yellow]Deletion cancelled.[/yellow]")

def agent_routing_flow() -> None:
    """Interactively configure which dynamic model/AI controls which workflow role (Planner vs Executor)."""
    from utils import config_manager
    
    roles = ["manager", "planner", "executor"]
    providers = list(SUPPORTED_MODELS.keys())
    
    console.print(Panel(
        "[bold cyan]⚙️ Configure Agent Role Routing[/bold cyan]\n"
        "Set custom models for Planner, Executor, or Base Coordinator roles.",
        border_style="cyan"
    ))
    
    print_separator()
    for idx, role in enumerate(roles, start=1):
        route = config_manager.get_orchestra_route(role)
        console.print(f" [{idx}] [bold magenta]{role.upper()}[/bold magenta] -> Provider: [green]{route['provider']}[/green] | Model: [green]{route['model']}[/green]")
    print_separator()
    
    role_choice = input("Select a Role to modify (1-3) or press Enter to cancel: ").strip()
    if role_choice not in ["1", "2", "3"]:
        return
    selected_role = roles[int(role_choice) - 1]
    
    console.print(f"\nSelect a Provider for [bold cyan]{selected_role.upper()}[/bold cyan]:")
    for idx, prov in enumerate(providers, start=1):
        console.print(f" [{idx}] {prov.upper()}")
        
    prov_choice = input(f"Choose Provider (1-{len(providers)}): ").strip()
    if not prov_choice.isdigit() or not (1 <= int(prov_choice) <= len(providers)):
        return
    selected_prov = providers[int(prov_choice) - 1]
    
    models = SUPPORTED_MODELS[selected_prov]
    console.print(f"\nSelect a Model from [green]{selected_prov.upper()}[/green]:")
    for idx, m in enumerate(models, start=1):
        console.print(f" [{idx}] {m['model']} ({m['desc']})")
        
    model_choice = input(f"Choose Model (1-{len(models)}): ").strip()
    if not model_choice.isdigit() or not (1 <= int(model_choice) <= len(models)):
        return
    selected_model = models[int(model_choice) - 1]["model"]
    
    config_manager.set_orchestra_route(selected_role, selected_prov, selected_model)
    console.print(f"\n🎉 [bold green]Successfully mapped {selected_role.upper()} role to {selected_model} ({selected_prov.upper()})![/bold green]\n")

def search_memories_flow() -> None:
    """Revives your built-in memory query logic, letting users search database context strings."""
    from queries.memory_queries import search_memories
    
    query = input("\n🔍 Enter a search term to scan long-term memories: ").strip()
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
        table.add_row(
            row.get("category", "general").upper(),
            row.get("content", ""),
            row.get("created_at", "")[:10]
        )
    console.print(table)