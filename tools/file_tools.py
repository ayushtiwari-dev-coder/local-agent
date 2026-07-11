
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
    full_path = os.path.abspath(os.path.join(sandbox_root, path))
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
    if not filename.lower().endswith('.pdf'):
        filename += '.pdf'
        
    safe_path = _resolve_safe_path(filename)
    if safe_path is None:
        return f"Error: Path '{filename}' is outside the allowed workspace."
        
    # 1. Auto-Sanitize unsupported Unicode characters to prevent PDF crashes
    markdown_content = markdown_content.replace('—', '-').replace('–', '-')
    markdown_content = markdown_content.replace('“', '"').replace('”', '"')
    markdown_content = markdown_content.replace('‘', "'").replace('’', "'")
    markdown_content = markdown_content.replace('…', '...')
        
    try:
        # 2. Convert Markdown to HTML WITH table support enabled
        html_body = markdown.markdown(markdown_content, extensions=['tables', 'fenced_code'])
        
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


 #ACTIVE EXECUTOR (RAM-Free Local Host Mode)
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
