import os
import sqlite3
# Import both the connection, the table creator, AND the database path from our database package
from database.connection import get_connection, DATABASE_PATH
from database.table_generator import create_tables

def run_database_test() -> None:
    """
    Validates that the database file is created, tables are initialized,
    and running table generation multiple times does not raise errors.
    """
    print("Starting database initialization test...")
    
    # 1. Run the table generation code
    try:
        create_tables()
        print("Success: create_tables() executed without errors.")
    except Exception as e:
        raise AssertionError(f"create_tables() failed on initial run: {e}")

    # 2. Verify that the database file actually exists at the correct path
    # We now use the imported DATABASE_PATH instead of the hardcoded "assistant.db"
    if not os.path.exists(DATABASE_PATH):
        raise AssertionError(f"Database file was not created at '{DATABASE_PATH}'.")
    print(f"Success: Database file found at '{DATABASE_PATH}'.")

    # 3. Query SQLite system table to verify the expected tables exist
    expected_tables = {
        "users", "projects", "tasks", "conversations", 
        "messages", "memories", "model_usage", "tool_logs","summaries"
    }
    
    conn = get_connection()
    try:
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table';")
        existing_tables = {row["name"] for row in cursor.fetchall()}
        
        # Verify each of our expected tables is present
        missing_tables = expected_tables - existing_tables
        if missing_tables:
            raise AssertionError(f"Missing expected tables in database: {missing_tables}")
            
        print("Success: All 9 foundational tables verified in the schema.")
        
    finally:
        conn.close()

    # 4. Run create_tables() again to verify it is safe to run multiple times
    try:
        create_tables()
        print("Success: Secondary run of create_tables() passed safely.")
    except Exception as e:
        raise AssertionError(f"create_tables() is not safe to run repeatedly: {e}")

    print("\nDatabase verification tests passed.")

if __name__ == "__main__":
    run_database_test()