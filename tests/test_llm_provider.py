# tests/test_llm_provider.py

import pytest
from unittest.mock import patch, MagicMock
from llm.providers.gemini import GeminiProvider
from llm.providers.groq import GroqProvider
from llm.schemas import ToolCall, StreamChunk

def test_gemini_message_formatting():
    """Ensures universal messages translate to Gemini's specific Part/Content schema."""
    provider = GeminiProvider(api_key="fake", model_name="gemini-3.1-flash-lite")

    standard_msgs = [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi there"},
    ]

    gemini_msgs = provider.format_messages(standard_msgs)

    assert gemini_msgs[0]["role"] == "user"
    assert gemini_msgs[0]["parts"][0]["text"] == "Hello"
    assert gemini_msgs[1]["role"] == "model"
    assert gemini_msgs[1]["parts"][0]["text"] == "Hi there"

def test_groq_message_formatting():
    """Ensures universal messages translate to Groq/OpenAI standard schema."""
    provider = GroqProvider(api_key="fake", model_name="llama-3.3-70b-versatile")

    standard_msgs = [
        {"role": "system", "content": "You are an AI."},
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi there"},
    ]

    groq_msgs = provider.format_messages(standard_msgs)

    assert groq_msgs[0]["role"] == "system"
    assert groq_msgs[0]["content"] == "You are an AI."
    assert groq_msgs[1]["role"] == "user"
    assert groq_msgs[1]["content"] == "Hello"
    assert groq_msgs[2]["role"] == "assistant"
    assert groq_msgs[2]["content"] == "Hi there"

def test_groq_parallel_tool_message_formatting():
    """Ensures executing the same tool in parallel maps strict sequential FIFO IDs to prevent 400 Bad Requests."""
    provider = GroqProvider(api_key="fake", model_name="llama-3.3-70b-versatile")

    standard_msgs = [
        {"role": "user", "content": "Process target files"},
        {
            "role": "assistant",
            "content": "Executing standard read tools...",
            "tool_calls": [
                ToolCall(name="read_files", args={"paths": ["first.txt"]}, id="call_A"),
                ToolCall(name="read_files", args={"paths": ["second.txt"]}, id="call_B"),
            ],
        },
        {
            "role": "tool",
            "tool_name": "read_files",
            "content": "Content of the first file",
        },
        {
            "role": "tool",
            "tool_name": "read_files",
            "content": "Content of the second file",
        },
    ]

    groq_msgs = provider.format_messages(standard_msgs)

    assert len(groq_msgs) == 4
    assert "tool_calls" in groq_msgs[1]
    assert groq_msgs[1]["tool_calls"][0]["id"] == "call_A"
    assert groq_msgs[1]["tool_calls"][1]["id"] == "call_B"

    assert groq_msgs[2]["role"] == "tool"
    assert groq_msgs[2]["tool_call_id"] == "call_A"
    assert groq_msgs[2]["content"] == "Content of the first file"

    assert groq_msgs[3]["role"] == "tool"
    assert groq_msgs[3]["tool_call_id"] == "call_B"

def test_gemini_parallel_tool_message_formatting():
    """Ensures executing multiple tools in parallel groups them into a single 'function' role."""
    provider = GeminiProvider(api_key="fake", model_name="gemini-3.1-flash-lite")

    standard_msgs = [
        {"role": "user", "content": "Process files"},
        {
            "role": "assistant",
            "content": "Reading...",
            "tool_calls": [
                ToolCall(name="read_files", args={"paths": ["a.txt"]}, id="call_A"),
                ToolCall(name="read_files", args={"paths": ["b.txt"]}, id="call_B"),
            ],
        },
        {"role": "tool", "tool_name": "read_files", "content": "A content"},
        {"role": "tool", "tool_name": "read_files", "content": "B content"},
    ]

    gemini_msgs = provider.format_messages(standard_msgs)

    assert len(gemini_msgs) == 3
    assert gemini_msgs[0]["role"] == "user"
    assert gemini_msgs[1]["role"] == "model"
    assert len(gemini_msgs[1]["parts"]) == 3  # 1 text part, 2 function_call parts

    assert gemini_msgs[2]["role"] == "user"
    assert len(gemini_msgs[2]["parts"]) == 2  # 2 function_response parts

# --- GROQ STREAMING TESTS ---

def test_groq_generate_content_stream():
    """Verifies Groq correctly parses a network stream into StreamChunks."""
    provider = GroqProvider(api_key="fake", model_name="llama-3.3-70b-versatile")

    class MockDelta:
        def __init__(self, content=None, tool_calls=None):
            self.content = content
            self.tool_calls = tool_calls

    class MockChoice:
        def __init__(self, delta, finish_reason=None):
            self.delta = delta
            self.finish_reason = finish_reason

    class MockUsage:
        def __init__(self):
            self.prompt_tokens = 15
            self.completion_tokens = 25

    class MockChunk:
        def __init__(self, content=None, tool_calls=None, finish_reason=None, has_usage=False):
            self.choices = [MockChoice(MockDelta(content, tool_calls), finish_reason)]
            self.usage = MockUsage() if has_usage else None
            self.x_groq = None

    mock_stream = [
        MockChunk(content="Hello "),
        MockChunk(content="World!"),
        MockChunk(finish_reason="stop", has_usage=True),
    ]

    with patch.object(provider, "_make_groq_request", return_value=mock_stream):
        generator = provider.generate_content(messages=[], tools=[])
        chunks = list(generator)

    assert len(chunks) == 3
    assert isinstance(chunks[0], StreamChunk)
    assert chunks[0].text == "Hello "
    assert chunks[1].text == "World!"
    assert chunks[2].is_finished is True
    assert chunks[2].prompt_tokens == 15
    assert chunks[2].completion_tokens == 25

# --- GEMINI UNARY TESTS ---

def test_gemini_generate_content_unary():
    """Verifies Gemini correctly parses a unary response into a single StreamChunk."""
    provider = GeminiProvider(api_key="fake", model_name="gemini-3.1-flash-lite")

    class MockFunctionCall:
        def __init__(self):
            self.name = "read_files"
            self.args = {"paths": ["test.txt"]}
            self.id = "call_123"

    class MockPart:
        def __init__(self, text=None, function_call=None):
            self.text = text
            self.function_call = function_call

    class MockContent:
        def __init__(self, parts):
            self.parts = parts

    class MockCandidate:
        def __init__(self, parts):
            self.content = MockContent(parts)

    class MockUsageMetadata:
        def __init__(self):
            self.prompt_token_count = 10
            self.candidates_token_count = 20

    class MockResponse:
        def __init__(self, parts=None, has_usage=False):
            self.candidates = [MockCandidate(parts)] if parts else []
            self.usage_metadata = MockUsageMetadata() if has_usage else None

    # Simulate a single unary response containing text, a tool call, and usage
    mock_response = MockResponse(
        parts=[
            MockPart(text="I will read that."),
            MockPart(function_call=MockFunctionCall())
        ],
        has_usage=True
    )

    # Patch the UNARY generate_content method
    provider.client.models.generate_content = MagicMock(return_value=mock_response)

    # Consume the generator
    generator = provider.generate_content(messages=[], tools=[])
    chunks = list(generator)

    # Unary response yields exactly ONE chunk
    assert len(chunks) == 1
    chunk = chunks[0]

    assert chunk.text == "I will read that."
    assert chunk.is_finished is True
    assert len(chunk.tool_call_deltas) == 1
    assert chunk.tool_call_deltas[0]["name"] == "read_files"
    assert "test.txt" in chunk.tool_call_deltas[0]["arguments"]
    assert chunk.prompt_tokens == 10
    assert chunk.completion_tokens == 20