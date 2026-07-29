# tests/test_terminal_tools.py

import pytest
from unittest.mock import patch, MagicMock
from tools.terminal_tools import run_script, manage_dependencies, run_tests

# =====================================================================
# 1. TESTS FOR run_script
# =====================================================================

@patch("tools.terminal_tools.get_sandbox")
def test_run_script_valid_python(mock_get_sandbox):
    """Happy Path: Ensures Python scripts run correctly with arguments."""
    mock_run = mock_get_sandbox.return_value.run_command
    mock_run.return_value = {"status": "success", "output": "Hello World"}

    res = run_script(language="python", filepath="main.py", args=["--verbose", "-p", "8080"])

    # Assert the command was built as a safe list with a 60s timeout
    mock_run.assert_called_once_with(["python", "main.py", "--verbose", "-p", "8080"], timeout_seconds=60)
    assert res["status"] == "success"
    assert res["output"] == "Hello World"

@patch("tools.terminal_tools.get_sandbox")
def test_run_script_valid_node(mock_get_sandbox):
    """Happy Path: Ensures Node scripts run correctly without arguments."""
    mock_run = mock_get_sandbox.return_value.run_command
    mock_run.return_value = {"status": "success", "output": "Server started"}

    res = run_script(language="node", filepath="app.js")

    mock_run.assert_called_once_with(["node", "app.js"], timeout_seconds=60)
    assert res["status"] == "success"

@patch("tools.terminal_tools.get_sandbox")
def test_run_script_invalid_language(mock_get_sandbox):
    """Edge Case: Rejects unsupported languages (like bash or ruby)."""
    mock_run = mock_get_sandbox.return_value.run_command
    
    res = run_script(language="bash", filepath="script.sh")

    assert res["status"] == "error"
    assert "Language must be 'python' or 'node'" in res["output"]
    mock_run.assert_not_called()  # Ensure it never reached the OS

# =====================================================================
# 2. TESTS FOR manage_dependencies
# =====================================================================

@patch("tools.terminal_tools.get_sandbox")
def test_manage_dependencies_pip_install_specific(mock_get_sandbox):
    """Happy Path: Installs specific pip packages."""
    mock_run = mock_get_sandbox.return_value.run_command
    
    manage_dependencies(manager="pip", action="install", packages=["requests", "numpy"])

    mock_run.assert_called_once_with(["pip", "install", "requests", "numpy"], timeout_seconds=120)

@patch("tools.terminal_tools.get_sandbox")
def test_manage_dependencies_npm_install_all(mock_get_sandbox):
    """Happy Path: Runs general npm install when no packages are provided."""
    mock_run = mock_get_sandbox.return_value.run_command
    
    manage_dependencies(manager="npm", action="install")

    mock_run.assert_called_once_with(["npm", "install"], timeout_seconds=120)

@patch("tools.terminal_tools.get_sandbox")
def test_manage_dependencies_pip_install_all(mock_get_sandbox):
    """Edge Case: Runs pip install -r requirements.txt when no packages are provided."""
    mock_run = mock_get_sandbox.return_value.run_command
    
    manage_dependencies(manager="pip", action="install")

    mock_run.assert_called_once_with(["pip", "install", "-r", "requirements.txt"], timeout_seconds=120)

@patch("tools.terminal_tools.get_sandbox")
def test_manage_dependencies_invalid_manager(mock_get_sandbox):
    """Edge Case: Rejects unsupported package managers."""
    mock_run = mock_get_sandbox.return_value.run_command
    
    res = manage_dependencies(manager="yarn", action="install")

    assert res["status"] == "error"
    assert "Manager must be 'pip' or 'npm'" in res["output"]
    mock_run.assert_not_called()

@patch("tools.terminal_tools.get_sandbox")
def test_manage_dependencies_invalid_action(mock_get_sandbox):
    """Edge Case: Rejects unsupported actions (like 'update')."""
    mock_run = mock_get_sandbox.return_value.run_command
    
    res = manage_dependencies(manager="npm", action="update")

    assert res["status"] == "error"
    assert "Action must be 'install' or 'uninstall'" in res["output"]
    mock_run.assert_not_called()

# =====================================================================
# 3. TESTS FOR run_tests
# =====================================================================

@patch("tools.terminal_tools.get_sandbox")
def test_run_tests_pytest_with_target(mock_get_sandbox):
    """Happy Path: Runs pytest on a specific file."""
    mock_run = mock_get_sandbox.return_value.run_command
    mock_run.return_value = {"status": "success", "output": "1 passed"}
    
    run_tests(framework="pytest", target="tests/test_api.py")

    mock_run.assert_called_once_with(["python", "-m", "pytest", "tests/test_api.py"], timeout_seconds=60)

@patch("tools.terminal_tools.get_sandbox")
def test_run_tests_pytest_all(mock_get_sandbox):
    """Happy Path: Runs pytest globally if no target is provided."""
    mock_run = mock_get_sandbox.return_value.run_command
    mock_run.return_value = {"status": "success", "output": "10 passed"}
    
    run_tests(framework="pytest")

    mock_run.assert_called_once_with(["python", "-m", "pytest"], timeout_seconds=60)

@patch("tools.terminal_tools.get_sandbox")
def test_run_tests_pytest_exit_code_1_override(mock_get_sandbox):
    """Edge Case: Pytest Exit Code 1 (Test Failed) should be returned as a success status."""
    mock_run = mock_get_sandbox.return_value.run_command
    mock_run.return_value = {"status": "error", "output": "Process failed with exit code 1.\n1 failed, 24 passed"}
    
    res = run_tests(framework="pytest")

    # The tool should override the error status to success so the LLM can read the failure
    assert res["status"] == "success"
    assert "1 failed" in res["output"]

@patch("tools.terminal_tools.get_sandbox")
def test_run_tests_npm(mock_get_sandbox):
    """Edge Case: Runs npm test and ignores specific targets (standard npm behavior)."""
    mock_run = mock_get_sandbox.return_value.run_command
    mock_run.return_value = {"status": "success", "output": "Tests passed"}
    
    run_tests(framework="npm", target="tests/test_api.js")

    mock_run.assert_called_once_with(["npm", "test"], timeout_seconds=60)

@patch("tools.terminal_tools.get_sandbox")
def test_run_tests_invalid_framework(mock_get_sandbox):
    """Edge Case: Rejects unsupported test frameworks."""
    mock_run = mock_get_sandbox.return_value.run_command
    
    res = run_tests(framework="jest")

    assert res["status"] == "error"
    assert "Framework must be 'pytest' or 'npm'" in res["output"]
    mock_run.assert_not_called()