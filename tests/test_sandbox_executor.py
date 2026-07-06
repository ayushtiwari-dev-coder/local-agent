# tests/test_sandbox_executor.py

import os
import unittest
from unittest.mock import patch, MagicMock
import docker
import subprocess
from tools.sandbox_executor import DockerSandboxExecutor

class TestSandboxExecutor(unittest.TestCase):
    def setUp(self):
        self.sandbox_root = os.path.abspath("/tmp/sandbox")
        self.executor = DockerSandboxExecutor(self.sandbox_root)

        self.path_patcher = patch(
            "tools.sandbox_executor.config_manager.get_workspace_path",
            return_value=self.sandbox_root,
        )
        self.image_patcher = patch(
            "tools.sandbox_executor.config_manager.get_docker_image",
            return_value="python:3.11-slim",
        )
        self.path_patcher.start()
        self.image_patcher.start()

    def tearDown(self):
        self.path_patcher.stop()
        self.image_patcher.stop()

    @patch("tools.sandbox_executor.docker.from_env")
    def test_run_command_via_docker_success(self, mock_from_env):
        """Verify standard Docker execution works."""
        mock_client = MagicMock()
        mock_client.containers.run.return_value = b"sample command output"
        mock_from_env.return_value = mock_client
        self.executor._docker_available = True

        result = self.executor.run_command("echo test")

        self.assertEqual(result, {"status": "success", "output": "sample command output"})
        mock_client.containers.run.assert_called_once()

    @patch("tools.sandbox_executor.docker.from_env")
    def test_run_command_container_exit_error(self, mock_from_env):
        """Verify Docker handles non-zero exit codes gracefully."""
        mock_client = MagicMock()
        container_error = docker.errors.ContainerError(
            container=None, exit_status=127, command="invalid_cmd",
            image="python:3.11-slim", stderr=b"Command not found",
        )
        mock_client.containers.run.side_effect = container_error
        mock_from_env.return_value = mock_client
        self.executor._docker_available = True

        # Use an allowed command that fails to bypass whitelist check
        result = self.executor.run_command("ls /nonexistent")

        self.assertEqual(result["status"], "error")
        self.assertIn("Process failed with exit code 127", result["output"])

    @patch("subprocess.run")
    def test_run_local_fallback_success(self, mock_subprocess_run):
        """Verify local fallback executes when Docker is offline."""
        self.executor._docker_available = False
        mock_response = MagicMock()
        mock_response.stdout = "local subprocess output"
        mock_response.stderr = ""
        mock_response.returncode = 0
        mock_subprocess_run.return_value = mock_response

        result = self.executor.run_command("echo local")

        self.assertEqual(result, {"status": "success", "output": "local subprocess output"})
        mock_subprocess_run.assert_called_once()

    @patch("subprocess.run")
    def test_run_local_fallback_timeout(self, mock_subprocess_run):
        """Verify local fallback catches infinite loops/timeouts using an allowed command."""
        self.executor._docker_available = False
        
        # Use 'cat' (whitelisted, blocks forever on stdin) to trigger a timeout mock safely
        mock_subprocess_run.side_effect = subprocess.TimeoutExpired(
            cmd="cat", timeout=15
        )

        result = self.executor.run_command("cat", timeout_seconds=15)

        self.assertEqual(result["status"], "error")
        self.assertIn("Command execution timed out", result["output"])

if __name__ == "__main__":
    unittest.main()