# tests/test_files_tools_edge_cases.py
import pytest
import os
import tempfile
from unittest.mock import (
    patch,
    mock_open,
)  # FIXED: Imported mock_open from standard library
from tools.file_tools import read_files, write_files
from tools.file_tools import list_workspace_directory, edit_file_chunk
from tools.skeleton_parser import generate_file_skeleton


@pytest.fixture(autouse=True)
def sandbox_workspace_fixture():
    """Generates a sandboxed workspace directory for testing file read/writes."""
    temp_sandbox = tempfile.TemporaryDirectory()

    # Patch config manager root
    patcher = patch(
        "tools.file_tools.config_manager.get_workspace_path",
        return_value=temp_sandbox.name,
    )
    patcher.start()

    yield temp_sandbox

    patcher.stop()
    temp_sandbox.cleanup()


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
    # FIXED: Replaced "pytest.mock_open" with standard library "mock_open"
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

# Add this import at the top of tests/test_files_tools_edge_cases.py if not present
from tools.file_tools import generate_pdf

def test_generate_pdf_success(sandbox_workspace_fixture):
    """Happy Path: Ensures markdown is converted and saved correctly."""
    markdown_payload = "# Hello World\nThis is a **bold** test."
    
    # Notice we don't pass .pdf, testing the auto-append feature
    res = generate_pdf(markdown_payload, "test_report")
    
    assert "Success" in res
    assert "test_report.pdf" in res
    
    # Verify the file actually exists in the sandbox
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
    # Force the xhtml2pdf library to crash
    mock_create_pdf.side_effect = Exception("Simulated xhtml2pdf rendering crash")
    
    res = generate_pdf("# Crash Test", "crash_report.pdf")
    
    assert "Error: Failed to generate PDF" in res
    assert "Simulated xhtml2pdf rendering crash" in res

# tests/test_files_tools_edge_cases.py
import pytest
import os
import tempfile
from unittest.mock import patch, mock_open
from tools.file_tools import (
    read_files, 
    write_files, 
    generate_pdf, 
    read_file_chunk, 
    search_inside_file, 
    get_file_skeleton
)

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

# --- 1. LEGACY TOOLS TESTS (read_files, write_files, generate_pdf) ---

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


# --- 2. NEW TOOLS TESTS (read_file_chunk, search_file, get_file_skeleton) ---

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

def test_search_file_happy_path(sandbox_workspace_fixture):
    """Happy Path: Finds string and returns correct context window."""
    test_file = os.path.join(sandbox_workspace_fixture.name, "search.txt")
    with open(test_file, "w") as f:
        f.write("Line1\nLine2\nTARGET\nLine4\nLine5\n")
    
    res = search_inside_file("search.txt", "TARGET", context_lines=1)
    assert "Line 2: Line2" in res
    assert "Line 3: TARGET" in res
    assert "Line 4: Line4" in res
    assert "Line 1: Line1" not in res

def test_search_file_overlapping_context(sandbox_workspace_fixture):
    """Edge Case: Multiple matches close together should not duplicate context lines."""
    test_file = os.path.join(sandbox_workspace_fixture.name, "overlap.txt")
    with open(test_file, "w") as f:
        f.write("A\nMATCH\nMATCH\nB\n")
    
    res = search_inside_file("overlap.txt", "MATCH", context_lines=1)
    assert res.count("Line 1: A") == 1
    assert res.count("Line 2: MATCH") == 1
    assert res.count("Line 3: MATCH") == 1
    assert res.count("Line 4: B") == 1

def test_search_file_no_match(sandbox_workspace_fixture):
    """Edge Case: Search term not in file."""
    test_file = os.path.join(sandbox_workspace_fixture.name, "nomatch.txt")
    with open(test_file, "w") as f:
        f.write("A\nB\n")
    
    res = search_inside_file("nomatch.txt", "GHOST")
    assert "No matches found for 'GHOST'" in res

def test_get_file_skeleton_security():
    """Security: Prevent reading outside the sandbox."""
    res = get_file_skeleton("../../../etc/passwd")
    assert "is outside the allowed workspace" in res

def test_get_file_skeleton_not_found(sandbox_workspace_fixture):
    """Edge Case: File doesn't exist."""
    res = get_file_skeleton("ghost_file.txt")
    assert "not found" in res

def test_search_file_none_context(sandbox_workspace_fixture):
    """
    Edge Case: Ensure the tool gracefully handles when the LLM SDK 
    explicitly passes None (null) for optional arguments.
    """
    test_file = os.path.join(sandbox_workspace_fixture.name, "none_test.txt")
    with open(test_file, "w") as f:
        f.write("Line1\nTARGET\nLine3\n")
        
    # Explicitly pass None for context_lines (simulating LLM API null payload)
    res = search_inside_file("none_test.txt", "TARGET", context_lines=None)
    
    assert "Line 2: TARGET" in res
    assert "Line 1: Line1" in res # Default context of 2 should kick in
    assert "Line 3: Line3" in res



# --- TESTS FOR list_workspace_directory ---

def test_list_workspace_directory_happy_path(sandbox_workspace_fixture):
    """Happy Path: Verifies that directory tree is correctly built and formatted."""
    workspace_path = sandbox_workspace_fixture.name
    
    # Create mock folder structure
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
    
    # Verify directory structure representation
    assert "Workspace Directory Structure:" in res
    assert "src/" in res
    assert "utils/" in res
    assert "helper.py" in res
    assert "readme.md" in res
    assert "root_config.json" in res


def test_list_workspace_directory_depth_limit(sandbox_workspace_fixture):
    """Depth Bounds: Verifies files deeper than max_depth are omitted."""
    workspace_path = sandbox_workspace_fixture.name
    
    # Create folder depth of 5 (Default max_depth = 4)
    deep_path = os.path.join(workspace_path, "d1", "d2", "d3", "d4", "d5")
    os.makedirs(deep_path, exist_ok=True)
    
    with open(os.path.join(deep_path, "hidden.txt"), "w") as f:
        f.write("hidden")

    # With max_depth=3, d4 and hidden.txt must not show
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


# --- TESTS FOR edit_file_chunk ---

def test_edit_file_chunk_happy_path(sandbox_workspace_fixture):
    """Surgical Edit: Verifies targeted line insertion and substitution."""
    workspace_path = sandbox_workspace_fixture.name
    test_file = os.path.join(workspace_path, "edit_test.txt")
    
    # 1. Prepare initial 5-line file
    original_lines = ["Line 1", "Line 2", "Line 3", "Line 4", "Line 5"]
    with open(test_file, "w", encoding="utf-8") as f:
        f.write("\n".join(original_lines) + "\n")

    # 2. Replace lines 2 through 4 (Line 2, Line 3, Line 4) surgically
    replacement = "NEW Line A\nNEW Line B"
    res = edit_file_chunk("edit_test.txt", start_line=2, end_line=4, content=replacement)
    
    assert "Success" in res
    
    # 3. Read and verify content
    with open(test_file, "r", encoding="utf-8") as f:
        updated_content = f.read()
        
    expected_content = "Line 1\nNEW Line A\nNEW Line B\nLine 5\n"
    assert updated_content == expected_content


def test_edit_file_chunk_file_not_found():
    """Safety Check: Verifies editing non-existent path handles gracefully."""
    res = edit_file_chunk("does_not_exist.txt", start_line=1, end_line=5, content="fail")
    assert "Error:" in res
    assert "not found" in res


def test_edit_file_chunk_out_of_bounds(sandbox_workspace_fixture):
    """Boundary Check: Verifies start_line exceeding file length fails gracefully."""
    workspace_path = sandbox_workspace_fixture.name
    test_file = os.path.join(workspace_path, "short.txt")
    
    with open(test_file, "w") as f:
        f.write("Line 1\nLine 2")

    res = edit_file_chunk("short.txt", start_line=5, end_line=10, content="Error expected")
    assert "Error:" in res
    assert "out of bounds" in res


def test_edit_file_chunk_invalid_range(sandbox_workspace_fixture):
    """Validation: Verifies illegal line boundaries are safely blocked."""
    workspace_path = sandbox_workspace_fixture.name
    test_file = os.path.join(workspace_path, "short.txt")
    
    with open(test_file, "w") as f:
        f.write("Line 1\nLine 2")

    res_neg = edit_file_chunk("short.txt", start_line=-1, end_line=2, content="fail")
    assert "Error: Invalid line range" in res_neg

    res_inv = edit_file_chunk("short.txt", start_line=5, end_line=3, content="fail")
    assert "Error: Invalid line range" in res_inv


def test_edit_file_chunk_security_traversal():
    """Security Boundary: Ensures directory traversals outside sandbox are blocked."""
    res = edit_file_chunk("../../../etc/shadow", start_line=1, end_line=10, content="unauthorized")
    assert "Error:" in res
    assert "outside the allowed workspace" in res


def test_skeleton_parser_empty_file():
    """Boundary Check: Verifies empty file structures return blank indicators."""
    res = generate_file_skeleton("", "empty.py")
    assert res == "No structural data could be extracted from this code file."


def test_skeleton_parser_missing_extension_long():
    """Edge Case: Long files (>40 lines) lacking extensions must fall back cleanly to spatial maps."""
    # Generate 50 lines to bypass the 40-line spatial map guard clause
    lines = [f"This is line {i} of flat text content." for i in range(1, 51)]
    no_ext_content = "\n".join(lines)
    
    res = generate_file_skeleton(no_ext_content, "README")
    
    # Verify spatial map is triggered and correctly rendered
    assert "No semantic structure" in res
    assert "Content Preview" in res


def test_skeleton_parser_missing_extension_short():
    """Edge Case: Short files (<40 lines) lacking extensions return the standard blank indicator."""
    short_content = "First line\nSecond line\nThird line\nFourth line"
    
    res = generate_file_skeleton(short_content, "README")
    
    # Verify the guard clause is safely executed for short files
    assert res == "No structural or spatial data could be extracted."


def test_skeleton_parser_corrupt_binary_encoding():
    """Error Handling: Verifies binary strings do not raise AST compilation errors."""
    binary_payload = "\x00\x01\x02\x03\xff\xfedef broken_syntax(:"
    res = generate_file_skeleton(binary_payload, "malformed.py")
    # Should fall back cleanly without throwing UnboundLocalError or AST syntax failures
    assert res is not None
    assert isinstance(res, str)


def test_skeleton_parser_code_no_structures():
    """Coverage: Code files lacking def/class keywords cleanly shift to fallback."""
    flat_code = "x = 10\ny = 20\nprint(x + y)"
    res = generate_file_skeleton(flat_code, "script.py")
    assert "No structural data could be extracted" in res


def test_symlink_path_traversal_jailbreak(sandbox_workspace_fixture, tmp_path):
    """
    CRITICAL SECURITY TEST: Ensures the agent cannot bypass the sandbox 
    by creating a symlink to an outside file and reading it.
    """
    # 1. Create a "secret" file completely outside the sandbox
    outside_secret = tmp_path / "system_password.txt"
    outside_secret.write_text("SUPER_SECRET_HASH")
    
    # 2. Simulate the LLM using the terminal to create a symlink INSIDE the sandbox
    symlink_path = os.path.join(sandbox_workspace_fixture.name, "innocent_link.txt")
    try:
        os.symlink(str(outside_secret), symlink_path)
    except OSError:
        pytest.skip("Symlinks not supported on this host OS (e.g., Windows without admin).")

    # 3. The LLM attempts to read the symlink using native tools
    res = read_files(["innocent_link.txt"])
    
    # 4. Assert the system caught the symlink resolution
    key = list(res.keys())[0]
    assert "SUPER_SECRET_HASH" not in res[key], "CRITICAL: Symlink jailbreak successful!"
    assert "Error" in res[key]
    assert "outside the allowed workspace" in res[key]