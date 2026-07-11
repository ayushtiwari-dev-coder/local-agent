# tests/test_cli_research_routing.py

import pytest
from unittest.mock import patch, MagicMock
from cli.chat_loop import enter_chat_session

@pytest.fixture
def mock_cli_dependencies():
    """Mocks the engine and config so we can test CLI routing without real API calls."""
    with patch("cli.chat_loop.AgentEngine") as mock_engine_class, \
         patch("cli.chat_loop.config_manager") as mock_config, \
         patch("cli.chat_loop.render_conversation_history"):
         
        mock_engine_instance = MagicMock()
        mock_engine_class.return_value = mock_engine_instance
        
        mock_config.get_default_provider.return_value = "gemini"
        mock_config.get_active_model.return_value = "gemini-3.1-flash-lite"
        mock_config.get_provider_api_key.return_value = "fake_key"
        
        yield mock_engine_instance

@pytest.mark.parametrize("user_input, expected_text", [
    ("Who won the super bowl in 2024?", "Who won the super bowl in 2024?"),
    ("Who won the super bowl in 2024? Generate a PDF.", "Who won the super bowl in 2024? Generate a PDF."),
    ("Who won the super bowl in 2024? Save it to a text file.", "Who won the super bowl in 2024? Save it to a text file.")
])
def test_small_research_routing(mock_cli_dependencies, user_input, expected_text):
    """Tests standard queries with different output requests."""
    with patch("builtins.input", side_effect=[user_input, "exit"]):
        enter_chat_session(conversation_id=1)
        
    send_message_kwargs = mock_cli_dependencies.send_message.call_args[1]
    user_text = send_message_kwargs["user_text"]
    
    assert user_text == expected_text
    assert "[SYSTEM DIRECTIVE" not in user_text

@pytest.mark.parametrize("user_input, expected_text", [
    ("Summarize this: https://example.com", "Summarize this: https://example.com"),
    ("Summarize this: https://example.com into a PDF", "Summarize this: https://example.com into a PDF"),
    ("Summarize this: https://example.com and write to summary.md", "Summarize this: https://example.com and write to summary.md")
])
def test_medium_research_routing(mock_cli_dependencies, user_input, expected_text):
    """Tests specific URL reading with different output requests."""
    with patch("builtins.input", side_effect=[user_input, "exit"]):
        enter_chat_session(conversation_id=1)
        
    send_message_kwargs = mock_cli_dependencies.send_message.call_args[1]
    user_text = send_message_kwargs["user_text"]
    
    assert user_text == expected_text
    assert "[SYSTEM DIRECTIVE" not in user_text


@pytest.mark.parametrize("user_input, expected_base_query", [
    ("/research Latest AI news", "Latest AI news"),
    ("/research Latest AI news. Make a PDF report.", "Latest AI news. Make a PDF report."),
    ("/research Latest AI news. Save to a markdown file.", "Latest AI news. Save to a markdown file.")
])
def test_deep_research_routing(mock_cli_dependencies, user_input, expected_base_query):
    """Tests the /research command intercept with different output requests."""
    with patch("builtins.input", side_effect=[user_input, "exit"]):
        enter_chat_session(conversation_id=1)
        
    send_message_kwargs = mock_cli_dependencies.send_message.call_args[1]
    user_text = send_message_kwargs["user_text"]
    
    # 1. Verify the output format request (PDF/File) was NOT stripped out
    assert expected_base_query in user_text
    
    # 2. Verify the strict Deep Research directive was appended
    assert "[SYSTEM DIRECTIVE: DEEP RESEARCH MODE ENGAGED]" in user_text
    assert "MUST use the `web_researcher` tool" in user_text
    assert "include a \"Sources\" section" in user_text
    
    # 3. Ensure the command trigger itself was removed from the final payload
    assert "/research" not in user_text