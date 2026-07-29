# tests/test_sandbox_executor.py

import pytest
import os
import sys
from unittest.mock import patch, MagicMock
from security.sandbox_executor import LocalSandboxExecutor

@pytest.fixture
def sandbox_executor_fixture(tmp_path):
    """Provides a LocalSandboxExecutor instance pointing to a temporary directory."""
    sandbox_root = str(tmp_path / "workspace")
    # Prevent actual venv creation during tests to keep them fast
    with patch("security.sandbox_executor.venv.create"), \
         patch("security.sandbox_executor.subprocess.run"):
        executor = LocalSandboxExecutor(sandbox_root)
    return executor

@patch("security.sandbox_executor.subprocess.run")
def test_run_command_intercepts_python(mock_run, sandbox_executor_fixture):
    """Ensures 'python' commands are rewritten to use the venv executable."""
    mock_run.return_value = MagicMock(returncode=0, stdout="Hello", stderr="")
    
    result = sandbox_executor_fixture.run_command(["python", "script.py"])
    
    assert result["status"] == "success"
    
    executed_command = mock_run.call_args[0][0]
    assert executed_command[0] != "python" 
    assert ".venv" in executed_command[0]

@patch("security.sandbox_executor.subprocess.run")
def test_run_command_intercepts_pip(mock_run, sandbox_executor_fixture):
    """Ensures 'pip' commands are rewritten to use the venv executable."""
    mock_run.return_value = MagicMock(returncode=0, stdout="Installed", stderr="")
    
    sandbox_executor_fixture.run_command(["pip", "install", "requests"])
    
    executed_command = mock_run.call_args[0][0]
    assert executed_command[0] != "pip"
    assert ".venv" in executed_command[0]

@patch("security.sandbox_executor.subprocess.run")
def test_run_command_injects_environment_variables(mock_run, sandbox_executor_fixture):
    """Security: Ensures VIRTUAL_ENV and PATH are injected to trap nested subprocesses."""
    mock_run.return_value = MagicMock(returncode=0, stdout="OK", stderr="")
    
    sandbox_executor_fixture.run_command(["node", "app.js"])
    
    injected_env = mock_run.call_args[1]["env"]
    
    assert "VIRTUAL_ENV" in injected_env
    assert injected_env["VIRTUAL_ENV"] == sandbox_executor_fixture.venv_dir
    assert ".venv" in injected_env["PATH"]

@patch("security.sandbox_executor.subprocess.run")
def test_run_command_handles_failures(mock_run, sandbox_executor_fixture):
    """Ensures non-zero exit codes are caught and formatted correctly."""
    mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="SyntaxError")
    
    result = sandbox_executor_fixture.run_command(["python", "bad.py"])
    
    assert result["status"] == "error"
    assert "Process failed with exit code 1" in result["output"]
    assert "SyntaxError" in result["output"]
