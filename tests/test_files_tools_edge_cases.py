# tests/test_files_tools_edge_cases.py

import pytest
import os
import tempfile
from unittest.mock import patch, mock_open
from tools.file_tools import (
    read_files, write_files, generate_pdf, 
    read_file_chunk, list_workspace_directory,
    get_file_skeleton, search_codebase, replace_in_file
)
from tools.skeleton_parser import generate_file_skeleton

@pytest.fixture(autouse=True)
def sandbox_workspace_fixture():
    """Generates a sandboxed workspace directory for testing file read/writes."""
    temp_sandbox = tempfile.TemporaryDirectory()
    patcher = patch(
        "tools.file_tools.config_manager.get_workspace_path",
        return_value=temp_sandbox.name,
    )
    patcher.start()
    yield temp_sandbox
    patcher.stop()
    temp_sandbox.cleanup()

# =====================================================================
# 1. LEGACY TOOLS TESTS (read_files, write_files, generate_pdf)
# =====================================================================

def test_invalid_json_inputs():
    """Edge Case: Verify that passing an invalid type returns a proper type safety error."""
    bad_json = '{"path": "file.txt" -- missing brackets'
    res_read = read_files(bad_json)
    assert "error" in res_read
    assert res_read["error"] == "Expected a list of paths."

def test_path_traversal_jailbreak():
    """Security: Attempts to read or write to system paths outside workspace are blocked."""
    hacker_payload = [{"path": "../../../../../etc/passwd", "content": "hacked"}]
    res_write = write_files(hacker_payload)
    key = list(res_write.keys())[0]
    assert "Error: Path" in res_write[key]
    assert "is outside the allowed workspace" in res_write[key]

def test_read_files_deduplication(sandbox_workspace_fixture):
    """Efficiency: Model requests the exact same file 3 times. Engine reads it only once."""
    test_file = os.path.join(sandbox_workspace_fixture.name, "dup.txt")
    with open(test_file, "w") as f:
        f.write("test_content")
        
    payload = ["dup.txt", "dup.txt", "dup.txt"]
    with patch("builtins.open", mock_open(read_data="test_content")) as m:
        res = read_files(payload)
        assert len(res) == 1
        m.assert_called_once()

def test_write_files_deduplication(sandbox_workspace_fixture):
    """Efficiency: Model writes overlapping files. Only the last payload is saved."""
    payload = [
        {"path": "file1.txt", "content": "old_data"},
        {"path": "file1.txt", "content": "latest_data"},
    ]
    write_files(payload)
    written_file = os.path.join(sandbox_workspace_fixture.name, "file1.txt")
    with open(written_file, "r") as f:
        data = f.read()
    assert data == "latest_data"

def test_generate_pdf_success(sandbox_workspace_fixture):
    """Happy Path: Ensures markdown is converted and saved correctly."""
    markdown_payload = "# Hello World\nThis is a **bold** test."
    res = generate_pdf(markdown_payload, "test_report")
    assert "Success" in res
    assert "test_report.pdf" in res
    expected_path = os.path.join(sandbox_workspace_fixture.name, "test_report.pdf")
    assert os.path.exists(expected_path)

def test_generate_pdf_path_traversal_blocked(sandbox_workspace_fixture):
    """Security: Ensures the LLM cannot write PDFs outside the sandbox."""
    res = generate_pdf("# Hacked", "../../../etc/shadow.pdf")
    assert "Error:" in res
    assert "outside the allowed workspace" in res

@patch("tools.file_tools.pisa.CreatePDF")
def test_generate_pdf_internal_crash(mock_create_pdf, sandbox_workspace_fixture):
    """Error Handling: Ensures library crashes return a clean string to the LLM."""
    mock_create_pdf.side_effect = Exception("Simulated xhtml2pdf rendering crash")
    res = generate_pdf("# Crash Test", "crash_report.pdf")
    assert "Error: Failed to generate PDF" in res
    assert "Simulated xhtml2pdf rendering crash" in res

# =====================================================================
# 2. READ_FILE_CHUNK TESTS
# =====================================================================

def test_read_file_chunk_happy_path(sandbox_workspace_fixture):
    """Happy Path: Reads exact lines with 1-based indexing."""
    test_file = os.path.join(sandbox_workspace_fixture.name, "chunk.txt")
    with open(test_file, "w") as f:
        f.write("A\nB\nC\nD\nE\nF\n")
    res = read_file_chunk("chunk.txt", start_line=2, end_line=4)
    assert "Line 2: B" in res
    assert "Line 4: D" in res
    assert "Line 1: A" not in res

def test_read_file_chunk_out_of_bounds(sandbox_workspace_fixture):
    """Edge Case: Requesting lines past the end of the file."""
    test_file = os.path.join(sandbox_workspace_fixture.name, "short.txt")
    with open(test_file, "w") as f:
        f.write("A\nB\n")
    res = read_file_chunk("short.txt", start_line=5, end_line=10)
    assert "No content found between lines 5 and 10" in res

def test_read_file_chunk_security_traversal():
    """Security: Prevent reading outside the sandbox."""
    res = read_file_chunk("../../../etc/passwd", 1, 10)
    assert "is outside the allowed workspace" in res

# =====================================================================
# 3. LIST_WORKSPACE_DIRECTORY TESTS
# =====================================================================

def test_list_workspace_directory_happy_path(sandbox_workspace_fixture):
    """Happy Path: Verifies that directory tree is correctly built and formatted."""
    workspace_path = sandbox_workspace_fixture.name
    os.makedirs(os.path.join(workspace_path, "src", "utils"), exist_ok=True)
    os.makedirs(os.path.join(workspace_path, "docs"), exist_ok=True)
    
    with open(os.path.join(workspace_path, "src", "main.py"), "w") as f:
        f.write("# Main")
    with open(os.path.join(workspace_path, "src", "utils", "helper.py"), "w") as f:
        f.write("# Helper")
    with open(os.path.join(workspace_path, "docs", "readme.md"), "w") as f:
        f.write("# Readme")
    with open(os.path.join(workspace_path, "root_config.json"), "w") as f:
        f.write("{}")
        
    res = list_workspace_directory()
    assert "Workspace Directory Structure:" in res
    assert "src/" in res
    assert "utils/" in res
    assert "helper.py" in res
    assert "readme.md" in res
    assert "root_config.json" in res

def test_list_workspace_directory_depth_limit(sandbox_workspace_fixture):
    """Depth Bounds: Verifies files deeper than max_depth are omitted."""
    workspace_path = sandbox_workspace_fixture.name
    deep_path = os.path.join(workspace_path, "d1", "d2", "d3", "d4", "d5")
    os.makedirs(deep_path, exist_ok=True)
    
    with open(os.path.join(deep_path, "hidden.txt"), "w") as f:
        f.write("hidden")
        
    res = list_workspace_directory(max_depth=3)
    assert "d1/" in res
    assert "d2/" in res
    assert "d3/" in res
    assert "d4/" not in res
    assert "hidden.txt" not in res

def test_list_workspace_directory_ignores(sandbox_workspace_fixture):
    """Sanitation: Ensures common build/runtime folders are automatically excluded."""
    workspace_path = sandbox_workspace_fixture.name
    os.makedirs(os.path.join(workspace_path, ".git"), exist_ok=True)
    os.makedirs(os.path.join(workspace_path, "__pycache__"), exist_ok=True)
    os.makedirs(os.path.join(workspace_path, "allowed_folder"), exist_ok=True)
    
    with open(os.path.join(workspace_path, ".git", "config"), "w") as f:
        f.write("[core]")
    with open(os.path.join(workspace_path, "allowed_folder", "app.py"), "w") as f:
        f.write("print('hello')")
        
    res = list_workspace_directory()
    assert "allowed_folder/" in res
    assert "app.py" in res
    assert ".git/" not in res
    assert "__pycache__" not in res

# =====================================================================
# 4. SKELETON PARSER EDGE CASES (Old + New)
# =====================================================================

def test_skeleton_parser_empty_file():
    """Boundary Check: Verifies empty file structures return blank indicators."""
    res = generate_file_skeleton("", "empty.py")
    assert res == "No structural data could be extracted from this code file."

def test_skeleton_parser_missing_extension_long():
    """Edge Case: Long files (>40 lines) lacking extensions must fall back cleanly to spatial maps."""
    lines = [f"This is line {i} of flat text content." for i in range(1, 51)]
    no_ext_content = "\n".join(lines)
    res = generate_file_skeleton(no_ext_content, "README")
    assert "No semantic structure" in res
    assert "Content Preview" in res

def test_skeleton_parser_missing_extension_short():
    """Edge Case: Short files (<40 lines) lacking extensions return the standard blank indicator."""
    short_content = "First line\nSecond line\nThird line\nFourth line"
    res = generate_file_skeleton(short_content, "README")
    assert res == "No structural or spatial data could be extracted."

def test_skeleton_parser_corrupt_binary_encoding():
    """Error Handling: Verifies binary strings do not raise AST compilation errors."""
    binary_payload = "\x00\x01\x02\x03\xff\xfedef broken_syntax(:"
    res = generate_file_skeleton(binary_payload, "malformed.py")
    assert res is not None
    assert isinstance(res, str)

def test_skeleton_parser_code_no_structures():
    """Coverage: Code files lacking def/class keywords cleanly shift to fallback."""
    flat_code = "x = 10\ny = 20\nprint(x + y)"
    res = generate_file_skeleton(flat_code, "script.py")
    assert "No structural data could be extracted" in res

def test_skeleton_parser_catches_imports_and_globals():
    """Verifies the parser catches imports, froms, and global variables."""
    code = (
        "import os\n"
        "from typing import List\n"
        "MAX_RETRIES = 5\n"
        "def hello():\n"
        "    pass\n"
    )
    res = generate_file_skeleton(code, "test.py")
    assert "Line 1: import os" in res
    assert "Line 2: from typing import List" in res
    assert "Line 3: MAX_RETRIES = 5" in res
    assert "Line 4: def hello():" in res

# =====================================================================
# 5. SYMLINK JAILBREAK TEST
# =====================================================================

def test_symlink_path_traversal_jailbreak(sandbox_workspace_fixture, tmp_path):
    """CRITICAL SECURITY TEST: Ensures the agent cannot bypass the sandbox by creating a symlink."""
    outside_secret = tmp_path / "system_password.txt"
    outside_secret.write_text("SUPER_SECRET_HASH")
    
    symlink_path = os.path.join(sandbox_workspace_fixture.name, "innocent_link.txt")
    try:
        os.symlink(str(outside_secret), symlink_path)
    except OSError:
        pytest.skip("Symlinks not supported on this host OS (e.g., Windows without admin).")
        
    res = read_files(["innocent_link.txt"])
    key = list(res.keys())[0]
    assert "SUPER_SECRET_HASH" not in res[key], "CRITICAL: Symlink jailbreak successful!"
    assert "Error" in res[key]
    assert "outside the allowed workspace" in res[key]

# =====================================================================
# 6. NEW TOOLS TESTS (get_file_skeleton, search_codebase, replace_in_file)
# =====================================================================

def test_get_file_skeleton_single_file(sandbox_workspace_fixture):
    """Happy Path: Generates a skeleton for a single file."""
    test_file = os.path.join(sandbox_workspace_fixture.name, "app.py")
    with open(test_file, "w") as f:
        f.write("def main():\n    print('hi')\n")
        
    res = get_file_skeleton("app.py")
    assert "--- SKELETON: app.py ---" in res
    assert "def main():" in res

def test_get_file_skeleton_directory(sandbox_workspace_fixture):
    """Happy Path: Recursively generates skeletons for a full directory."""
    ws = sandbox_workspace_fixture.name
    os.makedirs(os.path.join(ws, "src"))
    
    with open(os.path.join(ws, "src", "a.py"), "w") as f:
        f.write("def func_a():\n    pass\n")
    with open(os.path.join(ws, "src", "b.js"), "w") as f:
        f.write("function func_b() {}\n")
        
    res = get_file_skeleton("src")
    assert "--- SKELETON: src/a.py ---" in res.replace("\\", "/")
    assert "def func_a():" in res
    assert "--- SKELETON: src/b.js ---" in res.replace("\\", "/")
    assert "function func_b()" in res

def test_search_codebase_happy_path(sandbox_workspace_fixture):
    """Happy Path: Finds regex matches and scans upwards for function context."""
    test_file = os.path.join(sandbox_workspace_fixture.name, "logic.py")
    with open(test_file, "w") as f:
        f.write("import os\n\ndef calculate_tax(amount):\n    rate = 0.2\n    return amount * rate\n")
        
    res = search_codebase("amount \\* rate", "logic.py")
    assert res["status"] == "success"
    assert "[def calculate_tax(amount)]:" in res["output"]
    assert "return amount * rate" in res["output"]

def test_search_codebase_directory(sandbox_workspace_fixture):
    """Happy Path: Searches across multiple files in a directory."""
    ws = sandbox_workspace_fixture.name
    with open(os.path.join(ws, "f1.py"), "w") as f:
        f.write("TARGET_VAR = 1\n")
    with open(os.path.join(ws, "f2.py"), "w") as f:
        f.write("TARGET_VAR = 2\n")
        
    res = search_codebase("TARGET_VAR", ".")
    assert res["status"] == "success"
    assert "f1.py:1" in res["output"]
    assert "f2.py:1" in res["output"]

def test_replace_in_file_happy_path(sandbox_workspace_fixture):
    """Happy Path: Surgically replaces an exact block of code."""
    ws = sandbox_workspace_fixture.name
    test_file = os.path.join(ws, "app.py")
    
    original_code = "def main():\n    x = 1\n    y = 2\n    return x + y\n"
    with open(test_file, "w") as f:
        f.write(original_code)
        
    search_block = "    x = 1\n    y = 2"
    replace_block = "    x = 10\n    y = 20"
    
    res = replace_in_file("app.py", search_block, replace_block)
    assert res["status"] == "success"
    
    with open(test_file, "r") as f:
        new_code = f.read()
        
    assert "x = 10" in new_code
    assert "x = 1\n" not in new_code

def test_search_codebase_invalid_regex(sandbox_workspace_fixture):
    """Edge Case: Fails safely on bad regex."""
    res = search_codebase("[unclosed_bracket", ".")
    # FIXED: Check for 'error' key directly
    assert "error" in res
    assert "Invalid regex pattern" in res["error"]

def test_replace_in_file_not_found(sandbox_workspace_fixture):
    """Edge Case: Fails safely if the search block has wrong indentation/spacing."""
    ws = sandbox_workspace_fixture.name
    test_file = os.path.join(ws, "app.py")
    
    with open(test_file, "w") as f:
        f.write("def main():\n    x = 1\n")
        
    # FIXED: Use a multi-line block with missing indentation so it is NOT a valid substring
    search_block = "def main():\nx = 1\n"
    replace_block = "def main():\n    x = 2\n"
    
    res = replace_in_file("app.py", search_block, replace_block)
    
    assert "error" in res
    assert "Search block not found" in res["error"]

def test_replace_in_file_multiple_matches(sandbox_workspace_fixture):
    """Edge Case: Fails safely if the search block is not unique."""
    ws = sandbox_workspace_fixture.name
    test_file = os.path.join(ws, "app.py")
    
    with open(test_file, "w") as f:
        f.write("def a():\n    pass\n\ndef b():\n    pass\n")
        
    res = replace_in_file("app.py", "    pass\n", "    return True\n")
    assert res.get("error") is not None
    assert "Search block is not unique" in res["error"]