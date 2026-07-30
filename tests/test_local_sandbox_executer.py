# tests/test_local_sandbox_executor.py
import pytest
import os
import sys
from unittest.mock import patch, MagicMock
from security.sandbox_executor import LocalSandboxExecutor

def test_ensure_venv_creates_when_missing(tmp_path):
    """Ensures a .venv is created if it does not already exist in the workspace."""
    # tmp_path creates a real, valid temporary directory for this OS
    workspace = tmp_path / "workspace"
    
    with patch("security.sandbox_executor.venv.create") as mock_venv_create:
        executor = LocalSandboxExecutor(str(workspace))
        
        mock_venv_create.assert_called_once_with(
            os.path.join(str(workspace), ".venv"), 
            with_pip=True
        )
        # Verify the executor safely created the workspace directory on disk
        assert os.path.exists(str(workspace))

def test_ensure_venv_skips_when_exists(tmp_path):
    """Ensures .venv creation is skipped if the folder already exists (saves latency)."""
    workspace = tmp_path / "workspace"
    venv_dir = workspace / ".venv"
    # Pre-create the folder to simulate an existing environment
    os.makedirs(venv_dir) 
    
    with patch("security.sandbox_executor.venv.create") as mock_venv_create:
        executor = LocalSandboxExecutor(str(workspace))
        
        mock_venv_create.assert_not_called()

@patch("security.sandbox_executor.subprocess.run")
def test_run_command_intercepts_python(mock_run, tmp_path):
    """Ensures 'python' commands are dynamically rewritten to use the isolated .venv binary."""
    mock_run.return_value = MagicMock(returncode=0, stdout="Mock output", stderr="")
    workspace = tmp_path / "workspace"
    
    with patch("security.sandbox_executor.venv.create"):
        executor = LocalSandboxExecutor(str(workspace))
    
    res = executor.run_command(["python", "script.py"])
    
    # Extract the exact command list passed to subprocess.run
    called_cmd = mock_run.call_args[0][0]
    
    assert ".venv" in called_cmd[0]
    if sys.platform == "win32":
        assert called_cmd[0].endswith("python.exe")
        assert "Scripts" in called_cmd[0]
    else:
        assert called_cmd[0].endswith("python")
        assert "bin" in called_cmd[0]
    
    assert called_cmd[1] == "script.py"
    assert res["status"] == "success"

@patch("security.sandbox_executor.subprocess.run")
def test_run_command_intercepts_pip(mock_run, tmp_path):
    """Ensures 'pip' commands are dynamically rewritten to use the isolated .venv binary."""
    mock_run.return_value = MagicMock(returncode=0, stdout="Pip output", stderr="")
    workspace = tmp_path / "workspace"
    
    with patch("security.sandbox_executor.venv.create"):
        executor = LocalSandboxExecutor(str(workspace))
    
    executor.run_command(["pip", "install", "requests"])
    
    called_cmd = mock_run.call_args[0][0]
    assert ".venv" in called_cmd[0]
    if sys.platform == "win32":
        assert called_cmd[0].endswith("pip.exe")
    else:
        assert called_cmd[0].endswith("pip")

@patch("security.sandbox_executor.subprocess.run")
def test_run_command_ignores_node(mock_run, tmp_path):
    """Ensures non-Python commands (like Node/Git) are untouched by the interceptor."""
    mock_run.return_value = MagicMock(returncode=0, stdout="Node output", stderr="")
    workspace = tmp_path / "workspace"
    
    with patch("security.sandbox_executor.venv.create"):
        executor = LocalSandboxExecutor(str(workspace))
    
    executor.run_command(["node", "app.js"])
    
    called_cmd = mock_run.call_args[0][0]
    assert called_cmd[0] == "node"  # Completely untouched