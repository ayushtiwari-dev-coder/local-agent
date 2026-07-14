import os
import requests
from bs4 import BeautifulSoup
import logging
from tools.core import agent_tool
from ddgs import DDGS
from tools.file_tools import get_sandbox_root

logger = logging.getLogger("tools.research_tools")


def _search_web(query: str, max_results: int = 5) -> list[dict]:
    """Internal function to handle web searches."""
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
        return results
    except Exception as e:
        logger.error(f"Web search failed for query '{query}': {e}")
        return [{"error": f"Search failed: {str(e)}"}]


def _read_urls(urls: list[str], conversation_id: int = None) -> str:
    """Internal function to fetch, clean, and save webpage content to a dynamic scratchpad."""
    urls_to_process = urls[:3]
    warning = (
        " (Note: Only scraped first 3 URLs to prevent timeouts.)"
        if len(urls) > 3
        else ""
    )

    # DYNAMIC FILENAME: Prevents multi-agent/multi-chat overwrite collisions
    filename = (
        f"research_notes_{conversation_id}.md"
        if conversation_id
        else "research_notes.md"
    )
    filepath = os.path.join(get_sandbox_root(), filename)

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    success_count = 0

    for url in urls_to_process:
        try:
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, "html.parser")

            junk_tags = [
                "nav",
                "header",
                "footer",
                "aside",
                "script",
                "style",
                "meta",
                "noscript",
                "form",
                "iframe",
            ]
            for junk in soup(junk_tags):
                junk.decompose()

            text = soup.get_text(separator="\n")
            clean_lines = [line.strip() for line in text.splitlines() if line.strip()]
            clean_text = "\n".join(clean_lines)

            if clean_text:
                # APPEND to the scratchpad file
                with open(filepath, "a", encoding="utf-8") as f:
                    f.write(f"\n\n### Source: {url}\n\n")
                    f.write(clean_text)
                success_count += 1

        except Exception as e:
            logger.error(f"Failed to read URL '{url}': {e}")

    if success_count > 0:
        # THE NEW LLM INSTRUCTION STRING
        return (
            f"Success: Extracted content from {success_count} URLs and appended to '{filename}'.{warning} "
            f"ONLY use the `read_files` tool to read this file AFTER you have completed all your research."
        )
    else:
        return "Error: Failed to extract readable content from the provided URLs."


@agent_tool
def web_researcher(
    action: str,
    search_query: str = "",
    urls_to_read: list[str] = None,
    conversation_id: int = None,
):
    """
    The ultimate tool for internet research. MUST be used in two steps:

    Step 1: action="search" with 'search_query'. Returns top links and snippets.
    Step 2: action="read" with 'urls_to_read' (a list of URLs).

    CRITICAL RULES:
    - For simple factual questions (e.g., sports scores, weather), DO NOT use action="read". The search snippets are enough!
    - The "read" action will NOT return text. It saves text to a file. You must use `read_files` to read it later.
    """
    if action == "search":
        if not search_query:
            return "Error: You must provide a 'search_query' when action is 'search'."
        return _search_web(search_query)

    elif action == "read":
        if not urls_to_read or not isinstance(urls_to_read, list):
            return "Error: You must provide 'urls_to_read' as a list of URL strings when action is 'read'."
        return _read_urls(urls_to_read, conversation_id)

    else:
        return f"Error: Invalid action '{action}'. Must be 'search' or 'read'."
