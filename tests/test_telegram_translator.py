# tests/test_telegram_translator.py
import pytest
import json
import threading
from unittest.mock import patch, MagicMock
from engine.telegram_translator import (
    telegram_translator_layer,
    resolve_telegram_approval,
    active_approvals
)

@pytest.fixture(autouse=True)
def cleanup_approvals():
    """Ensure the global active_approvals dict is clean before each test."""
    active_approvals.clear()
    yield
    active_approvals.clear()

@patch("engine.telegram_translator.log_tool_run")
@patch("engine.telegram_translator.check_command_safety")
def test_layer1_security_intercept(mock_check_safety, mock_log_tool):
    """Edge Case: Malicious commands should be blocked instantly without freezing the thread."""
    # Simulate a malicious command
    mock_check_safety.return_value = (False, "Destructive 'rm' command detected")
    mock_callback = MagicMock()
    
    args = {"command": "rm -rf /"}
    output, status = telegram_translator_layer(
        "run_terminal_command", args, conversation_id=1, send_message_callback=mock_callback
    )
    
    assert status == "error"
    assert "Security Guard blocked this command" in output
    
    # Verify the user was alerted via Telegram callback
    mock_callback.assert_called_once()
    alert_text = mock_callback.call_args[0][1]
    assert "SECURITY INTERCEPT" in alert_text
    assert "Destructive 'rm' command detected" in alert_text
    
    # Verify it was logged
    mock_log_tool.assert_called_once()

@patch("engine.telegram_translator.threading.Event.wait")
@patch("engine.telegram_translator.log_tool_run")
@patch("engine.telegram_translator.check_command_safety")
def test_approval_timeout(mock_check_safety, mock_log_tool, mock_wait):
    """Edge Case: If the user doesn't click approve/deny within 5 minutes, it should timeout."""
    mock_check_safety.return_value = (True, None)
    mock_wait.return_value = False  # Simulate timeout
    
    output, status = telegram_translator_layer(
        "run_terminal_command", {"command": "ls"}, conversation_id=1
    )
    
    assert status == "error"
    assert "Approval timed out" in output
    mock_log_tool.assert_called_once()

@patch("engine.telegram_translator.execute_and_format_tool")
@patch("engine.telegram_translator.threading.Event.wait")
@patch("engine.telegram_translator.check_command_safety")
def test_user_approves_execution(mock_check_safety, mock_wait, mock_execute):
    """Normal Flow: User clicks approve, tool executes."""
    mock_check_safety.return_value = (True, None)
    mock_execute.return_value = ("Command output", "success")
    
    # Simulate the webhook resolving the approval while the thread is waiting
    def side_effect_wait(*args, **kwargs):
        resolve_telegram_approval(1, approved=True)
        return True
    
    mock_wait.side_effect = side_effect_wait
    
    output, status = telegram_translator_layer(
        "run_terminal_command", {"command": "ls"}, conversation_id=1
    )
    
    assert status == "success"
    assert output == "Command output"
    mock_execute.assert_called_once_with("run_terminal_command", {"command": "ls"}, 1)

@patch("engine.telegram_translator.log_tool_run")
@patch("engine.telegram_translator.threading.Event.wait")
@patch("engine.telegram_translator.check_command_safety")
def test_user_denies_execution(mock_check_safety, mock_wait, mock_log_tool):
    """Normal Flow: User clicks deny, execution halts."""
    mock_check_safety.return_value = (True, None)
    
    def side_effect_wait(*args, **kwargs):
        resolve_telegram_approval(1, approved=False)
        return True
    
    mock_wait.side_effect = side_effect_wait
    
    output, status = telegram_translator_layer(
        "run_terminal_command", {"command": "ls"}, conversation_id=1
    )
    
    assert status == "error"
    assert "Permission Denied" in output
    mock_log_tool.assert_called_once()

def test_resolve_telegram_approval_invalid_id():
    """Edge Case: Webhook receives an approval for an expired or invalid conversation ID."""
    # active_approvals is empty
    result = resolve_telegram_approval(999, True)
    assert result is False