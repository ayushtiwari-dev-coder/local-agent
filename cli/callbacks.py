# cli/callbacks.py
import sys
import time
import json
import random
import os
import ast
from rich.console import Console
from rich.panel import Panel
from rich.status import Status
from rich.syntax import Syntax
from cli.security_rules import UNSAFE_TOOLS

console = Console()

# Observability stats tracker
_api_request_counter = 0
_tool_execution_counter = 0
_spinner = None

THINKING_PHRASES = [
    "Agent is swirling...",
    "Agent is exploring...",
    "Agent is seeing some edge cases...",
    "Analyzing workspace vectors...",
    "Synthesizing context...",
    "Mapping logic pathways...",
    "Evaluating tool parameters...",
]

def reset_execution_counters() -> None:
    """Resets tracking counters for a brand new conversation turn."""
    global _api_request_counter, _tool_execution_counter
    _api_request_counter = 0
    _tool_execution_counter = 0

def _stop_spinner():
    """Helper to safely stop the spinner before printing UI elements."""
    global _spinner
    if _spinner is not None:
        _spinner.stop()
        _spinner = None

def _get_lexer_for_file(path: str) -> str:
    """Helper to determine the rich syntax lexer based on file extension."""
    ext = os.path.splitext(path)[1].replace(".", "").lower() or "text"
    supported_lexers = ["py", "js", "ts", "jsx", "tsx", "html", "css", "json", "md", "sh", "cpp", "c", "java", "rs", "go", "yaml", "xml"]
    return ext if ext in supported_lexers else "text"

def cli_status_callback(message: str) -> None:
    """Renders progress feedback, API transitions, and tool-run outputs."""
    global _api_request_counter, _tool_execution_counter, _spinner

    if "Generating thoughts" in message:
        _api_request_counter += 1
        phrase = random.choice(THINKING_PHRASES)

        if _spinner is None:
            _spinner = console.status(f"[bold cyan]✨ {phrase}[/bold cyan]", spinner="dots")
            _spinner.start()
        else:
            _spinner.update(f"[bold cyan]✨ {phrase}[/bold cyan]")

    elif "Executing tool" in message:
        _stop_spinner()
        _tool_execution_counter += 1

        try:
            parts = message.split("with arguments:\n")
            tool_name = parts[0].replace("Executing tool ", "").strip("' ")
            tool_args_str = parts[1] if len(parts) > 1 else "{}"
            
            # Intelligently parse the stringified Python dict to display code beautifully
            args_dict = None
            try:
                args_dict = ast.literal_eval(tool_args_str)
            except Exception:
                try:
                    args_dict = json.loads(tool_args_str)
                except Exception:
                    pass
            
            if isinstance(args_dict, dict):
                if tool_name == "write_files" and "files" in args_dict:
                    for f in args_dict["files"]:
                        path = f.get("path", "unknown_file")
                        content = f.get("content", "")
                        lexer = _get_lexer_for_file(path)
                        
                        syntax = Syntax(content, lexer, theme="monokai", line_numbers=True, word_wrap=True)
                        console.print(Panel(syntax, title=f"[bold cyan]📝 Writing File: {path}[/bold cyan]", border_style="cyan", expand=False))
                        
                elif tool_name == "edit_file_chunk" and "content" in args_dict:
                    path = args_dict.get("path", "unknown_file")
                    start = args_dict.get("start_line", "?")
                    end = args_dict.get("end_line", "?")
                    content = args_dict.get("content", "")
                    lexer = _get_lexer_for_file(path)
                    
                    # Try to start line numbers at the actual file line number
                    start_num = int(start) if str(start).isdigit() else 1
                    syntax = Syntax(content, lexer, theme="monokai", line_numbers=True, word_wrap=True, start_line=start_num)
                    console.print(Panel(syntax, title=f"[bold cyan]✂️ Editing File: {path} (Lines {start}-{end})[/bold cyan]", border_style="cyan", expand=False))
                    
                elif tool_name == "run_terminal_command" and "cmd" in args_dict:
                    cmd = args_dict.get("cmd", "")
                    syntax = Syntax(cmd, "bash", theme="monokai", line_numbers=False, word_wrap=True)
                    console.print(Panel(syntax, title="[bold green]🖥️ Running Command[/bold green]", border_style="green", expand=False))
                    
                else:
                    # Fallback for standard tools (read_files, search_web, etc.)
                    formatted_json = json.dumps(args_dict, indent=2)
                    syntax = Syntax(formatted_json, "json", theme="monokai", line_numbers=False, word_wrap=True)
                    console.print(Panel(syntax, title=f"[bold yellow]⚙️ Executing: {tool_name}[/bold yellow]", border_style="yellow", expand=False))
            else:
                # Absolute fallback if parsing fails completely
                syntax = Syntax(tool_args_str, "python", theme="monokai", line_numbers=False, word_wrap=True)
                console.print(Panel(syntax, title=f"[bold yellow]⚙️ Executing: {tool_name}[/bold yellow]", border_style="yellow", expand=False))

        except Exception as e:
            console.print(f"[dim yellow]{message}[/dim yellow]")

    elif "finished with status" in message:
        pass  # Silently acknowledge completion to keep UI clean
    else:
        _stop_spinner()
        console.print(f"[dim]System Status: {message}[/dim]")


def cli_stream_callback(text_chunk: str):
    """Streams tokens to the terminal in real-time."""
    _stop_spinner()
    sys.stdout.write(text_chunk)
    sys.stdout.flush()


def cli_approval_callback(tool_name: str, tool_args: dict, conversation_id: int) -> bool:
    """CLI specific approval prompt. Formatted like a code review."""
    _stop_spinner()
    console.print("\n")

    # If it's a file write, show the actual code being written
    if tool_name == "write_files" and "files" in tool_args:
        for f in tool_args["files"]:
            path = f.get("path", "unknown_file")
            content = f.get("content", "")
            lexer = _get_lexer_for_file(path)
            
            syntax = Syntax(content, lexer, theme="monokai", line_numbers=True, word_wrap=True)
            console.print(Panel(syntax, title=f"[bold red]🚨 SECURITY GUARD: REVIEW FILE WRITE ({path}) 🚨[/bold red]", border_style="red", expand=False))
            
    # If it's a file edit, show the chunk being edited
    elif tool_name == "edit_file_chunk" and "content" in tool_args:
        path = tool_args.get("path", "unknown_file")
        start = tool_args.get("start_line", 1)
        end = tool_args.get("end_line", "?")
        content = tool_args.get("content", "")
        lexer = _get_lexer_for_file(path)
        
        start_num = int(start) if str(start).isdigit() else 1
        syntax = Syntax(content, lexer, theme="monokai", line_numbers=True, word_wrap=True, start_line=start_num)
        console.print(Panel(syntax, title=f"[bold red]🚨 SECURITY GUARD: REVIEW FILE EDIT ({path} Lines {start}-{end}) 🚨[/bold red]", border_style="red", expand=False))
        
    # If it's a terminal command, highlight it as bash
    elif tool_name == "run_terminal_command" and "cmd" in tool_args:
        syntax = Syntax(tool_args["cmd"], "bash", theme="monokai", word_wrap=True)
        console.print(Panel(syntax, title="[bold red]🚨 SECURITY GUARD: REVIEW COMMAND 🚨[/bold red]", border_style="red", expand=False))
        
    # Standard fallback for other tools
    else:
        args_str = json.dumps(tool_args, indent=2)
        syntax = Syntax(args_str, "json", theme="monokai", word_wrap=True)
        console.print(Panel(syntax, title=f"[bold red]🚨 SECURITY GUARD: APPROVAL REQUIRED FOR `{tool_name}` 🚨[/bold red]", border_style="red", expand=False))

    console.print("[bold white]Allow this action? (y/N)[/bold white]")
    choice = input(" > ").strip().lower()
    return choice == "y"