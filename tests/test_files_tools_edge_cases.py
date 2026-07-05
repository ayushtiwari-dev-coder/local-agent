# FILE: tests/test_file_tools_edge_cases.py
import unittest
import os
import tempfile
from unittest.mock import patch
from tools.file_tools import read_files, write_files


class TestFileToolsEdgeCases(unittest.TestCase):
    def setUp(self):
        # Create a safe temp directory to act as the sandbox for the test
        self.temp_sandbox = tempfile.TemporaryDirectory()
        # FIX: Patch the config manager getter instead of the deleted SANDBOX_ROOT
        self.patcher = patch(
            "tools.file_tools.config_manager.get_workspace_path",
            return_value=self.temp_sandbox.name,
        )
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        self.temp_sandbox.cleanup()

    def test_invalid_json_inputs(self):
        """Edge Case: Verify that passing a invalid type returns a proper type safety error."""
        bad_json = '{"path": "file.txt" -- missing brackets'
        res_read = read_files(bad_json)
        self.assertIn("error", res_read)
        self.assertEqual(res_read["error"], "Expected a list of paths.")

    def test_path_traversal_jailbreak(self):
        """Security: Attempts to read or write to system paths outside workspace."""
        # Hacker payload is kept as a native Python list representation
        hacker_payload = [{"path": "../../../../../etc/passwd", "content": "hacked"}]
        res_write = write_files(hacker_payload)

        # Should block and return error dictionary
        key = list(res_write.keys())[0]
        self.assertIn("Error: Path", res_write[key])
        self.assertIn("is outside the allowed workspace", res_write[key])

    def test_read_files_deduplication(self):
        """Efficiency: Model requests the exact same file 3 times. Engine reads it only once."""
        test_file = os.path.join(self.temp_sandbox.name, "dup.txt")
        with open(test_file, "w") as f:
            f.write("test_content")

        # Payload is passed as a native Python list
        payload = ["dup.txt", "dup.txt", "dup.txt"]
        with patch(
            "builtins.open", unittest.mock.mock_open(read_data="test_content")
        ) as m:
            res = read_files(payload)

        self.assertEqual(len(res), 1)
        m.assert_called_once()

    def test_write_files_deduplication(self):
        """Efficiency: Model writes overlapping files. Only the last payload is saved."""
        # Payload is passed as a native Python list of dictionaries
        payload = [
            {"path": "file1.txt", "content": "old_data"},
            {"path": "file1.txt", "content": "latest_data"},
        ]
        res = write_files(payload)

        # Read back to ensure only "latest_data" exists
        written_file = os.path.join(self.temp_sandbox.name, "file1.txt")
        with open(written_file, "r") as f:
            data = f.read()
        self.assertEqual(data, "latest_data")


if __name__ == "__main__":
    unittest.main()
