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
        
        # FIX: Force the executor to use our test sandbox path and image
        self.path_patcher = patch('tools.sandbox_executor.config_manager.get_workspace_path', return_value=self.sandbox_root)
        self.image_patcher = patch('tools.sandbox_executor.config_manager.get_docker_image', return_value="python:3.11-slim")
        self.path_patcher.start()
        self.image_patcher.start()

    def tearDown(self):
        self.path_patcher.stop()
        self.image_patcher.stop()

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
        """Verify the complete parameters and the structured dictionary output of a successful sandboxed run call."""
        mock_client = MagicMock()
        mock_client.containers.run.return_value = b"sample command output"
        mock_from_env.return_value = mock_client
        self.executor._docker_available = True
        
        result = self.executor.run_command("echo test")
        
        self.assertEqual(result, {
            "status": "success",
            "output": "sample command output"
        })
        
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
        """Verify handling, parsing, and dictionary status of exit code errors from container subprocesses."""
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
        
        self.assertEqual(result["status"], "error")
        self.assertIn("Error: Process failed with exit code 127", result["output"])
        self.assertIn("Command not found", result["output"])

    @patch("subprocess.run")
    def test_run_command_local_subprocess_fallback(self, mock_subprocess_run):
        """Verify fallback to safe local subprocess execution and structured dictionary return if Docker is offline."""
        self.executor._docker_available = False
        mock_response = MagicMock()
        mock_response.stdout = "local subprocess output"
        mock_response.stderr = ""
        mock_response.returncode = 0
        mock_subprocess_run.return_value = mock_response
        
        result = self.executor.run_command("echo local")
        
        self.assertEqual(result, {
            "status": "success",
            "output": "local subprocess output"
        })
        mock_subprocess_run.assert_called_once_with(
            "echo local",
            shell=True,
            cwd=self.sandbox_root,
            capture_output=True,
            text=True,
            timeout=15
        )

    @patch("subprocess.run")
    @patch("builtins.input", return_value="y")
    def test_run_local_fallback_destructive_command_allowed(self, mock_input, mock_subprocess_run):
        """Scenario 1: A dangerous command is parsed, user responds with 'y' (allow)."""
        def test_callback(cmd, reason):
            choice = input(f"Unsafe command: {cmd}. Reason: {reason}. Allow? (y/n): ")
            return choice.strip().lower() == "y"
        self.executor.fallback_approval_callback = test_callback
        
        mock_response = MagicMock()
        mock_response.stdout = "Deletion executed successfully."
        mock_response.stderr = ""
        mock_response.returncode = 0
        mock_subprocess_run.return_value = mock_response
        
        destructive_cmd = "rm -rf /tmp/test_workspace_sandbox_dummy"
        result = self.executor._run_local_fallback(destructive_cmd, timeout_seconds=15)
        
        mock_input.assert_called_once()
        mock_subprocess_run.assert_called_once_with(
            destructive_cmd,
            shell=True,
            cwd=self.sandbox_root,
            capture_output=True,
            text=True,
            timeout=15
        )
        self.assertEqual(result, {
            "status": "success",
            "output": "Deletion executed successfully."
        })

    @patch("subprocess.run")
    @patch("builtins.input", return_value="n")
    def test_run_local_fallback_destructive_command_blocked(self, mock_input, mock_subprocess_run):
        """Scenario 2: A dangerous command is parsed, user responds with 'n' (block)."""
        def test_callback(cmd, reason):
            choice = input(f"Unsafe command: {cmd}. Reason: {reason}. Allow? (y/n): ")
            return choice.strip().lower() == "y"
        self.executor.fallback_approval_callback = test_callback
        
        destructive_cmd = "rm -rf /etc/hosts"
        result = self.executor._run_local_fallback(destructive_cmd, timeout_seconds=15)
        
        mock_input.assert_called_once()
        mock_subprocess_run.assert_not_called()
        self.assertEqual(result["status"], "error")
        self.assertIn("blocked by user", result["output"])
        self.assertIn("safety check", result["output"])

    @patch("builtins.input")
    def test_run_local_fallback_safe_command_no_prompt(self, mock_input, mock_subprocess_run=None): # Added optional mock to prevent crashing if not patched
        """Scenario 3: A safe command is parsed. The execution should run directly without prompting."""
        with patch("subprocess.run") as mock_subprocess_run:
            mock_response = MagicMock()
            mock_response.stdout = "Hello World"
            mock_response.stderr = ""
            mock_response.returncode = 0
            mock_subprocess_run.return_value = mock_response
            
            safe_cmd = "echo 'hello world'"
            result = self.executor._run_local_fallback(safe_cmd, timeout_seconds=15)
            
            mock_input.assert_not_called()
            mock_subprocess_run.assert_called_once()
            
            self.assertEqual(result, {
                "status": "success",
                "output": "Hello World"
            })

if __name__ == "__main__":
    unittest.main()