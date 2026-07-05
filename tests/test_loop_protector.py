# tests/test_loop_protector.py
import unittest
import json

from unittest.mock import patch
from llm.loop_protector import check_for_infinite_loop


class TestLoopProtector(unittest.TestCase):

    def setUp(self):
        # Sample tool details
        self.tool_name = "write_files"
        self.tool_args = {"files_json": '[{"path": "test.py", "content": "print(1)"}]'}
        self.serialized_args = json.dumps(self.tool_args, sort_keys=True)

    def test_allow_initial_tool_call(self):
        """Ensures a tool call is allowed to run on its first attempt."""
        tool_call_history = []

        is_looping, loop_error, _ = check_for_infinite_loop(
            tool_call_history, self.tool_name, self.tool_args
        )

        self.assertFalse(is_looping)
        self.assertIsNone(loop_error)

    def test_block_identical_failed_call(self):
        """Safety: Halts execution if a tool already failed 3 times with the exact same parameters."""
        tool_call_history = [
            {
                "name": self.tool_name,
                "args_json": self.serialized_args,
                "status": "error",
            },
            {
                "name": self.tool_name,
                "args_json": self.serialized_args,
                "status": "error",
            },
            {
                "name": self.tool_name,
                "args_json": self.serialized_args,
                "status": "error",
            },
        ]

        is_looping, loop_error, _ = check_for_infinite_loop(
            tool_call_history, self.tool_name, self.tool_args
        )

        self.assertTrue(is_looping)
        self.assertIn("already failed", loop_error)

    def test_block_identical_successful_call(self):
        """Safety: Halts execution if an agent repeatedly requests an already completed successful action 3 times."""
        tool_call_history = [
            {
                "name": self.tool_name,
                "args_json": self.serialized_args,
                "status": "success",
            },
            {
                "name": self.tool_name,
                "args_json": self.serialized_args,
                "status": "success",
            },
            {
                "name": self.tool_name,
                "args_json": self.serialized_args,
                "status": "success",
            },
        ]

        is_looping, loop_error, _ = check_for_infinite_loop(
            tool_call_history, self.tool_name, self.tool_args
        )

        self.assertTrue(is_looping)
        self.assertIn("already succeeded", loop_error)

    def test_allow_different_arguments(self):
        """Verification: Allows identical tools to run if the arguments are different."""
        tool_call_history = [
            {
                "name": self.tool_name,
                "args_json": self.serialized_args,
                "status": "success",
            }
        ]

        # New arguments (different content)
        new_args = {"files_json": '[{"path": "test.py", "content": "print(2)"}]'}

        is_looping, loop_error, _ = check_for_infinite_loop(
            tool_call_history, self.tool_name, new_args
        )

        self.assertFalse(is_looping)
        self.assertIsNone(loop_error)

    @patch("utils.config_manager.get_loop_guard")
    def test_loop_guard_dynamic_fallback(self, mock_get_loop_guard):
        """
        Ensures that if the user configured None, 0, or corrupted data in their config,
        the loop protector automatically falls back to raw defaults (3 failures, 2 successes).
        """
        # Mock the config returning explicit Nones/Zeroes
        mock_get_loop_guard.return_value = {
            "max_failed_attempts": None,
            "max_success_attempts": 0,
        }

        # --- Test Fallback for Failures (Default should be 3) ---
        # 2 failures: Should NOT loop yet
        history_2_fails = [
            {
                "name": self.tool_name,
                "args_json": self.serialized_args,
                "status": "error",
            }
        ] * 2
        is_looping, loop_error, _ = check_for_infinite_loop(
            history_2_fails, self.tool_name, self.tool_args
        )
        self.assertFalse(is_looping)

        # 3 failures: MUST trigger the fallback loop guard
        history_3_fails = [
            {
                "name": self.tool_name,
                "args_json": self.serialized_args,
                "status": "error",
            }
        ] * 3
        is_looping, loop_error, _ = check_for_infinite_loop(
            history_3_fails, self.tool_name, self.tool_args
        )
        self.assertTrue(is_looping)
        self.assertIn("already failed consecutively", loop_error)

        # --- Test Fallback for Successes (Default should be 2) ---
        # 1 success: Should NOT loop yet
        history_1_success = [
            {
                "name": self.tool_name,
                "args_json": self.serialized_args,
                "status": "success",
            }
        ]
        is_looping, loop_error, _ = check_for_infinite_loop(
            history_1_success, self.tool_name, self.tool_args
        )
        self.assertFalse(is_looping)

        # 2 successes: MUST trigger the fallback loop guard
        history_2_successes = [
            {
                "name": self.tool_name,
                "args_json": self.serialized_args,
                "status": "success",
            }
        ] * 2
        is_looping, loop_error, _ = check_for_infinite_loop(
            history_2_successes, self.tool_name, self.tool_args
        )
        self.assertTrue(is_looping)
        self.assertIn("already succeeded consecutively", loop_error)


if __name__ == "__main__":
    unittest.main()
