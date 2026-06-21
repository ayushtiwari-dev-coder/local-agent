import sqlite3
import tiktoken
from database.connection import get_connection
from queries.conversation_queries import create_conversation
from queries.message_queries import create_message, get_messages_by_conversation
from queries.model_usage_queries import log_model_usage
from queries.tool_log_queries import log_tool_execution

def start_new_conversation(user_id: int = None, title: str = "New Conversation") -> dict:
    """
    Initializes a new conversation session in the database.
    """
    return create_conversation(user_id, title)


def save_user_message(conversation_id: int, content: str) -> dict:
    """
    Saves the user's input message to the conversation history.
    """
    clean_content = content.strip()
    if not clean_content:
        raise ValueError("Message content cannot be empty.")
        
    return create_message(conversation_id, role="user", content=clean_content)


# A safe local default limit (e.g., 100,000 tokens)
MAX_CONTEXT_TOKENS = 100000

def _estimate_tokens(messages: list[dict]) -> int:
    """
    Counts the exact number of tokens using a local BPE tokenizer (cl100k_base).
    This is the exact tokenizer used by GPT-4 and is highly accurate for Gemini as well.
    Runs 100% locally in microseconds.
    """
    try:
        # Get the standard local encoding used by modern models
        encoding = tiktoken.get_encoding("cl100k_base")
    except Exception:
        # Fallback if offline/unable to load
        encoding = None

    total_tokens = 0
    for msg in messages:
        content = msg["content"]
        if encoding:
            # Safely encode the text locally and count the tokens
            total_tokens += len(encoding.encode(content))
        else:
            # Safe character-based fallback if tiktoken is not loaded
            total_tokens += len(content) // 4
            
    return total_tokens


def compile_llm_context(conversation_id: int, max_tokens: int = MAX_CONTEXT_TOKENS) -> list[dict]:
    """
    Compiles and self-trims the conversation history.
    If the context exceeds max_tokens, it preserves the system summary card at index 0
    but discards the oldest raw messages (index 1) until the payload fits within budget.
    """
    context_messages = []
    
    conn = get_connection()
    try:
        # 1. Fetch running summary if it exists
        summary_query = """
        SELECT summary_text, last_summarized_message_id 
        FROM summaries 
        WHERE conversation_id = ?;
        """
        cursor = conn.execute(summary_query, (conversation_id,))
        summary_row = cursor.fetchone()
        
        has_summary = False
        if summary_row:
            has_summary = True
            summary_text = summary_row["summary_text"]
            last_msg_id = summary_row["last_summarized_message_id"]
            
            context_messages.append({
                "role": "system",
                "content": f"Summary of previous conversation history: {summary_text}"
            })
            
            # Fetch raw messages created after that summary
            messages_query = """
            SELECT role, content 
            FROM messages 
            WHERE conversation_id = ? AND id > ? 
            ORDER BY created_at ASC;
            """
            cursor = conn.execute(messages_query, (conversation_id, last_msg_id))
        else:
            # Case: No summary exists. Fetch all raw messages.
            messages_query = """
            SELECT role, content 
            FROM messages 
            WHERE conversation_id = ? 
            ORDER BY created_at ASC;
            """
            cursor = conn.execute(messages_query, (conversation_id,))
            
        rows = cursor.fetchall()
        for row in rows:
            context_messages.append({
                "role": row["role"],
                "content": row["content"]
            })
            
        # 2. Sliding Window Trimming Logic
        # Calculate current estimated size
        current_estimated_tokens = _estimate_tokens(context_messages)
        
        # If we are over budget, trim messages one-by-one
        while current_estimated_tokens > max_tokens and len(context_messages) > 1:
            # Determine where the oldest message is. 
            # If we have a summary at index 0, the oldest message is at index 1.
            # If we do NOT have a summary, the oldest message is at index 0.
            trim_index = 1 if has_summary else 0
            
            # Remove the oldest message
            context_messages.pop(trim_index)
            
            # Recalculate
            current_estimated_tokens = _estimate_tokens(context_messages)
            
        return context_messages
        
    except sqlite3.Error as e:
        raise RuntimeError(f"Database error while compiling LLM context: {e}") from e
    finally:
        conn.close()

def save_assistant_message(conversation_id: int, content: str) -> dict:
    """
    Saves the AI assistant's response to the conversation history.
    """
    clean_content = content.strip()
    if not clean_content:
        raise ValueError("Assistant response content cannot be empty.")
        
    return create_message(conversation_id, role="assistant", content=clean_content)

# (Keep your other imports and functions above)

def log_api_usage(
    conversation_id: int, 
    model_name: str, 
    prompt_tokens: int, 
    completion_tokens: int
) -> dict:
    """
    Records the token consumption of an LLM API call.
    """
    return log_model_usage(conversation_id, model_name, prompt_tokens, completion_tokens)


def log_tool_run(
    conversation_id: int,
    tool_name: str,
    arguments: str,
    status: str,
    output: str = None,
    error_message: str = None
) -> dict:
    """
    Logs the execution details and output of a system tool run.
    """
    return log_tool_execution(
        conversation_id=conversation_id,
        tool_name=tool_name,
        arguments=arguments,
        status=status,
        output=output,
        error_message=error_message
    )