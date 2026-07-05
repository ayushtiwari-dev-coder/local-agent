# FILE: tests/test_engine_retry.py
import unittest
from unittest.mock import patch, MagicMock
from llm.generate_with_retry import generate_with_retry


class TestEngineRetry(unittest.TestCase):
    def setUp(self):
        self.mock_request_fn = MagicMock()
        self.mock_is_quota_error_fn = MagicMock()
        self.mock_callback = MagicMock()

    @patch("llm.generate_with_retry.time.sleep")
    def test_success_first_try(self, mock_sleep):
        """Normal scenario: returns immediately on first success."""
        mock_response = MagicMock()
        self.mock_request_fn.return_value = mock_response
        result = generate_with_retry(
            request_fn=self.mock_request_fn,
            is_quota_error_fn=self.mock_is_quota_error_fn,
            status_callback=self.mock_callback,
            max_attempts=3,
        )
        self.assertEqual(result, mock_response)
        self.assertEqual(self.mock_request_fn.call_count, 1)
        mock_sleep.assert_not_called()

    @patch("llm.generate_with_retry.time.sleep")
    def test_exponential_backoff_transient_errors(self, mock_sleep):
        """Edge Case: Fails twice, succeeds on third try. Checks exact sleep scaling."""
        mock_response = MagicMock()
        self.mock_request_fn.side_effect = [
            Exception("503 Service Unavailable"),
            Exception("500 Internal Error"),
            mock_response,
        ]
        self.mock_is_quota_error_fn.return_value = False
        result = generate_with_retry(
            request_fn=self.mock_request_fn,
            is_quota_error_fn=self.mock_is_quota_error_fn,
            status_callback=self.mock_callback,
            max_attempts=3,
        )
        self.assertEqual(result, mock_response)
        self.assertEqual(self.mock_request_fn.call_count, 3)
        mock_sleep.assert_any_call(2.0)
        mock_sleep.assert_any_call(4.0)
        self.assertEqual(mock_sleep.call_count, 2)

    @patch("llm.generate_with_retry.time.sleep")
    def test_429_quota_error_recovery(self, mock_sleep):
        """Edge Case: 429 Quota error triggers an immediate 3x base_delay sleep."""
        mock_response = MagicMock()
        self.mock_request_fn.side_effect = [
            Exception("ResourceExhausted: 429 Quota limit exceeded"),
            mock_response,
        ]
        self.mock_is_quota_error_fn.return_value = True
        result = generate_with_retry(
            request_fn=self.mock_request_fn,
            is_quota_error_fn=self.mock_is_quota_error_fn,
            status_callback=self.mock_callback,
            max_attempts=3,
        )
        self.assertEqual(result, mock_response)
        mock_sleep.assert_called_once_with(6.0)

    @patch("llm.generate_with_retry.time.sleep")
    def test_429_quota_error_fatal(self, mock_sleep):
        """Edge Case: If 429 Quota fails twice, it crashes safely."""
        self.mock_request_fn.side_effect = [
            Exception("ResourceExhausted: 429 Quota limit exceeded"),
            Exception("ResourceExhausted: 429 Quota limit exceeded"),
        ]
        self.mock_is_quota_error_fn.return_value = True
        with self.assertRaisesRegex(RuntimeError, "Daily quota limit has been reached"):
            generate_with_retry(
                request_fn=self.mock_request_fn,
                is_quota_error_fn=self.mock_is_quota_error_fn,
                status_callback=self.mock_callback,
                max_attempts=3,
            )


if __name__ == "__main__":
    unittest.main()
