# FILE: engine/test_engine.py

import os
import json
from tools.registry import get_all_tools
from engine.loop_protector import check_for_infinite_loop, _extract_paths
from engine.handle_permissions import determine_and_execute_tool
from managers.conversation_manager import (
    compile_llm_context, save_user_message, save_assistant_message, log_api_usage
)
from managers.summary_manager import trigger_background_summary
from llm.provider_factory import LLMFactory

class AgentEngine:
    def __init__(self, provider_name: str = "gemini", model_name: str = "gemini-3.1-flash-lite", api_key: str | None = None, autonomous: bool = False):
        resolved_key = api_key or os.environ.get("GEMINI_API_KEY")
        if not resolved_key:
            raise ValueError(f"API Key missing. Must pass api_key or set API key environment variable for {provider_name}.")
        
        # Instantiate the provider through our new factory!
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

        while True:
            if turn_count >= MAX_TURNS:
                error_msg = f"Error: Maximum tool execution limit ({MAX_TURNS} turns) reached."
                save_assistant_message(conversation_id, error_msg)
                return error_msg

            try:
                # 1. Generate content (Provider handles all formatting and retries natively)
                response = self.provider.generate_content(
                    messages=db_messages,
                    tools=get_all_tools(),
                    status_callback=status_callback
                )
            except Exception as e:
                raise RuntimeError(f"LLM API execution failed: {e}") from e

            # 2. Log token usage
            log_api_usage(conversation_id, self.provider.model_name, response.prompt_tokens, response.completion_tokens)

            # 3. Check for tool calls
            if response.tool_calls:
                turn_count += 1
                
                # We currently process one tool call at a time per turn
                tool_call = response.tool_calls[0]
                tool_name = tool_call.name
                tool_args = tool_call.args
                serialized_args = json.dumps(tool_args, sort_keys=True)

                # Check for infinite loops
                is_looping, loop_error, _ = check_for_infinite_loop(tool_call_history, tool_name, tool_args)
                if is_looping:
                    save_assistant_message(conversation_id, loop_error)
                    return loop_error

                # Execute tool
                tool_output, status = determine_and_execute_tool(
                    tool_name, tool_args, conversation_id, self.autonomous, approval_callback
                )

                # Record execution log in local memory
                tool_call_history.append({
                    'name': tool_name,
                    'args_json': serialized_args,
                    'status': status,
                    'paths': _extract_paths(tool_name, tool_args) or set()
                })

                # Append clean standard dicts for the next LLM iteration
                db_messages.append({"role": "assistant", "tool_calls": [tool_call]})
                db_messages.append({"role": "tool", "tool_name": tool_name, "content": tool_output})
                continue
            
            else:
                # 4. Final text response received
                final_text = response.text if response.text else ""
                save_assistant_message(conversation_id, final_text)
                self._trigger_summary_safely(conversation_id)
                return final_text