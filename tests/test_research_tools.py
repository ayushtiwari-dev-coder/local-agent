# tests/test_research_tools.py

import pytest
from unittest.mock import patch, MagicMock
from tools.research_tools import _search_web, _read_urls, web_researcher
import requests


@patch("tools.research_tools.DDGS")
def test_search_web_success(mock_ddgs):
    """Happy Path: Ensures DuckDuckGo returns the expected list of dicts."""
    mock_instance = MagicMock()
    mock_instance.text.return_value = [
        {"title": "Test Site", "href": "https://test.com", "body": "Test snippet"}
    ]
    # Mock the context manager (with DDGS() as ddgs:)
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
def test_read_urls_success(mock_get):
    """Happy Path: Ensures valid URLs are fetched and extracted."""
    mock_response = MagicMock()
    mock_response.text = "<html><body><p>Clean extracted text</p></body></html>"
    mock_get.return_value = mock_response
    
    res = _read_urls(["https://site1.com", "https://site2.com"])
    
    assert "Clean extracted text" in res["https://site1.com"]
    assert "Clean extracted text" in res["https://site2.com"]
    assert "SYSTEM_WARNING" not in res

@patch("tools.research_tools.requests.get")
def test_read_urls_over_limit(mock_get):
    """Edge Case: Ensures passing > 3 URLs slices the list and warns the LLM."""
    mock_response = MagicMock()
    mock_response.text = "<html><body><p>Clean text</p></body></html>"
    mock_get.return_value = mock_response
    
    urls = ["url1", "url2", "url3", "url4", "url5"]
    res = _read_urls(urls)
    
    assert "SYSTEM_WARNING" in res
    assert "Only scraped the first 3 URLs" in res["SYSTEM_WARNING"]
    assert "url1" in res and "url2" in res and "url3" in res
    assert "url4" not in res  # Proves it was sliced out

@patch("tools.research_tools.requests.get")
def test_read_urls_bot_blocked(mock_get):
    """Error Handling: Ensures sites that block bots (returning 403 Forbidden) are handled."""
    # Simulate a 403 Forbidden error raised by response.raise_for_status()
    mock_response = MagicMock()
    mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError("403 Forbidden")
    mock_get.return_value = mock_response
    
    res = _read_urls(["https://strict-site.com"])
    assert "Error: Failed to fetch webpage" in res["https://strict-site.com"]
    assert "403 Forbidden" in res["https://strict-site.com"]

@patch("tools.research_tools.requests.get")
def test_read_urls_no_readable_content(mock_get):
    """Error Handling: Ensures pages with no main body (like pure JS apps) are handled."""
    mock_response = MagicMock()
    # Provide HTML where all content is inside a junk tag (<script>)
    mock_response.text = "<html><script>ReactApp</script></html>"
    mock_get.return_value = mock_response
    
    res = _read_urls(["https://js-app.com"])
    assert "Error: Page contained no readable text after cleaning." in res["https://js-app.com"]

@patch("tools.research_tools.requests.get")
def test_read_urls_exception(mock_get):
    """Error Handling: Ensures timeouts are caught specifically."""
    mock_get.side_effect = requests.exceptions.Timeout("Read timed out")
    
    res = _read_urls(["https://slow-site.com"])
    assert "Error: Connection timed out." in res["https://slow-site.com"]


@patch("tools.research_tools._search_web")
def test_web_researcher_search_routing(mock_search):
    """Routing: Ensures action='search' calls the correct helper."""
    mock_search.return_value = [{"title": "Result"}]
    
    res = web_researcher(action="search", search_query="quantum physics")
    mock_search.assert_called_once_with("quantum physics")
    assert res == [{"title": "Result"}]

@patch("tools.research_tools._read_urls")
def test_web_researcher_read_routing(mock_read):
    """Routing: Ensures action='read' calls the correct helper."""
    mock_read.return_value = {"https://site.com": "Data"}
    
    res = web_researcher(action="read", urls_to_read=["https://site.com"])
    mock_read.assert_called_once_with(["https://site.com"])
    assert res == {"https://site.com": "Data"}

def test_web_researcher_invalid_action():
    """LLM Mistake: Ensures hallucinated actions are rejected."""
    res = web_researcher(action="hack_mainframe")
    assert "Error: Invalid action" in res

def test_web_researcher_missing_search_query():
    """LLM Mistake: Ensures missing search query is caught."""
    res = web_researcher(action="search", search_query="")
    assert "Error: You must provide a 'search_query'" in res

def test_web_researcher_missing_urls():
    """LLM Mistake: Ensures missing or malformed URLs are caught."""
    # Missing completely
    res1 = web_researcher(action="read", urls_to_read=None)
    assert "Error: You must provide 'urls_to_read' as a list" in res1
    
    # Passed as a string instead of a list
    res2 = web_researcher(action="read", urls_to_read="https://site.com")
    assert "Error: You must provide 'urls_to_read' as a list" in res2

@patch("tools.research_tools.requests.get")
def test_read_urls_junk_removal(mock_get):
    """
    Integration Test: Proves our deterministic BeautifulSoup cleaner 
    destroys navigation, sidebars, footers, and scripts.
    """
    messy_html = """
    <html>
        <head><title>Junk Test Page</title></head>
        <body>
            <header>
                <nav><ul><li>Home</li><li>About Us</li><li>Contact</li></ul></nav>
            </header>
            <aside class="advertisement">
                <p>CLICK HERE TO BUY OUR SPAMMY PRODUCT!</p>
            </aside>
            <main>
                <article>
                    <h1>Nuclear Fusion Breakthrough</h1>
                    <p>Scientists have successfully sustained a fusion reaction for 24 hours.</p>
                </article>
            </main>
            <footer>
                <p>Copyright 2026 ScamCompany Inc. All rights reserved.</p>
                <a href="/privacy">Privacy Policy</a>
            </footer>
            <script>
                sendTrackingData("user_stolen_data");
            </script>
        </body>
    </html>
    """
    
    # Mock the requests response
    mock_response = MagicMock()
    mock_response.text = messy_html
    mock_get.return_value = mock_response
    
    res = _read_urls(["https://junk-test.com"])
    clean_text = res["https://junk-test.com"]
    
    # 1. Assert the core data SURVIVED
    assert "Nuclear Fusion Breakthrough" in clean_text
    assert "Scientists have successfully sustained a fusion reaction" in clean_text
    
    # 2. Assert the junk was DESTROYED
    assert "Home" not in clean_text
    assert "About Us" not in clean_text
    assert "SPAMMY PRODUCT" not in clean_text
    assert "Copyright 2026" not in clean_text
    assert "Privacy Policy" not in clean_text
    assert "sendTrackingData" not in clean_text