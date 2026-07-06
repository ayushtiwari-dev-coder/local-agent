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
        {"role": "assistant", "content": "Hi there"}
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
        {"role": "assistant", "content": "Hi there"}
    ]
    
    groq_msgs = provider.format_messages(standard_msgs)
    
    assert groq_msgs[0]["role"] == "system"
    assert groq_msgs[0]["content"] == "You are an AI."
    assert groq_msgs[1]["role"] == "user"
    assert groq_msgs[1]["content"] == "Hello"
    assert groq_msgs[2]["role"] == "assistant"
    assert groq_msgs[2]["content"] == "Hi there"