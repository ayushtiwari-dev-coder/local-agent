# tests/test_database_queue.py
import unittest
import tempfile
import os
import threading
from unittest.mock import patch, MagicMock

# Import the database helper elements
import database.helper
from database.helper import execute_write, execute_read

class TestDatabaseQueue(unittest.TestCase):
    def setUp(self):
        # 1. Cleanly shut down any database background worker thread started by prior tests
        if hasattr(database.helper, "_db_worker") and database.helper._db_worker.is_alive():
            database.helper._db_worker.stop()
            database.helper._db_worker.join(timeout=2.0)
            
        # 2. Create a fresh temporary SQLite file to sandbox this queue test
        self.temp_db = tempfile.NamedTemporaryFile(delete=False)
        self.temp_db_path = self.temp_db.name
        self.temp_db.close()
        
        # 3. Patch the central database path dynamically
        self.db_path_patcher = patch("database.connection.DATABASE_PATH", self.temp_db_path)
        self.db_path_patcher.start()
        
        # 4. Generate the SQLite schemas in our clean test sandbox
        from database.table_generator import create_tables
        create_tables()
        
        # 5. Spin up a fresh DatabaseWorker bound strictly to the patched temporary database
        database.helper._db_worker = database.helper.DatabaseWorker()
        database.helper._db_worker.start()

    def tearDown(self):
        # Shut down worker cleanly
        if database.helper._db_worker.is_alive():
            database.helper._db_worker.stop()
            database.helper._db_worker.join(timeout=2.0)
            
        # Remove database patch and disk file
        self.db_path_patcher.stop()
        try:
            os.remove(self.temp_db_path)
        except OSError:
            pass

    def test_concurrent_database_writes_through_queue(self):
        """
        Verifies that multiple concurrent threads can issue write queries
        without causing database collisions, lockups, or 'database is locked' errors.
        """
        num_threads = 20
        results = []
        threads = []

        # Thread task: Insert a unique user into the database
        def write_task(thread_id):
            try:
                query = "INSERT INTO users (name, username) VALUES (?, ?);"
                execute_write(query, (f"Worker_{thread_id}", f"user_uname_{thread_id}"))
                results.append(True)
            except Exception as e:
                results.append(e)

        # Spawn all threads concurrently
        for i in range(num_threads):
            t = threading.Thread(target=write_task, args=(i,))
            threads.append(t)
            t.start()

        # Join threads back to the main thread
        for t in threads:
            t.join()

        # Check that every thread completed successfully
        for idx, res in enumerate(results):
            self.assertTrue(
                res is True, 
                f"Thread {idx} failed with error: {res}. "
                "This indicates serialized thread execution has failed or a lockup occurred."
            )

        # Read back from database through worker queue to verify count
        users = execute_read("SELECT COUNT(*) as total FROM users;", fetch_one=True)
        self.assertEqual(users["total"], num_threads)


if __name__ == "__main__":
    unittest.main()