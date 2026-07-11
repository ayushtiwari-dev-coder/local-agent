# tools/research_tools.py

import logging
from tools.core import agent_tool
from ddgs import DDGS
import requests
from bs4 import BeautifulSoup

logger = logging.getLogger("tools.research_tools")


def _search_web(query: str, max_results: int = 10) -> list[dict]:
    """Internal function to handle web searches."""
    try:
        with DDGS() as ddgs:
            # Returns a list of dicts containing 'title', 'href', and 'body'
            results = list(ddgs.text(query, max_results=max_results))
        return results
    except Exception as e:
        logger.error(f"Web search failed for query '{query}': {e}")
        return [{"error": f"Search failed: {str(e)}"}]



def _read_urls(urls: list[str]) -> dict:
    """Internal function to fetch and deterministically clean webpage content."""
    results = {}
    
    # HARD LIMIT: Cap at 3 URLs
    urls_to_process = urls[:3]
    if len(urls) > 3:
        results["SYSTEM_WARNING"] = "Only scraped the first 3 URLs to prevent timeouts. Please process these first."

    # Headers to prevent basic bot-blocking
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

    for url in urls_to_process:
        try:
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, "html.parser")
            
            # 1. DETERMINISTIC JUNK DESTRUCTION
            # We explicitly remove tags that NEVER contain the main article body
            junk_tags = [
                "nav", "header", "footer", "aside", "script", "style", 
                "meta", "noscript", "form", "iframe"
            ]
            for junk in soup(junk_tags):
                junk.decompose() # Completely destroys the tag and its contents
                
            # 2. Extract the remaining text, separating blocks with newlines
            text = soup.get_text(separator="\n")
            
            # 3. Clean up massive whitespace gaps to save tokens
            clean_lines = [line.strip() for line in text.splitlines() if line.strip()]
            clean_text = "\n".join(clean_lines)
            
            if clean_text:
                results[url] = clean_text
            else:
                results[url] = "Error: Page contained no readable text after cleaning."
                
        except requests.exceptions.Timeout:
            results[url] = "Error: Connection timed out."
        except Exception as e:
            logger.error(f"Failed to read URL '{url}': {e}")
            results[url] = f"Error: Failed to fetch webpage ({str(e)})"
            
    return results

@agent_tool
def web_researcher(action: str, search_query: str = "", urls_to_read: list[str] = None):
    """
    The ultimate tool for internet research. MUST be used in two steps:
    
    Step 1: Set action="search" and provide a 'search_query'. Returns top links and snippets.
    Step 2: Set action="read" and provide 'urls_to_read' (a list of URLs). Returns the full, clean text of the pages.
    
    RULES:
    - You can only read up to 3 URLs at a time.
    - Always 'search' first to find reliable sources before reading.
    """
    if action == "search":
        if not search_query:
            return "Error: You must provide a 'search_query' when action is 'search'."
        return _search_web(search_query)
        
    elif action == "read":
        if not urls_to_read or not isinstance(urls_to_read, list):
            return "Error: You must provide 'urls_to_read' as a list of URL strings when action is 'read'."
        return _read_urls(urls_to_read)
        
    else:
        return f"Error: Invalid action '{action}'. Must be 'search' or 'read'."