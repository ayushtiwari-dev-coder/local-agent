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
from queries.memory_queries import (
    create_category_with_embedding, 
    create_memory_with_embedding, 
    get_all_categories, 
    get_memories_by_category
)

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

    def test_semantic_memory_queries(self):
        """Verifies that memory categories and embedded memories are stored and retrieved correctly."""
        
        # 1. Write mock category and memory (using stringified JSON lists to mock vectors)
        mock_cat_embedding = "[0.1, 0.2, 0.3]"
        mock_mem_embedding = "[0.4, 0.5, 0.6]"
        
        create_category_with_embedding("Python Settings", mock_cat_embedding)
        create_memory_with_embedding("User prefers Python 3.11", "Python Settings", mock_mem_embedding)
        
        # 2. Verify Category Retrieval
        categories = get_all_categories()
        self.assertEqual(len(categories), 1)
        self.assertEqual(categories[0]["category"], "Python Settings")
        self.assertEqual(categories[0]["embedding"], mock_cat_embedding)
        
        # 3. Verify Memory Retrieval by Category
        memories = get_memories_by_category("Python Settings")
        self.assertEqual(len(memories), 1)
        self.assertEqual(memories[0]["content"], "User prefers Python 3.11")
        self.assertEqual(memories[0]["category"], "Python Settings")
        self.assertEqual(memories[0]["embedding"], mock_mem_embedding)
        
        # 4. Verify Empty Category Retrieval (No matches)
        empty_memories = get_memories_by_category("Non-existent Category")
        self.assertEqual(len(empty_memories), 0)

if __name__ == "__main__":
    unittest.main()