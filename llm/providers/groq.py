# llm/providers/groq.py
import os
import json
import inspect
from typing import List, Dict, Any, Callable, Generator
from collections import defaultdict
from groq import Groq
from ..base_provider import BaseLLMProvider
from ..schemas import LLMResponse, ToolCall, StreamChunk
from llm.context_formatter import format_context
from llm.generate_with_retry import generate_with_retry, is_quota_error
import re
import utils.config_manager as config_manager


def _function_to_schema(func: Callable) -> Dict[str, Any]:
    """Generates an OpenAI/Groq compatible tool schema from a Python callable."""
    name = func.__name__
    doc = func.__doc__ or ""
    description = doc.strip().split("\n")[0] if doc else "No description provided."
    sig = inspect.signature(func)

    properties = {}
    required = []

    for param_name, param in sig.parameters.items():
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
            "description": f"Parameter {param_name}",
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
                "required": required,
            },
        },
    }


class GroqProvider(BaseLLMProvider):
    def __init__(self, api_key: str, model_name: str):
        super().__init__(api_key, model_name)
        self.client = Groq(api_key=self.api_key)

    def format_messages(
        self, standard_messages: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Maps universal standardized messages to Groq's OpenAI-compatible schema."""
        openai_messages = []
        tool_queues = defaultdict(list)

        for msg in standard_messages:
            role = msg["role"]
            content = msg.get("content", "")

            if role == "system":
                openai_messages.append({"role": "system", "content": content})
            elif role == "user":
                openai_messages.append({"role": "user", "content": content})
            elif role == "tool":
                tool_name = msg.get("tool_name")
                if tool_name in tool_queues and tool_queues[tool_name]:
                    tool_call_id = tool_queues[tool_name].pop(0)
                else:
                    tool_call_id = f"call_{tool_name}"

                if isinstance(content, (dict, list)):
                    content_str = json.dumps(content, ensure_ascii=False)
                else:
                    content_str = str(content) if content is not None else ""

                openai_messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call_id,
                        "name": tool_name,
                        "content": content_str,
                    }
                )
            elif role == "assistant":
                openai_msg = {"role": "assistant"}
                if content:
                    openai_msg["content"] = content

                tool_calls = msg.get("tool_calls")
                if tool_calls:
                    openai_tool_calls = []
                    for tc in tool_calls:
                        # SAFELY handle both dicts (from DB) and ToolCall objects
                        if isinstance(tc, dict):
                            tc_name = tc.get("name")
                            tc_args = tc.get("args")
                            tc_id = tc.get("id") or f"call_{tc_name}"
                        else:
                            tc_name = getattr(tc, "name", None)
                            tc_args = getattr(tc, "args", None)
                            tc_id = getattr(tc, "id", None) or f"call_{tc_name}"

                        if tc_name:
                            tool_queues[tc_name].append(tc_id)

                        if isinstance(tc_args, dict):
                            args_str = json.dumps(tc_args)
                        else:
                            args_str = str(tc_args) if tc_args is not None else "{}"

                        openai_tool_calls.append(
                            {
                                "id": tc_id,
                                "type": "function",
                                "function": {
                                    "name": tc_name,
                                    "arguments": args_str,
                                },
                            }
                        )

                    openai_msg["tool_calls"] = openai_tool_calls
                openai_messages.append(openai_msg)

        return openai_messages

    def embed_text(self, texts: List[str]) -> List[List[float]]:
        """Generates embeddings using Groq's fast embedding endpoint."""
        try:
            embedding_model = config_manager.get_embedding_model("groq")
            response = self.client.embeddings.create(
                model=embedding_model, input=texts
            )
            return [emb.embedding for emb in response.data]
        except Exception as e:
            raise RuntimeError(f"Groq Embedding API failed: {str(e)}")

    def _make_groq_request(self, groq_messages, groq_tools):
        """Dedicated method to handle the actual Groq API call and salvage logic."""
        params = {
            "model": self.model_name,
            "messages": groq_messages,
            "stream": True,
        }
        if groq_tools:
            params["tools"] = groq_tools

        try:
            return self.client.chat.completions.create(**params)
        except Exception as e:
            # Intercept Groq's 400 tool_use_failed error
            if hasattr(e, "response") and getattr(e.response, "status_code", 0) == 400:
                try:
                    err_data = e.response.json().get("error", {})
                    if err_data.get("code") == "tool_use_failed":
                        failed_text = err_data.get("failed_generation", "")
                        salvaged_stream = salvage_groq_failed_generation_stream(
                            failed_text
                        )
                        if salvaged_stream:
                            return salvaged_stream
                except Exception:
                    pass
            raise e

    def generate_content(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Callable],
        system_instruction: str = "",
        **kwargs,
    ) -> Generator[StreamChunk, None, None]:
        db_sys_inst, standard_msgs = format_context(messages)
        final_system_instruction = f"{system_instruction}\n{db_sys_inst}".strip()
        groq_messages = self.format_messages(standard_msgs)

        if final_system_instruction:
            groq_messages.insert(
                0, {"role": "system", "content": final_system_instruction}
            )

        groq_tools = [_function_to_schema(t) for t in tools] if tools else None

        # 1. Initiate stream
        stream = generate_with_retry(
            request_fn=lambda: self._make_groq_request(groq_messages, groq_tools),
            is_quota_error_fn=is_quota_error,
            status_callback=kwargs.get("status_callback"),
            max_attempts=3,
        )

        prompt_tokens = 0
        comp_tokens = 0

        # 2. Consume stream
        try:
            for chunk in stream:
                delta = chunk.choices[0].delta if chunk.choices else None
                if not delta:
                    continue

                text_chunk = delta.content or ""
                tool_deltas = []

                if getattr(delta, "tool_calls", None):
                    for tc in delta.tool_calls:
                        tool_deltas.append(
                            {
                                "index": tc.index,
                                "id": tc.id,
                                "name": (
                                    tc.function.name if tc.function else None
                                ),
                                "arguments": (
                                    tc.function.arguments if tc.function else ""
                                ),
                            }
                        )

                # Extract token usage if available
                if getattr(chunk, "x_groq", None) and getattr(
                    chunk.x_groq, "usage", None
                ):
                    prompt_tokens = chunk.x_groq.usage.prompt_tokens
                    comp_tokens = chunk.x_groq.usage.completion_tokens
                elif getattr(chunk, "usage", None):
                    prompt_tokens = chunk.usage.prompt_tokens
                    comp_tokens = chunk.usage.completion_tokens

                is_finished = chunk.choices[0].finish_reason is not None

                yield StreamChunk(
                    text=text_chunk,
                    tool_call_deltas=tool_deltas,
                    is_finished=is_finished,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=comp_tokens,
                )
        except Exception as e:
            # Intercept Groq's 400 tool_use_failed during streaming
            if hasattr(e, "response") and getattr(e.response, "status_code", 0) == 400:
                try:
                    err_data = e.response.json().get("error", {})
                    if err_data.get("code") == "tool_use_failed":
                        failed_text = err_data.get("failed_generation", "")
                        salvaged_stream = salvage_groq_failed_generation_stream(
                            failed_text
                        )
                        if salvaged_stream:
                            for salvaged_chunk in salvaged_stream:
                                s_delta = (
                                    salvaged_chunk.choices[0].delta
                                    if salvaged_chunk.choices
                                    else None
                                )
                                if not s_delta:
                                    continue
                                s_text = s_delta.content or ""
                                s_tool_deltas = []
                                if getattr(s_delta, "tool_calls", None):
                                    for tc in s_delta.tool_calls:
                                        s_tool_deltas.append(
                                            {
                                                "index": tc.index,
                                                "id": tc.id,
                                                "name": (
                                                    tc.function.name
                                                    if tc.function
                                                    else None
                                                ),
                                                "arguments": (
                                                    tc.function.arguments
                                                    if tc.function
                                                    else ""
                                                ),
                                            }
                                        )
                                yield StreamChunk(
                                    text=s_text,
                                    tool_call_deltas=s_tool_deltas,
                                    is_finished=True,
                                    prompt_tokens=0,
                                    completion_tokens=0,
                                )
                            return
                except Exception:
                    pass
            raise e


def salvage_groq_failed_generation_stream(failed_text: str):
    """Intercepts Groq's 400 error and returns a mock stream iterable."""
    import re
    import json

    def create_error_text_chunk(error_message):
        class MockDeltaText:
            def __init__(self):
                self.content = (
                    f"\n[Groq API Intercepted a Broken Tool Call]:\n{error_message}\n"
                )
                self.tool_calls = None

        class MockChoiceText:
            def __init__(self):
                self.delta = MockDeltaText()
                self.finish_reason = "stop"

        class MockChunkText:
            def __init__(self):
                self.choices = [MockChoiceText()]
                self.usage = None
                self.x_groq = None

        return [MockChunkText()]

    # 1. Try to parse specific <function=name> format
    match = re.search(r"<function=(\w+)>(.*?)</function>", failed_text, re.DOTALL)
    if not match:
        return create_error_text_chunk(failed_text)

    tool_name = match.group(1)
    raw_args = match.group(2).strip()

    raw_args = re.sub(r"(?<!\\)\n", r"\\n", raw_args)
    raw_args = re.sub(r"(?<!\\)\t", r"\\t", raw_args)

    try:
        args_dict = json.loads(raw_args)
    except json.JSONDecodeError:
        return create_error_text_chunk(
            f"Tool: {tool_name}\nBroken Args: {raw_args}"
        )

    if isinstance(args_dict, list):
        if tool_name == "write_files":
            args_dict = {"files": args_dict}
        elif tool_name == "read_files":
            args_dict = {"paths": args_dict}
        else:
            args_dict = {"arguments": args_dict}

    class MockFunction:
        def __init__(self):
            self.name = tool_name
            self.arguments = json.dumps(args_dict)

    class MockToolCall:
        def __init__(self):
            self.index = 0
            self.id = f"call_{tool_name}_salvaged"
            self.function = MockFunction()

    class MockDelta:
        def __init__(self):
            thought_match = re.search(
                r"<thought>(.*?)</thought>", failed_text, re.DOTALL
            )
            self.content = (
                thought_match.group(1).strip() if thought_match else ""
            )
            self.tool_calls = [MockToolCall()]

    class MockChoice:
        def __init__(self):
            self.delta = MockDelta()
            self.finish_reason = "tool_calls"

    class MockChunk:
        def __init__(self):
            self.choices = [MockChoice()]
            self.usage = None
            self.x_groq = None

    return [MockChunk()]