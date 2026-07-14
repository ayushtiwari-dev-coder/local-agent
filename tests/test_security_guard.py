# tests/test_security_guard.py
import pytest
from security.security_guard import check_command_safety


def test_allowed_commands():
    """Ensures safe commands pass the whitelist."""
    safe_commands = [
        "echo 'Hello World'",
        "python3 script.py",
        "ls -la",
        "cat file.txt | grep 'error'",
        "mkdir new_folder",
    ]
    for cmd in safe_commands:
        is_safe, reason = check_command_safety(cmd)
        assert is_safe is True, f"Blocked incorrectly: {reason}"


def test_blocked_commands():
    """Ensures commands not in the whitelist are blocked."""
    unsafe_commands = ["wget http://virus.com", "sudo apt-get install nmap"]
    for cmd in unsafe_commands:
        is_safe, reason = check_command_safety(cmd)
        assert is_safe is False
        assert "not in the allowed whitelist" in reason


def test_destructive_rm_flags():
    """Ensures destructive targeting is blocked."""
    is_safe, reason = check_command_safety("rm -rf /")
    assert is_safe is False
    assert "targeting outside path" in reason


def test_allowed_commands():
    """Ensures safe commands pass the whitelist."""
    safe_commands = [
        "echo 'Hello World'",
        "python3 script.py",
        "ls -la",
        "cat file.txt | grep 'error'",
        "mkdir new_folder",
    ]
    for cmd in safe_commands:
        is_safe, reason = check_command_safety(cmd)
        assert is_safe is True, f"Blocked incorrectly: {reason}"


def test_blocked_commands():
    """Ensures commands not in the whitelist are blocked."""
    unsafe_commands = ["wget http://virus.com", "sudo apt-get install nmap"]
    for cmd in unsafe_commands:
        is_safe, reason = check_command_safety(cmd)
        assert is_safe is False
        assert "not in the allowed whitelist" in reason


def test_command_chaining_and_substitution():
    """Security: Blocks command injection techniques."""
    injections = [
        "echo 'hi'; rm -rf /",  # Semicolon chaining
        "echo 'hi' && rm -rf /",  # AND chaining
        "echo 'hi' || rm -rf /",  # OR chaining
        "echo $(rm -rf /)",  # $() substitution
        "echo `rm -rf /`",  # Backtick substitution
        "echo 'hi'\nrm -rf /",  # Newline injection
        "echo 'hi'\rrm -rf /",  # Carriage return injection
        "echo 'hi'&rm -rf /",  # Unspaced background/chaining
    ]

    for cmd in injections:
        is_safe, reason = check_command_safety(cmd)
        assert is_safe is False
        assert (
            "not in the allowed whitelist" in reason
            or "substitution" in reason
            or "targeting outside path" in reason
            or "Background execution" in reason
            or "Command substitution" in reason
        )


def test_destructive_rm_flags():
    """Ensures destructive targeting is blocked."""
    is_safe, reason = check_command_safety("rm -rf /")
    assert is_safe is False
    assert "targeting outside path" in reason
