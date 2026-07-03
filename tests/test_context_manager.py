# FILE: tests/test_context_manager.py
import unittest
from unittest.mock import patch
from managers.conversation_manager import _estimate_tokens
from managers.conversation_manager import compile_llm_context

class TestContextManager(unittest.TestCase):

    def test_estimate_tokens_with_tiktoken(self):
        """Ensures tiktoken counts tokens correctly when available."""
        messages = [
            {"content": "Hello, how are you?"},
            {"content": "I am fine, thank you."}
        ]
        # Should accurately estimate tokens (approx 10-15 tokens depending on cl100k_base)
        tokens = _estimate_tokens(messages)
        self.assertGreater(tokens, 5)
        self.assertLess(tokens, 20)

    @patch('managers.conversation_manager.tiktoken.get_encoding')
    def test_estimate_tokens_fallback(self, mock_tiktoken):
        """Edge Case: If tiktoken is unavailable, fallback character math (len/4) is used."""
        mock_tiktoken.side_effect = Exception("Offline/Module Not Found")
        
        # Total chars: 20 chars + 20 chars = 40 chars. 40 // 4 = 10 tokens
        messages = [
            {"content": "A" * 20},
            {"content": "B" * 20}
        ]
        tokens = _estimate_tokens(messages)
        self.assertEqual(tokens, 10)

    @patch('managers.conversation_manager.get_connection')
    @patch('managers.conversation_manager._estimate_tokens')
    def test_compile_llm_context_trimming(self, mock_estimate, mock_conn):
        """Edge case: Context manager discards index 1 when breaching MAX_CONTEXT_TOKENS."""
        
        
        # Mock database rows containing 3 messages
        mock_cursor = mock_conn.return_value.execute.return_value
        mock_cursor.fetchone.return_value = None # No summary exists
        mock_cursor.fetchall.return_value = [
            {"role": "user", "content": "Msg 1"},
            {"role": "assistant", "content": "Msg 2"},
            {"role": "user", "content": "Msg 3"}
        ]
        
        # Fake token sizes: 1st loop: 1500 tokens (over budget). 2nd loop: 900 tokens (under budget)
        mock_estimate.side_effect = [1500, 900]
        
        # Set max tokens extremely low for the test
        result = compile_llm_context(conversation_id=1, max_tokens=1000)
        
        # Should have trimmed the oldest message (Msg 1)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["content"], "Msg 1")
        self.assertEqual(result[1]["content"], "Msg 3")

    @patch('managers.conversation_manager.get_connection')
    @patch('managers.conversation_manager._estimate_tokens')
    def test_compile_llm_context_preserves_summary_at_index_0(self, mock_estimate, mock_conn):
        # Mock connection and cursor executions
        mock_cursor = mock_conn.return_value.execute.return_value
        
        # 1. First DB query returns a summary record
        mock_cursor.fetchone.side_effect = [
            {"summary_text": "This is the summary.", "last_summarized_message_id": 10},
        ]
        
        # 2. Second DB query returns subsequent raw messages (ID > 10)
        mock_cursor.fetchall.return_value = [
            {"role": "user", "content": "Msg 11"},
            {"role": "assistant", "content": "Msg 12"},
            {"role": "user", "content": "Msg 13"}
        ]
        
        # Mock token estimations to trigger trimming:
        # Loop 1: 1500 tokens (triggers trim)
        # Loop 2: 900 tokens (falls under the 1000 limit)
        mock_estimate.side_effect = [1500, 900]
        
        # Compile context with a narrow token budget
        result = compile_llm_context(conversation_id=1, max_tokens=1000)
        
       
        self.assertEqual(len(result), 3)
        self.assertEqual(result[0]["role"], "system")
        self.assertEqual(result[1]["content"], "Msg 11")
        self.assertEqual(result[2]["content"], "Msg 13")

if __name__ == "__main__":
    unittest.main()