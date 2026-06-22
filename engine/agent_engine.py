import os
import google.generativeai as genai
from tools.registry import get_all_tools, execute_tool
from managers.conversation_manager import (
    compile_llm_context,
    save_assistant_message,
    log_api_usage,
    log_tool_run,
    save_user_message
)


class AgentEngine:
    def __init__(self, api_key: str | None = None, autonomous: bool = False):
        """
        Initializes the Agent Engine.
        api_key: The Google Gemini API key. If None, looks for GEMINI_API_KEY env variable.
        autonomous: If True, executes tools immediately. If False, requires approval callback.
        """
        # Resolve API key from arguments or environment
        resolved_key = api_key or os.environ.get("GEMINI_API_KEY")
        if not resolved_key:
            raise ValueError("API Key missing. Must pass api_key or set GEMINI_API_KEY environment variable.")
            
        genai.configure(api_key=resolved_key)
        self.autonomous = autonomous
        # We use the standard fast model. For heavy coding, 'gemini-1.5-pro' can be swapped in.
        self.model_name = "gemini-2.5-flash"


    def _format_context_for_gemini(self, db_messages: list[dict]) -> tuple[str | None, list[dict]]:
        """
        Translates our clean database message formats into the official Gemini SDK format.
        Extracts any system summary cards to pass as a distinct system instruction.
        """
        system_instruction = None
        gemini_messages = []
        
        for msg in db_messages:
            role = msg["role"]
            content = msg["content"]
            
            if role == "system":
                # System message (usually our running summary) is separated
                system_instruction = content
            else:
                # Map 'assistant' role to Gemini's required 'model' keyword
                gemini_role = "model" if role == "assistant" else "user"
                gemini_messages.append({
                    "role": gemini_role,
                    "parts": [{"text": content}]
                })
                
        return system_instruction, gemini_messages


    def send_message(self, conversation_id: int, user_text: str, approval_callback=None) -> str:
            """
            Executes the ReAct tool-calling loop.
            Saves the turn, compiles local context, manages permissions, executes tools,
            logs token consumption, and returns the final textual assistant response.
            """
            # 1. Save the user's active input message to the database first!
            save_user_message(conversation_id, user_text)
            
            # 2. Now compile our optimized sliding-window context from the database
            db_messages = compile_llm_context(conversation_id)
            
            # 3. Extract system summary instruction and translate message formats
            system_instruction, gemini_messages = self._format_context_for_gemini(db_messages)
            
            # Instantiate the model with our dynamic tools registered
            model = genai.GenerativeModel(
                model_name=self.model_name,
                tools=get_all_tools(),
                system_instruction=system_instruction
            )
            
            # Start the execution loop.
            while True:
                try:
                    # Call Gemini with current history and registered tools
                    response = model.generate_content(gemini_messages)
                except Exception as e:
                    # Safely trap and propagate network or API outages in written format
                    raise RuntimeError(f"Gemini API execution failed: {e}") from e
                    
                # Extract token usage metadata from the response if available
                prompt_tokens = response.usage_metadata.prompt_token_count if response.usage_metadata else 0
                completion_tokens = response.usage_metadata.candidates_token_count if response.usage_metadata else 0
                
                # Log the token consumption of this specific turn to our usage table
                log_api_usage(conversation_id, self.model_name, prompt_tokens, completion_tokens)
                
                # Check if Gemini requested a function (tool) call
                candidate = response.candidates[0]
                function_calls = candidate.content.parts[0].function_call if candidate.content.parts else None
                
                if function_calls:
                    tool_name = function_calls.name
                    tool_args = dict(function_calls.args)
                    
                    # Handle Tool Execution Permissions
                    if not self.autonomous:
                        if approval_callback is None:
                            raise ValueError(
                                f"Engine is in supervised mode, but no approval_callback was provided "
                                f"to confirm tool call '{tool_name}'."
                            )
                        approved = approval_callback(tool_name, tool_args)
                        if not approved:
                            tool_output = f"Error: Permission Denied. User refused execution of '{tool_name}'."
                            log_tool_run(conversation_id, tool_name, str(tool_args), "error", error_message="User denied permission.")
                        else:
                            tool_output = execute_tool(tool_name, tool_args)
                            status = "error" if "Error:" in tool_output else "success"
                            log_tool_run(conversation_id, tool_name, str(tool_args), status, output=tool_output)
                    else:
                        tool_output = execute_tool(tool_name, tool_args)
                        status = "error" if "Error:" in tool_output else "success"
                        log_tool_run(conversation_id, tool_name, str(tool_args), status, output=tool_output)
                    
                    # Append the tool output to our conversational history
                    # Append the tool output to our conversational history
                    gemini_messages.append(candidate.content)
                    gemini_messages.append({
                        "role": "user",
                        "parts": [
                            {
                                "function_response": {
                                    "name": tool_name,
                                    "response": {"result": tool_output}
                                }
                            }
                        ]
                    })
                    # Loop back to let Gemini read the tool output and think again
                    continue
                    
                else:
                    # Case: No tool call requested. We have received our final text response!
                    final_text = response.text if response.text else ""
                    
                    # Save the final text exchange to the database
                    save_assistant_message(conversation_id, final_text)
                    
                    return final_text