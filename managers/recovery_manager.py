import logging

logger = logging.getLogger("managers.recovery_manager")

class ExecutionRecoveryManager:
    @staticmethod
    def recover_orphaned_tasks():
        """Scans SQLite tables on startup and updates orphaned 'in_progress' tasks to 'failed'."""
        from database.helper import execute_write
        try:
            tasks_updated = execute_write(
                "UPDATE tasks SET status = 'failed' WHERE status = 'in_progress';"
            )
            subtasks_updated = execute_write(
                "UPDATE sub_tasks SET status = 'failed' WHERE status = 'in_progress';"
            )
            if tasks_updated > 0 or subtasks_updated > 0:
                logger.info(
                    f"Startup State Recovery: Completed cleanup. "
                    f"Recovered {tasks_updated} tasks and {subtasks_updated} sub-tasks."
                )
        except Exception as e:
            logger.error(f"Critical error executing state recovery: {e}")