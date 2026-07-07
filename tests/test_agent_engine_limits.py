# tests/test_agent_engine_limits.py
import pytest
from unittest.mock import patch, MagicMock
from engine.agent_engine import AgentEngine
from llm.schemas import LLMResponse, ToolCall


@patch("engine.agent_engine.config_manager.get_max_turns", return_value=3)
@patch("engine.agent_engine.LLMFactory.get_provider")
@patch("engine.agent_engine.save_user_message")
@patch("engine.agent_engine.save_assistant_message")
@patch("engine.agent_engine.compile_llm_context", return_value=[])
@patch("engine.agent_engine.log_api_usage")
@patch("engine.agent_engine.check_for_infinite_loop")  # Bypass loop protector
def test_max_turns_exceeded(
    mock_loop_check,
    mock_log_api,
    mock_compile,
    mock_save_ast,
    mock_save_usr,
    mock_get_provider,
    mock_max_turns,
):
    """Ensures the AgentEngine forcefully stops if MAX_TURNS is reached."""
    # Tell the loop protector to never trigger during this test
    mock_loop_check.return_value = (False, None, '{"cmd": "ls"}')

    # 1. Setup a mock provider
    mock_provider = MagicMock()
    mock_provider.model_name = "fake-test-model"
    mock_get_provider.return_value = mock_provider

    # 2. Create a fake LLM response that ALWAYS requests a tool call
    fake_tool_call = ToolCall(name="run_terminal_command", args={"cmd": "ls"})
    fake_response = LLMResponse(
        text="", tool_calls=[fake_tool_call], prompt_tokens=10, completion_tokens=10
    )
    mock_provider.generate_content.return_value = fake_response

    # 3. Initialize the engine
    engine = AgentEngine(provider_name="gemini", api_key="fake_key")

    # 4. Mock the tool executor so it doesn't actually run terminal commands
    with patch(
        "engine.agent_engine.determine_and_execute_tool",
        return_value=("Success", "success"),
    ):
        # 5. Run the engine
        final_output = engine.send_message(
            conversation_id=1, user_text="Do something forever"
        )

    # 6. Assertions
    assert "Maximum tool execution limit (3 turns) reached" in final_output
    assert mock_provider.generate_content.call_count == 3
