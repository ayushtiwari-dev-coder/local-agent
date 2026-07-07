# tests/test_context_formatter.py
import pytest
from unittest.mock import patch
from llm.context_formatter import format_context


@patch("llm.context_formatter.config_manager.get_system_instruction", return_value=None)
def test_format_context_standard_message_flow(mock_get_inst):
    # Standard user-assistant-tool alternation
    raw_db_messages = [
        {"role": "user", "content": "Verify directories."},
        {
            "role": "assistant",
            "content": "Running task.",
            "tool_calls": [{"name": "read_files", "args": {}}],
        },
    ]
    system_instruction, standardized_messages = format_context(raw_db_messages)

    # Verify base system prompt is loaded from DEFAULT fallback
    assert "You are a highly efficient" in system_instruction

    # Verify standardized messages structure
    assert len(standardized_messages) == 2
    assert standardized_messages[0]["role"] == "user"
    assert standardized_messages[1]["role"] == "assistant"
    assert "tool_calls" in standardized_messages[1]


@patch(
    "llm.context_formatter.config_manager.get_system_instruction",
    return_value="CUSTOM INSTRUCTION ACTIVE.",
)
def test_format_context_custom_instruction(mock_get_inst):
    # Ensures that a custom configuration completely overrides the default
    raw_db_messages = [{"role": "user", "content": "Hi"}]
    system_instruction, _ = format_context(raw_db_messages)

    assert "CUSTOM INSTRUCTION ACTIVE." in system_instruction
    assert "You are a highly efficient" not in system_instruction


@patch("llm.context_formatter.config_manager.get_system_instruction", return_value=None)
def test_format_context_extracts_previous_summaries(mock_get_inst):
    # If a system role message containing a previous summary exists
    raw_db_messages = [
        {"role": "system", "content": "Workspace project directories initialized."},
        {"role": "user", "content": "List files."},
    ]
    system_instruction, standardized_messages = format_context(raw_db_messages)

    # Verify summary is safely appended as a header card inside the system instruction
    assert (
        "[Previous Conversation Summary]\nWorkspace project directories initialized."
        in system_instruction
    )

    # Verify the raw summary itself is discarded from the messages array
    assert len(standardized_messages) == 1
    assert standardized_messages[0]["role"] == "user"
