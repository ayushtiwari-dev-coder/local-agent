# FILE: tests/test_sandbox_executor.py
import os
import unittest
from unittest.mock import patch, MagicMock
import docker
from tools.sandbox_executor import DockerSandboxExecutor

class TestSandboxExecutor(unittest.TestCase):
    def setUp(self):
        # Dynamically resolve absolute paths to ensure compatibility on Windows, macOS, and Linux
        self.sandbox_root = os.path.abspath("/tmp/sandbox")
        self.executor = DockerSandboxExecutor(self.sandbox_root)

    @patch("tools.sandbox_executor.docker.from_env")
    def test_check_docker_success(self, mock_from_env):
        """Verify that a running Docker Desktop client is detected successfully."""
        mock_client = MagicMock()
        mock_from_env.return_value = mock_client
        
        is_available = self.executor._check_docker()
        self.assertTrue(is_available)
        mock_client.ping.assert_called_once()

    @patch("tools.sandbox_executor.docker.from_env")
    def test_check_docker_failure_fallback(self, mock_from_env):
        """Verify that check_docker returns False gracefully if the daemon is closed."""
        mock_client = MagicMock()
        mock_client.ping.side_effect = Exception("Daemon offline")
        mock_from_env.return_value = mock_client
        
        is_available = self.executor._check_docker()
        self.assertFalse(is_available)

    @patch("tools.sandbox_executor.docker.from_env")
    def test_run_command_via_docker_success(self, mock_from_env):
        """Verify the complete parameters of a successful sandboxed run call."""
        mock_client = MagicMock()
        mock_client.containers.run.return_value = b"sample command output"
        mock_from_env.return_value = mock_client
        self.executor._docker_available = True
        
        result = self.executor.run_command("echo test")
        self.assertEqual(result, "sample command output")
        
        mock_client.containers.run.assert_called_once_with(
            image="python:3.11-slim",
            command="sh -c 'echo test'",  
            volumes={self.sandbox_root: {"bind": "/workspace", "mode": "rw"}},
            working_dir="/workspace",
            network_disabled=True,
            mem_limit="512m",
            nano_cpus=1000000000,
            timeout=15,
            remove=True,
            stdout=True,
            stderr=True
        )

    @patch("tools.sandbox_executor.docker.from_env")
    def test_run_command_container_exit_error(self, mock_from_env):
        """Verify handling and parsing of exit code errors from container subprocesses."""
        mock_client = MagicMock()
        container_error = docker.errors.ContainerError(
            container=None,
            exit_status=127,
            command="invalid_cmd",
            image="python:3.11-slim",
            stderr=b"Command not found"
        )
        mock_client.containers.run.side_effect = container_error
        mock_from_env.return_value = mock_client
        self.executor._docker_available = True
        
        result = self.executor.run_command("invalid_cmd")
        self.assertIn("Error: Process failed with exit code 127", result)
        self.assertIn("Command not found", result)

    @patch("subprocess.run")  # Patched globally to handle local function imports
    def test_run_command_local_subprocess_fallback(self, mock_subprocess_run):
        """Verify fallback to safe local subprocess execution if Docker is offline."""
        self.executor._docker_available = False
        
        mock_response = MagicMock()
        mock_response.stdout = "local subprocess output"
        mock_response.stderr = ""
        mock_subprocess_run.return_value = mock_response
        
        result = self.executor.run_command("echo local")
        self.assertEqual(result, "local subprocess output")
        mock_subprocess_run.assert_called_once_with(
            "echo local",
            shell=True,
            cwd=self.sandbox_root,
            capture_output=True,
            text=True,
            timeout=15
        )

if __name__ == "__main__":
    unittest.main()