# FILE: tests/test_context_formatter.py
import unittest
from unittest.mock import patch
from llm.context_formatter import format_context

class TestContextFormatter(unittest.TestCase):
    """Verifies system summaries are mapped to system prompts and messages are formatted correctly."""

    @patch('llm.context_formatter.config_manager.get_system_instruction', return_value=None)
    def test_format_context_standard_message_flow(self, mock_get_inst):
        # Standard user-assistant-tool alternation
        raw_db_messages = [
            {"role": "user", "content": "Verify directories."},
            {"role": "assistant", "content": "Running task.", "tool_calls": [{"name": "read_files", "args": {}}]}
        ]
        
        system_instruction, standardized_messages = format_context(raw_db_messages)
        
        # Verify base system prompt is loaded from DEFAULT fallback
        self.assertIn("You are a highly efficient", system_instruction)
        
        # Verify standardized messages structure
        self.assertEqual(len(standardized_messages), 2)
        self.assertEqual(standardized_messages[0]["role"], "user")
        self.assertEqual(standardized_messages[1]["role"], "assistant")
        self.assertIn("tool_calls", standardized_messages[1])

    @patch('llm.context_formatter.config_manager.get_system_instruction', return_value="CUSTOM INSTRUCTION ACTIVE.")
    def test_format_context_custom_instruction(self, mock_get_inst):
        # Ensures that a custom configuration completely overrides the default
        raw_db_messages = [{"role": "user", "content": "Hi"}]
        system_instruction, _ = format_context(raw_db_messages)
        
        self.assertIn("CUSTOM INSTRUCTION ACTIVE.", system_instruction)
        self.assertNotIn("You are a highly efficient", system_instruction)

    @patch('llm.context_formatter.config_manager.get_system_instruction', return_value=None)
    def test_format_context_extracts_previous_summaries(self, mock_get_inst):
        # If a system role message containing a previous summary exists
        raw_db_messages = [
            {"role": "system", "content": "Workspace project directories initialized."},
            {"role": "user", "content": "List files."}
        ]
        
        system_instruction, standardized_messages = format_context(raw_db_messages)
        
        # Verify summary is safely appended as a header card inside the system instruction
        self.assertIn("[Previous Conversation Summary]\nWorkspace project directories initialized.", system_instruction)
        
        # Verify the raw summary itself is discarded from the messages array
        self.assertEqual(len(standardized_messages), 1)
        self.assertEqual(standardized_messages[0]["role"], "user")

if __name__ == "__main__":
    unittest.main()