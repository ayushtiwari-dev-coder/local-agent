# tests/test_static_analyzer.py
import pytest
from unittest.mock import patch, mock_open
from security.static_analyzer import scan_file_for_threats, MAX_SCAN_SIZE_BYTES


@patch("os.path.exists", return_value=True)
@patch("os.path.getsize", return_value=1024)  # 1 KB file
def test_safe_files_pass(mock_getsize, mock_exists):
    """Ensures perfectly normal code passes the static analyzer."""
    safe_python = "def hello():\n    print('world')\nimport json\nimport math"
    safe_js = "const x = 10;\nconsole.log(x);\nimport { debounce } from 'lodash';"

    with patch("builtins.open", mock_open(read_data=safe_python)):
        is_safe, reason = scan_file_for_threats("/workspace/script.py")
        assert is_safe is True
        assert reason is None

    with patch("builtins.open", mock_open(read_data=safe_js)):
        is_safe, reason = scan_file_for_threats("/workspace/app.js")
        assert is_safe is True


@patch("os.path.exists", return_value=True)
@patch("os.path.getsize", return_value=1024)
@pytest.mark.parametrize(
    "extension, malicious_code",
    [
        (".py", "import os\nos.system('rm -rf /')"),
        (".py", "from subprocess import run"),
        (".py", "eval('print(1)')"),
        (".js", "const cp = require('child_process');"),
        (".ts", "import * as fs from 'fs';"),
        (".c", 'int main() { system("rm -rf /"); }'),
        (".java", 'Runtime.getRuntime().exec("bash");'),
        (".sh", "rm -r /"),
        (".sh", "echo 'hack' > /dev/sda"),
    ],
)
def test_malicious_files_blocked(mock_getsize, mock_exists, extension, malicious_code):
    """Ensures dangerous imports and functions are caught across multiple languages."""
    with patch("builtins.open", mock_open(read_data=malicious_code)):
        is_safe, reason = scan_file_for_threats(f"/workspace/malicious{extension}")
        assert is_safe is False
        assert "Malicious signature detected" in reason


@patch("os.path.exists", return_value=True)
@patch("os.path.getsize", return_value=MAX_SCAN_SIZE_BYTES + 1)
def test_file_size_limit_enforced(mock_getsize, mock_exists):
    """Ensures huge files are blocked from scanning to prevent memory crashes."""
    is_safe, reason = scan_file_for_threats("/workspace/huge_file.py")
    assert is_safe is False
    assert "exceeds maximum scan size" in reason
