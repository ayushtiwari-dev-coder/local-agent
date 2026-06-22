import threading
import google.generativeai as genai
from database.helper import execute_read
from queries.summary_queries import create_or_update_summary, get_summary_by_conversation

def trigger_background_summary(api_key: str, model_name: str, conversation_id: int) -> None:
    """
    Spawns a local background thread to analyze and compress conversation history 
    without causing any terminal UI latency.
    """
    thread = threading.Thread(
        target=_run_summary_workflow,
        args=(api_key, model_name, conversation_id)
    )
    thread.daemon = True  # Allows the application to exit safely if thread is running
    thread.start()


def _run_summary_workflow(api_key: str, model_name: str, conversation_id: int) -> None:
    """
    The background worker function. Checks if there are more than 10 un-summarized messages,
    queries Gemini, and updates the summaries table.
    """
    # 1. Fetch old summary and determine the last message ID we summarized
    summary_record = get_summary_by_conversation(conversation_id)
    last_msg_id = summary_record["last_summarized_message_id"] if summary_record else 0
    
    # 2. Query the messages table for all un-summarized messages
    query = """
    SELECT id, role, content 
    FROM messages 
    WHERE conversation_id = ? AND id > ? 
    ORDER BY id ASC;
    """
    try:
        raw_messages = execute_read(query, (conversation_id, last_msg_id))
    except Exception:
        return  # Safely ignore DB read errors in the background
        
    # We only trigger a summary if we have accumulated more than 10 new un-summarized messages
    if len(raw_messages) < 30:
        return
        
    # 3. Compile the text block to feed to Gemini
    old_summary = summary_record["summary_text"] if summary_record else "No previous summary."
    new_text_to_summarize = ""
    for msg in raw_messages:
        new_text_to_summarize += f"{msg['role']}: {msg['content']}\n"
        
    prompt = f"""
    You are a background text compressor. 
    Incorporate the following new messages into the old running summary of this conversation.
    Keep the summary concise, factual, and strictly under 300 words. Preserve key facts and user preferences.
    
    [Old Summary]
    {old_summary}
    
    [New Messages]
    {new_text_to_summarize}
    """
    
    try:
        # Configure and call Gemini strictly inside the background thread
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(model_name=model_name)
        response = model.generate_content(prompt)
        
        if response.text:
            latest_msg_id = raw_messages[-1]["id"]
            # Save the new compressed summary to the database
            create_or_update_summary(conversation_id, response.text.strip(), latest_msg_id)
            
    except Exception:
        # Silent pass on API failures so we never disrupt your active terminal session
        pass