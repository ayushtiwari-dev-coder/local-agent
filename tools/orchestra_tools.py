# tools/orchestra_tools.py
import json
import threading
from engine.agent_template import AgentTemplate
from engine.agent_profiles import AGENT_PROFILES
from managers.conversation_manager import start_new_conversation, save_assistant_message
from queries.message_queries import create_message
from queries.project_queries import get_all_projects, create_project
from queries.task_queries import create_task, update_task_status
from queries.subtask_queries import create_sub_task, update_sub_task_status, get_sub_tasks_by_task

def trigger_multi_agent_workflow(conversation_id: int, task: str) -> str:
    """
    Spawns the background Planner and Executor orchestrator.
    Returns a success confirmation immediately so the main CLI remains completely unblocked.
    """
    # 
    thread = threading.Thread(
        target=_run_background_orchestra,
        args=(conversation_id, task)
    )
    thread.daemon = True
    thread.start()
    
    return (
        "[ORCHESTRA SYSTEM]: The Planner and Executor have been successfully spawned "
        "in the background. You can continue typing here. Use the '/status' command "
        "to check on their progress at any time."
    )

def _run_background_orchestra(conversation_id: int, task: str) -> None:
    """
    The main background lifecycle loop.
    Coordinates: Project Check -> Planning (JSON) -> DB Writing -> Sequential Execution.
    """
    try:
        
        project_id = _ensure_project_id()
        
        # 2. Spawn a silent Planner conversation thread 
        planner_session = start_new_conversation(user_id=None, title="[System] Background Planning")
        planner_conv_id = planner_session["id"]
        
        # Inject Planner's system instructions into its thread context [31, 38]

        create_message(planner_conv_id, "system", AGENT_PROFILES["planner"]["system_instruction"])
        
        # Ask the Planner to build the chunked task list [17]
        planner_agent = AgentTemplate.spawn("planner")
        planner_prompt = f"Deconstruct this user request into our structured chunk JSON format:\n{task}"
        
        raw_plan = planner_agent.send_message(planner_conv_id, planner_prompt)
        chunks = _parse_json_safely(raw_plan)
        
        # Notify the main thread that the plan is set [38]
        save_assistant_message(conversation_id, "[BACKGROUND PLANNER]: I have designed a structured execution plan. Kicking off background tasks.")
        
        # 3. Write plan chunks to SQLite using the query layer 
        task_id_queue = []
        for chunk in chunks:
            chunk_title = chunk.get("chunk_title", "Phase Step")
            sub_tasks = chunk.get("sub_tasks", [])
            
            # Create Parent Chunk in standard 'tasks' table 
            chunk_task = create_task(project_id, chunk_title, description="Multi-agent plan chunk.")
            task_id = chunk_task["id"]
            
            # Create child sub-tasks [14]
            for step_desc in sub_tasks:
                create_sub_task(task_id, step_desc)
                
            task_id_queue.append((task_id, chunk_title))
            
        # 4. Sequential Background Execution 
        for task_id, chunk_title in task_id_queue:
            # Update parent chunk state to in_progress 
            update_task_status(task_id, "in_progress")
            save_assistant_message(conversation_id, f"[BACKGROUND EXECUTOR]: Starting {chunk_title}...")
            
            # Gather child sub-tasks for this chunk [41]
            sub_steps = get_sub_tasks_by_task(task_id)
            for step in sub_steps:
                update_sub_task_status(step["id"], "in_progress")
                
            # Create a dedicated conversation sandbox for the Executor [30]
            executor_session = start_new_conversation(user_id=None, title=f"[System] Executor - {chunk_title}")
            executor_conv_id = executor_session["id"]
            
            # Inject Executor rules [38]
            create_message(executor_conv_id, "system", AGENT_PROFILES["executor"]["system_instruction"])
            
            # Format the sub-task objectives
            objectives_text = "\n".join([f"- {step['description']}" for step in sub_steps])
            executor_prompt = f"Complete the following sequential tasks in our workspace:\n{objectives_text}"
            
            # Execute [16, 17]
            executor_agent = AgentTemplate.spawn("executor", autonomous=True)
            result = executor_agent.send_message(executor_conv_id, executor_prompt)
            
            # Mark steps and chunk complete [41]
            for step in sub_steps:
                update_sub_task_status(step["id"], "completed")
            update_task_status(task_id, "completed")
            
            save_assistant_message(conversation_id, f"[BACKGROUND EXECUTOR]: Finished {chunk_title}.\nSummary:\n{result}")
            
        # Final Completion Notice [38]
        save_assistant_message(conversation_id, "[BACKGROUND SYSTEM COMPLETED]: All planned task chunks have executed successfully!")
        
    except Exception as e:
        # Gracefully write the error to the main chat so you know why it failed [38]
        save_assistant_message(conversation_id, f"[BACKGROUND ORCHESTRA ERROR]: Execution failed: {e}")

def _ensure_project_id() -> int:
    """Safely retrieves or creates a default project to satisfy SQLite constraints [39]."""
    projects = get_all_projects() # [39]
    if projects:
        return projects[0]["id"]
    new_project = create_project("Default CLI Workspace", "Auto-created parent workspace.") # [39]
    return new_project["id"]

def _parse_json_safely(text: str) -> list:
    """Strips markdown blocks and extracts the JSON list cleanly."""
    text = text.strip()
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()
    return json.loads(text)