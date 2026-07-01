# tests/test_loop_protector.py
import unittest
import json
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
            tool_call_history, 
            self.tool_name, 
            self.tool_args
        )
        
        self.assertFalse(is_looping)
        self.assertIsNone(loop_error)

    def test_block_identical_failed_call(self):
        """Safety: Halts execution if a tool already failed once with the exact same parameters."""
        tool_call_history = [
            {
                'name': self.tool_name,
                'args_json': self.serialized_args,
                'status': 'error'
            }
        ]
        
        is_looping, loop_error, _ = check_for_infinite_loop(
            tool_call_history, 
            self.tool_name, 
            self.tool_args
        )
        
        self.assertTrue(is_looping)
        self.assertIn("already failed once with these exact params", loop_error)

    def test_block_identical_successful_call(self):
        """Safety: Halts execution if an agent repeatedly requests an already completed successful action."""
        tool_call_history = [
            {
                'name': self.tool_name,
                'args_json': self.serialized_args,
                'status': 'success'
            }
        ]
        
        is_looping, loop_error, _ = check_for_infinite_loop(
            tool_call_history, 
            self.tool_name, 
            self.tool_args
        )
        
        self.assertTrue(is_looping)
        self.assertIn("already succeeded once with these exact params", loop_error)

    def test_allow_different_arguments(self):
        """Verification: Allows identical tools to run if the arguments are different."""
        tool_call_history = [
            {
                'name': self.tool_name,
                'args_json': self.serialized_args,
                'status': 'success'
            }
        ]
        
        # New arguments (different content)
        new_args = {"files_json": '[{"path": "test.py", "content": "print(2)"}]'}
        
        is_looping, loop_error, _ = check_for_infinite_loop(
            tool_call_history, 
            self.tool_name, 
            new_args
        )
        
        self.assertFalse(is_looping)
        self.assertIsNone(loop_error)

if __name__ == "__main__":
    unittest.main()