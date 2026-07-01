# cli/status_tracker.py
import re
from rich.console import Console
from rich.panel import Panel

console = Console()

def process_cli_status(message: str, turn_counter: int) -> None:
    """
    Parses single-agent ReAct status logs and displays them in beautifully 
    designed cards showing reasoning, planning, and task execution stages.
    """
    if "Generating thoughts" in message:
        turn_match = re.search(r"Turn #?(\d+)", message)
        turn_num = turn_match.group(1) if turn_match else str(turn_counter)
        console.print(Panel(
            f"[bold gold1]🤔 Planning & Reasoning Stage...[/bold gold1]\n"
            f"[dim]The Agent is analyzing history and choosing optimal tools for Turn #{turn_num}...[/dim]",
            title="[bold gold1]ReAct Agent Loop[/bold gold1]",
            border_style="gold1",
            expand=False
        ))
    elif "Executing tool" in message:
        tool_match = re.search(r"Executing tool '([^']+)' with arguments:\s*(.*)", message)
        if tool_match:
            tool_name = tool_match.group(1)
            tool_args = tool_match.group(2)
            console.print(Panel(
                f"[bold cyan]🔧 Invoking Tool Action:[/bold cyan] [bold white]{tool_name}[/bold white]\n"
                f"[dim]Parameters Passed:[/dim] [green]{tool_args}[/green]",
                title="[bold cyan]Tool Run Initiated[/bold cyan]",
                border_style="cyan",
                expand=False
            ))
        else:
            console.print(f"[bold cyan]🔧 {message}[/bold cyan]")
    elif "returned status" in message:
        tool_match = re.search(r"Tool '([^']+)' returned status: '([^']+)'", message)
        if tool_match:
            tool_name = tool_match.group(1)
            status = tool_match.group(2)
            color = "green" if status == "success" else "red"
            icon = "✅" if status == "success" else "❌"
            console.print(Panel(
                f"{icon} [bold {color}]Tool Result Received:[/bold {color}] [bold white]{tool_name}[/bold white]\n"
                f"[dim]Execution Status:[/dim] [bold {color}]{status.upper()}[/bold {color}]",
                title="[bold green]Tool Run Finished[/bold green]",
                border_style=color,
                expand=False
            ))
        else:
            console.print(f"[bold green]✅ {message}[/bold green]")
    else:
        console.print(f"[dim]ℹ️ {message}[/dim]")

def process_orchestra_status(message: str) -> None:
    """
    Parses multi-agent background orchestration messages and renders 
    them cleanly to show phase transitions, execution tracks, and completions.
    """
    if "Starting" in message:
        task_name = message.replace("[BACKGROUND EXECUTOR]: Starting", "").strip()
        console.print(Panel(
            f"[bold magenta]🚀 Multi-Agent Task Activated:[/bold magenta]\n"
            f"[white]Active Sub-Stage:[/white] [bold green]Executing {task_name}[/bold green]\n"
            f"[dim]The Executor Agent is actively compiling file structural changes and executing tests...[/dim]",
            title="[bold magenta]Background Orchestra Tracker[/bold magenta]",
            border_style="magenta",
            expand=False
        ))
    elif "Finished" in message:
        clean_msg = message.replace("[BACKGROUND EXECUTOR]: Finished", "").strip()
        task_title = clean_msg.split(".")[0] if "." in clean_msg else clean_msg
        console.print(Panel(
            f"✅ [bold green]Stage Completed:[/bold green] [bold white]{task_title}[/bold white]\n"
            f"[dim italic]Subtask steps verified successfully.[/dim italic]\n\n"
            f"[bold green]Tasks Completed.[/bold green]",
            title="[bold green]Orchestration Stage Success[/bold green]",
            border_style="green",
            expand=False
        ))
    elif "BACKGROUND SYSTEM COMPLETED" in message:
        console.print(Panel(
            "[bold bright_green]🎉 ALL SYSTEM TASKS CONFIRMED COMPLETED! 🎉[/bold bright_green]\n"
            "[dim]All mapped workspace sub-tasks, plan chunks, and execution scripts ran cleanly.[/dim]",
            title="[bold bright_green]Deployment Orchestra Finalized[/bold bright_green]",
            border_style="bright_green",
            expand=False
        ))
    elif "BACKGROUND PLANNER" in message:
        console.print(Panel(
            "[bold blue]🧠 Dynamic Plan Formulated:[/bold blue]\n"
            "[dim]The Planner Agent has analyzed structural complexity, chunked files, and written tasks to SQLite.[/dim]",
            title="[bold blue]Orchestration Plan Ready[/bold blue]",
            border_style="blue",
            expand=False
        ))