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
    Generates a line-numbered table of contents (skeleton) for code and markdown files.
    Useful for understanding the structure of a large file before reading specific chunks.

    Args:
        path: The path to the file.
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
            content = f.read()

        filename = os.path.basename(safe_path)
        # CALL THE ORCHESTRATOR
        skeleton = generate_file_skeleton(content, filename)
        if not skeleton:
            return f"No structural skeleton detected for '{filename}'."
        return skeleton
    except Exception as e:
        logger.exception(f"Failed to generate skeleton for '{path}': {e}")
        return f"Error: Failed to generate skeleton: {e}"


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
def search_inside_file(path: str, search_term: str, context_lines: int = 2) -> str:
    """
    Searches for an exact string inside a file and returns the matching lines with surrounding context.
    CRITICAL: Use this when a file has no skeleton, or when you need to find a specific variable, error, or keyword.

    Args:
        path: The path to the file.
        search_term: The exact string to search for (case-insensitive).
        context_lines: Number of lines to include before and after the match (default 2).
    """
    # DEFENSIVE TYPE-GUARD: If the LLM SDK explicitly passes null/None, fallback to default
    if context_lines is None:
        context_lines = 2
    else:
        context_lines = int(context_lines)

    safe_path = _resolve_safe_path(path)
    if safe_path is None:
        return f"Error: Path '{path}' is outside the allowed workspace."
    if not os.path.exists(safe_path):
        return f"Error: File '{path}' not found."

    try:
        with open(safe_path, "r", encoding="utf-8", errors="replace") as f:
            all_lines = f.readlines()

        results = []
        matched_indices = set()

        for i, line in enumerate(all_lines):
            if search_term.lower() in line.lower():
                start = max(0, i - context_lines)
                end = min(len(all_lines), i + context_lines + 1)

                for j in range(start, end):
                    if j not in matched_indices:
                        results.append(f"Line {j + 1}: {all_lines[j].rstrip()}")
                        matched_indices.add(j)
                results.append("---")

        if not results:
            return f"No matches found for '{search_term}' in {path}."

        return "\n".join(results).strip()
    except Exception as e:
        logger.exception(f"Failed to search in '{path}': {e}")
        return f"Error: Failed to search file: {e}"


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


@agent_tool
def edit_file_chunk(path: str, start_line: int, end_line: int, content: str) -> str:
    """
    Surgically replaces a specific range of lines in a file with new content.
    CRITICAL: Use this instead of write_files when editing existing large files.
    This saves massive completion tokens and keeps edits precise. Lines are 1-indexed.

    Args:
        path: The path to the file inside the workspace.
        start_line: The 1-based line number where the replacement should begin (inclusive).
        end_line: The 1-based line number where the replacement should end (inclusive).
        content: The new text content to insert into the specified line range.
    """
    safe_path = _resolve_safe_path(path)
    if safe_path is None:
        return f"Error: Path '{path}' is outside the allowed workspace."

    if not os.path.exists(safe_path):
        return f"Error: File '{path}' not found. Cannot surgically edit a non-existent file."

    if not os.path.isfile(safe_path):
        return f"Error: '{path}' is not a file."

    if start_line < 1 or end_line < start_line:
        return f"Error: Invalid line range {start_line} to {end_line}. Line numbers must be positive and start_line <= end_line."

    try:
        # 1. Read existing lines
        with open(safe_path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()

        total_lines = len(lines)

        # 2. Adjust boundaries defensively
        # Convert 1-indexed input to 0-indexed list indices
        idx_start = start_line - 1
        idx_end = end_line  # Slice is exclusive at end, which matches end_line inclusive in 1-index

        # Handle edge case where targeted start is completely out of bounds
        if idx_start > total_lines:
            return f"Error: start_line {start_line} is out of bounds. The file only has {total_lines} lines."

        # 3. Format incoming content into lines
        # Ensure we maintain line endings
        new_lines = [
            line + "\n" if not line.endswith("\n") else line
            for line in content.splitlines()
        ]
        if content.endswith("\n") or not content:
            new_lines.append("\n")

        # 4. Perform the surgical replacement
        lines[idx_start:idx_end] = new_lines

        # 5. Write the file back to disk
        with open(safe_path, "w", encoding="utf-8") as f:
            f.writelines(lines)

        return f"Success: Surgically updated lines {start_line} through {end_line} in '{path}' successfully."

    except Exception as e:
        logger.exception(f"Failed to surgically edit file '{path}': {e}")
        return f"Error: Failed to edit file chunk: {e}"


# ACTIVE EXECUTOR (RAM-Free Local Host Mode)
_sandbox = LocalSandboxExecutor(get_sandbox_root())

# =====================================================================
# FUTURE DOCKER ACTIVATION INSTRUCTIONS:
# If you eventually install Docker Desktop and want to activate containment,
# restore Docker files from optional_docker_extension/ and uncomment below:
#
# from tools.sandbox_executor import DockerSandboxExecutor
# _sandbox = DockerSandboxExecutor(get_sandbox_root())
# =====================================================================


@agent_tool
def run_terminal_command(command: str) -> dict:
    """
    Executes a shell command natively inside the safe local workspace directory.
    Use this to run Python scripts, install packages, or interact with the file system.
    """
    return _sandbox.run_command(command)
