# FILE: utils/orchestra_helpers.py

import json
from database.helper import execute_read
from queries.project_queries import get_all_projects, create_project
import re

def parse_json_safely(text: str):
    """Extracts and parses JSON from an LLM response, handling markdown blocks and preambles."""
    text = text.strip()
    
    # 1. Clean markdown formatting if present
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
        
    text = text.strip()
    
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # 2. Fallback: Use Regex to extract the first JSON object {} or array []
        match = re.search(r'(\{.*\}|\[.*\])', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass
        return None

def ensure_project_id(conversation_id: int = None) -> int:
    """Ensures a project is configured. Isolates tasks into a unique project for that conversation."""
    if conversation_id is not None:
        project_name = f"Project_Conv_{conversation_id}"
        project = execute_read("SELECT id FROM projects WHERE name = ?;", (project_name,), fetch_one=True)
        if project:
            return project["id"]
        new_project = create_project(project_name, f"Auto-created workspace for Conversation #{conversation_id}")
        return new_project["id"]
        
    projects = get_all_projects()
    if projects:
        return projects[0]["id"]
    new_project = create_project("Default CLI Workspace", "Auto-created parent workspace.")
    return new_project["id"]