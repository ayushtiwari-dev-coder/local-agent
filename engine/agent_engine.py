# FILE: engine/test_engine.py

import os
import json
from tools.registry import get_all_tools
from llm.loop_protector import check_for_infinite_loop, _extract_paths
from engine.handle_permissions import determine_and_execute_tool
from managers.conversation_manager import (
    compile_llm_context, save_user_message, save_assistant_message, log_api_usage
)
from managers.summary_manager import trigger_background_summary
from llm.provider_factory import LLMFactory

class AgentEngine:
    def __init__(self, provider_name: str = "gemini", model_name: str = "gemini-3.1-flash-lite", api_key: str | None = None, autonomous: bool = False):
        # Dynamically map the correct environment variable key name
        env_var_map = {
            "gemini": "GEMINI_API_KEY",
            "groq": "GROQ_API_KEY"
        }
        env_var_name = env_var_map.get(provider_name.lower(), "GEMINI_API_KEY")
        resolved_key = api_key or os.environ.get(env_var_name)
        
        if not resolved_key:
            raise ValueError(f"API Key missing. Must pass api_key or set environment variable {env_var_name} for {provider_name}.")
            
        # Instantiate the provider through the factory
        self.provider = LLMFactory.get_provider(provider_name, resolved_key, model_name)
        self.autonomous = autonomous

    def _trigger_summary_safely(self, conversation_id: int) -> None:
        try:
            trigger_background_summary(self.provider.api_key, self.provider.model_name, conversation_id)
        except Exception:
            pass

    def send_message(self, conversation_id: int, user_text: str, approval_callback=None, status_callback=None) -> str:
        """Executes the ReAct loop using the abstract LLM provider."""
        
        save_user_message(conversation_id, user_text)
        
        # compile_llm_context returns standard dicts: [{"role": "user", "content": "hi"}]
        db_messages = compile_llm_context(conversation_id)

        tool_call_history = []
        turn_count = 0
        MAX_TURNS = 15

        # In engine/agent_engine.py (Inside send_message, inside the while True loop)
        while True:
            if turn_count >= MAX_TURNS:
                error_msg = f"Error: Maximum tool execution limit ({MAX_TURNS} turns) reached."
                save_assistant_message(conversation_id, error_msg)
                return error_msg
                
            turn_count += 1
            
            # Emit a status update indicating a new API turn is beginning
            if status_callback:
                status_callback(f"Generating thoughts... [Turn #{turn_count}]")
                
            try:
                response = self.provider.generate_content(
                    messages=db_messages,
                    tools=get_all_tools(),
                    status_callback=status_callback
                )
            except Exception as e:
                raise RuntimeError(f"LLM API execution failed: {e}") from e
                
            log_api_usage(conversation_id, self.provider.model_name, response.prompt_tokens, response.completion_tokens)
            
            if response.tool_calls:
                db_messages.append({"role": "assistant", "tool_calls": response.tool_calls})
                
                for tool_call in response.tool_calls:
                    tool_name = tool_call.name
                    tool_args = tool_call.args
                    serialized_args = json.dumps(tool_args, sort_keys=True)
                    
                    is_looping, loop_error, _ = check_for_infinite_loop(
                        tool_call_history, tool_name, tool_args
                    )
                    
                    if is_looping:
                        save_assistant_message(conversation_id, loop_error)
                        return loop_error
                        
                    # Emit tool run status before execution
                    if status_callback:
                        status_callback(f"Executing tool '{tool_name}' with arguments:\n{tool_args}")
                        
                    tool_output, status = determine_and_execute_tool(
                        tool_name, tool_args, conversation_id, self.autonomous, approval_callback
                    )
                    
                    # Emit tool completion status
                    if status_callback:
                        status_callback(f"Tool '{tool_name}' returned status: '{status}'")
                        
                    tool_call_history.append({
                        'name': tool_name,
                        'args_json': serialized_args,
                        'status': status,
                        'paths': _extract_paths(tool_name, tool_args) or set()
                    })
                    
                    if status == "success":
                        formatted_output = f"SYSTEM: Action SUCCESS. DO NOT repeat this action. Review output and move to next step.\n\nOUTPUT:\n{tool_output}"
                    else:
                        formatted_output = f"SYSTEM: Action FAILED. Analyze the error below and change your approach.\n\nERROR:\n{tool_output}"
                        
                    db_messages.append({"role": "tool", "tool_name": tool_name, "content": formatted_output})
                    
                continue
            
            else:
                # 4. Final text response received
                final_text = response.text if response.text else ""
                save_assistant_message(conversation_id, final_text)
                self._trigger_summary_safely(conversation_id)
                return final_text