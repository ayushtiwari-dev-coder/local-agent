# tools/notion_tools.py

import requests
from datetime import datetime
import utils.config_manager as config_manager
from tools.core import agent_tool

# =====================================================================
# INTERNAL HELPERS (Hidden from LLM)
# =====================================================================
import re

def _clean_id(raw_id: str) -> str:
    """Strips URLs, hyphens, and query params to extract the clean 32-character Notion ID."""
    if not raw_id:
        return ""
    # Extract 32-character hex string (with or without hyphens)
    clean = raw_id.split("/")[-1].split("?")[0].replace("-", "")
    match = re.search(r"([a-f0-9]{32})", clean, re.IGNORECASE)
    if match:
        return match.group(1)
    return raw_id.strip()

def _get_db_id(db_key: str) -> str:
    """Dynamically fetches and cleans a specific database ID from the config."""
    dbs = config_manager.get_notion_dbs()
    db_id = dbs.get(db_key)
    if not db_id:
        raise ValueError(f"Missing Notion Database ID for '{db_key}'. Please configure it in the CLI.")
    return _clean_id(db_id) # <--- Cleans the ID automatically!

def _notion_api_request(endpoint: str, method: str = "POST", payload: dict = None) -> dict:
    """Central boilerplate for all Notion API requests."""
    notion_key = config_manager.get_tool_api_key("notion")
    if not notion_key:
        return {"status": "error", "message": "Notion API key is missing. Please configure it in the CLI."}

    headers = {
        "Authorization": f"Bearer {notion_key}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
    }

    url = f"https://api.notion.com/v1/{endpoint}"

    try:
        if method == "POST":
            response = requests.post(url, headers=headers, json=payload)
        elif method == "PATCH":
            response = requests.patch(url, headers=headers, json=payload)
        else:
            return {"status": "error", "message": f"Unsupported method: {method}"}

        if response.status_code in (200, 201):
            return {"status": "success", "data": response.json()}
        else:
            error_data = response.json()
            return {"status": "error", "message": f"Notion API Error: {error_data.get('message', response.text)}"}

    except Exception as e:
        return {"status": "error", "message": f"Request failed: {str(e)}"}

def _get_project_id(project_name: str) -> str:
    """Queries the Projects database to find the exact Notion Page ID for a project name."""
    try:
        db_projects = _get_db_id("db_projects")
    except ValueError as e:
        return f"Error: {str(e)}"

    payload = {
        "filter": {
            "property": "Name",
            "title": {"equals": project_name}
        }
    }
    
    res = _notion_api_request(f"databases/{db_projects}/query", method="POST", payload=payload)
    
    if res["status"] == "error":
        return f"Error querying projects: {res['message']}"
        
    results = res["data"].get("results", [])
    
    if len(results) == 0:
        return f"Error: No project found with the exact name '{project_name}'."
    if len(results) > 1:
        return f"Error: Multiple projects found with the name '{project_name}'. Please be more specific."
        
    return results[0]["id"]


# =====================================================================
# AGENT TOOLS (Exposed to the LLM)
# =====================================================================

@agent_tool
def list_active_projects() -> str:
    """
    Returns a list of all active project names in notion Projects database. 
    Use this if you are unsure of the exact spelling of a project name before logging reasoning.
    """
    try:
        db_projects = _get_db_id("db_projects")
    except ValueError as e:
        return f"Error: {str(e)}"

    payload = {
        "filter": {
            "property": "Status",
            "select": {"equals": "Active"}
        }
    }
    res = _notion_api_request(f"databases/{db_projects}/query", method="POST", payload=payload)
    
    if res["status"] == "error":
        return res["message"]
        
    names = []
    for page in res["data"].get("results", []):
        try:
            name = page["properties"]["Name"]["title"][0]["plain_text"]
            names.append(name)
        except (KeyError, IndexError):
            continue
            
    if not names:
        return "No active projects found."
    return "Active Projects: " + ", ".join(names)


@agent_tool
def create_project(name: str, description: str, reasoning: str, status: str) -> str:
    """
    Create a new project in the Projects hub table in notion.
    Args:
        name: Unique project name.
        description: What the project is.
        reasoning: Why this project was started; the core motivation.
        status: MUST be 'Active', 'Paused', or 'Completed'.
    """
    if status not in ["Active", "Paused", "Completed"]:
        return "Error: Status must be 'Active', 'Paused', or 'Completed'."

    try:
        db_projects = _get_db_id("db_projects")
    except ValueError as e:
        return f"Error: {str(e)}"

    payload = {
        "parent": {"database_id": db_projects},
        "properties": {
            "Name": {"title": [{"text": {"content": name}}]},
            "Description": {"rich_text": [{"text": {"content": description}}]},
            "Reasoning": {"rich_text": [{"text": {"content": reasoning}}]},
            "Status": {"select": {"name": status}}
        }
    }
    
    res = _notion_api_request("pages", method="POST", payload=payload)
    return "Success: Project created." if res["status"] == "success" else res["message"]


@agent_tool
def complete_project(project_name: str) -> str:
    """
    Mark a project as Completed and stamp End Date with the current date. In notion Projects database
    """
    project_id = _get_project_id(project_name)
    if project_id.startswith("Error"):
        return project_id

    today_str = datetime.now().strftime("%Y-%m-%d")

    payload = {
        "properties": {
            "Status": {"select": {"name": "Completed"}},
            "End Date": {"date": {"start": today_str}}
        }
    }
    
    res = _notion_api_request(f"pages/{project_id}", method="PATCH", payload=payload)
    return f"Success: Project '{project_name}' marked as completed." if res["status"] == "success" else res["message"]


@agent_tool
def log_project_reasoning(project_name: str, thought: str, context: str, type: str) -> str:
    """
    Log a thought, bug fix, or architectural decision against an existing project.
    Args:
        project_name: Name of the existing project.
        thought: What was done or thought.
        context: Which function, file, or bug this concerns.
        type: MUST be 'Architecture', 'Bug Fix', or 'Feature'.
        Log a thought, bug fix, or architectural decision into your Notion Project Reasoning database.
    """
    if type not in ["Architecture", "Bug Fix", "Feature"]:
        return "Error: Type must be 'Architecture', 'Bug Fix', or 'Feature'."

    try:
        db_reasoning = _get_db_id("db_reasoning")
    except ValueError as e:
        return f"Error: {str(e)}"

    project_id = _get_project_id(project_name)
    if project_id.startswith("Error"):
        return project_id

    payload = {
        "parent": {"database_id": db_reasoning},
        "properties": {
            "Thought": {"title": [{"text": {"content": thought}}]},
            "Context": {"rich_text": [{"text": {"content": context}}]},
            "Type": {"select": {"name": type}},
            "Project": {"relation": [{"id": project_id}]}
        }
    }
    
    res = _notion_api_request("pages", method="POST", payload=payload)
    return "Success: Reasoning logged." if res["status"] == "success" else res["message"]


@agent_tool
def log_knowledge(project_name: str, topic: str, proficiency: str, reasoning: str) -> str:
    """
    Record a skill/topic learned, tied to the project that forced learning it inside Notion knowledge database.
    Args:
        project_name: Name of the existing project.
        topic: e.g. 'SQLite Vector Search', 'FastAPI'.
        proficiency: MUST be 'Learning', 'Medium', or 'Master'.
        reasoning: Why this was learned; what problem it solved.
    """
    if proficiency not in ["Learning", "Medium", "Master"]:
        return "Error: Proficiency must be 'Learning', 'Medium', or 'Master'."

    try:
        db_knowledge = _get_db_id("db_knowledge")
    except ValueError as e:
        return f"Error: {str(e)}"

    project_id = _get_project_id(project_name)
    if project_id.startswith("Error"):
        return project_id

    payload = {
        "parent": {"database_id": db_knowledge},
        "properties": {
            "Topic": {"title": [{"text": {"content": topic}}]},
            "Proficiency": {"select": {"name": proficiency}},
            "Reasoning": {"rich_text": [{"text": {"content": reasoning}}]},
            "Project": {"relation": [{"id": project_id}]}
        }
    }
    
    res = _notion_api_request("pages", method="POST", payload=payload)
    return "Success: Knowledge logged." if res["status"] == "success" else res["message"]


@agent_tool
def brain_dump(raw_text: str) -> str:
    """
    Capture a raw, unstructured thought directly into your Notion Brain Dumps database.
    Use this whenever the user wants to save a random thought or general update to Notion.
    Args:
        raw_text: The thought itself.
    """
    try:
        db_brain_dumps = _get_db_id("db_brain_dumps")
    except ValueError as e:
        return f"Error: {str(e)}"

    payload = {
        "parent": {"database_id": db_brain_dumps},
        "properties": {
            "Raw Text": {"title": [{"text": {"content": raw_text}}]}
        }
    }
    res = _notion_api_request("pages", method="POST", payload=payload)
    return "Success: Brain dump saved." if res["status"] == "success" else res["message"]


@agent_tool
def log_idea(idea: str, reasoning: str) -> str:
    """
    Capture a standalone idea, disconnected from any current project in notion Ideas database.
    Args:
        idea: What the idea is.
        reasoning: Why it's a good idea; where it came from; the logic behind it.
    """
    try:
        db_ideas = _get_db_id("db_ideas")
    except ValueError as e:
        return f"Error: {str(e)}"

    payload = {
        "parent": {"database_id": db_ideas},
        "properties": {
            "Idea": {"title": [{"text": {"content": idea}}]},
            "Reasoning": {"rich_text": [{"text": {"content": reasoning}}]}
        }
    }
    res = _notion_api_request("pages", method="POST", payload=payload)
    return "Success: Idea saved." if res["status"] == "success" else res["message"]