# tests/test_handle_permissions.py
import pytest
import json
from unittest.mock import patch
from engine.handle_permissions import (
    _detect_tool_error, determine_and_execute_tool, execute_and_format_tool
)



@patch("engine.handle_permissions.execute_and_format_tool")
def test_determine_safe_tool_bypasses_translator(mock_execute):
    """Safe tools (like read_files) should execute instantly. No REQUIRES_APPROVAL."""
    mock_execute.return_value = ("File contents", "success")
    output, status = determine_and_execute_tool(
        "read_files", {"paths": ["test.txt"]}, 1, autonomous=False
    )
    assert status == "success"
    assert output == "File contents"
    mock_execute.assert_called_once()

@patch("engine.handle_permissions.execute_and_format_tool")
def test_determine_unsafe_tool_triggers_approval(mock_execute):
    """Unsafe tools MUST halt execution and return REQUIRES_APPROVAL state."""
    args = {"command": "echo 'hello'"}
    output, status = determine_and_execute_tool(
        "run_terminal_command", args, 1, autonomous=False
    )
    assert status == "REQUIRES_APPROVAL"
    assert output == json.dumps(args)
    mock_execute.assert_not_called()

@patch("engine.handle_permissions.execute_and_format_tool")
def test_autonomous_mode_bypasses_approval(mock_execute):
    """If autonomous mode is True, even unsafe tools execute immediately."""
    mock_execute.return_value = ("Executed", "success")
    output, status = determine_and_execute_tool(
        "run_terminal_command", {"command": "ls"}, 1, autonomous=True
    )
    assert status == "success"
    mock_execute.assert_called_once()



def test_structured_contract_success():
    """Ensures standard dictionary success is parsed correctly."""
    output = {"status": "success", "output": "Command ran fine."}
    has_error = _detect_tool_error("run_terminal_command", output)
    assert has_error is False

def test_structured_contract_error():
    """Ensures standard dictionary errors are caught."""
    output = {"status": "error", "output": "Permission denied."}
    has_error = _detect_tool_error("run_terminal_command", output)
    assert has_error is True

def test_legacy_string_error():
    """Ensures flat strings starting with 'Error:' are caught (used by memory tools)."""
    output = "Error: Failed to store memory due to database lock."
    has_error = _detect_tool_error("remember_user_preference", output)
    assert has_error is True

def test_legacy_string_success():
    """Ensures normal flat strings are treated as success."""
    output = "Memory successfully stored and clustered."
    has_error = _detect_tool_error("remember_user_preference", output)
    assert has_error is False