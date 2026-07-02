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

# queries/task_queries.py

def get_orchestra_status_summary(conversation_id: int = None) -> list[dict]:
    """
    Fetches task status summary.
    If conversation_id is provided, returns ALL statuses (completed, in-progress, pending, failed) 
    scoped strictly to that conversation.
    If conversation_id is None, returns global active tasks (pending/in-progress) only.
    """
    if conversation_id is not None:
        project_name = f"Project_Conv_{conversation_id}"
        project_row = execute_read("SELECT id FROM projects WHERE name = ?;", (project_name,), fetch_one=True)
        if not project_row:
            return []
        project_id = project_row["id"]
        
        # Scoped to conversation: Retrieve everything (completed, in_progress, pending, failed)
        tasks_query = """
            SELECT id, title, status
            FROM tasks
            WHERE project_id = ?
            ORDER BY id ASC;
        """
        tasks = execute_read(tasks_query, (project_id,))
    else:
        # Global dashboard: Retrieve active tasks only
        tasks_query = """
            SELECT id, title, status
            FROM tasks
            WHERE status IN ('pending', 'in_progress')
            ORDER BY id ASC;
        """
        tasks = execute_read(tasks_query)
        
    remaining_tasks = []
    for t in tasks:
        # Retrieve all sub-tasks belonging to this task segment
        subtasks_query = """
            SELECT description, status
            FROM sub_tasks
            WHERE task_id = ?
            ORDER BY id ASC;
        """
        active_subs = execute_read(subtasks_query, (t["id"],))
        
        task_dict = dict(t)
        task_dict["sub_tasks"] = active_subs
        remaining_tasks.append(task_dict)
        
    return remaining_tasks