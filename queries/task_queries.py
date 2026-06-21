import sqlite3
from database.helper import execute_read, execute_write

def create_task(project_id: int, title: str, description: str = None) -> dict:
    """
    Creates a new task linked to a project.
    """
    query = "INSERT INTO tasks (project_id, title, description) VALUES (?, ?, ?);"
    try:
        task_id = execute_write(query, (project_id, title, description))
        return get_task_by_id(task_id)
    except sqlite3.IntegrityError as e:
        raise ValueError(f"Cannot create task. Project with ID {project_id} does not exist.") from e


def get_task_by_id(task_id: int) -> dict:
    """
    Retrieves a single task by its ID.
    """
    query = "SELECT id, project_id, title, description, status, created_at, completed_at FROM tasks WHERE id = ?;"
    task = execute_read(query, (task_id,), fetch_one=True)
    if task is None:
        raise ValueError(f"Task with ID {task_id} not found.")
    return task


def get_tasks_by_project(project_id: int) -> list[dict]:
    """
    Retrieves all tasks linked to a specific project.
    """
    query = "SELECT id, project_id, title, description, status, created_at, completed_at FROM tasks WHERE project_id = ? ORDER BY created_at ASC;"
    return execute_read(query, (project_id,))


def update_task_status(task_id: int, status: str) -> dict:
    """
    Updates status and automatically controls the completed_at timestamp.
    """
    query = """
    UPDATE tasks 
    SET status = ?, 
        completed_at = CASE WHEN ? = 'completed' THEN CURRENT_TIMESTAMP ELSE NULL END
    WHERE id = ?;
    """
    rows_affected = execute_write(query, (status, status, task_id))
    if rows_affected == 0:
        raise ValueError(f"Task with ID {task_id} not found.")
    return get_task_by_id(task_id)