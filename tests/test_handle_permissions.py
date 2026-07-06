# tests/test_handle_permissions.py

import unittest
import json
from unittest.mock import patch
from engine.handle_permissions import (
    _detect_tool_error,
    determine_and_execute_tool,
    execute_and_format_tool
)

class TestHandlePermissions(unittest.TestCase):

    # --- 1. ROUTER TESTS ---

    @patch("engine.handle_permissions.execute_and_format_tool")
    def test_determine_safe_tool_bypasses_translator(self, mock_execute):
        """Safe tools (like read_files) should execute instantly. No REQUIRES_APPROVAL."""
        mock_execute.return_value = ("File contents", "success")
        
        output, status = determine_and_execute_tool("read_files", {"paths": ["test.txt"]}, 1, autonomous=False)
        
        self.assertEqual(status, "success")
        self.assertEqual(output, "File contents")
        mock_execute.assert_called_once()

    @patch("engine.handle_permissions.execute_and_format_tool")
    def test_determine_unsafe_tool_triggers_approval(self, mock_execute):
        """Unsafe tools MUST halt execution and return REQUIRES_APPROVAL state."""
        args = {"command": "echo 'hello'"}
        
        output, status = determine_and_execute_tool("run_terminal_command", args, 1, autonomous=False)
        
        self.assertEqual(status, "REQUIRES_APPROVAL")
        self.assertEqual(output, json.dumps(args))
        # Ensure it did NOT execute
        mock_execute.assert_not_called()

    @patch("engine.handle_permissions.execute_and_format_tool")
    def test_autonomous_mode_bypasses_approval(self, mock_execute):
        """If autonomous mode is True, even unsafe tools execute immediately."""
        mock_execute.return_value = ("Executed", "success")
        
        output, status = determine_and_execute_tool("run_terminal_command", {"command": "ls"}, 1, autonomous=True)
        
        self.assertEqual(status, "success")
        mock_execute.assert_called_once()

    # --- 2. LEGACY ERROR PARSING TESTS ---

    def test_structured_contract_success(self):
        """Ensures standard dictionary success is parsed correctly."""
        output = {"status": "success", "output": "Command ran fine."}
        has_error = _detect_tool_error("run_terminal_command", output)
        self.assertFalse(has_error)

    def test_structured_contract_error(self):
        """Ensures standard dictionary errors are caught."""
        output = {"status": "error", "output": "Permission denied."}
        has_error = _detect_tool_error("run_terminal_command", output)
        self.assertTrue(has_error)

    def test_legacy_string_error(self):
        """Ensures flat strings starting with 'Error:' are caught (used by memory tools)."""
        output = "Error: Failed to store memory due to database lock."
        has_error = _detect_tool_error("remember_user_preference", output)
        self.assertTrue(has_error)

    def test_legacy_string_success(self):
        """Ensures normal flat strings are treated as success."""
        output = "Memory successfully stored and clustered."
        has_error = _detect_tool_error("remember_user_preference", output)
        self.assertFalse(has_error)

if __name__ == "__main__":
    unittest.main()