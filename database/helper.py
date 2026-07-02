# database/helper.py
import queue
import threading
import sqlite3
from database.connection import get_connection

class DatabaseWorker(threading.Thread):
    """
    Dedicated thread worker that handles ALL database reads and writes sequentially.
    Ensures that only a single thread accesses the SQLite file at any point.
    """
    def __init__(self):
        super().__init__(name="SQLiteDatabaseWorker", daemon=True)
        self.task_queue = queue.Queue()
        self._stop_event = threading.Event()

    def run(self):
        while not self._stop_event.is_set():
            try:
                # Block for up to 0.5s waiting for work
                task = self.task_queue.get(timeout=0.5)
            except queue.Empty:
                continue

            query, params, fetch_one, is_write, reply_queue = task
            conn = None

            try:

                conn = get_connection()
                
                if is_write:
                    with conn:  # Transaction wrapper
                        cursor = conn.execute(query, params)
                        if cursor.lastrowid and cursor.lastrowid > 0:
                            result = cursor.lastrowid
                        else:
                            result = cursor.rowcount
                else:
                    cursor = conn.execute(query, params)
                    if fetch_one:
                        row = cursor.fetchone()
                        result = dict(row) if row is not None else None
                    else:
                        rows = cursor.fetchall()
                        result = [dict(row) for row in rows]
                
                conn.close()
                conn = None
                
                reply_queue.put((result, None))
            except Exception as e:
                if conn is not None:
                    try:
                        conn.close()
                    except Exception:
                        pass

                reply_queue.put((None, e))
            finally:
                self.task_queue.task_done()

    def stop(self):
        self._stop_event.set()



_db_worker = DatabaseWorker()
_db_worker.start()


def execute_read(query: str, params: tuple = (), fetch_one: bool = False) -> any:
    """
    Public API replacement: Submits read tasks safely to the serialized database worker thread.
    """
    reply_queue = queue.Queue(maxsize=1)
    _db_worker.task_queue.put((query, params, fetch_one, False, reply_queue))
    
    # Block calling thread until worker finishes processing
    result, error = reply_queue.get()
    if error:
        raise RuntimeError(f"Database read error: {error}") from error
    return result


def execute_write(query: str, params: tuple = ()) -> int:
    """
    Public API replacement: Submits write tasks safely to the serialized database worker thread.
    """
    reply_queue = queue.Queue(maxsize=1)
    _db_worker.task_queue.put((query, params, False, True, reply_queue))
    
    # Block calling thread until worker finishes processing
    result, error = reply_queue.get()
    if error:
        raise error
    return result