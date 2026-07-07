# tools/security_guard.py

import re
import shlex

# 1. STRICT WHITELIST: Only these base commands are allowed to even reach the user prompt.
ALLOWED_COMMANDS = {
    "python",
    "python3",
    "pip",
    "pip3",
    "node",
    "npm",
    "npx",
    "yarn",
    "ls",
    "cd",
    "pwd",
    "cat",
    "echo",
    "grep",
    "find",
    "mkdir",
    "touch",
    "cp",
    "mv",
    "rm",
    "tree",
    "head",
    "tail",
    "git",
    "pytest",
    "bash",
    "sh",
    "apt",
    "apt-get",
    "apk",
}


def check_command_safety(command: str) -> tuple[bool, str | None]:
    """
    Scans a shell command against a strict whitelist of allowed commands.
    Prevents bypasses via command chaining (; && || |) and command substitution.
    Returns (is_safe, warning_reason).
    """
    cmd_str = command.strip()

    # 1. Block command substitution which can hide malicious commands
    if re.search(r"\$\(.*?\)|`.*?`", cmd_str):
        return False, "Command substitution ($(cmd) or `cmd`) is not allowed."

    # 2. Split the command by shell operators to validate EVERY chained command
    try:
        segments = re.split(r";|\||&&|\|\|", cmd_str)
    except Exception as e:
        return False, f"Failed to parse command structure: {e}"

    for segment in segments:
        segment = segment.strip()
        if not segment:
            continue

        try:
            # shlex safely parses the command respecting quotes
            tokens = shlex.split(segment)
            if not tokens:
                continue

            base_cmd = tokens[0]
            base_cmd_name = base_cmd.split("/")[-1]

            if base_cmd_name not in ALLOWED_COMMANDS:
                return (
                    False,
                    f"Command '{base_cmd_name}' is not in the allowed whitelist.",
                )

            # 3. Additional strict checks for specific commands (e.g., rm)
            if base_cmd_name == "rm":
                if any(arg in tokens for arg in ["-rf", "-r", "-f", "-R"]):
                    if "/" in tokens or "/*" in tokens or "~" in tokens:
                        return (
                            False,
                            "Destructive 'rm' command detected on critical path.",
                        )

        except ValueError as e:
            return False, f"Malformed command syntax (e.g., unclosed quotes): {e}"

    return True, None
