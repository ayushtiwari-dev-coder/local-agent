# tests/test_handle_permissions.py
import unittest
from engine.handle_permissions import _detect_tool_error


class TestHandlePermissions(unittest.TestCase):

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

    def test_file_tool_partial_errors(self):
        """Edge Case: read_files returns a dict where keys are paths and values are contents/errors."""
        # One file succeeded, one failed. The whole tool run should be flagged as an error.
        output = {
            "good_file.txt": "print('hello')",
            "bad_file.txt": "Error: File not found.",
        }
        has_error = _detect_tool_error("read_files", output)
        self.assertTrue(has_error)


if __name__ == "__main__":
    unittest.main()
