# tests/test_handle_permissions.py
import pytest
import json
from unittest.mock import patch, MagicMock
from engine.handle_permissions import determine_and_execute_tool

@patch("engine.handle_permissions.execute_and_format_tool")
@patch("engine.handle_permissions.log_tool_run")
def test_safe_tool_executes_directly(mock_log, mock_execute):
    """Safe tools (like read_files) should execute instantly without asking for approval."""
    mock_execute.return_value = ("File contents", "success")
    mock_callback = MagicMock()

    output, status = determine_and_execute_tool(
        "read_files", {"paths": ["test.txt"]}, conversation_id=1, autonomous=False, approval_callback=mock_callback
    )

    assert status == "success"
    assert output == "File contents"
    mock_execute.assert_called_once()
    mock_callback.assert_not_called() # Callback should NOT be triggered

@patch("engine.handle_permissions.execute_and_format_tool")
@patch("engine.handle_permissions.log_tool_run")
def test_malicious_command_blocked_instantly(mock_log, mock_execute):
    """Security Guard should block malicious commands BEFORE asking the user."""
    mock_callback = MagicMock()
    args = {"command": "rm -rf /"}

    output, status = determine_and_execute_tool(
        "run_terminal_command", args, conversation_id=1, autonomous=False, approval_callback=mock_callback
    )

    assert status == "error"
    assert "Security Guard blocked this command" in output
    mock_execute.assert_not_called()
    mock_callback.assert_not_called() # User shouldn't even be bothered
    mock_log.assert_called_once()

@patch("engine.handle_permissions.execute_and_format_tool")
@patch("engine.handle_permissions.log_tool_run")
def test_unsafe_tool_missing_callback(mock_log, mock_execute):
    """If an unsafe tool is called but no UI callback is provided, it must fail safely."""
    args = {"command": "echo 'hello'"}

    output, status = determine_and_execute_tool(
        "run_terminal_command", args, conversation_id=1, autonomous=False, approval_callback=None
    )

    assert status == "error"
    assert "no UI callback was provided" in output
    mock_execute.assert_not_called()

@patch("engine.handle_permissions.execute_and_format_tool")
@patch("engine.handle_permissions.log_tool_run")
def test_unsafe_tool_user_approves(mock_log, mock_execute):
    """Normal Flow: User approves via callback, tool executes."""
    mock_execute.return_value = ("hello", "success")
    mock_callback = MagicMock(return_value=True) # User clicks 'Yes'
    args = {"command": "echo 'hello'"}

    output, status = determine_and_execute_tool(
        "run_terminal_command", args, conversation_id=1, autonomous=False, approval_callback=mock_callback
    )

    assert status == "success"
    assert output == "hello"
    mock_callback.assert_called_once_with("run_terminal_command", args, 1)
    mock_execute.assert_called_once()

@patch("engine.handle_permissions.execute_and_format_tool")
@patch("engine.handle_permissions.log_tool_run")
def test_unsafe_tool_user_denies(mock_log, mock_execute):
    """Normal Flow: User denies via callback, execution halts."""
    mock_callback = MagicMock(return_value=False) # User clicks 'No'
    args = {"command": "echo 'hello'"}

    output, status = determine_and_execute_tool(
        "run_terminal_command", args, conversation_id=1, autonomous=False, approval_callback=mock_callback
    )

    assert status == "error"
    assert "Permission Denied" in output
    mock_callback.assert_called_once()
    mock_execute.assert_not_called()

@patch("engine.handle_permissions.execute_and_format_tool")
def test_autonomous_mode_bypasses_approval(mock_execute):
    """If autonomous mode is True, even unsafe tools execute immediately."""
    mock_execute.return_value = ("Executed", "success")
    mock_callback = MagicMock()

    output, status = determine_and_execute_tool(
        "run_terminal_command", {"command": "ls"}, conversation_id=1, autonomous=True, approval_callback=mock_callback
    )

    assert status == "success"
    mock_execute.assert_called_once()
    mock_callback.assert_not_called()