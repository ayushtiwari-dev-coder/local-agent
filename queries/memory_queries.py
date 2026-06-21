import sqlite3
from database.helper import execute_read, execute_write

def create_memory(content: str, category: str = "general") -> dict:
    """
    Saves a new long-term memory fact or preference.
    """
    query = "INSERT INTO memories (content, category) VALUES (?, ?);"
    memory_id = execute_write(query, (content, category))
    return get_memory_by_id(memory_id)


def get_memory_by_id(memory_id: int) -> dict:
    """
    Retrieves a single memory by its ID.
    """
    query = "SELECT id, content, category, created_at FROM memories WHERE id = ?;"
    memory = execute_read(query, (memory_id,), fetch_one=True)
    if memory is None:
        raise ValueError(f"Memory with ID {memory_id} not found.")
    return memory


def search_memories(search_term: str) -> list[dict]:
    """
    Keyword searches content and categories using wildcards.
    """
    query = "SELECT id, content, category, created_at FROM memories WHERE content LIKE ? OR category LIKE ? ORDER BY created_at DESC;"
    wildcard_term = f"%{search_term}%"
    return execute_read(query, (wildcard_term, wildcard_term))


def get_all_memories() -> list[dict]:
    """
    Retrieves all stored memories.
    """
    query = "SELECT id, content, category, created_at FROM memories ORDER BY created_at DESC;"
    return execute_read(query)


def delete_memory(memory_id: int) -> None:
    """
    Deletes a specific memory record.
    """
    query = "DELETE FROM memories WHERE id = ?;"
    rows_affected = execute_write(query, (memory_id,))
    if rows_affected == 0:
        raise ValueError(f"Memory with ID {memory_id} not found.")