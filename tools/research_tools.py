import os
import re
import requests
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from tools.core import agent_tool
from ddgs import DDGS
from tools.file_tools import get_sandbox_root
from utils import config_manager

logger = logging.getLogger("tools.research_tools")

def _sanitize_topic(topic: str) -> str:
    """Strips invalid OS filename characters and prevents path traversal."""
    if not topic:
        return "general"
    clean = re.sub(r'[^a-zA-Z0-9_]', '_', str(topic))
    return clean.strip('_') or "general"

import time

def _search_web_bulk(queries: list[str], max_results: int = 4) -> dict:
    """
    Executes multiple web search queries safely without triggering DuckDuckGo rate limits.
    Keeps everything inside 1 single tool execution turn.
    """
    results = {}
    try:
        with DDGS() as ddgs:
            for q in queries:
                try:
                    # Execute search
                    res = list(ddgs.text(q, max_results=max_results))
                    results[q] = res if res else [{"snippet": "No results found on web."}]
                except Exception as search_err:
                    results[q] = [{"error": f"Search failed: {str(search_err)}"}]
                

                time.sleep(0.3)
    except Exception as e:
        logger.error(f"DDGS Session failed: {e}")
        for q in queries:
            if q not in results:
                results[q] = [{"error": f"DDGS Session error: {e}"}]

    return results

def _read_urls(urls: list[str], filepath: str) -> str:
    """Internal function to fetch, clean, and save webpage content to a dynamic scratchpad."""
    urls_to_process = urls[:3]
    warning = (
        " (Note: Only scraped first 3 URLs to prevent timeouts.)"
        if len(urls) > 3
        else ""
    )

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }

    jina_key = config_manager.get_tool_api_key("jina")
    if jina_key:
        headers["Authorization"] = f"Bearer {jina_key}"

    success_count = 0
    for url in urls_to_process:
        try:
            jina_url = f"https://r.jina.ai/{url}"
            response = requests.get(jina_url, headers=headers, timeout=15)
            response.raise_for_status()

            clean_text = response.text
            if clean_text:
                with open(filepath, "a", encoding="utf-8") as f:
                    f.write(f"\n\n### Source: {url}\n\n")
                    f.write(clean_text[:15000])  # Cap at 15k chars per URL
                success_count += 1
        except Exception as e:
            logger.error(f"Failed to read URL '{url}': {e}")

    if success_count > 0:
        filename = os.path.basename(filepath)
        return (
            f"Success: Extracted content from {success_count} URLs and appended to "
            f"'{filename}'.{warning} "
            f"ONLY use the `read_files` tool to read this file AFTER you have completed all your research."
        )
    else:
        return "Error: Failed to extract readable content from the provided URLs."

@agent_tool
def web_researcher(
    action: str,
    topic_name: str = "general",
    search_queries: list[str] = None,
    urls_to_read: list[str] = None,
    conversation_id: int = None,
):
    """
    The ultimate tool for internet research. MUST be used in two steps:

    Step 1: action="search" with 'topic_name' AND 'search_queries' (a list of query strings). Returns top links and snippets.
    Step 2: action="read" with 'topic_name' and 'urls_to_read' (a list of URL strings). Saves full text to a scratchpad file.

    CRITICAL RULES:
    - BATCH YOUR SEARCHES: Always pass multiple queries in `search_queries` (e.g. ["query 1", "query 2"]) to research 
      everything in a single turn. Do NOT do one search per turn.
    - 'topic_name' MUST be a short, 1-2 word description of the current task.
    - For simple factual questions, DO NOT use action="read". The search snippets are enough!
    - The "read" action will NOT return text directly. It saves text to a file. You must use `read_files` on the generated filename later.
    """
    safe_topic = _sanitize_topic(topic_name)

    filename = (
        f"research_{conversation_id}_{safe_topic}.md"
        if conversation_id
        else f"research_{safe_topic}.md"
    )
    filepath = os.path.join(get_sandbox_root(), filename)

    if action == "search":
        if not search_queries or not isinstance(search_queries, list):
            return "Error: You must provide 'search_queries' as a list of strings when action is 'search'."
        return _search_web_bulk(search_queries)

    elif action == "read":
        if not urls_to_read or not isinstance(urls_to_read, list):
            return "Error: You must provide 'urls_to_read' as a list of URL strings when action is 'read'."
        return _read_urls(urls_to_read, filepath)

    else:
        return f"Error: Invalid action '{action}'. Must be 'search' or 'read'."