# FILE: tests/test_database_queries.py
import unittest
import tempfile
import os
import sqlite3
from unittest.mock import patch

# Consolidated clean imports
from database.table_generator import create_tables
from queries.user_queries import create_user, get_user_by_id
from queries.conversation_queries import create_conversation, get_conversation_by_id
from queries.message_queries import create_message
from queries.memory_queries import create_memory, search_memories

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

    def test_memory_search_wildcard_matching(self):
        """Verifies that search_memories matches keywords in both contents and categories."""
        # 1. Write mock memories (lowercase inputs)
        create_memory("The user prefers using Python 3.11", category="preferences")
        create_memory("Project documentation initialized", category="system_logs")

        # 2. Search keyword in content
        matches_content = search_memories("Python")
        self.assertEqual(len(matches_content), 1)
        # Fix: Assert lowercase 'preferences' to match raw database values
        self.assertEqual(matches_content[0]["category"], "preferences")
        self.assertIn("Python 3.11", matches_content[0]["content"])

        # 3. Search keyword in category (case insensitive search via LIKE query)
        matches_category = search_memories("system")
        self.assertEqual(len(matches_category), 1)
        # Fix: Assert lowercase 'system_logs' to match raw database values
        self.assertEqual(matches_category[0]["category"], "system_logs")

        # 4. Search term with no matches
        no_matches = search_memories("non-existent-key")
        self.assertEqual(len(no_matches), 0)

if __name__ == "__main__":
    unittest.main()