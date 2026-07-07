# engine/orchestrator.py
from cli.translator import cli_translator_layer
from engine.telegram_translator import telegram_translator_layer


def unified_translator_layer(
    tool_name: str,
    tool_args: dict,
    conversation_id: int,
    source: str = "cli",
    send_message_callback=None,
) -> tuple[str, str]:
    """
    Routes unsafe tool executions to the correct interface translator.
    """
    if source == "cli":
        return cli_translator_layer(tool_name, tool_args, conversation_id)

    elif source == "telegram":
        return telegram_translator_layer(
            tool_name,
            tool_args,
            conversation_id,
            send_message_callback=send_message_callback,
        )

    elif source == "react":
        # Placeholder for future React WebSocket translator
        return (
            f"Error: React translator not yet implemented for '{tool_name}'.",
            "error",
        )

    else:
        return f"Error: Unknown execution source '{source}'.", "error"
