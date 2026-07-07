# tests/test_llm_providers.py
import pytest
from llm.providers.gemini import GeminiProvider
from llm.providers.groq import GroqProvider


def test_gemini_message_formatting():
    """Ensures universal messages translate to Gemini's specific Part/Content schema."""
    provider = GeminiProvider(api_key="fake", model_name="gemini-3.1-flash-lite")

    # FIX: Removed the 'system' role, as the engine extracts it before this step
    standard_msgs = [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi there"},
    ]

    gemini_msgs = provider.format_messages(standard_msgs)

    # Gemini maps 'assistant' to 'model'
    assert gemini_msgs[0]["role"] == "user"
    assert gemini_msgs[0]["parts"][0]["text"] == "Hello"
    assert gemini_msgs[1]["role"] == "model"
    assert gemini_msgs[1]["parts"][0]["text"] == "Hi there"


def test_groq_message_formatting():
    """Ensures universal messages translate to Groq/OpenAI standard schema."""
    provider = GroqProvider(api_key="fake", model_name="llama-3.3-70b-versatile")

    # Groq/OpenAI DOES accept system roles in the messages array
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
    from llm.providers.groq import GroqProvider
    from llm.schemas import ToolCall
    
    # Initialize mock provider settings
    provider = GroqProvider(api_key="fake", model_name="llama-3.3-70b-versatile")
    
    # Setup conversation containing parallel requests to 'read_files' with independent IDs
    standard_msgs = [
        {"role": "user", "content": "Process target files"},
        {
            "role": "assistant",
            "content": "Executing standard read tools...",
            "tool_calls": [
                ToolCall(name="read_files", args={"paths": ["first.txt"]}, id="call_A"),
                ToolCall(name="read_files", args={"paths": ["second.txt"]}, id="call_B"),
            ]
        },
        {
            "role": "tool",
            "tool_name": "read_files",
            "content": "Content of the first file"
        },
        {
            "role": "tool",
            "tool_name": "read_files",
            "content": "Content of the second file"
        }
    ]
    
    # Process conversion schema through refactored formatting logic
    groq_msgs = provider.format_messages(standard_msgs)
    
    # Assert both tool calls in assistant turn are parsed correctly
    assert len(groq_msgs) == 4
    assert "tool_calls" in groq_msgs[1]
    assert groq_msgs[1]["tool_calls"][0]["id"] == "call_A"
    assert groq_msgs[1]["tool_calls"][1]["id"] == "call_B"
    
    # Verify sequential mapping adheres strictly to requested queue positions
    assert groq_msgs[2]["role"] == "tool"
    assert groq_msgs[2]["tool_call_id"] == "call_A"  # Successfully mapped to the first execution call
    assert groq_msgs[2]["content"] == "Content of the first file"
    
    assert groq_msgs[3]["role"] == "tool"
    assert groq_msgs[3]["tool_call_id"] == "call_B"  # Successfully mapped to the second execution call
    assert groq_msgs[3]["content"] == "Content of the second file"
