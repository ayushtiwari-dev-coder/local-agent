import os
import json
import google.generativeai as genai
from tools.registry import get_all_tools, execute_tool
from engine.loop_protector import check_for_infinite_loop  # Import our helper
from managers.conversation_manager import (
    compile_llm_context, save_user_message, save_assistant_message,
    log_api_usage, log_tool_run
)
from managers.summary_manager import trigger_background_summary

class AgentEngine:
    def __init__(self, api_key: str | None = None, autonomous: bool = False):
        resolved_key = api_key or os.environ.get("GEMINI_API_KEY")
        if not resolved_key:
            raise ValueError("API Key missing. Must pass api_key or set GEMINI_API_KEY environment variable.")
        
        genai.configure(api_key=resolved_key)
        self.api_key = resolved_key
        self.autonomous = autonomous
        self.model_name = "gemini-2.5-flash"

    def _format_context_for_gemini(self, db_messages: list[dict]) -> tuple[str | None, list[dict]]:
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
                system_instruction += f"\n\n[Previous Conversation Summary]\n{content}"
            else:
                gemini_role = "model" if role == "assistant" else "user"
                gemini_messages.append({
                    "role": gemini_role,
                    "parts": [{"text": content}]
                })
        return system_instruction, gemini_messages

    def _trigger_summary_safely(self, conversation_id: int) -> None:
        """
        Safely invokes the background summary thread without locking execution.
        """
        try:
            # Note: summary_manager's trigger_background_summary already spawns its own thread.
            # We call it directly here to avoid redundant double-threading.
            trigger_background_summary(self.api_key, self.model_name, conversation_id)
        except Exception:
            pass

    def send_message(self, conversation_id: int, user_text: str, approval_callback=None) -> str:
        """
        Executes the ReAct loop. Saves the turn, compiles local context,
        manages permissions, and handles execution tracking.
        """
        save_user_message(conversation_id, user_text)
        db_messages = compile_llm_context(conversation_id)
        system_instruction, gemini_messages = self._format_context_for_gemini(db_messages)
        
        model = genai.GenerativeModel(
            model_name=self.model_name,
            tools=get_all_tools(),
            system_instruction=system_instruction
        )
        
        # In-memory execution history for loop protection
        tool_call_history = []
        turn_count = 0
        MAX_TURNS = 15
        
        while True:
            if turn_count >= MAX_TURNS:
                error_msg = f"Error: Maximum tool execution limit ({MAX_TURNS} turns) reached."
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
                turn_count += 1
                tool_name = function_calls.name
                tool_args = dict(function_calls.args)
                
                # Use our external helper function to check for infinite loops
                is_looping, loop_error, serialized_args = check_for_infinite_loop(
                    tool_call_history, tool_name, tool_args
                )
                
                if is_looping:
                    save_assistant_message(conversation_id, loop_error)
                    return loop_error
                
                # Handle Permissions
                if not self.autonomous:
                    if approval_callback is None:
                        raise ValueError("Engine is in supervised mode, but no approval_callback was provided.")
                    
                    approved = approval_callback(tool_name, tool_args)
                    if not approved:
                        tool_output = f"Error: Permission Denied. User refused execution of '{tool_name}'."
                        log_tool_run(
                            conversation_id, tool_name,
                            json.dumps(tool_args), "error", error_message="User denied permission."
                        )
                        status = "error"
                    else:
                        tool_output = execute_tool(tool_name, tool_args)
                        status = "error" if "Error:" in str(tool_output) else "success"
                        log_tool_run(conversation_id, tool_name, json.dumps(tool_args), status, output=tool_output)
                else:
                    tool_output = execute_tool(tool_name, tool_args)
                    status = "error" if "Error:" in str(tool_output) else "success"
                    log_tool_run(conversation_id, tool_name, json.dumps(tool_args), status, output=tool_output)
                
                # Record this execution in our local memory list for loop tracking
                tool_call_history.append({
                    'name': tool_name,
                    'args_json': serialized_args,
                    'status': status
                })
                
                # Append tool calls to message history for ReAct flow
                gemini_messages.append(candidate.content)
                gemini_messages.append({
                    "role": "user",
                    "parts": [{"function_response": {
                        "name": tool_name,
                        "response": {"result": tool_output}
                    }}]
                })
                continue
                
            else:
                # Case: Final text response received!
                final_text = response.text if response.text else ""
                save_assistant_message(conversation_id, final_text)
                
                # Trigger background summarizer via our clean helper
                self._trigger_summary_safely(conversation_id)
                
                return final_text