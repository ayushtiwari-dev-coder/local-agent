# tests/test_research_tools.py

import pytest
import requests
from unittest.mock import patch, MagicMock, mock_open,ANY
from tools.research_tools import _search_web, _read_urls, web_researcher

import os
import tempfile

@pytest.fixture(autouse=True)
def sandbox_research_fixture():
    """
    Safely sandboxes the get_sandbox_root function for all research tools tests,
    preventing any PermissionError writes to the host file system.
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        # Patch get_sandbox_root inside research_tools to return our safe temp folder
        with patch("tools.research_tools.get_sandbox_root", return_value=temp_dir):
            yield temp_dir

@patch("tools.research_tools.DDGS")
def test_search_web_success(mock_ddgs):
    """Happy Path: Ensures DuckDuckGo returns the expected list of dicts."""
    mock_instance = MagicMock()
    mock_instance.text.return_value = [
        {"title": "Test Site", "href": "https://test.com", "body": "Test snippet"}
    ]
    mock_ddgs.return_value.__enter__.return_value = mock_instance
    
    res = _search_web("test query")
    assert len(res) == 1
    assert res[0]["title"] == "Test Site"

@patch("tools.research_tools.DDGS")
def test_search_web_exception(mock_ddgs):
    """Error Handling: Ensures network timeouts return a clean error dict."""
    mock_ddgs.side_effect = Exception("Connection timed out")
    
    res = _search_web("test query")
    assert "error" in res[0]
    assert "Connection timed out" in res[0]["error"]


@patch("tools.research_tools.requests.get")
@patch("builtins.open", new_callable=mock_open)
def test_read_urls_success_and_dynamic_filename(mock_file, mock_get):
    """Happy Path: Ensures valid URLs are fetched, cleaned, and appended to the dynamic file."""
    mock_response = MagicMock()
    mock_response.text = "<html><body><p>Clean extracted text</p></body></html>"
    mock_get.return_value = mock_response
    
    # Pass conversation_id=42 to test dynamic naming
    res = _read_urls(["https://site1.com", "https://site2.com"], conversation_id=42)
    
    # 1. Assert the return string is correct
    assert "Success: Extracted content from 2 URLs" in res
    assert "research_notes_42.md" in res
    
    # 2. Assert the file was opened in Append ("a") mode
    mock_file.assert_called_with(ANY, "a", encoding="utf-8")
    
    # 3. Assert the content was actually written to the file
    handle = mock_file()
    written_text = "".join(call.args[0] for call in handle.write.call_args_list)
    assert "### Source: https://site1.com" in written_text
    assert "Clean extracted text" in written_text

@patch("tools.research_tools.requests.get")
@patch("builtins.open", new_callable=mock_open)
def test_read_urls_over_limit(mock_file, mock_get):
    """Edge Case: Ensures passing > 3 URLs slices the list and warns the LLM."""
    mock_response = MagicMock()
    mock_response.text = "<html><body><p>Clean text</p></body></html>"
    mock_get.return_value = mock_response
    
    urls = ["url1", "url2", "url3", "url4", "url5"]
    res = _read_urls(urls)
    
    # Assert the warning is in the return string
    assert "Only scraped first 3 URLs" in res
    assert "Success: Extracted content from 3 URLs" in res
    
    # Assert it only wrote 3 times
    assert mock_get.call_count == 3

@patch("tools.research_tools.requests.get")
@patch("builtins.open", new_callable=mock_open)
def test_read_urls_bot_blocked(mock_file, mock_get):
    """Error Handling: Ensures sites that block bots return a clean error string and write nothing."""
    mock_response = MagicMock()
    mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError("403 Forbidden")
    mock_get.return_value = mock_response
    
    res = _read_urls(["https://strict-site.com"])
    
    assert res == "Error: Failed to extract readable content from the provided URLs."
    mock_file().write.assert_not_called()  # Proves nothing was written to disk

@patch("tools.research_tools.requests.get")
@patch("builtins.open", new_callable=mock_open)
def test_read_urls_no_readable_content(mock_file, mock_get):
    """Error Handling: Ensures pages with no main body write nothing to the file."""
    mock_response = MagicMock()
    mock_response.text = "<html><script>ReactApp</script></html>"
    mock_get.return_value = mock_response
    
    res = _read_urls(["https://js-app.com"])
    
    assert res == "Error: Failed to extract readable content from the provided URLs."
    mock_file().write.assert_not_called()

@patch("tools.research_tools.requests.get")
@patch("builtins.open", new_callable=mock_open)
def test_read_urls_junk_removal(mock_file, mock_get):
    """
    Integration Test: Proves our deterministic BeautifulSoup cleaner 
    destroys navigation, sidebars, footers, and scripts BEFORE writing to the file.
    """
    messy_html = """
    <html>
        <body>
            <nav><ul><li>Home</li></ul></nav>
            <aside><p>SPAMMY PRODUCT!</p></aside>
            <main><article><h1>Fusion Breakthrough</h1></article></main>
            <footer><p>Copyright 2026</p></footer>
            <script>sendTrackingData();</script>
        </body>
    </html>
    """
    mock_response = MagicMock()
    mock_response.text = messy_html
    mock_get.return_value = mock_response
    
    _read_urls(["https://junk-test.com"])
    
    # Extract what was written to the file
    handle = mock_file()
    written_text = "".join(call.args[0] for call in handle.write.call_args_list)
    
    # 1. Assert the core data SURVIVED
    assert "Fusion Breakthrough" in written_text
    
    # 2. Assert the junk was DESTROYED
    assert "Home" not in written_text
    assert "SPAMMY PRODUCT" not in written_text
    assert "Copyright 2026" not in written_text
    assert "sendTrackingData" not in written_text


@patch("tools.research_tools._search_web")
def test_web_researcher_search_routing(mock_search):
    """Routing: Ensures action='search' calls the correct helper."""
    mock_search.return_value = [{"title": "Result"}]
    res = web_researcher(action="search", search_query="quantum physics")
    mock_search.assert_called_once_with("quantum physics")
    assert res == [{"title": "Result"}]

@patch("tools.research_tools._read_urls")
def test_web_researcher_read_routing(mock_read):
    """Routing: Ensures action='read' calls the correct helper and passes conversation_id."""
    mock_read.return_value = "Success: Appended to file."
    
    res = web_researcher(action="read", urls_to_read=["https://site.com"], conversation_id=99)
    
    mock_read.assert_called_once_with(["https://site.com"], 99)
    assert res == "Success: Appended to file."

def test_web_researcher_invalid_action():
    res = web_researcher(action="hack_mainframe")
    assert "Error: Invalid action" in res

def test_web_researcher_missing_search_query():
    res = web_researcher(action="search", search_query="")
    assert "Error: You must provide a 'search_query'" in res

def test_web_researcher_missing_urls():
    res1 = web_researcher(action="read", urls_to_read=None)
    assert "Error: You must provide 'urls_to_read' as a list" in res1