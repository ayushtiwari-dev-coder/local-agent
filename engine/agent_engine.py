# FILE: engine/agent_engine.py
import os
from google import genai
from google.genai import types
from tools.registry import get_all_tools
from engine.loop_protector import check_for_infinite_loop,_extract_paths
from engine.handle_permissions import determine_and_execute_tool
from managers.conversation_manager import (
    compile_llm_context, save_user_message, save_assistant_message, log_api_usage
)
from managers.summary_manager import trigger_background_summary
from engine.generate_with_retry import generate_with_retry
from utils.native_types_helpers import  _to_native_types
from engine.thinking_configure import get_thinking_config



class AgentEngine:
    def __init__(self, api_key: str | None = None, autonomous: bool = False):
        resolved_key = api_key or os.environ.get("GEMINI_API_KEY")
        if not resolved_key:
            raise ValueError("API Key missing. Must pass api_key or set GEMINI_API_KEY environment variable.")
        self.client = genai.Client(api_key=resolved_key)
        self.api_key = resolved_key
        self.autonomous = autonomous
        self.model_name = "gemini-3.1-flash-lite"

    def _format_context_for_gemini(self, db_messages: list[dict]) -> tuple[str | None, list[dict]]:
        base_instructions = (
            "You are a highly efficient, focused, and concise local development AI assistant.\n"
            "Your primary goal is to solve the user's request using the available tools while STRICTLY "
            "minimizing API calls, token usage, and execution time.\n\n"
            
            "CRITICAL RULES FOR ALL TOOL USAGE:\n"
            "1. DO NOT REPEAT SUCCESSFUL ACTIONS: Once a tool executes successfully and achieves the desired result, "
            "YOU MUST STOP CALLING TOOLS. Do not call the same tool with the exact same arguments again just to be sure. "
            "Instead, provide a final conversational response to the user to conclude the task.\n"
            
            "2. BATCH OPERATIONS (NO SEQUENTIAL SPAMMING): Whenever possible, batch multiple actions into a single tool call. "
            "If a tool accepts arrays or lists (e.g., reading/writing multiple files, processing multiple database rows), "
            "process them all in ONE single turn. Never do sequentially what you can do simultaneously.\n"
            
            "3. HANDLE ERRORS SMARTLY: If a tool returns an error (e.g., 'File not found', 'Invalid input'), "
            "DO NOT blindly repeat the exact same request. Analyze the error, adjust your parameters, try a different approach, "
            "or immediately stop and ask the user for clarification.\n"
            
            "4. AVOID UNNECESSARY VERIFICATIONS: Trust the tool's success output. If an action succeeds, do not waste tokens "
            "calling another tool to 'verify' the work unless the user explicitly requested it.\n"
            
            "5. BE CONCISE: Do not waste tokens on long-winded conversational filler. Provide direct, factual, and helpful responses."
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
        try:
            trigger_background_summary(self.api_key, self.model_name, conversation_id)
        except Exception:
            pass

    def send_message(self, conversation_id: int, user_text: str, approval_callback=None, status_callback=None) -> str:
        """ Executes the ReAct loop. Saves the turn, compiles local context, manages permissions, and handles execution tracking. """
        save_user_message(conversation_id, user_text)
        db_messages = compile_llm_context(conversation_id)


        system_instruction, gemini_messages = self._format_context_for_gemini(db_messages)
        
        config_params = {
            "tools": get_all_tools(),
            "system_instruction": system_instruction,
        
        "automatic_function_calling":types.AutomaticFunctionCallingConfig(disable=True)
        }
        
        thinking_cfg = get_thinking_config(self.model_name)
        if thinking_cfg:
            config_params["thinking_config"] = thinking_cfg
            
        config = types.GenerateContentConfig(**config_params)
        tool_call_history = []
        turn_count = 0
        MAX_TURNS = 15
        
        while True:
            if turn_count >= MAX_TURNS:
                error_msg = f"Error: Maximum tool execution limit ({MAX_TURNS} turns) reached."
                save_assistant_message(conversation_id, error_msg)
                return error_msg
            
            try:
                response = generate_with_retry(
                    self.client,
                    self.model_name,
                    gemini_messages,
                    config,
                    status_callback=status_callback
                )
            except Exception as e:
                raise RuntimeError(f"Gemini API execution failed: {e}") from e
            
            # Log token usage metadata
            prompt_tokens = response.usage_metadata.prompt_token_count if response.usage_metadata else 0
            completion_tokens = response.usage_metadata.candidates_token_count if response.usage_metadata else 0
            log_api_usage(conversation_id, self.model_name, prompt_tokens, completion_tokens)
            
            # Check for tool call
            candidate = response.candidates[0]
            function_calls = None
            if candidate.content.parts:
                for part in candidate.content.parts:
                    if part.function_call and part.function_call.name:
                        function_calls = part.function_call
                        break
            
            if function_calls:
                turn_count += 1
                tool_name = function_calls.name
                # Recursively unpack complex protobuf parameters into clean native JSON types
                tool_args = _to_native_types(function_calls.args)
                
                # Check for loops
                is_looping, loop_error, serialized_args = check_for_infinite_loop(
                    tool_call_history, tool_name, tool_args
                )
                if is_looping:
                    save_assistant_message(conversation_id, loop_error)
                    return loop_error
                
                # Execute tool using our clean permission handler helper
                tool_output, status = determine_and_execute_tool(
                    tool_name, tool_args, conversation_id, self.autonomous, approval_callback
                )
                
                # Record the execution log inside local memory
                tool_call_history.append({
                    'name': tool_name,
                    'args_json': serialized_args,
                    'status': status,
                    'paths':_extract_paths(tool_name,tool_args) or set()
                })
                
                # Append tool response for the next model iteration
                gemini_messages.append(candidate.content)
                gemini_messages.append({
                    "role": "function",
                    "parts": [{
                        "function_response": {
                            "name": tool_name,
                            "response": {"result": tool_output}
                        }
                    }]
                })
                continue
            else:
                # Case: Final text response received
                final_text = response.text if response.text else ""
                save_assistant_message(conversation_id, final_text)
                self._trigger_summary_safely(conversation_id)
                return final_text