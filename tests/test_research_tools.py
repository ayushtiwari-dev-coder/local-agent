# tests/test_research_tools.py

import pytest
import requests
import os
import tempfile
from unittest.mock import patch, MagicMock, mock_open, ANY

from tools.research_tools import _search_web_bulk, _read_urls, web_researcher

@pytest.fixture(autouse=True)
def sandbox_research_fixture():
    """
    Safely sandboxes the get_sandbox_root function for all research tools tests,
    preventing any PermissionError writes to the host file system.
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        with patch("tools.research_tools.get_sandbox_root", return_value=temp_dir):
            yield temp_dir

@patch("tools.research_tools.DDGS")
def test_search_web_success(mock_ddgs):
    """Happy Path: Ensures bulk DuckDuckGo returns the expected dict of lists."""
    mock_instance = MagicMock()
    mock_instance.text.return_value = [
        {"title": "Test Site", "href": "https://test.com", "body": "Test snippet"}
    ]
    mock_ddgs.return_value.__enter__.return_value = mock_instance

    res = _search_web_bulk(["test query 1", "test query 2"])
    
    assert len(res) == 2
    assert "test query 1" in res
    assert res["test query 1"][0]["title"] == "Test Site"

@patch("tools.research_tools.DDGS")
def test_search_web_exception(mock_ddgs):
    """Error Handling: Ensures network timeouts return a clean error dict."""
    mock_ddgs.side_effect = Exception("Connection timed out")

    res = _search_web_bulk(["test query"])
    
    assert "error" in res["test query"][0]
    assert "Connection timed out" in res["test query"][0]["error"]

@patch("tools.research_tools.config_manager.get_tool_api_key")
@patch("tools.research_tools.requests.get")
@patch("builtins.open", new_callable=mock_open)
def test_read_urls_success(mock_file, mock_get, mock_get_key):
    """Happy Path: Ensures valid URLs are fetched via Jina, cleaned, and saved."""
    mock_get_key.return_value = "fake_jina_key_123"
    
    mock_response = MagicMock()
    mock_response.text = "# Clean Extracted Markdown Data"
    mock_response.headers = {"x-usage-tokens": "2048"}
    mock_get.return_value = mock_response

    res = _read_urls(["https://site1.com", "https://site2.com"], "dummy_path.md")

    assert mock_get.call_count == 2
    mock_get.assert_any_call("https://r.jina.ai/https://site1.com", headers=ANY, timeout=15)
    
    call_kwargs = mock_get.call_args_list[0][1]
    assert "Authorization" in call_kwargs["headers"]
    assert call_kwargs["headers"]["Authorization"] == "Bearer fake_jina_key_123"

    assert "Success: Extracted content from 2 URLs" in res
    assert "dummy_path.md" in res

    mock_file.assert_called_with("dummy_path.md", "a", encoding="utf-8")

@patch("tools.research_tools.config_manager.get_tool_api_key", return_value=None)
@patch("tools.research_tools.requests.get")
def test_read_urls_over_limit(mock_get, mock_get_key):
    """Edge Case: Ensures passing > 3 URLs slices the list and warns the LLM."""
    mock_response = MagicMock()
    mock_response.text = "Content"
    mock_response.headers = {}
    mock_get.return_value = mock_response

    urls = ["url1", "url2", "url3", "url4", "url5"]
    with patch("builtins.open", mock_open()):
        res = _read_urls(urls, "dummy.md")

    assert "Only scraped first 3 URLs" in res
    assert "Success: Extracted content from 3 URLs" in res
    assert mock_get.call_count == 3

@patch("tools.research_tools.config_manager.get_tool_api_key", return_value=None)
@patch("tools.research_tools.requests.get")
def test_read_urls_bot_blocked(mock_get, mock_get_key):
    """Error Handling: Ensures sites that block requests return clean error string."""
    mock_response = MagicMock()
    mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError("403 Forbidden")
    mock_get.return_value = mock_response

    with patch("builtins.open", mock_open()) as mock_file:
        res = _read_urls(["https://strict-site.com"], "dummy.md")

    assert res == "Error: Failed to extract readable content from the provided URLs."
    mock_file().write.assert_not_called()

@patch("tools.research_tools._search_web_bulk")
def test_web_researcher_search_routing(mock_search):
    """Routing: Ensures action='search' calls the correct helper."""
    mock_search.return_value = {"quantum physics": [{"title": "Result"}]}
    res = web_researcher(action="search", search_queries=["quantum physics"])
    mock_search.assert_called_once_with(["quantum physics"])
    assert res == {"quantum physics": [{"title": "Result"}]}

@patch("tools.research_tools._read_urls")
def test_web_researcher_read_routing(mock_read):
    """Routing: Ensures action='read' calls the correct helper and dynamic filepath."""
    mock_read.return_value = "Success: Appended to file."
    res = web_researcher(
        action="read",
        topic_name="test_topic",
        urls_to_read=["https://site.com"],
        conversation_id=99
    )
    mock_read.assert_called_once_with(["https://site.com"], ANY)
    assert res == "Success: Appended to file."

def test_web_researcher_invalid_action():
    res = web_researcher(action="hack_mainframe")
    assert "Error: Invalid action" in res

def test_web_researcher_missing_search_query():
    res = web_researcher(action="search", search_queries=None)
    assert "Error: You must provide 'search_queries' as a list" in res

def test_web_researcher_missing_urls():
    res1 = web_researcher(action="read", urls_to_read=None)
    assert "Error: You must provide 'urls_to_read' as a list" in res1