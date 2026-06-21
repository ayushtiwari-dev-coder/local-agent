import sqlite3
from database.helper import execute_read, execute_write

def create_project(name: str, description: str = None) -> dict:
    """
    Creates a new project. Default status is 'active'.
    """
    query = "INSERT INTO projects (name, description) VALUES (?, ?);"
    try:
        project_id = execute_write(query, (name, description))
        return get_project_by_id(project_id)
    except sqlite3.IntegrityError as e:
        raise ValueError(f"Project with name '{name}' already exists.") from e


def get_project_by_id(project_id: int) -> dict:
    """
    Retrieves a single project by its ID.
    """
    query = "SELECT id, name, description, status, created_at FROM projects WHERE id = ?;"
    project = execute_read(query, (project_id,), fetch_one=True)
    if project is None:
        raise ValueError(f"Project with ID {project_id} not found.")
    return project


def get_all_projects() -> list[dict]:
    """
    Retrieves all projects stored in the database.
    """
    query = "SELECT id, name, description, status, created_at FROM projects ORDER BY created_at DESC;"
    return execute_read(query)


def update_project_status(project_id: int, status: str) -> dict:
    """
    Updates the status of an existing project.
    """
    query = "UPDATE projects SET status = ? WHERE id = ?;"
    rows_affected = execute_write(query, (status, project_id))
    if rows_affected == 0:
        raise ValueError(f"Project with ID {project_id} not found.")
    return get_project_by_id(project_id)