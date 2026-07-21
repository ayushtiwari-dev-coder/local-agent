import os
import re
import ast
import logging

logger = logging.getLogger("tools.static_analyzer")

# Max file size to scan (2MB). Source code files are rarely larger than this.
MAX_SCAN_SIZE_BYTES = 2 * 1024 * 1024

# ---------------------------------------------------------
# 1. PYTHON AST ANALYZER (Structure & Intention Based)
# ---------------------------------------------------------
class PythonSecurityVisitor(ast.NodeVisitor):
    def __init__(self):
        self.is_safe = True
        self.reason = None
        
        # System access / networking modules
        self.blocked_imports = {
            'os', 'subprocess', 'pty', 'shutil', 
            'socket', 'requests', 'urllib', 'sys'
        }
        
        # Dynamic execution primitives & blocking I/O
        self.blocked_calls = {
            'eval', 'exec', '__import__', 'input', 'compile'
        }

    def visit_Import(self, node: ast.Import):
        for alias in node.names:
            base_module = alias.name.split('.')[0]
            if base_module in self.blocked_imports:
                self.is_safe = False
                self.reason = f"Malicious signature detected in .py file: 'import {alias.name}'"
                return
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        if node.module:
            base_module = node.module.split('.')[0]
            if base_module in self.blocked_imports:
                self.is_safe = False
                self.reason = f"Malicious signature detected in .py file: 'from {node.module} import ...'"
                return
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call):
        # Direct calls: eval(), exec(), input()
        if isinstance(node.func, ast.Name):
            if node.func.id in self.blocked_calls:
                self.is_safe = False
                self.reason = f"Malicious signature detected in .py file: '{node.func.id}'"
                return

        # Attribute calls: getattr(builtins, 'eval')
        elif isinstance(node.func, ast.Attribute):
            if node.func.attr in self.blocked_calls:
                self.is_safe = False
                self.reason = f"Malicious signature detected in .py file: '{node.func.attr}'"
                return

        self.generic_visit(node)

def _scan_python_ast(content: str) -> tuple[bool, str | None]:
    try:
        tree = ast.parse(content)
        visitor = PythonSecurityVisitor()
        visitor.visit(tree)
        return visitor.is_safe, visitor.reason
    except SyntaxError as e:
        return False, f"Static analysis failed due to Python syntax error: {e}"

# ---------------------------------------------------------
# 2. REGEX SIGNATURES FOR NON-PYTHON LANGUAGES
# ---------------------------------------------------------
_RAW_SIGNATURES = {
    # JavaScript / Node.js
    ".js": [
        r"require\s*\(\s*['\"](child_process|fs|os|net|http|https)['\"]\s*\)",
        r"import\s+.*?\s+from\s+['\"](child_process|fs|os|net|http|https)['\"]",
        r"eval\s*\(",
        r"exec\s*\(",
        r"spawn\s*\(",
    ],
    # TypeScript
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

# Pre-compile regex patterns for performance
_COMPILED_SIGNATURES = {}
for ext, patterns in _RAW_SIGNATURES.items():
    combined_pattern = f"({'|'.join(patterns)})"
    _COMPILED_SIGNATURES[ext] = re.compile(combined_pattern)

def _scan_regex(content: str, ext: str) -> tuple[bool, str | None]:
    compiled_regex = _COMPILED_SIGNATURES.get(ext)
    if not compiled_regex:
        return True, None

    match = compiled_regex.search(content)
    if match:
        dangerous_code = match.group(0).strip()
        return False, f"Malicious signature detected in {ext} file: '{dangerous_code}'"
    return True, None

# ---------------------------------------------------------
# 3. MAIN ROUTER
# ---------------------------------------------------------
def scan_file_for_threats(filepath: str) -> tuple[bool, str | None]:
    """
    Reads a file and scans it against static analysis rules.
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

    # Unmonitored extensions (e.g. .txt, .md, .json) pass through safely
    if ext not in [".py", ".pyw"] and ext not in _COMPILED_SIGNATURES:
        return True, None

    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()

        if ext in [".py", ".pyw"]:
            return _scan_python_ast(content)
        else:
            return _scan_regex(content, ext)

    except Exception as e:
        logger.error(f"Failed to scan file {filepath}: {e}")
        return False, f"Static analysis failed: {e}"