# tests/test_telegram_bot.py
import pytest
import sys
from unittest.mock import patch, MagicMock

@pytest.fixture(scope="module", autouse=True)
def setup_telegram_mocks():
    """Mocks the config and TeleBot class before the module is imported."""
    with patch("utils.config_manager.get_telegram_config") as mock_config, \
         patch("telebot.TeleBot") as mock_telebot:
        
        # Provide a valid-looking token to bypass telebot's internal regex/colon checks
        mock_config.return_value = {
            "bot_token": "123456789:fake_test_token",
            "allowed_user_ids": [12345]
        }
        
        # Create a mock bot that PRESERVES decorated functions instead of eating them
        mock_bot_instance = MagicMock()
        def preserve_func(*args, **kwargs):
            return lambda func: func
            
        mock_bot_instance.message_handler.side_effect = preserve_func
        mock_bot_instance.callback_query_handler.side_effect = preserve_func
        mock_telebot.return_value = mock_bot_instance
        
        # Force reload the module so the patches apply cleanly
        if "interfaces.telegram_bot" in sys.modules:
            del sys.modules["interfaces.telegram_bot"]
            
        import interfaces.telegram_bot
        yield interfaces.telegram_bot

@pytest.fixture
def tg_bot_module():
    """Provides the telegram_bot module and resets the mock bot for each test."""
    import interfaces.telegram_bot as tg_bot
    tg_bot.bot.reset_mock()
    return tg_bot

def test_is_authorized_success(tg_bot_module):
    """Normal Flow: Whitelisted user is allowed."""
    mock_update = MagicMock()
    mock_update.from_user.id = 12345
    assert tg_bot_module.is_authorized(mock_update) is True

def test_is_authorized_failure(tg_bot_module):
    """Security: Non-whitelisted user is blocked and alerted."""
    mock_update = MagicMock()
    mock_update.from_user.id = 99999
    mock_update.message.chat.id = 111
    
    assert tg_bot_module.is_authorized(mock_update) is False
    tg_bot_module.bot.send_message.assert_called_once_with(111, "🚫 Unauthorized. Your User ID is 99999.")

@patch("interfaces.telegram_bot.resolve_telegram_approval")
def test_handle_approval_query_success(mock_resolve, tg_bot_module):
    """Normal Flow: User clicks 'Approve' button."""
    mock_resolve.return_value = True
    
    mock_call = MagicMock()
    mock_call.from_user.id = 12345
    mock_call.data = "approve_42"
    mock_call.id = "query_1"
    mock_call.message.chat.id = 111
    mock_call.message.message_id = 222
    mock_call.message.text = "Original message text"
    
    tg_bot_module.handle_approval_query(mock_call)
    
    mock_resolve.assert_called_once_with(42, True)
    tg_bot_module.bot.answer_callback_query.assert_called_once_with("query_1", "Action registered.")
    tg_bot_module.bot.edit_message_text.assert_called_once()
    
    # Verify the text was updated to show approval
    kwargs = tg_bot_module.bot.edit_message_text.call_args[1]
    assert "Action Approved" in kwargs["text"]
    assert kwargs["chat_id"] == 111
    assert kwargs["message_id"] == 222

@patch("interfaces.telegram_bot.resolve_telegram_approval")
def test_handle_approval_query_expired(mock_resolve, tg_bot_module):
    """Edge Case: User clicks a button for a session that already timed out."""
    mock_resolve.return_value = False
    
    mock_call = MagicMock()
    mock_call.from_user.id = 12345
    mock_call.data = "deny_42"
    mock_call.id = "query_1"
    
    tg_bot_module.handle_approval_query(mock_call)
    
    tg_bot_module.bot.answer_callback_query.assert_called_once_with(
        "query_1", "Error: Approval session expired or not found."
    )

# Mock the config calls so AgentEngine doesn't crash from missing API keys during the test
@patch("interfaces.telegram_bot.config_manager.get_default_provider", return_value="gemini")
@patch("interfaces.telegram_bot.config_manager.get_active_model", return_value="gemini-3.1-flash-lite")
@patch("interfaces.telegram_bot.config_manager.get_provider_api_key", return_value="fake_key")
@patch("interfaces.telegram_bot.AgentEngine")
@patch("interfaces.telegram_bot.create_conversation")
def test_agent_worker_thread_markdown_crash_fallback(mock_create_conv, mock_engine_class, mock_key, mock_model, mock_prov, tg_bot_module):
    """
    API Edge Case: If the LLM outputs broken Markdown (e.g. unclosed code blocks), 
    the Telegram API throws an error. The bot MUST catch this and send a raw text fallback.
    """
    mock_create_conv.return_value = {"id": 1}
    
    mock_engine_instance = MagicMock()
    mock_engine_instance.send_message.return_value = "Here is your code: ```python print('broken"
    mock_engine_class.return_value = mock_engine_instance
    
    def send_message_side_effect(chat_id, text, **kwargs):
        if "Here is your code" in text:
            raise Exception("Bad Request: can't parse entities")
    
    tg_bot_module.bot.send_message.side_effect = send_message_side_effect
    
    tg_bot_module.agent_worker_thread(chat_id=111, user_text="Write me a script")
    
    assert tg_bot_module.bot.send_message.call_count == 2
    
    # Extract the text from the SECOND call (the fallback). 
    # Text is passed as the 2nd positional argument: bot.send_message(chat_id, text)
    fallback_text = tg_bot_module.bot.send_message.call_args[0][1]
    
    assert "Error during execution" in fallback_text
    assert "Bad Request: can't parse entities" in fallback_text

@patch("interfaces.telegram_bot.config_manager.get_default_provider", return_value="gemini")
@patch("interfaces.telegram_bot.config_manager.get_active_model", return_value="gemini-3.1-flash-lite")
@patch("interfaces.telegram_bot.config_manager.get_provider_api_key", return_value="fake_key")
@patch("interfaces.telegram_bot.AgentEngine")
@patch("interfaces.telegram_bot.create_conversation")
def test_telegram_send_message_callback_routing(mock_create_conv, mock_engine_class, mock_key, mock_model, mock_prov, tg_bot_module):
    """Verifies that the internal callback correctly attaches InlineKeyboards ONLY for Action Required prompts."""
    mock_create_conv.return_value = {"id": 1}
    
    # Grab the mock engine instance that will be returned
    engine_mock = mock_engine_class.return_value
    
    # Run the thread to initialize the internal functions
    tg_bot_module.agent_worker_thread(chat_id=111, user_text="Hello")
    
    # Extract the internal callback function that was passed to the engine
    send_msg_kwargs = engine_mock.send_message.call_args[1]
    internal_callback = send_msg_kwargs["send_message_callback"]
    
    # 1. Test normal message
    internal_callback(1, "Just a normal status update")
    tg_bot_module.bot.send_message.assert_called_with(111, "Just a normal status update", parse_mode="Markdown")
    
    # 2. Test Action Required message
    # NOTE: This string MUST match the exact string/emoji in your telegram_bot.py `if` statement!
    trigger_text = "🚨 *Action Required*" 
    
    internal_callback(1, f"{trigger_text}\nPlease approve.")
    
    # Verify reply_markup was attached
    call_kwargs = tg_bot_module.bot.send_message.call_args[1]
    assert "reply_markup" in call_kwargs, f"Test failed: The text '{trigger_text}' did not trigger the Yes/No buttons."
    assert call_kwargs["reply_markup"] is not None