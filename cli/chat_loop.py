# cli/chat_loop.py
import sys
import json
import textwrap
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from cli.constants import SEPARATOR, IN_CHAT_HELP, SUPPORTED_MODELS
from cli.callbacks import (
    reset_execution_counters,
    cli_approval_callback,
    cli_status_callback,
)
from engine.agent_engine import AgentEngine
from engine.thinking_configure import supports_thinking
from queries.message_queries import get_messages_by_conversation
from queries.tool_log_queries import get_tool_logs_by_conversation
import utils.config_manager as config_manager
import config_configure.in_chat_config as in_chat_config

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

    for _, _, kind, row in timeline:
        if kind == "message":
            icon = ROLE_ICONS.get(row["role"], row["role"])
            print(f"\n{icon} [{row['created_at']}]")
            print(
                textwrap.fill(
                    row["content"],
                    width=90,
                    initial_indent="  ",
                    subsequent_indent="  ",
                )
            )
        else:
            status_icon = "✅" if row["status"] == "success" else "❌"
            print(
                f"\n  {status_icon} Tool Run: {row['tool_name']} [{row['created_at']}]"
            )
            print(f"    args: {row['arguments']}")
            if row.get("output"):
                print(f"    output: {row['output']}")
            if row.get("error_message"):
                print(f"    error: {row['error_message']}")
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
        status_icon = "✅" if t["status"] == "success" else "❌"
        print(f"\n{status_icon} {t['tool_name']} [{t['created_at']}]")
        print(f"    args: {t['arguments']}")
        if t.get("output"):
            print(f"    output: {t['output']}")
        if t.get("error_message"):
            print(f"    error: {t['error_message']}")
    print()
    print(SEPARATOR)


def search_memories_flow() -> None:
    """Conducts keyword-based searches and displays results."""
    query = input("\nEnter keyword search term to query memories: ").strip()
    res = in_chat_config.search_semantic_memories(query)

    if res["status"] == "error":
        return

    results = res["data"]
    if not results:
        console.print("[yellow]No matching database memories found.[/yellow]")
        return

    table = Table(
        title=f"Memory Search Results for '{query}'",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("Category", style="green", width=15)
    table.add_column("Memory Details", style="white")
    table.add_column("Logged Date", style="dim", width=15)

    for row in results:
        category = row.get("category", "general").upper()
        content = row.get("content", "")
        created = row.get("created_at", "")[:10]
        table.add_row(category, content, created)
    console.print(table)


def cli_stream_callback(text_chunk: str):
    """Streams tokens to the terminal in real-time."""
    sys.stdout.write(text_chunk)
    sys.stdout.flush()


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
        print(f"Initialization Error: {e}")
        return

    print(
        f"\n=== You're in conversation {conversation_id}. Type 'help' for commands. ===\n"
    )
    render_conversation_history(conversation_id)

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
                confirm = (
                    input("Delete current session and exit back to menu? (y/n): ")
                    .strip()
                    .lower()
                )
                if confirm == "y":
                    res = in_chat_config.delete_active_conversation(conversation_id)
                    print(res["message"])
                    if res["status"] == "success":
                        break
                continue
            elif lowered == "/models":
                print(SEPARATOR)
                print(" Model & Parameter Controller")
                print(" [1] Switch Active Model / Provider")
                print(
                    f" [2] Set Model Temperature (Current: {config_manager.get_temperature()})"
                )
                print(SEPARATOR)

                sub_choice = input(" Choose option (1-2): ").strip()
                if sub_choice == "1":
                    print(SEPARATOR)
                    print(" Model Selection Selector")
                    available_providers = list(SUPPORTED_MODELS.keys())
                    for idx, prov in enumerate(available_providers, start=1):
                        print(f" [{idx}] {prov.capitalize()}")
                    print(SEPARATOR)

                    choice = input(" Choose Provider (1-2): ").strip()
                    if choice.isdigit() and 1 <= int(choice) <= len(
                        available_providers
                    ):
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
                            res = in_chat_config.switch_active_model(
                                provider_choice, model_choice
                            )
                            print(f"\n{res['message']}")

                            if res["status"] == "success":
                                engine = AgentEngine(
                                    provider_name=res["data"]["provider"],
                                    model_name=res["data"]["model"],
                                    api_key=res["data"]["api_key"],
                                    autonomous=False,
                                )
                        else:
                            print("\nSelection cancelled or invalid.")
                    else:
                        print(" Invalid selection.")

                elif sub_choice == "2":
                    if (
                        "gemini-3" in model_choice.lower()
                        and "thinking" in config_manager.get_thinking_level().lower()
                    ):
                        print(
                            f"\n[Note] Native reasoning/thinking is currently active on {model_choice}."
                        )
                        print(
                            "Reasoning models typically override manual temperature configurations.\n"
                        )

                    print(
                        " Choose a value between 0.0 (deterministic/coding) and 1.5 (creative/emails)."
                    )
                    val = input(
                        f" New Temperature (Current: {config_manager.get_temperature()}): "
                    ).strip()
                    try:
                        res = in_chat_config.update_temperature(float(val))
                        print(f"\n[{res['status'].capitalize()}] {res['message']}")
                    except ValueError:
                        print(" Invalid input. Please enter a numerical value.")
                continue

            elif lowered == "/thinking":
                if not supports_thinking(model_choice):
                    print(
                        f"\nThe current model [{model_choice}] does not support reasoning/thinking budgets.\n"
                    )
                    continue

                print(
                    f"\nCurrent thinking level: {config_manager.get_thinking_level().upper()}"
                )
                print(" [1] Off (Fastest, standard generation)")
                print(" [2] Low (Light reasoning)")
                print(" [3] Medium (Balanced thought)")
                print(" [4] High (Deepest system analysis)")
                print(SEPARATOR)

                pick = input(" Select thinking level (1-4): ").strip()
                res = in_chat_config.update_thinking_level(pick)
                print(f"\n[{res['status'].capitalize()}] {res['message']}")
                continue
            elif lowered.startswith("/research"):
                query = user_input[len("/research") :].strip()
                if not query:
                    print(
                        " Please provide a research topic. Example: /research quantum computing"
                    )
                    continue

                # Wrap the query in our strict Deep Research directive
                research_directive = f"""{query}

                [SYSTEM DIRECTIVE: DEEP RESEARCH MODE ENGAGED]
                You must act as an exhaustive research analyst. 
                1. You MUST use the `web_researcher` tool to search for information.
                2. You MUST use the `web_researcher` tool with action="read" to extract full text from at least 3 to 5 highly relevant URLs.
                3. You MUST cross-reference the data.
                4. At the very end of your final response, you MUST include a "Sources" section listing all URLs you read."""

                reset_execution_counters()
                response_text = engine.send_message(
                    conversation_id=conversation_id,
                    user_text=research_directive,  # Pass the wrapped directive
                    source="cli",
                    status_callback=cli_status_callback,
                    approval_callback=cli_approval_callback,
                )
                print(f"\n Assistant: {response_text}\n")
                continue

            # --- Standard Message Dispatch ---
            reset_execution_counters()
            response_text = engine.send_message(
                conversation_id=conversation_id,
                user_text=user_input,
                source="cli",
                send_message_callback=cli_stream_callback,
                status_callback=cli_status_callback,
                approval_callback=cli_approval_callback,
            )
            print("\n")

        except Exception as e:
            print(f"Error during execution loop: {e}")
