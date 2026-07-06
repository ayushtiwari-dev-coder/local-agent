import sqlite3
from database.connection import DATABASE_PATH
from database.table_generator import create_tables


def migrate_memory_tables():
    print(f"Migrating database at {DATABASE_PATH}...")
    conn = sqlite3.connect(DATABASE_PATH)
    try:
        # Drop the old table because it lacks the 'embedding' column and foreign keys
        conn.execute("DROP TABLE IF EXISTS memories;")
        conn.execute("DROP TABLE IF EXISTS memory_categories;")
        conn.commit()
        print("Old memory tables dropped safely.")
    except Exception as e:
        print(f"Error dropping tables: {e}")
    finally:
        conn.close()


    create_tables()
    print("New semantic memory tables created successfully!")


if __name__ == "__main__":
    migrate_memory_tables()
