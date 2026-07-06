# tests/test_translator.py
import pytest
from unittest.mock import patch
from cli.translator import cli_translator_layer

@patch("cli.translator.log_tool_run")
@patch("builtins.input")
def test_layer1_malicious_command_blocked_instantly(mock_input, mock_log):
    """Edge Case: Block harmful shell command execution immediately without alerting user."""
    args = {"command": "rm -rf /"}
    output, status = cli_translator_layer("run_terminal_command", args, conversation_id=1)
    
    assert status == "error"
    assert "Security Guard blocked this command" in output
    assert "Destructive 'rm' command detected" in output
    mock_input.assert_not_called()
    mock_log.assert_called_once()

@patch("cli.translator.execute_and_format_tool")
@patch("cli.translator.log_tool_run")
@patch("builtins.input", return_value="n")
def test_layer2_safe_command_user_denies(mock_input, mock_log, mock_execute):
    """Edge Case: Prompt the user for approval. If denied, stop execution."""
    args = {"command": "echo 'hello world'"}
    output, status = cli_translator_layer("run_terminal_command", args, conversation_id=1)
    
    assert status == "error"
    assert "Permission Denied" in output
    assert "User refused execution" in output
    mock_input.assert_called_once()
    mock_execute.assert_not_called()

@patch("cli.translator.execute_and_format_tool")
@patch("builtins.input", return_value="y")
def test_layer2_safe_command_user_approves(mock_input, mock_execute):
    """Normal flow: Prompt the user for permission. If approved, execute command."""
    mock_execute.return_value = ("hello world", "success")
    args = {"command": "echo 'hello world'"}
    output, status = cli_translator_layer("run_terminal_command", args, conversation_id=1)
    
    assert status == "success"
    assert output == "hello world"
    mock_input.assert_called_once()
    mock_execute.assert_called_once_with("run_terminal_command", args, 1)

@patch("cli.translator.execute_and_format_tool")
@patch("builtins.input", return_value="y")
def test_future_unsafe_tool_bypasses_layer1(mock_input, mock_execute):
    """Future-proofing: Custom unsafe tools bypass Layer 1 filters but still ask user approval."""
    mock_execute.return_value = ("Pushed to main", "success")
    args = {"repo": "main"}
    output, status = cli_translator_layer("git_push", args, conversation_id=1)
    
    assert status == "success"
    mock_input.assert_called_once()
    mock_execute.assert_called_once_with("git_push", args, 1)