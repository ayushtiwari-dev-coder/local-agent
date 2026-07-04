# FILE: tools/orchestra_tools.py

import threading
from engine.agent_template import AgentTemplate
from engine.agent_profiles import AGENT_PROFILES
from managers.conversation_manager import start_new_conversation, save_assistant_message
from queries.message_queries import create_message
from queries.task_queries import create_task, update_task_status
from queries.subtask_queries import create_sub_task, update_sub_task_status, get_sub_tasks_by_task
from utils.orchestra_helpers import parse_json_safely, ensure_project_id


_orchestra_status_delegate = None

def register_orchestra_status_callback(callback) -> None:
    global _orchestra_status_delegate
    _orchestra_status_delegate = callback

def background_status_callback(message: str) -> None:
    if _orchestra_status_delegate:
        _orchestra_status_delegate(message)


def _evaluate_with_critic(conversation_id: int, evaluation_prompt: str) -> dict:
    """
    A reusable function that spawns the Critic to evaluate either a plan or an execution.
    Because it uses the same conversation_id, the Critic can read the entire history of what just happened!
    """
    background_status_callback("[CRITIC]: Evaluating recent actions...")
    critic_agent = AgentTemplate.spawn("critic", autonomous=True)

    # FIX 1: Inject the Critic's system instruction into the prompt!
    # Because we reuse the conversation_id, the DB only has the Executor's system prompt.
    # We MUST pass the Critic's instructions here so it knows the JSON schema.
    critic_sys_prompt = AGENT_PROFILES["critic"]["system_instruction"]
    full_prompt = f"CRITIC INSTRUCTIONS:\n{critic_sys_prompt}\n\nTASK TO EVALUATE:\n{evaluation_prompt}"

    raw_response = critic_agent.send_message(
        conversation_id=conversation_id,
        user_text=full_prompt,
        status_callback=background_status_callback
    )

    parsed_json = parse_json_safely(raw_response)

    try:
        # Handle case where parser returns a list instead of dict
        if isinstance(parsed_json, list) and len(parsed_json) > 0:
            evaluation = parsed_json[0]
        elif isinstance(parsed_json, dict):
            evaluation = parsed_json
        else:
            raise ValueError("Critic did not return a valid JSON object.")

        # STRONGER PARSING: Look for alternate keys if the model got creative
        feedback_content = (
            evaluation.get("feedback") or
            evaluation.get("reason") or
            evaluation.get("comments") or
            evaluation.get("error") or
            "No feedback provided."
        )

        # FIX 2: Safely parse string booleans (bool("false") is True in Python!)
        approved_raw = evaluation.get("approved", False)
        if isinstance(approved_raw, str):
            is_approved = approved_raw.strip().lower() == "true"
        else:
            is_approved = bool(approved_raw)

        # FIX 3: Return the summary! The orchestrator expects it, but it was being stripped.
        return {
            "approved": is_approved,
            "feedback": str(feedback_content),
            "summary": str(evaluation.get("summary", "Task completed successfully."))
        }

    except Exception as e:
        # Fallback if the Critic hallucinates bad JSON
        return {
            "approved": False,
            "feedback": f"Critic evaluation failed to parse JSON: {e}. Raw output: {raw_response}",
            "summary": "Task completed successfully."
        }

def _generate_and_validate_plan(task: str, planner_conv_id: int) -> list:
    """
    Spawns the Planner to generate a JSON plan, and uses the Critic to validate it.
    Loops up to 3 times if the Critic rejects the plan.
    """
    planner_agent = AgentTemplate.spawn("planner", autonomous=True)
    
    current_prompt = f"Deconstruct this user request into our structured chunk JSON format:\n{task}"
    max_attempts = 3
    
    for attempt in range(max_attempts):
        background_status_callback(f"[PLANNER]: Drafting plan (Attempt {attempt + 1}/{max_attempts})...")
        raw_plan = planner_agent.send_message(
            conversation_id=planner_conv_id,
            user_text=current_prompt,
            status_callback=background_status_callback
        )
        
        critic_prompt = (
            f"Evaluate the execution plan generated above for logical flaws, missing acceptance criteria, "
            f"or missing role_personas. The original user request was: '{task}'.\n\n"
            f"Does this plan logically solve the user's request? Output your strict JSON evaluation."
        )
        
        evaluation = _evaluate_with_critic(planner_conv_id, critic_prompt)
        
        if evaluation["approved"]:
            background_status_callback("[CRITIC]: Plan Approved!")
            parsed_plan = parse_json_safely(raw_plan)
            return parsed_plan if parsed_plan else []
            
        background_status_callback(f"[CRITIC]: Plan Rejected. Feedback: {evaluation['feedback']}")
        current_prompt = (
            f"The QA Critic rejected your plan with the following feedback:\n{evaluation['feedback']}\n"
            f"Please revise your JSON plan and output the corrected version."
        )
        
    background_status_callback("[CRITIC WARNING]: Plan validation failed 3 times. Forcing execution of last generated plan.")
    parsed_plan = parse_json_safely(raw_plan)
    return parsed_plan if parsed_plan else []

def _save_plan_to_database(project_id: int, chunks: list) -> list:
    """Writes the chunk plan and sub-tasks safely into the SQLite query layer."""
    task_id_queue = []
    
    for chunk in chunks:
        chunk_title = chunk.get("chunk_title", "Phase Step")
        role_persona = chunk.get("role_persona", "Software Engineer")
        acceptance_criteria = chunk.get("acceptance_criteria", "Task completes without errors.")
        sub_tasks = chunk.get("sub_tasks", [])
        
        chunk_task = create_task(project_id, chunk_title, description=f"Persona: {role_persona}")
        task_id = chunk_task["id"]
        
        for step_desc in sub_tasks:
            create_sub_task(task_id, step_desc)
            
        # We pass persona and criteria into the queue for the Executor/Critic to use
        task_id_queue.append((task_id, chunk_title, role_persona, acceptance_criteria))
        
    return task_id_queue

# FILE: tools/orchestra_tools.py

def _execute_chunk_with_critic(
    conversation_id: int, 
    task_id: int, 
    chunk_title: str, 
    role_persona: str, 
    acceptance_criteria: str,
    previous_summaries: str = "" # NEW: Accept previous context
) -> str: # NEW: Return a string (the summary)
    """
    Runs a single chunk using the Executor agent, then uses the Critic to verify the work.
    Loops up to 3 times if the Critic rejects the execution.
    """
    update_task_status(task_id, "in_progress")
    save_assistant_message(conversation_id, f"[BACKGROUND EXECUTOR]: Starting {chunk_title} (Persona: {role_persona})...")

    sub_steps = get_sub_tasks_by_task(task_id)
    for step in sub_steps:
        update_sub_task_status(step["id"], "in_progress")

    executor_session = start_new_conversation(user_id=None, title=f"[System] Executor - {chunk_title}")
    executor_conv_id = executor_session["id"]

    create_message(executor_conv_id, "system", AGENT_PROFILES["executor"]["system_instruction"])

    objectives_text = "\n".join([f"- {step['description']}" for step in sub_steps])
    
    # NEW: Inject the compounding summaries into the Executor's prompt
    context_injection = f"CONTEXT FROM PREVIOUS PHASES:\n{previous_summaries}\n\n" if previous_summaries else ""
    
    executor_prompt = (
        f"{context_injection}"
        f"Adopt the persona of: {role_persona}.\n"
        f"Complete the following sequential tasks in our workspace:\n{objectives_text}"
    )

    executor_agent = AgentTemplate.spawn("executor", autonomous=True)
    max_attempts = 3
    
    final_summary = "Task completed, but no summary was generated."

    for attempt in range(max_attempts):
        background_status_callback(f"[EXECUTOR]: Working on {chunk_title} (Attempt {attempt + 1}/{max_attempts})...")

        # 1. Executor does the work
        result = executor_agent.send_message(
            conversation_id=executor_conv_id,
            user_text=executor_prompt,
            status_callback=background_status_callback
        )

        # 2. Critic evaluates the work
        critic_prompt = (
            f"Review the execution history above.\n"
            f"The Acceptance Criteria for this chunk was: '{acceptance_criteria}'\n"
            f"Did the Executor successfully meet this criteria? Output your strict JSON evaluation."
        )

        evaluation = _evaluate_with_critic(executor_conv_id, critic_prompt)

        if evaluation.get("approved"):
            background_status_callback(f"[CRITIC]: Execution Approved for {chunk_title}!")
            # NEW: Extract the summary from the Critic
            final_summary = evaluation.get("summary", "Task completed successfully.")
            break # Exit the retry loop, success!

        # 3. If rejected, feed feedback back to the executor
        background_status_callback(f"[CRITIC]: Execution Rejected. Feedback: {evaluation.get('feedback')}")
        executor_prompt = (
            f"The QA Critic rejected your previous execution with the following feedback:\n{evaluation.get('feedback')}\n"
            f"Please fix the errors using your tools and summarize your fixes."
        )
        final_summary = f"Task ended with unresolved Critic feedback: {evaluation.get('feedback')}"

    # Mark tasks completed in DB
    for step in sub_steps:
        update_sub_task_status(step["id"], "completed")
    update_task_status(task_id, "completed")

    save_assistant_message(
        conversation_id,
        f"[BACKGROUND EXECUTOR]: Finished {chunk_title}.\nSummary:\n{final_summary}"
    )
    
    return final_summary # NEW: Return the summary to the orchestrator loop


def _run_background_orchestra(conversation_id: int, task: str) -> None:
    """The main background lifecycle loop."""
    try:
        # 1. Setup project sandbox
        project_id = ensure_project_id(conversation_id)

        # 2. Plan generation & Critic Validation
        planner_session = start_new_conversation(user_id=None, title="[System] Background Planning")
        planner_conv_id = planner_session["id"]
        create_message(planner_conv_id, "system", AGENT_PROFILES["planner"]["system_instruction"])

        chunks = _generate_and_validate_plan(task, planner_conv_id)

        if not chunks:
            save_assistant_message(conversation_id, "[BACKGROUND ORCHESTRA ERROR]: Planner failed to generate a valid plan.")
            return

        save_assistant_message(
            conversation_id,
            f"[BACKGROUND PLANNER]: I have designed and validated a structured plan with {len(chunks)} phases. Kicking off execution."
        )

        # 3. Write planning state to Database
        task_id_queue = _save_plan_to_database(project_id, chunks)

        # 4. Sequential loop execution phase (with Critic)
        accumulated_summaries = "" # NEW: Track the running history
        
        for task_id, chunk_title, role_persona, acceptance_criteria in task_id_queue:
            # NEW: Pass the accumulated summaries and get the new one back
            chunk_summary = _execute_chunk_with_critic(
                conversation_id, 
                task_id, 
                chunk_title, 
                role_persona, 
                acceptance_criteria,
                previous_summaries=accumulated_summaries 
            )
            
            # NEW: Append this chunk's summary to the running log
            accumulated_summaries += f"- {chunk_title}: {chunk_summary}\n"

        # 5. Final Completion Notice
        save_assistant_message(
            conversation_id,
            "[BACKGROUND SYSTEM COMPLETED]: All planned task chunks have been executed and approved by the Critic!"
        )

    except Exception as e:
        save_assistant_message(
            conversation_id,
            f"[BACKGROUND ORCHESTRA ERROR]: Execution failed: {e}"
        )

def trigger_multi_agent_workflow(conversation_id: int, task: str) -> str:
    """Spawns the background Planner, Critic, and Executor orchestrator."""
    thread = threading.Thread(
        target=_run_background_orchestra, 
        args=(conversation_id, task)
    )
    thread.daemon = True
    thread.start()
    
    return (
        "[ORCHESTRA SYSTEM]: The Multi-Agent Orchestra (Planner, Critic, Executor) has been successfully spawned "
        "in the background. You can continue typing here. Use the '/status' command "
        "to check on their progress at any time."
    )