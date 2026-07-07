# interfaces/telegram_bot.py
import telebot
import threading
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import utils.config_manager as config_manager
from engine.agent_engine import AgentEngine
from engine.telegram_translator import resolve_telegram_approval
from queries.conversation_queries import create_conversation

# 1. Load Config
tg_config = config_manager.get_telegram_config()
BOT_TOKEN = tg_config.get("bot_token")
ALLOWED_USERS = tg_config.get("allowed_user_ids", [])

if not BOT_TOKEN:
    print("Error: Telegram bot_token is not set in config.json.")
    exit(1)

# Initialize Bot
bot = telebot.TeleBot(BOT_TOKEN)


def is_authorized(update) -> bool:
    """Security check: Only allow whitelisted Telegram User IDs."""
    user_id = update.from_user.id
    if user_id not in ALLOWED_USERS:
        # Safely get chat_id whether it's a Message or a CallbackQuery
        chat_id = (
            update.message.chat.id if hasattr(update, "message") else update.chat.id
        )

        print(f"[SECURITY BLOCK] Unauthorized access attempt from User ID: {user_id}")
        bot.send_message(chat_id, f"🚫 Unauthorized. Your User ID is {user_id}.")
        return False
    return True


def agent_worker_thread(chat_id: int, user_text: str):
    """Runs the AgentEngine in a background thread so the bot stays responsive."""
    # Create or fetch a conversation for this Telegram chat
    # For simplicity, we create a new conversation per message,
    # but you can map chat_id to a specific conversation_id later.
    conv = create_conversation(title=f"Telegram Chat {chat_id}")
    conv_id = conv["id"]

    provider_choice = config_manager.get_default_provider()
    model_choice = config_manager.get_active_model(provider_choice)
    resolved_key = config_manager.get_provider_api_key(provider_choice)

    engine = AgentEngine(
        provider_name=provider_choice,
        model_name=model_choice,
        api_key=resolved_key,
        autonomous=False,
    )

    # Callback to send messages back to Telegram
    def telegram_send_message(c_id, text):
        # If the text asks for approval, attach Yes/No buttons
        if "⚠️ *Action Required*" in text:
            markup = InlineKeyboardMarkup()
            markup.row(
                InlineKeyboardButton("✅ Approve", callback_data=f"approve_{c_id}"),
                InlineKeyboardButton("❌ Deny", callback_data=f"deny_{c_id}"),
            )
            bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=markup)
        else:
            bot.send_message(chat_id, text, parse_mode="Markdown")

    # Callback for live status updates ("Generating thoughts...")
    def telegram_status_callback(status_text):
        # Optional: You can send a temporary message here, or just log it.
        # To avoid spamming Telegram, we will just print it locally for now.
        print(f"[Telegram Status] {status_text}")

    try:
        # Send a typing indicator
        bot.send_chat_action(chat_id, "typing")

        # Run the engine!
        final_response = engine.send_message(
            conversation_id=conv_id,
            user_text=user_text,
            source="telegram",
            send_message_callback=telegram_send_message,
            status_callback=telegram_status_callback,
        )

        # Send the final result back to the user
        bot.send_message(
            chat_id,
            final_response,
        )

    except Exception as e:
        bot.send_message(
            chat_id,
            f"❌ *Error during execution:*\n```text\n{str(e)}\n```",
            parse_mode="Markdown",
        )


@bot.message_handler(commands=["start", "help"])
def send_welcome(message):
    if not is_authorized(message):
        return
    bot.reply_to(message, "👋 Welcome to your Local AI Agent! Send me a task to begin.")


@bot.message_handler(func=lambda message: True)
def handle_all_messages(message):
    if not is_authorized(message):
        return

    # Spawn a thread so the bot can keep listening for approvals/other messages
    threading.Thread(
        target=agent_worker_thread, args=(message.chat.id, message.text), daemon=True
    ).start()


@bot.callback_query_handler(
    func=lambda call: call.data.startswith("approve_") or call.data.startswith("deny_")
)
def handle_approval_query(call):
    """Catches the button clicks for tool approvals."""
    if not is_authorized(call):
        return

    action, conv_id_str = call.data.split("_")
    conv_id = int(conv_id_str)
    approved = action == "approve"

    # Unfreeze the engine thread!
    # Unfreeze the engine thread!
    success = resolve_telegram_approval(conv_id, approved)

    if success:
        # Tell the Telegram UI to stop the loading spinner
        bot.answer_callback_query(call.id, "Action registered.")

        status_text = "✅ *Action Approved*" if approved else "❌ *Action Denied*"
        # Edit the message to remove the buttons so they can't be clicked twice
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=f"{call.message.text}\n\n{status_text}",
        )
    else:
        bot.answer_callback_query(
            call.id, "Error: Approval session expired or not found."
        )


def run_telegram_bot():
    """Starts the Telegram bot polling loop."""
    print("🚀 Starting Telegram Bot (Long Polling)...")
    print("Press Ctrl+C to stop.")
    bot.infinity_polling()


if __name__ == "__main__":
    run_telegram_bot()
