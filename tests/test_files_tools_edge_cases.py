# tests/test_files_tools_edge_cases.py

import pytest
import os
import tempfile
from unittest.mock import patch, mock_open, MagicMock, ANY

from tools.file_tools import (
    read_files,
    write_files,
    generate_pdf,
    read_file_chunks,
    search_inside_files,
    get_file_skeletons,
    edit_file_chunk,
    list_workspace_directory,
    read_pdf
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


# --- 2. BULK FILE TOOLS TESTS (read_file_chunks, search_inside_files, etc.) ---

def test_read_file_chunks_happy_path(sandbox_workspace_fixture):
    """Happy Path: Reads exact lines with 1-based indexing for multiple chunks."""
    test_file = os.path.join(sandbox_workspace_fixture.name, "chunk.txt")
    with open(test_file, "w") as f:
        f.write("A\nB\nC\nD\nE\nF\n")

    req = [{"path": "chunk.txt", "start_line": 2, "end_line": 4}]
    res = read_file_chunks(req)
    
    key = list(res.keys())[0]
    assert "Line 2: B" in res[key]
    assert "Line 4: D" in res[key]
    assert "Line 1: A" not in res[key]

def test_read_file_chunks_out_of_bounds(sandbox_workspace_fixture):
    """Edge Case: Requesting lines past the end of the file."""
    test_file = os.path.join(sandbox_workspace_fixture.name, "short.txt")
    with open(test_file, "w") as f:
        f.write("A\nB\n")

    res = read_file_chunks([{"path": "short.txt", "start_line": 5, "end_line": 10}])
    key = list(res.keys())[0]
    assert "No content found in range" in res[key]

def test_read_file_chunks_security_traversal():
    """Security: Prevent reading outside the sandbox."""
    req = [{"path": "../../../etc/passwd", "start_line": 1, "end_line": 10}]
    res = read_file_chunks(req)
    
    key = list(res.keys())[0]
    assert "outside workspace" in res[key]

def test_search_inside_files_happy_path(sandbox_workspace_fixture):
    """Happy Path: Finds string and returns correct context window."""
    test_file = os.path.join(sandbox_workspace_fixture.name, "search.txt")
    with open(test_file, "w") as f:
        f.write("Line1\nLine2\nTARGET\nLine4\nLine5\n")

    req = [{"path": "search.txt", "search_term": "TARGET", "context_lines": 1}]
    res = search_inside_files(req)
    
    key = list(res.keys())[0]
    assert "Line 2: Line2" in res[key]
    assert "Line 3: TARGET" in res[key]
    assert "Line 4: Line4" in res[key]

def test_search_inside_files_overlapping_context(sandbox_workspace_fixture):
    """Edge Case: Multiple matches close together should not duplicate context lines."""
    test_file = os.path.join(sandbox_workspace_fixture.name, "overlap.txt")
    with open(test_file, "w") as f:
        f.write("A\nMATCH\nMATCH\nB\n")

    res = search_inside_files([{"path": "overlap.txt", "search_term": "MATCH", "context_lines": 1}])
    key = list(res.keys())[0]
    output = res[key]
    assert output.count("Line 1: A") == 1
    assert output.count("Line 2: MATCH") == 1
    assert output.count("Line 3: MATCH") == 1
    assert output.count("Line 4: B") == 1

def test_search_inside_files_no_match(sandbox_workspace_fixture):
    """Edge Case: Search term not in file."""
    test_file = os.path.join(sandbox_workspace_fixture.name, "nomatch.txt")
    with open(test_file, "w") as f:
        f.write("A\nB\n")

    res = search_inside_files([{"path": "nomatch.txt", "search_term": "GHOST"}])
    key = list(res.keys())[0]
    assert "No matches found" in res[key]

def test_search_inside_files_none_context(sandbox_workspace_fixture):
    """Edge Case: Ensure the tool gracefully handles explicit None (null)."""
    test_file = os.path.join(sandbox_workspace_fixture.name, "none_test.txt")
    with open(test_file, "w") as f:
        f.write("Line1\nTARGET\nLine3\n")

    res = search_inside_files([{"path": "none_test.txt", "search_term": "TARGET", "context_lines": None}])
    key = list(res.keys())[0]
    assert "Line 2: TARGET" in res[key]
    assert "Line 1: Line1" in res[key]  # Default context of 2 should kick in

def test_get_file_skeletons_security():
    """Security: Prevent reading outside the sandbox."""
    res = get_file_skeletons(["../../../etc/passwd"])
    key = list(res.keys())[0]
    assert "outside allowed workspace" in res[key]

def test_get_file_skeletons_not_found(sandbox_workspace_fixture):
    """Edge Case: File doesn't exist."""
    res = get_file_skeletons(["ghost_file.txt"])
    key = list(res.keys())[0]
    assert "File not found" in res[key]

def test_get_file_skeletons_happy_path(sandbox_workspace_fixture):
    """Verifies skeletons can be fetched for multiple files at once."""
    test_file = os.path.join(sandbox_workspace_fixture.name, "script.py")
    with open(test_file, "w") as f:
        f.write("def main():\n    pass\n")

    res = get_file_skeletons(["script.py", "ghost.py"])
    assert "def main():" in res["script.py"]
    assert "Error: File not found." in res["ghost.py"]


# --- 3. TESTS FOR edit_file_chunk (Singular) ---

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
    res = edit_file_chunk(
        "edit_test.txt", start_line=2, end_line=4, content=replacement
    )

    assert "Success" in res

    # 3. Read and verify content
    with open(test_file, "r", encoding="utf-8") as f:
        updated_content = f.read()

    expected_content = "Line 1\nNEW Line A\nNEW Line B\nLine 5\n"
    assert updated_content == expected_content

def test_edit_file_chunk_file_not_found():
    """Safety Check: Verifies editing non-existent path handles gracefully."""
    res = edit_file_chunk(
        "does_not_exist.txt", start_line=1, end_line=5, content="fail"
    )
    assert "Error:" in res
    assert "not found" in res

def test_edit_file_chunk_out_of_bounds(sandbox_workspace_fixture):
    """Boundary Check: Verifies start_line exceeding file length fails gracefully."""
    workspace_path = sandbox_workspace_fixture.name
    test_file = os.path.join(workspace_path, "short.txt")

    with open(test_file, "w") as f:
        f.write("Line 1\nLine 2")

    res = edit_file_chunk(
        "short.txt", start_line=5, end_line=10, content="Error expected"
    )
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
    res = edit_file_chunk(
        "../../../etc/shadow", start_line=1, end_line=10, content="unauthorized"
    )
    assert "Error:" in res
    assert "outside the allowed workspace" in res

# --- 4. TESTS FOR list_workspace_directory ---

def test_list_workspace_directory_happy_path(sandbox_workspace_fixture):
    """Happy Path: Verifies that directory tree is correctly built and formatted."""
    workspace_path = sandbox_workspace_fixture.name
    os.makedirs(os.path.join(workspace_path, "src", "utils"), exist_ok=True)
    os.makedirs(os.path.join(workspace_path, "docs"), exist_ok=True)

    with open(os.path.join(workspace_path, "src", "main.py"), "w") as f: f.write("# Main")
    with open(os.path.join(workspace_path, "src", "utils", "helper.py"), "w") as f: f.write("# Helper")
    with open(os.path.join(workspace_path, "docs", "readme.md"), "w") as f: f.write("# Readme")

    res = list_workspace_directory()

    assert "Workspace Directory Structure:" in res
    assert "src/" in res
    assert "utils/" in res
    assert "helper.py" in res
    assert "readme.md" in res

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
    os.makedirs(os.path.join(workspace_path, "node_modules"), exist_ok=True)
    os.makedirs(os.path.join(workspace_path, "allowed_folder"), exist_ok=True)

    with open(os.path.join(workspace_path, "allowed_folder", "app.py"), "w") as f: f.write("print('hello')")

    res = list_workspace_directory()
    assert "allowed_folder/" in res
    assert "app.py" in res
    assert ".git/" not in res
    assert "node_modules/" not in res

# --- 5. SKELETON PARSER LOGIC TESTS ---

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

def test_skeleton_parser_corrupt_binary_encoding():
    """Error Handling: Verifies binary strings do not raise AST compilation errors."""
    binary_payload = "\x00\x01\x02\x03\xff\xfedef broken_syntax(:"
    res = generate_file_skeleton(binary_payload, "malformed.py")
    assert res is not None

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

# --- 6. PDF TOOL TESTS (read_pdf) ---

def test_read_pdf_path_traversal_blocked():
    """Security: Ensures the LLM cannot read PDFs outside the sandbox."""
    res = read_pdf("../../../etc/passwords.pdf")
    assert "Error:" in res
    assert "outside the allowed workspace" in res

def test_read_pdf_file_not_found(sandbox_workspace_fixture):
    """Edge Case: Requesting a PDF that doesn't exist."""
    res = read_pdf("ghost_document.pdf")
    assert "Error:" in res
    assert "not found" in res

def test_read_pdf_invalid_extension(sandbox_workspace_fixture):
    """Validation: Ensures the tool rejects non-PDF files."""
    test_file = os.path.join(sandbox_workspace_fixture.name, "document.txt")
    with open(test_file, "w") as f:
        f.write("I am a text file")
        
    res = read_pdf("document.txt")
    assert "Error: File is not a PDF." in res

@patch("tools.file_tools.pymupdf4llm.to_markdown")
@patch("tools.file_tools.fitz.open")
def test_read_pdf_small_default(mock_fitz, mock_to_markdown, sandbox_workspace_fixture):
    """Happy Path: A small PDF (< 10 pages) should be read entirely by default."""
    test_file = os.path.join(sandbox_workspace_fixture.name, "small.pdf")
    with open(test_file, "w") as f: f.write("dummy pdf content")
    
    mock_doc = MagicMock()
    mock_doc.__len__.return_value = 3
    mock_fitz.return_value = mock_doc
    mock_to_markdown.return_value = "# Page 1\n# Page 2\n# Page 3"
    
    res = read_pdf("small.pdf")
    assert "SYSTEM NOTE" not in res  
    assert "# Page 1" in res
    mock_to_markdown.assert_called_once_with(ANY, pages=[0, 1, 2])

@patch("tools.file_tools.pymupdf4llm.to_markdown")
@patch("tools.file_tools.fitz.open")
def test_read_pdf_large_truncation(mock_fitz, mock_to_markdown, sandbox_workspace_fixture):
    """Memory Protection: A large PDF (> 10 pages) should truncate to 5 pages by default."""
    test_file = os.path.join(sandbox_workspace_fixture.name, "massive_book.pdf")
    with open(test_file, "w") as f: f.write("dummy pdf content")
    
    mock_doc = MagicMock()
    mock_doc.__len__.return_value = 500
    mock_fitz.return_value = mock_doc
    mock_to_markdown.return_value = "# Table of Contents..."
    
    res = read_pdf("massive_book.pdf")
    assert "SYSTEM NOTE" in res
    assert "massive (500 pages)" in res
    assert "pages 1-5 were extracted" in res
    mock_to_markdown.assert_called_once_with(ANY, pages=[0, 1, 2, 3, 4])

@patch("tools.file_tools.pymupdf4llm.to_markdown")
@patch("tools.file_tools.fitz.open")
def test_read_pdf_specific_pages(mock_fitz, mock_to_markdown, sandbox_workspace_fixture):
    """Precision: Ensures requesting specific pages maps correctly to 0-indexed PyMuPDF."""
    test_file = os.path.join(sandbox_workspace_fixture.name, "report.pdf")
    with open(test_file, "w") as f: f.write("dummy pdf content")
    
    mock_doc = MagicMock()
    mock_doc.__len__.return_value = 20
    mock_fitz.return_value = mock_doc
    mock_to_markdown.return_value = "Financial Data for Q3"
    
    res = read_pdf("report.pdf", pages=[2, 10, 15])
    assert "Financial Data for Q3" in res
    mock_to_markdown.assert_called_once_with(ANY, pages=[1, 9, 14])

@patch("tools.file_tools.fitz.open")
def test_read_pdf_out_of_bounds(mock_fitz, sandbox_workspace_fixture):
    """Boundary Check: Requesting pages that don't exist should fail cleanly."""
    test_file = os.path.join(sandbox_workspace_fixture.name, "short.pdf")
    with open(test_file, "w") as f: f.write("dummy pdf content")
    
    mock_doc = MagicMock()
    mock_doc.__len__.return_value = 5
    mock_fitz.return_value = mock_doc
    
    res = read_pdf("short.pdf", pages=[1, 6])
    assert "Error:" in res
    assert "out of bounds" in res
    assert "only has 5 pages" in res

@patch("tools.file_tools.pymupdf4llm.to_markdown")
@patch("tools.file_tools.fitz.open")
def test_read_pdf_empty_scanned(mock_fitz, mock_to_markdown, sandbox_workspace_fixture):
    """Edge Case: Scanned PDFs (images) return empty strings. Handle gracefully."""
    test_file = os.path.join(sandbox_workspace_fixture.name, "scanned_receipt.pdf")
    with open(test_file, "w") as f: f.write("dummy pdf content")
    mock_doc = MagicMock()
    mock_doc.__len__.return_value = 2
    mock_fitz.return_value = mock_doc
    mock_to_markdown.return_value = "   \n  \t " 
    
    res = read_pdf("scanned_receipt.pdf")
    assert "Success:" in res
    assert "no extractable text was found" in res
    assert "scanned image" in res

@patch("tools.file_tools.fitz.open")
def test_read_pdf_corrupt_file_exception(mock_fitz, sandbox_workspace_fixture):
    """Error Handling: If the PDF library crashes (e.g., corrupt file), catch it."""
    test_file = os.path.join(sandbox_workspace_fixture.name, "corrupt.pdf")
    with open(test_file, "w") as f: f.write("dummy pdf content")
    
    mock_fitz.side_effect = Exception("mupdf: invalid PDF structure")
    res = read_pdf("corrupt.pdf")
    assert "Error: Failed to read PDF" in res
    assert "invalid PDF structure" in res