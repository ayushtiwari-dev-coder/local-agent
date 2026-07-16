# tools/static_analyzer.py
import os
import re
import ast
import logging

logger = logging.getLogger("tools.static_analyzer")

# Max file size to scan (e.g., 2MB).
MAX_SCAN_SIZE_BYTES = 2 * 1024 * 1024

# 1. AST Visitor for Smart Python Analysis
class PythonSecurityVisitor(ast.NodeVisitor):
    """
    Smart AST parser that allows safe OS operations (like moving files) 
    but strictly blocks terminal execution and sneaky code evaluation.
    """
    def __init__(self):
        self.violations = []
        # Modules that are completely banned
        self.banned_modules = {"pty", "subprocess", "importlib"}
        
        # Specific functions that are banned
        self.banned_calls = {
            "eval", "exec", "__import__", "compile", "globals", "locals",
            "os.system", "os.popen", "shutil.rmtree"
        }
        self.aliases = {} # Tracks imports like `import os as my_os`

    def visit_Import(self, node):
        for alias in node.names:
            name = alias.name
            asname = alias.asname or name
            self.aliases[asname] = name
            if name in self.banned_modules:
                self.violations.append(f"Banned module imported: {name}")
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        if node.module in self.banned_modules:
            self.violations.append(f"Banned module imported: {node.module}")
        for alias in node.names:
            name = f"{node.module}.{alias.name}" if node.module else alias.name
            asname = alias.asname or alias.name
            self.aliases[asname] = name
        self.generic_visit(node)

    def visit_Call(self, node):
        func_name = self._get_full_name(node.func)
        if func_name:
            resolved_name = self._resolve_alias(func_name)
            if self._is_banned(resolved_name):
                self.violations.append(f"Banned function call detected: {resolved_name}")
        self.generic_visit(node)

    def _get_full_name(self, node):
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            value_name = self._get_full_name(node.value)
            if value_name:
                return f"{value_name}.{node.attr}"
        return None

    def _resolve_alias(self, name):
        parts = name.split('.')
        base = parts[0]
        if base in self.aliases:
            parts[0] = self.aliases[base]
        return ".".join(parts)

    def _is_banned(self, name):
        if name in self.banned_calls:
            return True
        # Catch all os.exec*, os.spawn*, os.fork* variants
        if name.startswith("os.exec") or name.startswith("os.spawn") or name.startswith("os.fork"):
            return True
        # Catch any subprocess calls if they bypassed the import block
        if name.startswith("subprocess."):
            return True
        return False


# 2. Regex Signatures for Non-Python Languages
_RAW_SIGNATURES = {
    # JavaScript / TypeScript / Node.js
    ".js": [
        r"require\s*\(\s*['\"](child_process|fs|os|net|http|https)['\"]\s*\)",
        r"import\s+.*?\s+from\s+['\"](child_process|fs|os|net|http|https)['\"]",
        r"eval\s*\(", r"exec\s*\(", r"spawn\s*\("
    ],
    ".ts": [
        r"import\s+.*?\s+from\s+['\"](child_process|fs|os|net|http|https)['\"]",
        r"Deno\.run", r"eval\s*\("
    ],
    # C / C++
    ".c": [r"system\s*\(", r"exec[lvpe]*\s*\(", r"remove\s*\("],
    ".cpp": [r"system\s*\(", r"exec[lvpe]*\s*\(", r"remove\s*\("],
    ".h": [r"system\s*\(", r"exec[lvpe]*\s*\("],
    # Java
    ".java": [
        r"Runtime\.getRuntime\(\)\.exec",
        r"new\s+ProcessBuilder",
        r"File\.delete\(\)"
    ],
    # Rust
    ".rs": [
        r"std::process::Command",
        r"std::fs::remove_file",
        r"std::fs::remove_dir_all"
    ],
    # Shell / Bash
    ".sh": [r"rm\s+-r", r">\s*/dev/", r"mkfs", r"wget\s+", r"curl\s+"]
}

_COMPILED_SIGNATURES = {}
for ext, patterns in _RAW_SIGNATURES.items():
    combined_pattern = f"({'|'.join(patterns)})"
    _COMPILED_SIGNATURES[ext] = re.compile(combined_pattern)


def scan_file_for_threats(filepath: str) -> tuple[bool, str | None]:
    """
    Reads a file and scans it against AST (for Python) or Regex (for others).
    Returns (is_safe, error_reason).
    """
    if not os.path.exists(filepath):
        return True, None

    if os.path.getsize(filepath) > MAX_SCAN_SIZE_BYTES:
        return False, f"File exceeds maximum scan size of {MAX_SCAN_SIZE_BYTES/1024/1024}MB."

    _, ext = os.path.splitext(filepath)
    ext = ext.lower()

    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()

        # --- SMART AST PARSING FOR PYTHON ---
        if ext in [".py", ".pyw"]:
            try:
                tree = ast.parse(content, filename=filepath)
                visitor = PythonSecurityVisitor()
                visitor.visit(tree)
                
                if visitor.violations:
                    return False, f"Malicious AST signatures detected: {', '.join(visitor.violations)}"
                return True, None
                
            except SyntaxError as e:
                return False, f"Syntax error in Python file (could be obfuscation): {e}"
            except Exception as e:
                return False, f"AST parsing failed: {e}"

        # --- REGEX PARSING FOR OTHER LANGUAGES ---
        if ext not in _COMPILED_SIGNATURES:
            return True, None  # Not a known script extension, treat as safe text/data

        compiled_regex = _COMPILED_SIGNATURES[ext]
        match = compiled_regex.search(content)
        if match:
            dangerous_code = match.group(0).strip()
            return False, f"Malicious signature detected in {ext} file: '{dangerous_code}'"

        return True, None

    except Exception as e:
        logger.error(f"Failed to scan file {filepath}: {e}")
        return False, f"Static analysis failed: {e}"