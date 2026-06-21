import sqlite3
from database.helper import execute_read, execute_write

def log_tool_execution(
    conversation_id: int | None, 
    tool_name: str, 
    arguments: str, 
    status: str, 
    output: str = None, 
    error_message: str = None
) -> dict:
    """
    Logs execution history and status of a tool.
    """
    if status not in {"success", "error"}:
        raise ValueError("Tool execution status must be either 'success' or 'error'.")
        
    query = "INSERT INTO tool_logs (conversation_id, tool_name, arguments, output, status, error_message) VALUES (?, ?, ?, ?, ?, ?);"
    log_id = execute_write(query, (conversation_id, tool_name, arguments, output, status, error_message))
    return get_tool_log_by_id(log_id)


def get_tool_log_by_id(log_id: int) -> dict:
    """
    Retrieves a single tool log entry.
    """
    query = "SELECT id, conversation_id, tool_name, arguments, output, status, error_message, created_at FROM tool_logs WHERE id = ?;"
    log = execute_read(query, (log_id,), fetch_one=True)
    if log is None:
        raise ValueError(f"Tool log with ID {log_id} not found.")
    return log


def get_tool_logs_by_conversation(conversation_id: int) -> list[dict]:
    """
    Retrieves chronological tool executions inside a conversation context.
    """
    query = "SELECT id, conversation_id, tool_name, arguments, output, status, error_message, created_at FROM tool_logs WHERE conversation_id = ? ORDER BY created_at ASC;"
    return execute_read(query, (conversation_id,))