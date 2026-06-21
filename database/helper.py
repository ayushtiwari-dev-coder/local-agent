import sqlite3
from database.connection import get_connection

def execute_read(query: str, params: tuple = (), fetch_one: bool = False) -> any:
    """
    Executes a SELECT query, manages the connection lifecycle, 
    and automatically converts rows to dictionaries.
    """
    conn = get_connection()
    try:
        cursor = conn.execute(query, params)
        if fetch_one:
            row = cursor.fetchone()
            return dict(row) if row is not None else None
        else:
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
            
    except sqlite3.Error as e:
        raise RuntimeError(f"Database read error: {e}") from e
    finally:
        conn.close()


def execute_write(query: str, params: tuple = ()) -> int:
    """
    Executes an INSERT, UPDATE, or DELETE query within a transaction context.
    Returns:
        - lastrowid (for INSERTs)
        - rowcount (number of modified rows for UPDATE/DELETE)
    """
    conn = get_connection()
    try:
        with conn:
            cursor = conn.execute(query, params)
            # If it was an INSERT, return the newly created row's ID
            if cursor.lastrowid and cursor.lastrowid > 0:
                return cursor.lastrowid
            # For UPDATE/DELETE, return the count of modified rows
            return cursor.rowcount
            
    except sqlite3.Error as e:
        # We let the raw exception propagate so specific query files 
        # can catch specialized errors (like sqlite3.IntegrityError)
        raise e
    finally:
        conn.close()