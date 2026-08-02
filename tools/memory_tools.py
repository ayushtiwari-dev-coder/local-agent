# tools/memory_tools.py
"""
Long-Term Memory Tools.
Allows the agent to autonomously remember user preferences, facts, and retrieve past context.
"""

from managers.memory_manager import save_semantic_memory, retrieve_semantic_memory
from tools.core import agent_tool


@agent_tool
def remember_user_preferences(preferences: list[dict]) -> dict:
    """
    Autonomously remembers multiple user preferences, settings, or facts in one go.
    Args:
        preferences: e.g. [{"content": "User prefers pytest", "category": "coding"}, ...]
    """
    if not isinstance(preferences, list):
        return {"error": "Expected a list of preference objects."}
        
    results = {}
    for pref in preferences:
        content = pref.get("content")
        category = pref.get("category", "general")
        try:
            save_semantic_memory(content, category)
            results[content[:20] + "..."] = "Successfully stored."
        except Exception as e:
            results[content[:20] + "..."] = f"Failed to store: {e}"
            
    return results

@agent_tool
def search_user_histories(searches: list[dict]) -> dict:
    """
    Searches user context history for multiple queries simultaneously.
    Args:
        searches: e.g. [{"query": "database config", "category": "general"}]
    """
    if not isinstance(searches, list):
        return {"error": "Expected a list of search objects."}
        
    results = {}
    for req in searches:
        query = req.get("query")
        category = req.get("category", "general")
        try:
            matches = retrieve_semantic_memory(query, category)
            results[query] = "\n".join(f"- {m}" for m in matches) if matches else "No relevant history found."
        except Exception as e:
            results[query] = f"Error: {e}"
            
    return results
