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
import fitz  
import pymupdf4llm

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
    # 1. Get the root and resolve any symlinks/casing issues (CRITICAL FOR WINDOWS)
    sandbox_root = os.path.realpath(get_sandbox_root())
    
    # 2. Strip leading slashes so os.path.join doesn't treat it as an absolute path
    clean_path = path.lstrip("/\\")
    
    # 3. Join and resolve the final target path
    full_path = os.path.realpath(os.path.join(sandbox_root, clean_path))
    
    # 4. Safely check if the target path is inside the sandbox root
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
def get_file_skeletons(paths: list[str]) -> dict:
    """
    Generates a line-numbered table of contents (skeleton) for multiple code/markdown files at once.
    CRITICAL: Always pass a list of paths, e.g., ["src/main.py", "README.md"].
    """
    if not isinstance(paths, list):
        return {"error": "Expected a list of paths."}
        
    results = {}
    for path in paths:
        safe_path = _resolve_safe_path(path)
        if safe_path is None:
            results[path] = "Error: Path is outside allowed workspace."
            continue
        if not os.path.exists(safe_path):
            results[path] = "Error: File not found."
            continue
            
        try:
            with open(safe_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            filename = os.path.basename(safe_path)
            skeleton = generate_file_skeleton(content, filename)
            results[path] = skeleton if skeleton else "No structural skeleton detected."
        except Exception as e:
            results[path] = f"Error generating skeleton: {e}"
            
    return results


@agent_tool
def read_file_chunks(chunks: list[dict]) -> dict:
    """
    Reads specific ranges of lines from multiple files at once.
    Args:
        chunks: A list of objects. e.g., [{"path": "main.py", "start_line": 10, "end_line": 20}]
    """
    if not isinstance(chunks, list):
        return {"error": "Expected a list of chunk objects."}
        
    results = {}
    for chunk in chunks:
        path = chunk.get("path")
        start_line = chunk.get("start_line", 1)
        end_line = chunk.get("end_line", 100)
        
        chunk_id = f"{path}:{start_line}-{end_line}"
        safe_path = _resolve_safe_path(path)
        
        if safe_path is None or not os.path.isfile(safe_path):
            results[chunk_id] = "Error: Invalid file or outside workspace."
            continue
            
        try:
            with open(safe_path, "r", encoding="utf-8", errors="replace") as f:
                lines = []
                for i, line in enumerate(f):
                    if i + 1 > end_line: break
                    if i + 1 >= start_line: lines.append(f"Line {i + 1}: {line.rstrip()}")
            results[chunk_id] = "\n".join(lines) if lines else "No content found in range."
        except Exception as e:
            results[chunk_id] = f"Error reading chunk: {e}"
            
    return results


@agent_tool
def search_inside_files(searches: list[dict]) -> dict:
    """
    Searches for exact strings inside multiple files simultaneously.
    Args:
        searches: A list of objects. e.g., [{"path": "main.py", "search_term": "def login", "context_lines": 2}]
    """
    if not isinstance(searches, list):
        return {"error": "Expected a list of search objects."}
        
    results = {}
    for req in searches:
        path = req.get("path")
        term = req.get("search_term", "")
        
        # DEFENSIVE TYPE-GUARD: If the LLM SDK explicitly passes null/None, fallback to default
        ctx = req.get("context_lines")
        if ctx is None:
            ctx = 2
        else:
            ctx = int(ctx)
            
        search_id = f"{path} -> '{term}'"
        
        safe_path = _resolve_safe_path(path)
        if safe_path is None or not os.path.isfile(safe_path):
            results[search_id] = "Error: Invalid file or outside workspace."
            continue
            
        try:
            with open(safe_path, "r", encoding="utf-8", errors="replace") as f:
                all_lines = f.readlines()
                
            matched_indices = set()
            match_output = []
            
            for i, line in enumerate(all_lines):
                if term.lower() in line.lower():
                    start = max(0, i - ctx)
                    end = min(len(all_lines), i + ctx + 1)
                    for j in range(start, end):
                        if j not in matched_indices:
                            match_output.append(f"Line {j + 1}: {all_lines[j].rstrip()}")
                            matched_indices.add(j)
                    match_output.append("---")
            
            final_output = "\n".join(match_output).strip()
            results[search_id] = final_output if final_output else "No matches found."
        except Exception as e:
            results[search_id] = f"Error: {e}"
            
    return results



@agent_tool
def list_workspace_directory(max_depth: int = 4) -> str:
    """
    Generates a visual, tree-like layout of all folders and files inside the workspace.
    CRITICAL: Use this at the start of a session to locate files and folders.
    """
    try:
        sandbox_root = get_sandbox_root()
        
        # EXPANDED JUNK EXCLUSIONS (Saves massive amounts of context tokens!)
        ignore_dirs = {
            # Package / Dependency folders
            "node_modules", "vendor", "target", "Pods",
            
            # Build / Compiler output folders
            "dist", "build", "out", ".next", ".nuxt", ".output", "coverage", ".turbo", ".nx",
            
            # Version Control & IDEs
            ".git", ".svn", ".hg", ".idea", ".vscode", ".vs",
            
            # Python / Caching / Virtual Envs
            "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".local_workflow_agent",
            ".venv", "venv", "env", "ENV",
        }
        
        # Individual massive/useless files to ignore in the tree
        ignore_files = {
            ".DS_Store", "Thumbs.db", 
            "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "Cargo.lock"
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
                # Skip ignored directories OR ignored files
                if item in ignore_dirs or item in ignore_files:
                    continue

                path = os.path.join(directory, item)
                is_last = idx == len(items) - 1
                connector = "└── " if is_last else "├── "

                if os.path.isdir(path):
                    lines.append(f"{prefix}{connector}{item}/")
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

@agent_tool
def read_pdf(path: str, pages: list[int] = None) -> str:
    """
    Reads a PDF file and converts it to clean Markdown.
    CRITICAL: For PDFs containing 5 pages or fewer:
- Read the entire document in a single call.
- Do not reread individual pages unless the user explicitly requests it.

For larger PDFs:
1. Read the opening pages.
2. Locate the table of contents if present.
3. Read only the relevant page ranges.
4. Avoid repeatedly rereading pages that have already been processed.
    
    Args:
        path: The path to the PDF file inside the workspace.
        pages: Optional. A list of specific 1-based page numbers to read (e.g., [1, 2, 10]). 
               If empty, reads the document (but caps at 5 pages for large files).
    """
    safe_path = _resolve_safe_path(path)
    if safe_path is None:
        return f"Error: Path '{path}' is outside the allowed workspace."
    
    if not os.path.exists(safe_path):
        return f"Error: File '{path}' not found."
        
    if not safe_path.lower().endswith(".pdf"):
        return "Error: File is not a PDF."

    try:
        # 1. Quickly check the total page count
        doc = fitz.open(safe_path)
        total_pages = len(doc)
        doc.close()
        
        warning_msg = ""
        
        # 2. Smart Chunking Logic to protect the LLM's memory
        if not pages:
            if total_pages > 10:
                # If it's a big book, only read the first 5 pages by default
                pages = list(range(1, 6))
                warning_msg = (
                    f"\n\n> **SYSTEM NOTE:** This PDF is massive ({total_pages} pages). "
                    f"To protect your memory, only pages 1-5 were extracted. "
                    f"Please call `read_pdf` again using the `pages` argument to read specific sections."
                )
            else:
                # If it's short, read the whole thing
                pages = list(range(1, total_pages + 1))
        
        # 3. Validate requested pages
        valid_pages = []
        for p in pages:
            if 1 <= p <= total_pages:
                valid_pages.append(p - 1)  # Convert 1-based to 0-based for PyMuPDF
            else:
                return f"Error: Page {p} is out of bounds. The PDF only has {total_pages} pages."

        # 4. Extract to Markdown
        md_text = pymupdf4llm.to_markdown(safe_path, pages=valid_pages)
        
        if not md_text.strip():
            return f"Success: Read pages {pages}, but no extractable text was found (it might be a scanned image)."
            
        return md_text + warning_msg
        
    except Exception as e:
        logger.exception(f"Failed to read PDF '{path}': {e}")
        return f"Error: Failed to read PDF: {e}"

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