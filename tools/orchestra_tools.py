import json
import threading
from engine.agent_template import AgentTemplate
from engine.agent_profiles import AGENT_PROFILES
from managers.conversation_manager import start_new_conversation, save_assistant_message
from queries.message_queries import create_message
from queries.project_queries import get_all_projects, create_project
from queries.task_queries import create_task, update_task_status
from queries.subtask_queries import create_sub_task, update_sub_task_status, get_sub_tasks_by_task

# Global status delegate holder
_orchestra_status_delegate = None

def register_orchestra_status_callback(callback) -> None:
    global _orchestra_status_delegate
    _orchestra_status_delegate = callback

def background_status_callback(message: str) -> None:
    if _orchestra_status_delegate:
        _orchestra_status_delegate(message)


def _generate_orchestra_plan(task: str) -> list:
    """Spawns the silent Planner session to generate a structured JSON plan."""
    planner_session = start_new_conversation(user_id=None, title="[System] Background Planning")
    planner_conv_id = planner_session["id"]
    
    # Inject system prompts
    create_message(planner_conv_id, "system", AGENT_PROFILES["planner"]["system_instruction"])
    
    # Spawn planner and run request
    planner_agent = AgentTemplate.spawn("planner")
    planner_prompt = f"Deconstruct this user request into our structured chunk JSON format:\n{task}"
    raw_plan = planner_agent.send_message(
        conversation_id=planner_conv_id,
        user_text=planner_prompt,
        status_callback=background_status_callback
    )
    
    return _parse_json_safely(raw_plan)

def _save_plan_to_database(project_id: int, chunks: list) -> list:
    """Writes the chunk plan and sub-tasks safely into the SQLite query layer."""
    task_id_queue = []
    for chunk in chunks:
        chunk_title = chunk.get("chunk_title", "Phase Step")
        sub_tasks = chunk.get("sub_tasks", [])
        
        chunk_task = create_task(project_id, chunk_title, description="Multi-agent plan chunk.")
        task_id = chunk_task["id"]
        
        for step_desc in sub_tasks:
            create_sub_task(task_id, step_desc)
            
        task_id_queue.append((task_id, chunk_title))
    return task_id_queue

def _execute_plan_sequential(conversation_id: int, task_id_queue: list) -> None:
    """Runs each database task step-by-step using an autonomous Executor agent."""
    for task_id, chunk_title in task_id_queue:
        update_task_status(task_id, "in_progress")
        save_assistant_message(conversation_id, f"[BACKGROUND EXECUTOR]: Starting {chunk_title}...")
        
        sub_steps = get_sub_tasks_by_task(task_id)
        for step in sub_steps:
            update_sub_task_status(step["id"], "in_progress")
            
        # Spawn execution agent session
        executor_session = start_new_conversation(user_id=None, title=f"[System] Executor - {chunk_title}")
        executor_conv_id = executor_session["id"]
        create_message(executor_conv_id, "system", AGENT_PROFILES["executor"]["system_instruction"])
        
        objectives_text = "\n".join([f"- {step['description']}" for step in sub_steps])
        executor_prompt = f"Complete the following sequential tasks in our workspace:\n{objectives_text}"
        
        executor_agent = AgentTemplate.spawn("executor", autonomous=True)
        result = executor_agent.send_message(
            conversation_id=executor_conv_id,
            user_text=executor_prompt,
            status_callback=background_status_callback
        )
        
        # Complete tasks inside the database state
        for step in sub_steps:
            update_sub_task_status(step["id"], "completed")
        update_task_status(task_id, "completed")
        
        save_assistant_message(
            conversation_id, 
            f"[BACKGROUND EXECUTOR]: Finished {chunk_title}.\nSummary:\n{result}"
        )



def _run_background_orchestra(conversation_id: int, task: str) -> None:
    """The main background lifecycle loop."""
    try:
        # 1. Setup project sandbox isolated to this conversation
        project_id = _ensure_project_id(conversation_id)
        
        # 2. Plan generation phase
        chunks = _generate_orchestra_plan(task)
        save_assistant_message(
            conversation_id, 
            "[BACKGROUND PLANNER]: I have designed a structured plan. Kicking off background tasks."
        )
        
        # 3. Write planning state to Database
        task_id_queue = _save_plan_to_database(project_id, chunks)
        
        # 4. Sequential loop execution phase
        _execute_plan_sequential(conversation_id, task_id_queue)
        
        # 5. Final Completion Notice
        save_assistant_message(
            conversation_id, 
            "[BACKGROUND SYSTEM COMPLETED]: All planned task chunks have executed successfully!"
        )
    except Exception as e:
        save_assistant_message(
            conversation_id, 
            f"[BACKGROUND ORCHESTRA ERROR]: Execution failed: {e}"
        )

def trigger_multi_agent_workflow(conversation_id: int, task: str) -> str:
    """Spawns the background Planner and Executor orchestrator."""
    thread = threading.Thread(
        target=_run_background_orchestra, args=(conversation_id, task)
    )
    thread.daemon = True
    thread.start()
    return (
        "[ORCHESTRA SYSTEM]: The Planner and Executor have been successfully spawned "
        "in the background. You can continue typing here. Use the '/status' command "
        "to check on their progress at any time."
    )

def _ensure_project_id(conversation_id: int = None) -> int:
    """
    Ensures a project is configured. If conversation_id is provided, 
    isolates tasks into a unique project for that conversation.
    """
    from database.helper import execute_read
    
    if conversation_id is not None:
        project_name = f"Project_Conv_{conversation_id}"
        project = execute_read("SELECT id FROM projects WHERE name = ?;", (project_name,), fetch_one=True)
        if project:
            return project["id"]
        # Create a new isolated project for this conversation
        new_project = create_project(
            project_name, 
            f"Auto-created workspace for Conversation #{conversation_id}"
        )
        return new_project["id"]
    
    # Fallback legacy logic
    projects = get_all_projects()
    if projects:
        return projects[0]["id"]
    new_project = create_project("Default CLI Workspace", "Auto-created parent workspace.")
    return new_project["id"]

def _parse_json_safely(text: str) -> list:
    text = text.strip()
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()
    return json.loads(text)


# tools/orchestra_tools.py

