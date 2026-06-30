from typing import List, Dict, Any, Callable
from google import genai
from google.genai import types
from ..base_provider import BaseLLMProvider
from ..schemas import LLMResponse, ToolCall
from utils.native_types_helpers import _to_native_types
from llm.context_formatter import format_context
from llm.generate_with_retry import generate_with_retry
from engine.thinking_configure import get_thinking_config
from utils.config_manager import get_thinking_level

class GeminiProvider(BaseLLMProvider):
    def __init__(self, api_key: str, model_name: str):
        super().__init__(api_key, model_name)
        self.client = genai.Client(api_key=self.api_key)
        
    def format_messages(self, standard_messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Maps the universal standard messages to Gemini's specific SDK format."""
        gemini_messages = []
        for msg in standard_messages:
            role = msg["role"]
            content = msg.get("content", "")
            if role == "tool":
                # Gemini specific tool response syntax
                gemini_messages.append({
                    "role": "function",
                    "parts": [{"function_response": {"name": msg.get("tool_name"), "response": {"result": content}}}]
                })
            else:
                # Gemini specific user/model syntax
                gemini_role = "model" if role == "assistant" else "user"
                parts = [{"text": content}] if content else []
                
                if msg.get("tool_calls"):
                    for tc in msg["tool_calls"]:
                        fc_dict = {"name": tc.name, "args": tc.args}
                        metadata = tc.metadata if getattr(tc, "metadata", None) else {}
                        
                        
                        if "id" in metadata:
                            fc_dict["id"] = metadata["id"]
                            
                        # Build the Part structure
                        part_dict = {"function_call": fc_dict}
                        
                        # thought_signature belongs on the Part level as a sibling
                        if "thought_signature" in metadata:
                            part_dict["thought_signature"] = metadata["thought_signature"]
                            
                        parts.append(part_dict)
                        
                if parts:
                    gemini_messages.append({"role": gemini_role, "parts": parts})
        return gemini_messages

    def generate_content(self, messages: List[Dict[str, Any]], tools: List[Callable], system_instruction: str = "", **kwargs) -> LLMResponse:
        # 1. Extract app-wide logic using your new file!
        db_sys_inst, standard_msgs = format_context(messages)
        final_system_instruction = f"{system_instruction}\n{db_sys_inst}".strip()
        # 2. Translate to Gemini format
        gemini_messages = self.format_messages(standard_msgs)
        # 3. Build Gemini configuration
        config_params = {"automatic_function_calling":
        types.AutomaticFunctionCallingConfig(disable=True)}
        if final_system_instruction:
            config_params["system_instruction"] = final_system_instruction
        if tools:
            config_params["tools"] = tools
            
        # Dynamically retrieve and apply the active thinking level
        
        active_thinking_level = get_thinking_level()
        thinking_cfg = get_thinking_config(self.model_name, level=active_thinking_level)
        
        if thinking_cfg:
            config_params["thinking_config"] = thinking_cfg
        config = types.GenerateContentConfig(**config_params)

        def make_gemini_request():
            return self.client.models.generate_content(
                model=self.model_name, contents=gemini_messages, config=config
            )
        # Define the Gemini-specific 429 check
        def is_gemini_quota_error(e):
            exc_str = str(e)
            exc_class = type(e).__name__
            return (
                "ResourceExhausted" in exc_class or
                "429" in exc_str or
                "quota" in exc_str.lower()
            )
        # 4. Use the generic retry template
        response = generate_with_retry(
            request_fn=make_gemini_request,
            is_quota_error_fn=is_gemini_quota_error, status_callback=kwargs.get("status_callback"), max_attempts=3
        )
        return self._parse_response(response)

    def _parse_response(self, response: Any) -> LLMResponse:
        """Parses native Gemini protobuf responses into standardized LLMResponse schema."""
        prompt_tokens = response.usage_metadata.prompt_token_count if getattr(response, "usage_metadata", None) else 0
        completion_tokens = response.usage_metadata.candidates_token_count if getattr(response, "usage_metadata", None) else 0
        
        candidate = response.candidates[0]
        text_response = ""
        tool_calls = []
        
        if getattr(candidate, "content", None) and getattr(candidate.content, "parts", None):
            for part in candidate.content.parts:
                if getattr(part, "text", None):
                    text_response += part.text
                if getattr(part, "function_call", None):
                    fc = part.function_call
                    metadata = {}
                    
                    if hasattr(fc, "id") and fc.id:
                        metadata["id"] = fc.id
                        
                    # Fix: Extract from the Part object (part) instead of the FunctionCall (fc)
                    if hasattr(part, "thought_signature") and part.thought_signature:
                        metadata["thought_signature"] = part.thought_signature
                        
                    tool_calls.append(ToolCall(
                        name=fc.name, 
                        args=_to_native_types(fc.args),
                        id=getattr(fc, "id", None), 
                        metadata=metadata
                    ))
                    
        return LLMResponse(
            text=text_response.strip(),
            tool_calls=tool_calls,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens
        )