import sqlite3
from database.connection import DATABASE_PATH

def add_pending_approvals_table():
    print(f"Migrating database at {DATABASE_PATH}...")
    conn = sqlite3.connect(DATABASE_PATH)
    try:
        # Create the new table for queuing unsafe tools
        conn.execute("""
        CREATE TABLE IF NOT EXISTS pending_approvals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER NOT NULL,
            tool_call_id TEXT NOT NULL,
            tool_name TEXT NOT NULL,
            arguments TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
        );
        """)
        conn.commit()
        print("Successfully added 'pending_approvals' table.")
    except Exception as e:
        print(f"Error updating database: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    add_pending_approvals_table()
