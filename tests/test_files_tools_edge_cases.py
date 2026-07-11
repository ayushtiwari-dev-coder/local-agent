# tests/test_files_tools_edge_cases.py
import pytest
import os
import tempfile
from unittest.mock import (
    patch,
    mock_open,
)  # FIXED: Imported mock_open from standard library
from tools.file_tools import read_files, write_files


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