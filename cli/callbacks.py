# cli/callbacks.py
import time
from rich.console import Console
from rich.panel import Panel

console = Console()

# Observability stats tracker
_api_request_counter = 0
_tool_execution_counter = 0

def reset_execution_counters() -> None:
    """Resets tracking counters for a brand new conversation turn."""
    global _api_request_counter, _tool_execution_counter
    _api_request_counter = 0
    _tool_execution_counter = 0

def cli_tool_approval_callback(tool_name: str, arguments: dict) -> bool:
    """Supervised Permission Check: Halts execution to ask the user for authorization."""
    print(f"\n🔑 [AI Requests Tool Run] -> {tool_name}")
    print(f"   Parameters: {arguments}")
    choice = input("   Allow this action? (y/n): ").strip().lower()
    return choice == "y"

def validate_api_key(provider: str, key: str) -> bool:
    """Attempts a quick, lightweight request using the SDK client to validate key permissions."""
    print("\n   Validating API key... Please wait.")
    try:
        if provider == "gemini":
            from google import genai
            client = genai.Client(api_key=key)
            client.models.generate_content(
                model="gemini-3.1-flash-lite", 
                contents="test validation key"
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
        print(f"\n   Validation failed: {e}")
        return False
    return False

def cli_status_callback(message: str) -> None:
    """Renders progress feedback, API transitions, and tool-run outputs."""
    global _api_request_counter, _tool_execution_counter

    # 1. Capture Orchestrator (Multi-Agent Background) Transitions
    if any(tag in message for tag in ["[BACKGROUND", "BACKGROUND SYSTEM", "BACKGROUND PLANNER"]):
        if "Starting" in message:
            task_name = message.replace("[BACKGROUND EXECUTOR]: Starting", "").strip()
            console.print(Panel(
                f"[bold magenta]🚀 Multi-Agent Task Activated:[/bold magenta] Executing {task_name}\n"
                f"[dim]The Executor Agent is actively compiling workspace changes...[/dim]",
                title="[bold magenta]Background Orchestra[/bold magenta]", border_style="magenta", expand=False
            ))
        elif "Finished" in message:
            clean_msg = message.replace("[BACKGROUND EXECUTOR]: Finished", "").strip()
            task_title = clean_msg.split(".")[0] if "." in clean_msg else clean_msg
            console.print(Panel(
                f"✅ [bold green]Stage Completed:[/bold green] [bold white]{task_title}[/bold white]\n"
                f"[dim]Subtask steps verified successfully.[/dim]",
                title="[bold green]Orchestration Success[/bold green]", border_style="green", expand=False
            ))
        elif "BACKGROUND SYSTEM COMPLETED" in message:
            console.print(Panel(
                "[bold bright_green]🎉 ALL WORKSPACE TASKS COMPLETED SUCCESSFULLY! 🎉[/bold bright_green]\n"
                "[dim]All planned workspace scripts, files, and updates executed cleanly.[/dim]",
                title="[bold bright_green]Deployment Orchestra Finalized[/bold bright_green]", border_style="bright_green", expand=False
            ))
        elif "BACKGROUND PLANNER" in message:
            console.print(Panel(
                "[bold blue]🧠 Dynamic Plan Formulated:[/bold blue]\n"
                "[dim]The Planner Agent has analyzed structural complexity and written chunk tasks to database.[/dim]",
                title="[bold blue]Orchestration Plan Ready[/bold blue]", border_style="blue", expand=False
            ))
        else:
            print(f"\n⚙️ [Background Orchestra] {message}")
        return

    # 2. Capture Single-Agent ReAct loop status maps
    if "Generating thoughts" in message:
        _api_request_counter += 1
        console.print(Panel(
            f"[bold gold1]🤔 Planning & Reasoning Stage...[/bold gold1]\n"
            f"[dim]Analyzing execution logs and choosing optimal tools (API Turn #{_api_request_counter})...[/dim]\n"
            f"[dim cyan]Session Stats: {_api_request_counter} API requests | {_tool_execution_counter} tools run[/dim cyan]",
            title="[bold gold1]ReAct Agent Loop[/bold gold1]", border_style="gold1", expand=False
        ))
        time.sleep(1.0)
    elif "Executing tool" in message:
        _tool_execution_counter += 1
        print(f"🛠️ [Orchestra Tool Run] {message}")
    elif "finished with status" in message:
        print(f"✅ [Orchestra Tool Output] {message}")
    else:
        print(f"ℹ️ [System Status] {message}")