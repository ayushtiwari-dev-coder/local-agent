# FILE: tests/test_engine_retry.py
import unittest
from unittest.mock import patch, MagicMock
from engine.generate_with_retry import generate_with_retry

class TestEngineRetry(unittest.TestCase):
    def setUp(self):
        self.mock_client = MagicMock()
        self.mock_model_name = "gemini-3.1-flash-lite"
        self.messages = [{"role": "user", "parts": [{"text": "Hello"}]}]
        self.mock_config = MagicMock()
        self.mock_callback = MagicMock()

    @patch('engine.generate_with_retry.time.sleep')
    def test_success_first_try(self, mock_sleep):
        """Normal scenario: returns immediately on first success."""
        mock_response = MagicMock()
        mock_response.candidates = [MagicMock()]
        self.mock_client.models.generate_content.return_value = mock_response
        
        result = generate_with_retry(
            self.mock_client, 
            self.mock_model_name, 
            self.messages, 
            self.mock_config, 
            3, 
            self.mock_callback
        )
        
        self.assertEqual(result, mock_response)
        self.assertEqual(self.mock_client.models.generate_content.call_count, 1)
        mock_sleep.assert_not_called()

    @patch('engine.generate_with_retry.time.sleep')
    def test_exponential_backoff_transient_errors(self, mock_sleep):
        """Edge Case: Fails twice, succeeds on third try. Checks exact sleep scaling."""
        mock_response = MagicMock()
        mock_response.candidates = [MagicMock()]
        # 1st: Error, 2nd: Error, 3rd: Success
        self.mock_client.models.generate_content.side_effect = [
            Exception("503 Service Unavailable"), 
            Exception("500 Internal Error"), 
            mock_response
        ]
        
        result = generate_with_retry(
            self.mock_client, 
            self.mock_model_name, 
            self.messages, 
            self.mock_config, 
            3, 
            self.mock_callback
        )
        
        self.assertEqual(result, mock_response)
        self.assertEqual(self.mock_client.models.generate_content.call_count, 3)
        # Attempt 0: sleep(2.0), Attempt 1: sleep(4.0)
        mock_sleep.assert_any_call(2.0)
        mock_sleep.assert_any_call(4.0)
        self.assertEqual(mock_sleep.call_count, 2)

    @patch('engine.generate_with_retry.time.sleep')
    def test_429_quota_error_recovery(self, mock_sleep):
        """Edge Case: 429 Quota error triggers an immediate 3x base_delay sleep."""
        mock_response = MagicMock()
        mock_response.candidates = [MagicMock()]
        self.mock_client.models.generate_content.side_effect = [
            Exception("ResourceExhausted: 429 Quota limit exceeded"), 
            mock_response
        ]
        
        result = generate_with_retry(
            self.mock_client, 
            self.mock_model_name, 
            self.messages, 
            self.mock_config, 
            3, 
            self.mock_callback
        )
        
        self.assertEqual(result, mock_response)
        # Base delay is 2.0. 3x is 6.0
        mock_sleep.assert_called_once_with(6.0)

    @patch('engine.generate_with_retry.time.sleep')
    def test_429_quota_error_fatal(self, mock_sleep):
        """Edge Case: If 429 Quota fails twice, it crashes safely."""
        self.mock_client.models.generate_content.side_effect = [
            Exception("ResourceExhausted: 429 Quota limit exceeded"), 
            Exception("ResourceExhausted: 429 Quota limit exceeded")
        ]
        
        with self.assertRaisesRegex(RuntimeError, "Daily quota limit has been reached"):
            generate_with_retry(
                self.mock_client, 
                self.mock_model_name, 
                self.messages, 
                self.mock_config, 
                3, 
                self.mock_callback
            )

if __name__ == "__main__":
    unittest.main()