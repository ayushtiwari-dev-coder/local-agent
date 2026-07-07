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

@patch("interfaces.telegram_bot.create_conversation")
@patch("interfaces.telegram_bot.get_latest_conversation_by_title")
def test_telegram_memory_flow(mock_get_latest_by_title, mock_create, tg_bot_module):
    """ Tests the full memory lifecycle:
    1. First touch (Creates new)
    2. Subsequent touch (Reuses existing)
    3. /clean command (Creates new to reset)
    """
    # --- SCENARIO 1: First Touch (No history exists) ---
    mock_get_latest_by_title.return_value = None
    mock_create.return_value = {"id": 1, "title": "Telegram Chat 111"}
    conv1 = tg_bot_module.get_latest_tg_conversation(111)
    
    mock_create.assert_called_once_with(title="Telegram Chat 111")
    assert conv1["id"] == 1
    
    # --- SCENARIO 2: Subsequent Touch (History exists) ---
    mock_create.reset_mock()
    mock_get_latest_by_title.return_value = {"id": 1, "title": "Telegram Chat 111"}
    conv2 = tg_bot_module.get_latest_tg_conversation(111)
    
    mock_create.assert_not_called()
    assert conv2["id"] == 1
    
    # --- SCENARIO 3: User types /clean ---
    mock_create.reset_mock()
    mock_message = MagicMock()
    mock_message.chat.id = 111
    
    with patch.object(tg_bot_module, 'is_authorized', return_value=True):
        tg_bot_module.handle_clean_command(mock_message)
        
    mock_create.assert_called_once_with(title="Telegram Chat 111")
    assert "Memory cleared" in tg_bot_module.bot.reply_to.call_args[0][1]


# Replace the old test_telegram_send_message_callback_routing with this:
@patch("interfaces.telegram_bot.config_manager.get_default_provider", return_value="gemini")
@patch("interfaces.telegram_bot.config_manager.get_active_model", return_value="gemini-3.1-flash-lite")
@patch("interfaces.telegram_bot.config_manager.get_provider_api_key", return_value="fake_key")
@patch("interfaces.telegram_bot.AgentEngine")
@patch("interfaces.telegram_bot.get_latest_tg_conversation") # <--- CHANGED THIS MOCK
def test_telegram_send_message_callback_routing(mock_get_latest_conv, mock_engine_class, mock_key, mock_model, mock_prov, tg_bot_module):
    """Verifies that the internal callback correctly attaches InlineKeyboards ONLY for Action Required prompts."""
    # Mock the database return value
    mock_get_latest_conv.return_value = {"id": 1}
    
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
    trigger_text = "🚨 *Action Required*" 
    
    internal_callback(1, f"{trigger_text}\nPlease approve.")
    
    # Verify reply_markup was attached
    call_kwargs = tg_bot_module.bot.send_message.call_args[1]
    assert "reply_markup" in call_kwargs, f"Test failed: The text '{trigger_text}' did not trigger the Approve/Deny buttons."
    assert call_kwargs["reply_markup"] is not None



@patch("interfaces.telegram_bot.create_conversation")
@patch("interfaces.telegram_bot.get_latest_conversation_by_title")
def test_telegram_memory_flow(mock_get_latest_by_title, mock_create, tg_bot_module):
    """ Tests the full memory lifecycle:
    1. First touch (Creates new)
    2. Subsequent touch (Reuses existing)
    3. /clean command (Creates new to reset)
    """
    # --- SCENARIO 1: First Touch (No history exists) ---
    mock_get_latest_by_title.return_value = None
    mock_create.return_value = {"id": 1, "title": "Telegram Chat 111"}
    conv1 = tg_bot_module.get_latest_tg_conversation(111)
    
    mock_create.assert_called_once_with(title="Telegram Chat 111")
    assert conv1["id"] == 1
    
    # --- SCENARIO 2: Subsequent Touch (History exists) ---
    mock_create.reset_mock()
    mock_get_latest_by_title.return_value = {"id": 1, "title": "Telegram Chat 111"}
    conv2 = tg_bot_module.get_latest_tg_conversation(111)
    
    mock_create.assert_not_called()
    assert conv2["id"] == 1
    
    # --- SCENARIO 3: User types /clean ---
    mock_create.reset_mock()
    mock_message = MagicMock()
    mock_message.chat.id = 111
    
    with patch.object(tg_bot_module, 'is_authorized', return_value=True):
        tg_bot_module.handle_clean_command(mock_message)
        
    mock_create.assert_called_once_with(title="Telegram Chat 111")
    assert "Memory cleared" in tg_bot_module.bot.reply_to.call_args[0][1]


@patch("config_configure.in_chat_config.switch_active_model")
@patch("config_configure.in_chat_config.update_thinking_level")
@patch("queries.conversation_queries.execute_write", return_value=1)
@patch("queries.conversation_queries.execute_read", return_value={"id": 1, "title": "Telegram Chat 111"})
def test_interactive_menu_command_flows(mock_read, mock_write, mock_update_think, mock_switch_model, tg_bot_module):
    """ Tests that the interactive menu buttons correctly route to the backend functions.
    Patches the source modules and DB executors directly to prevent AttributeErrors and Thread crashes.
    """
    def make_call(data):
        call = MagicMock()
        call.data = data
        call.message.chat.id = 111
        call.message.message_id = 222
        return call
        
    with patch.object(tg_bot_module, 'is_authorized', return_value=True):
        # 1. Test clicking "New Chat" in the menu
        tg_bot_module.handle_config_queries(make_call("tg_cmd_clean"))
        
        # Robustly extract the text argument whether passed as positional or keyword to prevent KeyError
        args, kwargs = tg_bot_module.bot.edit_message_text.call_args
        text_sent = kwargs.get("text") or (args[0] if args else "")
        assert "Memory cleared" in text_sent
        
        # 2. Test clicking a specific Model (e.g., Gemini Flash Lite)
        mock_switch_model.return_value = {"message": "Model switched successfully"}
        tg_bot_module.handle_config_queries(make_call("tg_set_mod_gemini_gemini-3.1-flash-lite"))
        mock_switch_model.assert_called_once_with("gemini", "gemini-3.1-flash-lite")
        
        # 3. Test clicking a Thinking Level (e.g., Low)
        mock_update_think.return_value = {"message": "Thinking updated successfully"}
        tg_bot_module.handle_config_queries(make_call("tg_set_thk_low"))
        mock_update_think.assert_called_once_with("low")