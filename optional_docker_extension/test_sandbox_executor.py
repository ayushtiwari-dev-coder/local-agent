# import pytest
# from unittest.mock import patch, MagicMock
# import docker
# from tools.sandbox_executor import DockerSandboxExecutor

# @pytest.fixture
# def sandbox_executor_fixture():
#     sandbox_root = "/tmp/sandbox"
#     return DockerSandboxExecutor(sandbox_root)


# @patch("tools.sandbox_executor.docker.from_env")
# @patch("tools.sandbox_executor.time.sleep")
# def test_docker_offline_exponential_backoff_exhaustion(mock_sleep, mock_from_env, sandbox_executor_fixture):
#     """
#     Security Verification: Assert that connection failure triggers 3 retries and 
#     exits with a structured error payload. Verify zero host subprocess leakage.
#     """
#     # Force the Docker API initialization to fail
#     mock_from_env.side_effect = Exception("Docker socket connection refused")
    
#     # Execute command
#     result = sandbox_executor_fixture.run_command("echo test", conversation_id=42)
    
#     # Verification A: No execution is passed to local host shell, returning structured error
#     assert result["status"] == "error"
#     assert "Connection failed due to this error" in result["output"]
#     assert "connection refused" in result["output"]
    
#     # Verification B: Assert connection backoff retried exactly 3 times
#     assert mock_from_env.call_count == 3
    
#     # Verification C: Assert sequential retry backoffs matches: 1s, 2s, and 4s
#     mock_sleep.assert_any_call(1)
#     mock_sleep.assert_any_call(2)
#     mock_sleep.assert_any_call(4)


# @patch("tools.sandbox_executor.docker.from_env")
# def test_docker_client_caching(mock_from_env, sandbox_executor_fixture):
#     """Verify connection socket is cached across successive calls to optimize network operations."""
#     mock_client = MagicMock()
#     mock_from_env.return_value = mock_client
    
#     # Run consecutive validation checks
#     sandbox_executor_fixture._get_docker_client_with_retry()
#     sandbox_executor_fixture._get_docker_client_with_retry()
    
#     # Assert that from_env was only invoked once initially and then cached
#     assert mock_from_env.call_count == 1
#     # Verify the fallback ping mechanism is used to check connection health instead of rebuilding client
#     assert mock_client.ping.call_count == 2


# @patch("tools.sandbox_executor.DockerSandboxExecutor._get_docker_client_with_retry")
# @patch("tools.sandbox_executor.enforce_sandbox_lifecycle_policy")
# def test_container_creation_failure_handling(mock_lifecycle, mock_get_client, sandbox_executor_fixture):
#     """Verify that container creation errors return a clean error payload rather than crashing the engine."""
#     mock_client = MagicMock()
#     # Mock container not existing, and running/instantiating it throws a write limit error
#     mock_client.containers.get.side_effect = docker.errors.NotFound("Not Found")
#     mock_client.containers.run.side_effect = Exception("Docker disk space limit hit")
#     mock_get_client.return_value = mock_client
    
#     result = sandbox_executor_fixture.run_command("echo test", conversation_id=42)
    
#     assert result["status"] == "error"
#     assert "Failed to initialize sandbox container" in result["output"]
#     assert "Docker disk space limit hit" in result["output"]


# @patch("tools.sandbox_executor.DockerSandboxExecutor._get_docker_client_with_retry")
# @patch("tools.sandbox_executor.enforce_sandbox_lifecycle_policy")
# def test_execution_inside_sandbox_container_failure(mock_lifecycle, mock_get_client, sandbox_executor_fixture):
#     """Verify shell execution errors inside the sandbox are captured and isolated gracefully."""
#     mock_client = MagicMock()
#     mock_container = MagicMock()
#     mock_container.status = "running"
    
#     # Simulate a command process crashing with an exit code of 127 (command not found) inside the sandbox
#     mock_container.exec_run.return_value = MagicMock(exit_code=127, output=b"sh: make: command not found")
#     mock_client.containers.get.return_value = mock_container
#     mock_get_client.return_value = mock_client
    
#     result = sandbox_executor_fixture.run_command("make build", conversation_id=42)
    
#     assert result["status"] == "error"
#     assert "Process failed with exit code 127" in result["output"]
#     assert "make: command not found" in result["output"]\

#this is test for sandbox executer