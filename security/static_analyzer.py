# tools/static_analyzer.py
import os
import re
import logging

logger = logging.getLogger("tools.static_analyzer")

# Max file size to scan (e.g., 2MB). Source code files are rarely larger than this.
MAX_SCAN_SIZE_BYTES = 2 * 1024 * 1024

# 1. Define the Raw Signatures for Top Languages
_RAW_SIGNATURES = {
    # Python
    ".py": [
        r"import\s+(os|subprocess|shutil|pty|socket|requests|urllib)",
        r"from\s+(os|subprocess|shutil|pty|socket|requests|urllib)\s+import",
        r"__import__\s*\(\s*['\"](os|subprocess|shutil|pty|socket)['\"]\s*\)",
        r"eval\s*\(",
        r"exec\s*\(",
    ],
    # JavaScript / TypeScript / Node.js
    ".js": [
        r"require\s*\(\s*['\"](child_process|fs|os|net|http|https)['\"]\s*\)",
        r"import\s+.*?\s+from\s+['\"](child_process|fs|os|net|http|https)['\"]",
        r"eval\s*\(",
        r"exec\s*\(",
        r"spawn\s*\(",
    ],
    ".ts": [
        r"import\s+.*?\s+from\s+['\"](child_process|fs|os|net|http|https)['\"]",
        r"Deno\.run",
        r"eval\s*\(",
    ],
    # C / C++
    ".c": [r"system\s*\(", r"exec[lvpe]*\s*\(", r"remove\s*\("],
    ".cpp": [r"system\s*\(", r"exec[lvpe]*\s*\(", r"remove\s*\("],
    ".h": [r"system\s*\(", r"exec[lvpe]*\s*\("],
    # Java
    ".java": [
        r"Runtime\.getRuntime\(\)\.exec",
        r"new\s+ProcessBuilder",
        r"File\.delete\(\)",
    ],
    # Rust
    ".rs": [
        r"std::process::Command",
        r"std::fs::remove_file",
        r"std::fs::remove_dir_all",
    ],
    # Shell / Bash
    ".sh": [r"rm\s+-r", r">\s*/dev/", r"mkfs", r"wget\s+", r"curl\s+"],
}

# 2. Pre-compile regex patterns into a single OR statement per language for blazing-fast speed.
_COMPILED_SIGNATURES = {}
for ext, patterns in _RAW_SIGNATURES.items():
    combined_pattern = f"({'|'.join(patterns)})"
    _COMPILED_SIGNATURES[ext] = re.compile(combined_pattern)


def scan_file_for_threats(filepath: str) -> tuple[bool, str | None]:
    """
    Reads a file and scans it against the compiled static analysis signatures.
    Returns (is_safe, error_reason).
    """
    if not os.path.exists(filepath):
        return True, None

    if os.path.getsize(filepath) > MAX_SCAN_SIZE_BYTES:
        return (
            False,
            f"File exceeds maximum scan size of {MAX_SCAN_SIZE_BYTES/1024/1024}MB.",
        )

    _, ext = os.path.splitext(filepath)
    ext = ext.lower()

    if ext not in _COMPILED_SIGNATURES:
        return True, None  # Not a known script extension, treat as safe text/data

    compiled_regex = _COMPILED_SIGNATURES[ext]

    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()

        match = compiled_regex.search(content)
        if match:
            dangerous_code = match.group(0).strip()
            return (
                False,
                f"Malicious signature detected in {ext} file: '{dangerous_code}'",
            )

        return True, None

    except Exception as e:
        logger.error(f"Failed to scan file {filepath}: {e}")
        return False, f"Static analysis failed: {e}"
