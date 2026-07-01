import os
import json
import inspect
from typing import List, Dict, Any, Callable
from groq import Groq
from ..base_provider import BaseLLMProvider
from ..schemas import LLMResponse, ToolCall
from llm.context_formatter import format_context
from llm.generate_with_retry import generate_with_retry,is_quota_error

def _function_to_schema(func: Callable) -> Dict[str, Any]:
    """Generates an OpenAI/Groq compatible tool schema from a Python callable."""
    name = func.__name__
    doc = func.__doc__ or ""
    description = doc.strip().split("\n")[0] if doc else "No description provided."
    
    sig = inspect.signature(func)
    properties = {}
    required = []
    
    for param_name, param in sig.parameters.items():
        # Map basic Python annotations to JSON-schema types
        param_type = "string"
        if param.annotation == int:
            param_type = "integer"
        elif param.annotation == float:
            param_type = "number"
        elif param.annotation == bool:
            param_type = "boolean"
        elif param.annotation in (list, list[dict], list[str]):
            param_type = "array"
        elif param.annotation == dict:
            param_type = "object"
            
        properties[param_name] = {
            "type": param_type,
            "description": f"Parameter {param_name}"
        }
        
        if param.default == inspect.Parameter.empty:
            required.append(param_name)
            
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required
            }
        }
    }


class GroqProvider(BaseLLMProvider):
    def __init__(self, api_key: str, model_name: str):
        super().__init__(api_key, model_name)
        # Initialize official Groq client
        self.client = Groq(api_key=self.api_key)

    def format_messages(self, standard_messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Maps universal standardized messages to Groq's OpenAI-compatible schema."""
        openai_messages = []
        tool_call_id_map = {}  # Tracks mapping of tool_name -> tool_call_id
        
        for msg in standard_messages:
            role = msg["role"]
            content = msg.get("content", "")
            
            if role == "system":
                openai_messages.append({"role": "system", "content": content})
            elif role == "user":
                openai_messages.append({"role": "user", "content": content})
            elif role == "tool":
                tool_name = msg.get("tool_name")
                # Resolve the matching tool_call_id or fall back to a structured one
                tool_call_id = tool_call_id_map.get(tool_name, f"call_{tool_name}")
                

                if isinstance(content, (dict, list)):
                    content_str = json.dumps(content, ensure_ascii=False)
                else:
                    content_str = str(content) if content is not None else ""
                    
                openai_messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "name": tool_name,
                    "content": content_str
                })
            elif role == "assistant":
                openai_msg = {"role": "assistant"}
                if content:
                    openai_msg["content"] = content
                    
                tool_calls = msg.get("tool_calls")
                if tool_calls:
                    openai_tool_calls = []
                    for tc in tool_calls:
                        # Handle both dataclass and dictionary formats
                        tc_name = getattr(tc, "name", None) or tc.get("name")
                        tc_args = getattr(tc, "args", None) or tc.get("args")
                        tc_id = getattr(tc, "id", None) or tc.get("id") or f"call_{tc_name}"
                        
                        tool_call_id_map[tc_name] = tc_id
                        
                        if isinstance(tc_args, dict):
                            args_str = json.dumps(tc_args)
                        else:
                            args_str = str(tc_args)
                            
                        openai_tool_calls.append({
                            "id": tc_id,
                            "type": "function",
                            "function": {
                                "name": tc_name,
                                "arguments": args_str
                            }
                        })
                    openai_msg["tool_calls"] = openai_tool_calls
                openai_messages.append(openai_msg)
                
        return openai_messages

    def generate_content(self, messages: List[Dict[str, Any]], tools: List[Callable], system_instruction: str = "", **kwargs) -> LLMResponse:
        """Executes content generation for Groq with local tools and retry capabilities."""
        db_sys_inst, standard_msgs = format_context(messages)
        final_system_instruction = f"{system_instruction}\n{db_sys_inst}".strip()
        
        groq_messages = self.format_messages(standard_msgs)
        if final_system_instruction:
            groq_messages.insert(0, {"role": "system", "content": final_system_instruction})
            
        groq_tools = [_function_to_schema(t) for t in tools] if tools else None
        
        def make_groq_request():
            params = {
                "model": self.model_name,
                "messages": groq_messages
            }
            if groq_tools:
                params["tools"] = groq_tools
            return self.client.chat.completions.create(**params)
            
        response = generate_with_retry(
            request_fn=make_groq_request,
            is_quota_error_fn=is_quota_error,
            status_callback=kwargs.get("status_callback"),
            max_attempts=3
        )
        return self._parse_response(response)

    def _parse_response(self, response: Any) -> LLMResponse:
        """Parses native Groq API chat completions into standard LLMResponse."""
        prompt_tokens = response.usage.prompt_tokens if getattr(response, "usage", None) else 0
        completion_tokens = response.usage.completion_tokens if getattr(response, "usage", None) else 0
        
        message = response.choices[0].message
        text_response = message.content or ""
        tool_calls = []
        
        if getattr(message, "tool_calls", None):
            for tc in message.tool_calls:
                try:
                    args = json.loads(tc.function.arguments)
                except Exception:
                    args = {}
                    
                tool_calls.append(ToolCall(
                    name=tc.function.name,
                    args=args,
                    id=tc.id,
                    metadata={}
                ))
                
        return LLMResponse(
            text=text_response.strip(),
            tool_calls=tool_calls,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens
        )