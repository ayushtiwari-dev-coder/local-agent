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
        "read_files",
        {"paths": ["test.txt"]},
        conversation_id=1,
        autonomous=False,
        approval_callback=mock_callback,
    )

    assert status == "success"
    assert output == "File contents"
    mock_execute.assert_called_once()
    mock_callback.assert_not_called()  # Callback should NOT be triggered



@patch("engine.handle_permissions.execute_and_format_tool")
@patch("engine.handle_permissions.log_tool_run")
def test_unsafe_tool_missing_callback(mock_log, mock_execute):
    """If an unsafe tool is called but no UI callback is provided, it must fail safely."""
    # CHANGED: Use the new unsafe tool 'run_script'
    args = {"language": "python", "filepath": "test.py"}

    output, status = determine_and_execute_tool(
        "run_script",
        args,
        conversation_id=1,
        autonomous=False,
        approval_callback=None,
    )

    assert status == "error"
    assert "no UI callback was provided" in output
    mock_execute.assert_not_called()


@patch("engine.handle_permissions.execute_and_format_tool")
@patch("engine.handle_permissions.log_tool_run")
def test_unsafe_tool_user_approves(mock_log, mock_execute):
    """Normal Flow: User approves via callback, tool executes."""
    mock_execute.return_value = ("hello", "success")
    mock_callback = MagicMock(return_value=True)  # User clicks 'Yes'
    
    # CHANGED: Use the new unsafe tool 'run_script'
    args = {"language": "python", "filepath": "test.py"}

    output, status = determine_and_execute_tool(
        "run_script",
        args,
        conversation_id=1,
        autonomous=False,
        approval_callback=mock_callback,
    )

    assert status == "success"
    assert output == "hello"
    mock_callback.assert_called_once_with("run_script", args, 1)
    mock_execute.assert_called_once()


@patch("engine.handle_permissions.execute_and_format_tool")
@patch("engine.handle_permissions.log_tool_run")
def test_unsafe_tool_user_denies(mock_log, mock_execute):
    """Normal Flow: User denies via callback, execution halts."""
    mock_callback = MagicMock(return_value=False)  # User clicks 'No'
    
    # CHANGED: Use the new unsafe tool 'run_script'
    args = {"language": "python", "filepath": "test.py"}

    output, status = determine_and_execute_tool(
        "run_script",
        args,
        conversation_id=1,
        autonomous=False,
        approval_callback=mock_callback,
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
        "run_script", # CHANGED to run_script
        {"language": "python", "filepath": "test.py"},
        conversation_id=1,
        autonomous=True,
        approval_callback=mock_callback,
    )

    assert status == "success"
    mock_execute.assert_called_once()
    mock_callback.assert_not_called()


@patch("engine.handle_permissions.execute_and_format_tool")
def test_autonomous_mode_bypasses_approval(mock_execute):
    """If autonomous mode is True, even unsafe tools execute immediately."""
    mock_execute.return_value = ("Executed", "success")
    mock_callback = MagicMock()

    output, status = determine_and_execute_tool(
        "run_terminal_command",
        {"command": "ls"},
        conversation_id=1,
        autonomous=True,
        approval_callback=mock_callback,
    )

    assert status == "success"
    mock_execute.assert_called_once()
    mock_callback.assert_not_called()
