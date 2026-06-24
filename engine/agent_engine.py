import os
import json
import google.generativeai as genai
from tools.registry import get_all_tools, execute_tool
from managers.conversation_manager import (
    compile_llm_context, 
    save_user_message, 
    save_assistant_message,
    log_api_usage,
    log_tool_run
)
from managers.summary_manager import trigger_background_summary

class AgentEngine:
    def __init__(self, api_key: str | None = None, autonomous: bool = False):
        """
        Initializes the Agent Engine.
        
        api_key: The Google Gemini API key. Defaults to GEMINI_API_KEY env variable.
        autonomous: If True, executes tools immediately. If False, requires approval callback.
        """
        resolved_key = api_key or os.environ.get("GEMINI_API_KEY")
        if not resolved_key:
            raise ValueError("API Key missing. Must pass api_key or set GEMINI_API_KEY environment variable.")
        
        genai.configure(api_key=resolved_key)
        self.api_key = resolved_key
        self.autonomous = autonomous
        self.model_name = "gemini-3.1-flash-lite"

    def _format_context_for_gemini(self, db_messages: list[dict]) -> tuple[str | None, list[dict]]:
        """
        Translates database message formats into Gemini SDK formats and prepends
        strict system directives to force batching and protect API quotas.
        """
        # --- Strict operational instructions for the AI planner ---
        base_instructions = (
            "You are a highly efficient local development assistant.\n"
            "To prevent API rate limits (HTTP 429 Errors) and optimize execution speed:\n"
            "1. You MUST batch multiple file reads or writes into a single tool call. "
            "Never call 'write_files' or 'read_files' sequentially in separate turns for individual files "
            "if you can process them together in one single turn.\n"
            "2. Ensure the JSON arrays you construct for 'files_json' or 'paths_json' contain "
            "all target files at once."
        )
        
        system_instruction = base_instructions
        gemini_messages = []
        
        for msg in db_messages:
            role = msg["role"]
            content = msg["content"]
            if role == "system":
                # Append the running system summary to our base instructions
                system_instruction += f"\n\n[Previous Conversation Summary]\n{content}"
            else:
                gemini_role = "model" if role == "assistant" else "user"
                gemini_messages.append({
                    "role": gemini_role,
                    "parts": [{"text": content}]
                })
                
        return system_instruction, gemini_messages

    def send_message(self, conversation_id: int, user_text: str, approval_callback=None) -> str:
        """
        Executes the ReAct loop. Saves the turn, compiles local context,
        manages permissions, executes tools, logs token consumption,
        and runs asynchronous background summarization.
        """
        # Save user's message to the database first
        save_user_message(conversation_id, user_text)
        
        # Compile our optimized sliding-window context
        db_messages = compile_llm_context(conversation_id)
        system_instruction, gemini_messages = self._format_context_for_gemini(db_messages)
        
        model = genai.GenerativeModel(
            model_name=self.model_name,
            tools=get_all_tools(),
            system_instruction=system_instruction
        )
        
        # Loop Breaker limits
        turn_count = 0
        MAX_TURNS = 5
        
        while True:
            # Loop Breaker: stops execution if the AI enters an infinite run loop
            if turn_count >= MAX_TURNS:
                error_msg = f"Error: Maximum tool execution limit ({MAX_TURNS} turns) reached to prevent infinite loops."
                save_assistant_message(conversation_id, error_msg)
                return error_msg
            
            try:
                response = model.generate_content(gemini_messages)
            except Exception as e:
                raise RuntimeError(f"Gemini API execution failed: {e}") from e
            
            # Log token usage metadata
            prompt_tokens = response.usage_metadata.prompt_token_count if response.usage_metadata else 0
            completion_tokens = response.usage_metadata.candidates_token_count if response.usage_metadata else 0
            log_api_usage(conversation_id, self.model_name, prompt_tokens, completion_tokens)
            
            # Check for tool call
            candidate = response.candidates[0]
            function_calls = candidate.content.parts[0].function_call if candidate.content.parts else None
            
            if function_calls:
                # Increment turn count as a tool run is happening
                turn_count += 1
                tool_name = function_calls.name
                tool_args = dict(function_calls.args)
                
                # Handle Permissions
                if not self.autonomous:
                    if approval_callback is None:
                        raise ValueError("Engine is in supervised mode, but no approval_callback was provided.")
                    
                    approved = approval_callback(tool_name, tool_args)
                    if not approved:
                        tool_output = f"Error: Permission Denied. User refused execution of '{tool_name}'."
                        log_tool_run(
                            conversation_id, 
                            tool_name, 
                            json.dumps(tool_args), 
                            "error", 
                            error_message="User denied permission."
                        )
                    else:
                        tool_output = execute_tool(tool_name, tool_args)
                        
                        # Safely detect errors across both dictionary and string outputs
                        if isinstance(tool_output, dict):
                            has_error = any("Error:" in str(v) for v in tool_output.values())
                        else:
                            has_error = "Error:" in str(tool_output)
                        status = "error" if has_error else "success"
                        
                        log_tool_run(
                            conversation_id, 
                            tool_name, 
                            json.dumps(tool_args), 
                            status, 
                            output=tool_output
                        )
                else:
                    tool_output = execute_tool(tool_name, tool_args)
                    
                    # Safely detect errors across both dictionary and string outputs
                    if isinstance(tool_output, dict):
                        has_error = any("Error:" in str(v) for v in tool_output.values())
                    else:
                        has_error = "Error:" in str(tool_output)
                    status = "error" if has_error else "success"
                    
                    log_tool_run(
                        conversation_id, 
                        tool_name, 
                        json.dumps(tool_args), 
                        status, 
                        output=tool_output
                    )
                
                # Append tool calls using robust plain dictionary formats (prevents Part SDK crashes)
                gemini_messages.append(candidate.content)
                gemini_messages.append({
                    "role": "user",
                    "parts": [{
                            "function_response": {
                                "name": tool_name,
                                "response": {"result": tool_output}
                            }
                }]
                    })
                
                continue
            else:
                # Case: Final text response received!
                final_text = response.text if response.text else ""
                
                # Save the final text exchange to the database
                save_assistant_message(conversation_id, final_text)
                
                # Trigger our background summarization thread cleanly
                try:
                    import threading
                    summary_thread = threading.Thread(
                        target=trigger_background_summary,
                        args=(self.api_key, self.model_name, conversation_id)
                    )
                    summary_thread.daemon = True # Daemon threads shut down automatically on main exit
                    summary_thread.start()
                except Exception:
                    # Fail silently in the background to prevent user interruption
                    pass
                
                return final_text