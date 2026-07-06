# tests/test_translator.py

import unittest
import json
from unittest.mock import patch
from cli.translator import cli_translator_layer

class TestCliTranslator(unittest.TestCase):

    @patch("cli.translator.log_tool_run")
    @patch("builtins.input")
    def test_layer1_malicious_command_blocked_instantly(self, mock_input, mock_log):
        """Edge Case: Malicious critical-path commands are blocked by the Security Guard. User is NEVER prompted."""
        # rm -rf / is strictly blocked on a critical path
        args = {"command": "rm -rf /"}
        
        output, status = cli_translator_layer("run_terminal_command", args, conversation_id=1)
        
        self.assertEqual(status, "error")
        self.assertIn("Security Guard blocked this command", output)
        self.assertIn("Destructive 'rm' command detected", output)
        
        # Assert user was NOT prompted
        mock_input.assert_not_called()
        # Assert it was logged to the DB as an error
        mock_log.assert_called_once()

    @patch("cli.translator.execute_and_format_tool")
    @patch("cli.translator.log_tool_run")
    @patch("builtins.input", return_value="n")
    def test_layer2_safe_command_user_denies(self, mock_input, mock_log, mock_execute):
        """Edge Case: Safe commands prompt the user. User types 'n' to block."""
        args = {"command": "echo 'hello world'"}
        
        output, status = cli_translator_layer("run_terminal_command", args, conversation_id=1)
        
        self.assertEqual(status, "error")
        self.assertIn("Permission Denied", output)
        self.assertIn("User refused execution", output)
        
        # Assert user WAS prompted
        mock_input.assert_called_once()
        # Assert tool was NEVER executed
        mock_execute.assert_not_called()

    @patch("cli.translator.execute_and_format_tool")
    @patch("builtins.input", return_value="y")
    def test_layer2_safe_command_user_approves(self, mock_input, mock_execute):
        """Normal Flow: Safe commands prompt the user. User types 'y' to execute."""
        mock_execute.return_value = ("hello world", "success")
        args = {"command": "echo 'hello world'"}
        
        output, status = cli_translator_layer("run_terminal_command", args, conversation_id=1)
        
        self.assertEqual(status, "success")
        self.assertEqual(output, "hello world")
        
        mock_input.assert_called_once()
        # Assert execution was delegated back to the unified layer
        mock_execute.assert_called_once_with("run_terminal_command", args, 1)

    @patch("cli.translator.execute_and_format_tool")
    @patch("builtins.input", return_value="y")
    def test_future_unsafe_tool_bypasses_layer1(self, mock_input, mock_execute):
        """
        Future-proofing: If we add a tool like 'git_push' to UNSAFE_TOOLS, 
        it skips the terminal security guard but still asks for user Y/N approval.
        """
        mock_execute.return_value = ("Pushed to main", "success")
        args = {"repo": "main"}
        
        output, status = cli_translator_layer("git_push", args, conversation_id=1)
        
        self.assertEqual(status, "success")
        mock_input.assert_called_once()
        mock_execute.assert_called_once_with("git_push", args, 1)

if __name__ == "__main__":
    unittest.main()