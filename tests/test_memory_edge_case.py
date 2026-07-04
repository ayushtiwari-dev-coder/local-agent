import unittest
from unittest.mock import patch, MagicMock
from cli.callbacks import cli_tool_approval_callback
from llm.providers.gemini import GeminiProvider
from tools.memory_tools import remember_user_preference

class TestMemoryAndCallbackEdgeCases(unittest.TestCase):

    # --- 1. Callback Edge Cases ---
    @patch('builtins.input', return_value='y')
    def test_callback_unsafe_tool_prompts_user(self, mock_input):
        """Edge Case: Unsafe tools MUST trigger the input prompt."""
        result = cli_tool_approval_callback("run_terminal_command", {"cmd": "rm -rf"})
        mock_input.assert_called_once()
        self.assertTrue(result)

    @patch('builtins.input')
    def test_callback_safe_tool_bypasses_prompt(self, mock_input):
        """Edge Case: Safe tools MUST NOT trigger the input prompt."""
        result = cli_tool_approval_callback("remember_user_preference", {"content": "test"})
        mock_input.assert_not_called()  # Input should never be called
        self.assertTrue(result)

    # --- 2. Provider API Failure Edge Cases ---
    def test_gemini_embedding_api_failure(self):
        """Edge Case: If the Gemini API goes down, it must raise a clean RuntimeError."""
        provider = GeminiProvider(api_key="fake_key", model_name="gemini-3.1-flash-lite")
        
        # Mock the internal client to simulate a 500 Internal Server Error
        provider.client.models.embed_content = MagicMock(side_effect=Exception("500 Internal Server Error"))
        
        with self.assertRaisesRegex(RuntimeError, "Gemini Embedding API failed: 500 Internal Server Error"):
            provider.embed_text(["Test string"])

    # --- 3. Tool Graceful Degradation Edge Case ---
    @patch('tools.memory_tools.save_semantic_memory')
    def test_memory_tool_returns_error_to_llm(self, mock_save):
        """Edge Case: If the manager/provider fails, the tool must return a string to the LLM, NOT crash."""
        # Simulate the RuntimeError bubbling up from the provider
        mock_save.side_effect = RuntimeError("Gemini Embedding API failed: Quota Exceeded")
        
        # Call the tool exactly as the AgentEngine would
        result = remember_user_preference("User likes dark mode", "UI Preferences")
        
        # Verify it returns a string starting with "Error:" so the LLM can read it
        self.assertIsInstance(result, str)
        self.assertTrue(result.startswith("Error: Failed to store memory"))
        self.assertIn("Quota Exceeded", result)

if __name__ == "__main__":
    unittest.main()