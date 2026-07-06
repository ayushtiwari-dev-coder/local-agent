# tests/test_sandbox_executor.py
import pytest
import os
import subprocess
import docker
from unittest.mock import patch, MagicMock
from tools.sandbox_executor import DockerSandboxExecutor

@pytest.fixture
def sandbox_executor_fixture():
    """Sets up a sandboxed environment with mocked workspace paths and Docker configurations."""
    sandbox_root = os.path.abspath("/tmp/sandbox")
    executor = DockerSandboxExecutor(sandbox_root)
    
    path_patcher = patch(
        "tools.sandbox_executor.config_manager.get_workspace_path",
        return_value=sandbox_root
    )
    image_patcher = patch(
        "tools.sandbox_executor.config_manager.get_docker_image",
        return_value="python:3.11-slim"
    )
    
    path_patcher.start()
    image_patcher.start()
    
    yield executor
    
    path_patcher.stop()
    image_patcher.stop()

@patch("tools.sandbox_executor.docker.from_env")
def test_run_command_via_docker_success(mock_from_env, sandbox_executor_fixture):
    """Verify standard Docker command execution works correctly."""
    mock_client = MagicMock()
    mock_client.containers.run.return_value = b"sample command output"
    mock_from_env.return_value = mock_client
    
    sandbox_executor_fixture._docker_available = True
    result = sandbox_executor_fixture.run_command("echo test")
    
    assert result == {"status": "success", "output": "sample command output"}
    mock_client.containers.run.assert_called_once()

@patch("tools.sandbox_executor.docker.from_env")
def test_run_command_container_exit_error(mock_from_env, sandbox_executor_fixture):
    """Verify Docker gracefully captures container failures and non-zero exit codes."""
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
    
    sandbox_executor_fixture._docker_available = True
    result = sandbox_executor_fixture.run_command("ls /nonexistent")
    
    assert result["status"] == "error"
    assert "Process failed with exit code 127" in result["output"]

@patch("subprocess.run")
def test_run_local_fallback_success(mock_subprocess_run, sandbox_executor_fixture):
    """Verify local subprocess boundary execution when Docker is offline."""
    sandbox_executor_fixture._docker_available = False
    
    mock_response = MagicMock()
    mock_response.stdout = "local subprocess output"
    mock_response.stderr = ""
    mock_response.returncode = 0
    mock_subprocess_run.return_value = mock_response
    
    result = sandbox_executor_fixture.run_command("echo local")
    assert result == {"status": "success", "output": "local subprocess output"}
    mock_subprocess_run.assert_called_once()

@patch("subprocess.run")
def test_run_local_fallback_timeout(mock_subprocess_run, sandbox_executor_fixture):
    """Verify local fallback catches execution timeouts of hanging commands."""
    sandbox_executor_fixture._docker_available = False
    mock_subprocess_run.side_effect = subprocess.TimeoutExpired(cmd="cat", timeout=15)
    
    result = sandbox_executor_fixture.run_command("cat", timeout_seconds=15)
    assert result["status"] == "error"
    assert "Command execution timed out" in result["output"]