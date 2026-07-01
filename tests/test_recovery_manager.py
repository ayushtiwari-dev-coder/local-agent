# FILE: tests/test_recovery_manager.py
import unittest
from unittest.mock import patch, MagicMock
from managers.recovery_manager import ExecutionRecoveryManager

class TestRecoveryManager(unittest.TestCase):
    @patch("database.helper.execute_write")  # Changed target to point directly to the source module
    def test_recover_orphaned_tasks_no_active_records(self, mock_execute_write):
        """Verify recovery manager runs without updates if no hanging tasks exist."""
        mock_execute_write.return_value = 0
        ExecutionRecoveryManager.recover_orphaned_tasks()
        self.assertEqual(mock_execute_write.call_count, 2)

    @patch("database.helper.execute_write")  # Changed target to point directly to the source module
    def test_recover_orphaned_tasks_resets_states(self, mock_execute_write):
        """Verify recovery manager logs successful conversions of orphaned database states."""
        mock_execute_write.return_value = 1
        with patch("managers.recovery_manager.logger") as mock_logger:
            ExecutionRecoveryManager.recover_orphaned_tasks()
            mock_logger.info.assert_called_once_with(
                "Startup State Recovery: Completed cleanup. Recovered 1 tasks and 1 sub-tasks."
            )

if __name__ == "__main__":
    unittest.main()