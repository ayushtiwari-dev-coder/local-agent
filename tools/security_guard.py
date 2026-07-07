# tools/security_guard.py

import re
import shlex

# 1. STRICT WHITELIST: Only these base commands are allowed to even reach the user prompt.
ALLOWED_COMMANDS = {
    "python", "python3", "pip", "pip3", "node", "npm", "npx", "yarn",
    "ls", "cd", "pwd", "cat", "echo", "grep", "find", "mkdir", "touch",
    "cp", "mv", "rm", "tree", "head", "tail", "git", "pytest", "bash", "sh",
    "apt", "apt-get", "apk"
}

def check_command_safety(command: str) -> tuple[bool, str | None]:
    """
    Scans a shell command against a strict whitelist of allowed commands.
    Prevents bypasses via command chaining, redirection, and command substitution.
    Returns (is_safe, warning_reason).
    """
    cmd_str = command.strip()

    # 1. Block command substitution which can hide malicious commands
    if re.search(r"\$\(.*?\)|`.*?`", cmd_str):
        return False, "Command substitution ($(cmd) or `cmd`) is not allowed."

    # 2. Block background execution (prevents rogue detached processes)
    if cmd_str.endswith("&") or " & " in cmd_str:
        return False, "Background execution (&) is not allowed."

    # 3. Split the command by shell operators to validate EVERY chained command
    try:
        segments = re.split(r";|\|\||\||&&", cmd_str)
    except Exception as e:
        return False, f"Failed to parse command structure: {e}"

    for segment in segments:
        segment = segment.strip()
        if not segment:
            continue

        # 4. Redirection Safety Check (CRITICAL)
        if ">" in segment or ">>" in segment:
            redir_parts = re.split(r">+", segment)
            if len(redir_parts) > 1:
                target = redir_parts[-1].strip()
                if target.startswith("/") or target.startswith("~") or ".." in target:
                    return False, f"Redirection to outside paths is blocked: {target}"

        try:
            # shlex safely parses the command respecting quotes
            tokens = shlex.split(segment)
            if not tokens:
                continue
            
            # Handle environment variable assignments before the command
            cmd_idx = 0
            while cmd_idx < len(tokens) and "=" in tokens[cmd_idx]:
                cmd_idx += 1
            
            if cmd_idx >= len(tokens):
                continue  # Only environment variables were set, which is safe
            
            base_cmd = tokens[cmd_idx]
            base_cmd_name = base_cmd.split("/")[-1]

            if base_cmd_name not in ALLOWED_COMMANDS:
                return False, f"Command '{base_cmd_name}' is not in the allowed whitelist."

            # 5. INLINE SCRIPT BYPASS PREVENTION (The fix for your failing test!)
            # Blocks `bash -c`, `python -c`, and `node -e` which hide malicious payloads
            if base_cmd_name in {"bash", "sh", "python", "python3", "node"}:
                if "-c" in tokens or "-e" in tokens or "--eval" in tokens:
                    return False, f"Inline execution ({base_cmd_name} -c/-e) is blocked to prevent bypasses."

            # 6. Strict Path Checks for ALL Destructive Commands (rm, mv, cp)
            if base_cmd_name in {"rm", "mv", "cp"}:
                for arg in tokens[cmd_idx+1:]:
                    if arg.startswith("-"):
                        continue
                    if arg.startswith("/") or arg.startswith("~") or ".." in arg:
                        return False, f"Destructive command '{base_cmd_name}' targeting outside path: {arg}"

        except ValueError as e:
            return False, f"Malformed command syntax (e.g., unclosed quotes): {e}"

    return True, None