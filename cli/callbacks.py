# cli/callbacks.py
import time
from rich.console import Console
from rich.panel import Panel
from cli.security_rules import UNSAFE_TOOLS
import json

console = Console()

# Observability stats tracker
_api_request_counter = 0
_tool_execution_counter = 0


def reset_execution_counters() -> None:
    """Resets tracking counters for a brand new conversation turn."""
    global _api_request_counter, _tool_execution_counter
    _api_request_counter = 0
    _tool_execution_counter = 0


def cli_approval_callback(
    tool_name: str, tool_args: dict, conversation_id: int
) -> bool:
    """CLI specific approval prompt. Freezes terminal via input()."""
    print(f"\n [🚨 CRUCIAL ACTION REQUESTED] -> {tool_name}")
    print(f" Parameters: {json.dumps(tool_args, indent=2)}")
    choice = input(" Allow this action? (y/n): ").strip().lower()
    return choice == "y"


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
                max_tokens=1,
            )
            return True
    except Exception as e:
        print(f"\n Validation failed: {e}")
        return False
    return False


def cli_status_callback(message: str) -> None:
    """Renders progress feedback, API transitions, and tool-run outputs."""
    global _api_request_counter, _tool_execution_counter

    # Capture Single-Agent ReAct loop status maps only
    if "Generating thoughts" in message:
        _api_request_counter += 1
        console.print(
            Panel(
                f"[bold gold1] Planning & Reasoning Stage...[/bold gold1]\n"
                f"[dim]Analyzing execution logs and choosing optimal tools (API Turn #{_api_request_counter})...[/dim]\n"
                f"[dim cyan]Session Stats: {_api_request_counter} API requests | {_tool_execution_counter} tools run[/dim cyan]",
                title="[bold gold1]ReAct Agent Loop[/bold gold1]",
                border_style="gold1",
                expand=False,
            )
        )
        time.sleep(1.0)
    elif "Executing tool" in message:
        _tool_execution_counter += 1
        print(f" [Orchestra Tool Run] {message}")
    elif "finished with status" in message:
        print(f" [Orchestra Tool Output] {message}")
    else:
        print(f" [System Status] {message}")
