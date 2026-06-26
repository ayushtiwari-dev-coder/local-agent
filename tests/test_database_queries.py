# FILE: tests/test_database_queries.py
import unittest
import tempfile
import os
import sqlite3
from unittest.mock import patch
from queries.user_queries import create_user, get_user_by_id
from database.table_generator import create_tables
from queries.user_queries import create_user
from queries.conversation_queries import create_conversation
from queries.message_queries import create_message
from queries.user_queries import create_user
from queries.conversation_queries import get_conversation_by_id
from queries.task_queries import get_task_by_id

class TestDatabaseQueries(unittest.TestCase):
    def setUp(self):
        # Create a blank temporary database file
        self.temp_db = tempfile.NamedTemporaryFile(delete=False)
        self.temp_db_path = self.temp_db.name
        self.temp_db.close()
        
        # Patch the DATABASE_PATH so the helper uses our temporary file
        self.db_patcher = patch('database.connection.DATABASE_PATH', self.temp_db_path)
        self.db_patcher.start()
        
        # Initialize the tables in the temp db
        
        create_tables()

    def tearDown(self):
        self.db_patcher.stop()
        os.remove(self.temp_db_path)

    def test_create_and_fetch_user(self):
        """Tests standard creation and retrieval queries."""
        
        
        user = create_user("Test User", "testuser")
        self.assertEqual(user["username"], "testuser")
        self.assertIsNotNone(user["id"])
        
        fetched = get_user_by_id(user["id"])
        self.assertEqual(fetched["name"], "Test User")

    def test_user_unique_constraint(self):
        """Edge Case: Cannot create two users with the identical username."""
        
        create_user("User One", "unique_name")
        with self.assertRaisesRegex(ValueError, "is already taken"):
            create_user("User Two", "unique_name")

    def test_message_role_constraint(self):
        """Edge Case: SQLite message insertion throws ValueError if role is invalid."""
        
        
        
        user = create_user("A", "A")
        conv = create_conversation(user["id"], "Test Title")
        
        with self.assertRaisesRegex(ValueError, "Invalid message role"):
            create_message(conv["id"], role="hacker", content="Malicious code")
            
        # Valid roles should pass
        msg = create_message(conv["id"], role="user", content="Good payload")
        self.assertEqual(msg["role"], "user")

    def test_missing_data_exceptions(self):
        """Ensures get_*_by_id functions raise clean ValueErrors when IDs don't exist."""
        
        
        with self.assertRaises(ValueError):
            get_conversation_by_id(9999)
            
        with self.assertRaises(ValueError):
            get_task_by_id(9999)

if __name__ == "__main__":
    unittest.main()