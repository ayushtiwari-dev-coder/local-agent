# tools/security_guard.py
import re

# Common dangerous or destructive commands/patterns
DESTRUCTIVE_PATTERNS = [
    (r"\brm\s+-[rf]+\b", "Recursive deletion command ('rm -rf')"),
    (r"\bshred\b", "File shredding/wiping tool ('shred')"),
    (r"\bformat\b", "Disk formatting command ('format')"),
    (r"\bmkfs\b", "Filesystem creation tool ('mkfs')"),
    (r"\bdd\s+if=\b", "Direct sector disk writes ('dd')"),
    (r"\bchown\b", "Host file ownership modification ('chown')"),
    (r"\bchmod\b", "File permissions adjustments ('chmod')"),
    (r"\b(?:parted|fdisk|gparted)\b", "Disk partition utility"),
    (r"\b(?:sudo|su)\b", "Root privilege escalation attempt"),
    (r"\b(?:wget|curl)\b.*\b\|\s*(?:bash|sh)\b", "Piping remote internet scripts directly to raw shell"),
    (r"\b(?:shutdown|reboot|poweroff)\b", "System state changes"),
]

def check_command_safety(command: str) -> tuple[bool, str | None]:
    """
    Scans a shell command against a set of destructive patterns.
    Returns (is_safe, match_description).
    """
    cmd_lower = command.lower()
    
    for pattern, description in DESTRUCTIVE_PATTERNS:
        if re.search(pattern, cmd_lower):
            return False, description
            
    return True, None