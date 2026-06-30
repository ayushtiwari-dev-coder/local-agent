# queries/subtask_queries.py
import sqlite3
from database.helper import execute_read, execute_write

def create_sub_task(task_id: int, description: str) -> dict:
    """
    Creates a new granular sub-task step linked to a parent chunk task.
    """
    query = "INSERT INTO sub_tasks (task_id, description) VALUES (?, ?);"
    sub_task_id = execute_write(query, (task_id, description.strip()))
    return get_sub_task_by_id(sub_task_id)

def get_sub_task_by_id(sub_task_id: int) -> dict:
    """
    Retrieves a single sub-task record by its ID.
    """
    query = "SELECT id, task_id, description, status, created_at, completed_at FROM sub_tasks WHERE id = ?;"
    sub_task = execute_read(query, (sub_task_id,), fetch_one=True)
    if sub_task is None:
        raise ValueError(f"Sub-task with ID {sub_task_id} not found.")
    return sub_task

def get_sub_tasks_by_task(task_id: int) -> list[dict]:
    """
    Retrieves all sub-tasks linked to a specific parent chunk task.
    """
    query = "SELECT id, task_id, description, status, created_at, completed_at FROM sub_tasks WHERE task_id = ? ORDER BY id ASC;"
    return execute_read(query, (task_id,))

def update_sub_task_status(sub_task_id: int, status: str) -> dict:
    """
    Updates status and automatically controls the completed_at timestamp.
    """
    valid_statuses = {"pending", "in_progress", "completed", "failed"}
    if status not in valid_statuses:
        raise ValueError(f"Invalid status '{status}'. Must be one of {valid_statuses}")
        
    query = """
        UPDATE sub_tasks
        SET status = ?, 
            completed_at = CASE WHEN ? = 'completed' THEN CURRENT_TIMESTAMP ELSE NULL END
        WHERE id = ?;
    """
    rows_affected = execute_write(query, (status, status, sub_task_id))
    if rows_affected == 0:
        raise ValueError(f"Sub-task with ID {sub_task_id} not found.")
    return get_sub_task_by_id(sub_task_id)


