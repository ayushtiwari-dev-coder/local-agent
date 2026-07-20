# tests/test_terminal_tools.py

import pytest
from unittest.mock import patch
from tools.terminal_tools import run_script, manage_dependencies, run_tests

# =====================================================================
# 1. TESTS FOR run_script
# =====================================================================

@patch("tools.terminal_tools._sandbox.run_command")
def test_run_script_valid_python(mock_run):
    """Happy Path: Ensures Python scripts run correctly with arguments."""
    mock_run.return_value = {"status": "success", "output": "Hello World"}
    
    res = run_script(language="python", filepath="main.py", args=["--verbose", "-p", "8080"])
    
    # Assert the command was built as a safe list
    mock_run.assert_called_once_with(["python", "main.py", "--verbose", "-p", "8080"])
    assert res["status"] == "success"
    assert res["output"] == "Hello World"

@patch("tools.terminal_tools._sandbox.run_command")
def test_run_script_valid_node(mock_run):
    """Happy Path: Ensures Node scripts run correctly without arguments."""
    mock_run.return_value = {"status": "success", "output": "Server started"}
    
    res = run_script(language="node", filepath="app.js")
    
    mock_run.assert_called_once_with(["node", "app.js"])
    assert res["status"] == "success"

@patch("tools.terminal_tools._sandbox.run_command")
def test_run_script_invalid_language(mock_run):
    """Edge Case: Rejects unsupported languages (like bash or ruby)."""
    res = run_script(language="bash", filepath="script.sh")
    
    assert res["status"] == "error"
    assert "Language must be 'python' or 'node'" in res["output"]
    mock_run.assert_not_called()  # Ensure it never reached the OS


# =====================================================================
# 2. TESTS FOR manage_dependencies
# =====================================================================

@patch("tools.terminal_tools._sandbox.run_command")
def test_manage_dependencies_pip_install_specific(mock_run):
    """Happy Path: Installs specific pip packages."""
    manage_dependencies(manager="pip", action="install", packages=["requests", "numpy"])
    
    mock_run.assert_called_once_with(["pip", "install", "requests", "numpy"])

@patch("tools.terminal_tools._sandbox.run_command")
def test_manage_dependencies_npm_install_all(mock_run):
    """Happy Path: Runs general npm install when no packages are provided."""
    manage_dependencies(manager="npm", action="install")
    
    mock_run.assert_called_once_with(["npm", "install"])

@patch("tools.terminal_tools._sandbox.run_command")
def test_manage_dependencies_pip_install_all(mock_run):
    """Edge Case: Runs pip install -r requirements.txt when no packages are provided."""
    manage_dependencies(manager="pip", action="install")
    
    mock_run.assert_called_once_with(["pip", "install", "-r", "requirements.txt"])

@patch("tools.terminal_tools._sandbox.run_command")
def test_manage_dependencies_invalid_manager(mock_run):
    """Edge Case: Rejects unsupported package managers."""
    res = manage_dependencies(manager="yarn", action="install")
    
    assert res["status"] == "error"
    assert "Manager must be 'pip' or 'npm'" in res["output"]
    mock_run.assert_not_called()

@patch("tools.terminal_tools._sandbox.run_command")
def test_manage_dependencies_invalid_action(mock_run):
    """Edge Case: Rejects unsupported actions (like 'update')."""
    res = manage_dependencies(manager="npm", action="update")
    
    assert res["status"] == "error"
    assert "Action must be 'install' or 'uninstall'" in res["output"]
    mock_run.assert_not_called()


# =====================================================================
# 3. TESTS FOR run_tests
# =====================================================================

@patch("tools.terminal_tools._sandbox.run_command")
def test_run_tests_pytest_with_target(mock_run):
    """Happy Path: Runs pytest on a specific file."""
    run_tests(framework="pytest", target="tests/test_api.py")
    
    mock_run.assert_called_once_with(["pytest", "tests/test_api.py"])

@patch("tools.terminal_tools._sandbox.run_command")
def test_run_tests_pytest_all(mock_run):
    """Happy Path: Runs pytest globally if no target is provided."""
    run_tests(framework="pytest")
    
    mock_run.assert_called_once_with(["pytest"])

@patch("tools.terminal_tools._sandbox.run_command")
def test_run_tests_npm(mock_run):
    """Edge Case: Runs npm test and ignores specific targets (standard npm behavior)."""
    run_tests(framework="npm", target="tests/test_api.js")
    
    mock_run.assert_called_once_with(["npm", "test"])

@patch("tools.terminal_tools._sandbox.run_command")
def test_run_tests_invalid_framework(mock_run):
    """Edge Case: Rejects unsupported test frameworks."""
    res = run_tests(framework="jest")
    
    assert res["status"] == "error"
    assert "Framework must be 'pytest' or 'npm'" in res["output"]
    mock_run.assert_not_called()