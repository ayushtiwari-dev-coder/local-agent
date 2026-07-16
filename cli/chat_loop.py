# cli/chat_loop.py
import sys
import os
import json
import textwrap
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.table import Table
from rich.live import Live
from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import HTML

from cli.constants import SEPARATOR, IN_CHAT_HELP, ROLE_ICONS
from cli.callbacks import reset_execution_counters, cli_approval_callback, cli_status_callback, _stop_spinner
from engine.agent_engine import AgentEngine
from engine.thinking_configure import supports_thinking
from queries.message_queries import get_messages_by_conversation
from queries.tool_log_queries import get_tool_logs_by_conversation
import utils.config_manager as config_manager
import config_configure.in_chat_config as in_chat_config

console = Console()

def render_conversation_history(conversation_id: int) -> None:
    """Reprints the chronological dialog transcript with rich formatting."""
    messages = get_messages_by_conversation(conversation_id)
    
    if not messages:
        console.print("[dim](No messages yet - this conversation is empty.)[/dim]")
        return
        
    for msg in messages:
        if msg["role"] == "user":
            console.print(f"\n[bold cyan]{ROLE_ICONS.get('user', 'You')}:[/bold cyan]\n{msg['content']}")
        elif msg["role"] == "assistant":
            console.print(Panel(Markdown(msg["content"]), title=f"[bold blue]{ROLE_ICONS.get('assistant', 'Agent')}[/bold blue]", border_style="blue", expand=True))

def show_tool_calls_only(conversation_id: int) -> None:
    """Prints tool metrics and logs alone in a clean table format."""
    tool_logs = get_tool_logs_by_conversation(conversation_id)
    
    if not tool_logs:
        console.print(Panel("[dim]No tools have been run in this conversation yet.[/dim]", border_style="yellow"))
        return
        
    table = Table(title=f"Tool Calls for Conversation {conversation_id}", show_header=True, header_style="bold magenta", expand=True)
    table.add_column("Status", width=5)
    table.add_column("Tool Name", style="bold cyan")
    table.add_column("Timestamp", style="dim")
    table.add_column("Details")

    for t in tool_logs:
        status_icon = "✅" if t["status"] == "success" else "❌"
        
        details = f"Args: {t['arguments']}"
        if t.get("output"):
            out = t['output']
            if len(out) > 200:
                out = out[:200] + "... [TRUNCATED]"
            details += f"\nOutput: {out}"
        if t.get("error_message"):
            details += f"\n[red]Error: {t['error_message']}[/red]"
            
        table.add_row(status_icon, t['tool_name'], t['created_at'], details)
        
    console.print(table)

def search_memories_flow() -> None:
    """Conducts keyword-based searches and displays results."""
    from rich.prompt import Prompt
    query = Prompt.ask("\nEnter keyword search term to query memories")
    
    with console.status("[bold yellow]Searching memories...[/bold yellow]"):
        res = in_chat_config.search_semantic_memories(query)
        
    if res["status"] == "error":
        console.print(f"[bold red]Error: {res.get('message', 'Unknown error')}[/bold red]")
        return
        
    results = res["data"]
    if not results:
        console.print("[yellow]No matching database memories found.[/yellow]")
        return
        
    table = Table(title=f"Memory Search Results for '{query}'", show_header=True, header_style="bold cyan", expand=True)
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
            autonomous=False,
        )
    except Exception as e:
        console.print(f"[bold red]Initialization Error: {e}[/bold red]")
        return
        
    os.system('cls' if os.name == 'nt' else 'clear')
    
    header_text = (
        f"[bold green]Conversation ID:[/bold green] {conversation_id} | "
        f"[bold green]Model:[/bold green] {model_choice}\n"
        f"[dim]Type '/help' for commands. Paste code freely. Press Esc followed by Enter to send.[/dim]"
    )
    console.print(Panel(header_text, border_style="green", expand=True))
    
    render_conversation_history(conversation_id)
    
    # Initialize advanced prompt session
    session = PromptSession()
    
    while True:
        try:
            # Multi-line prompt. User presses Esc then Enter to submit.
            user_input = session.prompt(
                HTML("\n<b><ansicyan> 💬 You (Esc + Enter to send): </ansicyan></b>\n"),
                multiline=True
            ).strip()
            
            if not user_input:
                continue
                
            lowered = user_input.lower()
            
            # Simple Commands
            if lowered in {"/exit", "/quit", "exit", "quit"}:
                console.print("[bold yellow]Saving and exiting...[/bold yellow]")
                sys.exit(0)
            elif lowered in {"/menu", "menu"}:
                return
            elif lowered in {"/help", "help"}:
                console.print(Panel(IN_CHAT_HELP, title="Help Menu", border_style="cyan"))
                continue
            elif lowered == "/clear":
                os.system('cls' if os.name == 'nt' else 'clear')
                render_conversation_history(conversation_id)
                continue
            elif lowered in {"/settings", "settings"}:
                # LOCAL IMPORT TO BREAK CIRCULAR DEPENDENCY
                from cli.menu_flows import advanced_settings_flow
                advanced_settings_flow()
                os.system('cls' if os.name == 'nt' else 'clear')
                render_conversation_history(conversation_id)
                continue
            elif lowered in {"/models", "/model", "models"}:
                # LOCAL IMPORT TO BREAK CIRCULAR DEPENDENCY
                from cli.menu_flows import models_configuration_flow
                models_configuration_flow()
                # Re-init engine with new model
                return enter_chat_session(conversation_id)
            elif lowered in {"/tools", "tools"}:
                show_tool_calls_only(conversation_id)
                continue
            elif lowered in {"/history", "history"}:
                render_conversation_history(conversation_id)
                continue
            elif lowered == "/search":
                search_memories_flow()
                continue
            elif lowered == "/delete":
                from rich.prompt import Confirm
                confirm = Confirm.ask("Delete current session and exit back to menu?")
                if confirm:
                    res = in_chat_config.delete_active_conversation(conversation_id)
                    console.print(f"[bold green]{res['message']}[/bold green]")
                    if res["status"] == "success":
                        break
                continue
            elif lowered.startswith("/think"):
                if not supports_thinking(model_choice):
                    console.print(f"\n[yellow]The current model [{model_choice}] does not support reasoning/thinking budgets.[/yellow]\n")
                    continue
                    
                console.print(f"\nCurrent thinking level: [bold]{config_manager.get_thinking_level().upper()}[/bold]")
                from rich.prompt import Prompt
                pick = Prompt.ask("Select thinking level", choices=["1", "2", "3", "4"], default="3")
                res = in_chat_config.update_thinking_level(pick)
                console.print(f"\n[bold green][{res['status'].capitalize()}] {res['message']}[/bold green]")
                continue
            elif lowered.startswith("/research"):
                query = user_input[len("/research") :].strip()
                if not query:
                    console.print("[yellow]Please provide a research topic. Example: /research quantum computing[/yellow]")
                    continue
                    
                # Wrap the query in our strict Deep Research directive
                user_input = f"""{query}

[SYSTEM DIRECTIVE: DEEP RESEARCH MODE ENGAGED]
You must act as an exhaustive research analyst.
1. You MUST use the `web_researcher` tool to search for information.
2. You MUST use the `web_researcher` tool with action="read" to extract full text from at least 3 to 5 highly relevant URLs.
3. You MUST cross-reference the data.
4. At the very end of your final response, you MUST include a "Sources" section listing all URLs you read."""

            # Dispatch to Agent
            reset_execution_counters()
            print() # Spacer
            
            streamed_text = ""
            live_display = None

            def custom_stream_callback(chunk: str):
                nonlocal streamed_text, live_display
                
                # Stop the global spinner from cli_status_callback so it doesn't clash
                _stop_spinner()
                
                streamed_text += chunk
                panel = Panel(
                    Markdown(streamed_text), 
                    title=f"[bold blue]{ROLE_ICONS.get('assistant', 'Agent')}[/bold blue]", 
                    border_style="blue", 
                    expand=True
                )
                
                # Initialize Live display on first chunk
                if live_display is None:
                    live_display = Live(panel, console=console, refresh_per_second=15)
                    live_display.start()
                else:
                    live_display.update(panel)

            try:
                response_text = engine.send_message(
                    conversation_id=conversation_id,
                    user_text=user_input,
                    source="cli",
                    send_message_callback=custom_stream_callback,
                    status_callback=cli_status_callback,
                    approval_callback=cli_approval_callback,
                )
            finally:
                # Ensure the live display is gracefully stopped, leaving the final panel on screen
                if live_display is not None:
                    live_display.stop()
            
            # Fallback if nothing streamed (e.g., instant error return or tool-only execution)
            if live_display is None and response_text:
                console.print(Panel(Markdown(response_text), title=f"[bold blue]{ROLE_ICONS.get('assistant', 'Agent')}[/bold blue]", border_style="blue", expand=True))
            
        except KeyboardInterrupt:
            continue
        except Exception as e:
            console.print(f"[bold red]Error during execution loop: {e}[/bold red]")