"""
File System & Workspace Tools.
These tools allow the agent to read, write, and manipulate files inside the secure local workspace.
"""

import os
import json
import subprocess
import logging
import utils.config_manager as config_manager
from security.sandbox_executor import LocalSandboxExecutor
from tools.core import agent_tool
import markdown
from xhtml2pdf import pisa

logger = logging.getLogger("tools.file_tools")
import re
from tools.skeleton_parser import generate_file_skeleton

SANDBOX_ROOT = os.path.abspath(
    os.path.join(os.path.expanduser("~"), ".local_workflow_agent", "workspace")
)
os.makedirs(SANDBOX_ROOT, exist_ok=True)


def get_sandbox_root() -> str:
    """Returns the absolute path to the sandboxed workspace root."""
    path = config_manager.get_workspace_path()
    os.makedirs(path, exist_ok=True)
    return path


def _resolve_safe_path(path: str) -> str | None:
    sandbox_root = get_sandbox_root()
    full_path = os.path.realpath(os.path.join(sandbox_root, path))
    if os.path.commonpath([full_path, sandbox_root]) != sandbox_root:
        return None
    return full_path


@agent_tool
def read_files(paths: list[str]) -> dict:
    """
    Safely reads multiple files from the sandboxed workspace in a single turn.

    Args:
        paths: A list of file paths, e.g. ["file1.txt", "src/main.py"]
    """
    if not isinstance(paths, list):
        return {"error": "Expected a list of paths."}

    unique_paths = []
    for p in paths:
        if p and p not in unique_paths:
            unique_paths.append(p)

    results = {}
    for path in unique_paths:
        safe_path = _resolve_safe_path(path)
        if safe_path is None:
            results[path] = f"Error: Path '{path}' is outside the allowed workspace."
            continue
        try:
            if not os.path.exists(safe_path):
                results[path] = "Error: File not found."
            elif os.path.isdir(safe_path):
                results[path] = "Error: Path is a directory, not a file."
            else:
                with open(safe_path, "r", encoding="utf-8", errors="replace") as f:
                    results[path] = f.read()

        except Exception as e:
            logger.exception(f"Failed to read file '{path}': {e}")
            results[path] = f"Error: Failed to read file: {e}"

    return results


@agent_tool
def write_files(files: list[dict]) -> dict:
    """
    Safely writes multiple files to disk inside the sandboxed workspace.

    Args:
        files: A list of objects, each with 'path' and 'content' keys.
               e.g. [{"path": "hello.txt", "content": "print('hi')"}]
    """
    if not isinstance(files, list):
        return {"error": "Expected a list of file objects."}

    unique_files = {}
    for file_info in files:
        if not isinstance(file_info, dict):
            continue
        path = file_info.get("path")
        content = file_info.get("content", "")
        if path:
            unique_files[path] = content

    results = {}
    for path, content in unique_files.items():
        safe_path = _resolve_safe_path(path)
        if safe_path is None:
            results[path] = f"Error: Path '{path}' is outside the allowed workspace."
            continue
        try:
            parent_dir = os.path.dirname(safe_path)
            if parent_dir and not os.path.exists(parent_dir):
                os.makedirs(parent_dir, exist_ok=True)
            with open(safe_path, "w", encoding="utf-8") as f:
                f.write(content)
            results[path] = "Success: File written successfully."
        except Exception as e:
            logger.exception(f"Failed to write file '{path}': {e}")
            results[path] = f"Error: Failed to write file: {e}"

    return results


@agent_tool
def generate_pdf(markdown_content: str, filename: str) -> str:
    """
    Converts markdown text into a beautifully formatted PDF file and saves it to the workspace.
    """
    if not filename.lower().endswith(".pdf"):
        filename += ".pdf"

    safe_path = _resolve_safe_path(filename)
    if safe_path is None:
        return f"Error: Path '{filename}' is outside the allowed workspace."

    # 1. Auto-Sanitize unsupported Unicode characters to prevent PDF crashes
    markdown_content = markdown_content.replace("—", "-").replace("–", "-")
    markdown_content = markdown_content.replace("“", '"').replace("”", '"')
    markdown_content = markdown_content.replace("‘", "'").replace("’", "'")
    markdown_content = markdown_content.replace("…", "...")

    try:
        # 2. Convert Markdown to HTML WITH table support enabled
        html_body = markdown.markdown(
            markdown_content, extensions=["tables", "fenced_code"]
        )

        # 3. Wrap in professional CSS for beautiful tables and typography
        full_html = f"""
        <html>
        <head>
            <style>
                @page {{ margin: 2cm; }}
                body {{ font-family: Helvetica, Arial, sans-serif; font-size: 12pt; line-height: 1.6; color: #333333; }}
                h1, h2, h3 {{ color: #111111; margin-bottom: 10px; }}
                p {{ margin-bottom: 15px; }}
                table {{ border-collapse: collapse; width: 100%; margin-bottom: 20px; }}
                th {{ background-color: #f2f2f2; font-weight: bold; text-align: left; border: 1px solid #dddddd; padding: 8px; }}
                td {{ border: 1px solid #dddddd; padding: 8px; }}
                code {{ background-color: #f4f4f4; padding: 2px 4px; font-family: Courier, monospace; font-size: 10pt; }}
                pre {{ background-color: #f4f4f4; padding: 10px; border: 1px solid #dddddd; }}
            </style>
        </head>
        <body>
            {html_body}
        </body>
        </html>
        """

        # 4. Render the PDF
        with open(safe_path, "wb") as pdf_file:
            pisa_status = pisa.CreatePDF(full_html, dest=pdf_file)

        if pisa_status.err:
            return f"Error: PDF generation completed with internal formatting errors."

        return f"Success: PDF generated and saved to {filename}"

    except Exception as e:
        logger.exception(f"Failed to generate PDF '{filename}': {e}")
        return f"Error: Failed to generate PDF: {e}"


@agent_tool
def get_file_skeleton(path: str) -> str:
    """
    Generates a line-numbered table of contents (skeleton) for code files.
    If 'path' is a directory, it recursively generates skeletons for all Python/JS files inside it.
    If 'path' is a file, it generates the skeleton for just that file.
    """
    safe_path = _resolve_safe_path(path)
    if safe_path is None:
        return f"Error: Path '{path}' is outside the allowed workspace."
    if not os.path.exists(safe_path):
        return f"Error: Path '{path}' not found."

    allowed_exts = (".py", ".js", ".ts", ".jsx", ".tsx")
    ignore_dirs = {".git", "node_modules", "__pycache__", ".venv", "venv"}

    def _process_single_file(filepath: str) -> str:
        try:
            with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            filename = os.path.basename(filepath)
            skeleton = generate_file_skeleton(content, filename)
            if not skeleton:
                return ""
            rel_path = os.path.relpath(filepath, get_sandbox_root())
            return f"--- SKELETON: {rel_path} ---\n{skeleton}\n"
        except Exception:
            return ""

    # Case A: Single File
    if os.path.isfile(safe_path):
        if not safe_path.endswith(allowed_exts):
            return f"Error: Only Python and JS/TS files are supported."
        result = _process_single_file(safe_path)
        return result if result else f"No structural skeleton detected for '{path}'."

    # Case B: Directory
    skeletons = []
    for root, dirs, files in os.walk(safe_path):
        dirs[:] = [d for d in dirs if d not in ignore_dirs and not d.startswith('.')]
        for file in files:
            if file.endswith(allowed_exts):
                filepath = os.path.join(root, file)
                skel = _process_single_file(filepath)
                if skel:
                    skeletons.append(skel)

    if not skeletons:
        return f"No Python or JS/TS skeletons found in directory '{path}'."
    
    # Truncate if the codebase map is absurdly large
    final_output = "\n".join(skeletons)
    if len(final_output) > 30000:
        return final_output[:30000] + "\n...[TRUNCATED: Directory too large. Target specific sub-folders.]"
    return final_output


@agent_tool
def search_codebase(regex_pattern: str, path: str = ".") -> dict:
    """
    Searches a specific file or an entire directory for a regex pattern.
    Returns matching file paths, line numbers, and the enclosing function/class context.
    Use this instead of grep.
    """
    safe_path = _resolve_safe_path(path)
    if not safe_path or not os.path.exists(safe_path):
        return {"error": f"Invalid path: {path}"}
        
    try:
        regex = re.compile(regex_pattern)
    except re.error as e:
        return {"error": f"Invalid regex pattern: {e}"}
        
    results = []
    ignore_dirs = {".git", "node_modules", "__pycache__", ".venv", "venv"}
    
    # Regex to catch Python and JS/TS function/class declarations for context scanning
    sig_regex = re.compile(r'^\s*(def |class |async def |function |const \w+\s*=\s*\(|let \w+\s*=\s*\()')
    
    def _search_file(filepath: str):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                
            for i, line in enumerate(lines):
                if regex.search(line):
                    # Scan upwards to find the enclosing function/class
                    context_sig = "global"
                    for j in range(i, -1, -1):
                        if sig_regex.match(lines[j]):
                            context_sig = lines[j].strip()
                            context_sig = context_sig.rstrip('{:').strip()
                            if len(context_sig) > 60:
                                context_sig = context_sig[:57] + "..."
                            break
                            
                    rel_path = os.path.relpath(filepath, get_sandbox_root())
                    results.append(f"{rel_path}:{i+1} [{context_sig}]: {line.strip()}")
        except UnicodeDecodeError:
            pass # Skip binary files

    if os.path.isfile(safe_path):
        _search_file(safe_path)
    else:
        for root, dirs, files in os.walk(safe_path):
            dirs[:] = [d for d in dirs if d not in ignore_dirs and not d.startswith('.')] 
            for file in files:
                if file.endswith(('.pyc', '.pdf', '.png', '.jpg', '.sqlite3')): 
                    continue
                _search_file(os.path.join(root, file))
                
    if not results:
        return {"status": "success", "output": "No matches found."}
        
    output = "\n".join(results)
    if len(output) > 15000:
        output = output[:15000] + "\n...[TRUNCATED: Too many matches, make your regex more specific]"
        
    return {"status": "success", "output": output}


@agent_tool
def replace_in_file(filepath: str, search_block: str, replace_block: str) -> dict:
    """
    Surgically replaces a specific block of code in a file with new code.
    CRITICAL: The 'search_block' MUST exactly match the existing file content, 
    including all original indentation and spacing. Provide enough context lines 
    to make the search_block unique.
    """
    safe_path = _resolve_safe_path(filepath)
    if not safe_path or not os.path.exists(safe_path):
        return {"error": f"File '{filepath}' not found."}
        
    with open(safe_path, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()
        
    # Normalize line endings to prevent OS mismatch issues
    content = content.replace("\r\n", "\n")
    search_block = search_block.replace("\r\n", "\n")
    replace_block = replace_block.replace("\r\n", "\n")
        
    occurrences = content.count(search_block)
    
    if occurrences == 0:
        return {"error": "Search block not found. Check your exact spacing/indentation."}
    if occurrences > 1:
        return {"error": "Search block is not unique. Include more context lines in your search_block."}
        
    new_content = content.replace(search_block, replace_block)
    
    with open(safe_path, "w", encoding="utf-8") as f:
        f.write(new_content)
        
    return {"status": "success", "output": f"Successfully updated '{filepath}'."}


@agent_tool
def read_file_chunk(path: str, start_line: int, end_line: int) -> str:
    """
    Reads a specific range of lines from a file.
    CRITICAL: Use this AFTER looking at a file's skeleton to read specific sections without overloading your memory.
    Lines are 1-indexed.

    Args:
        path: The path to the file.
        start_line: The line number to start reading from (inclusive, starts at 1).
        end_line: The line number to stop reading at (inclusive).
    """
    safe_path = _resolve_safe_path(path)
    if safe_path is None:
        return f"Error: Path '{path}' is outside the allowed workspace."
    if not os.path.exists(safe_path):
        return f"Error: File '{path}' not found."
    if not os.path.isfile(safe_path):
        return f"Error: '{path}' is not a file."

    try:
        with open(safe_path, "r", encoding="utf-8", errors="replace") as f:
            lines = []
            for i, line in enumerate(f):
                if i + 1 > end_line:
                    break
                if i + 1 >= start_line:
                    lines.append(f"Line {i + 1}: {line.rstrip()}")

            if not lines:
                return f"No content found between lines {start_line} and {end_line}."
            return "\n".join(lines)
    except Exception as e:
        logger.exception(f"Failed to read chunk from '{path}': {e}")
        return f"Error: Failed to read file chunk: {e}"

@agent_tool
def list_workspace_directory(max_depth: int = 4) -> str:
    """
    Generates a visual, tree-like layout of all folders and files inside the workspace.
    CRITICAL: Use this at the start of a session to locate files and folders.
    This prevents path guessing and respects sandbox boundaries.

    Args:
        max_depth: How deep to recursively search folders (default is 4).
    """
    try:
        sandbox_root = get_sandbox_root()
        ignore_dirs = {
            ".git",
            ".local_workflow_agent",
            "__pycache__",
            "node_modules",
            ".venv",
            "venv",
            ".pytest_cache",
            ".idea",
        }

        lines = ["Workspace Directory Structure:"]

        def _build_tree(directory: str, prefix: str = "", depth: int = 1):
            if depth > max_depth:
                return
            try:
                # Sort items so folders appear first, then files alphabetically
                items = sorted(
                    os.listdir(directory),
                    key=lambda x: (
                        not os.path.isdir(os.path.join(directory, x)),
                        x.lower(),
                    ),
                )
            except Exception as e:
                lines.append(f"{prefix}└── [Error reading folder: {e}]")
                return

            for idx, item in enumerate(items):
                if item in ignore_dirs:
                    continue

                path = os.path.join(directory, item)
                is_last = idx == len(items) - 1
                connector = "└── " if is_last else "├── "

                if os.path.isdir(path):
                    lines.append(f"{prefix}{connector}{item}/")
                    # Prepare prefix for nested directories
                    new_prefix = prefix + ("    " if is_last else "│   ")
                    _build_tree(path, new_prefix, depth + 1)
                else:
                    lines.append(f"{prefix}{connector}{item}")

        _build_tree(sandbox_root)
        return "\n".join(lines)
    except Exception as e:
        logger.exception(f"Failed to map directory: {e}")
        return f"Error: Failed to list workspace directory: {e}"


# Replace the bottom of tools/file_tools.py with this:

def get_sandbox() -> LocalSandboxExecutor:
    """Returns a LocalSandboxExecutor dynamically bound to the active workspace path."""
    return LocalSandboxExecutor(get_sandbox_root())

# =====================================================================
# FUTURE DOCKER ACTIVATION INSTRUCTIONS:
# If you eventually install Docker Desktop and want to activate containment,
# restore Docker files from optional_docker_extension/ and uncomment below:
#
# from tools.sandbox_executor import DockerSandboxExecutor
# _sandbox = DockerSandboxExecutor(get_sandbox_root())
# =====================================================================