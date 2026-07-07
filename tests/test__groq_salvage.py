# tests/test_groq_salvage.py
import pytest
from llm.providers.groq import salvage_groq_failed_generation


def test_salvage_xml_wrapped_json():
    """Tests if the regex correctly extracts tool parameters from Llama's raw XML tags."""
    broken_llama_output = """
    I will write the file for you now.
    <function=write_files>{"files_json": "{\\"path\\": \\"test.py\\", \\"content\\": \\"print(1)\\"}"}</function>
    """
    response = salvage_groq_failed_generation(broken_llama_output)

    assert response is not None
    tool_call = response.choices[0].message.tool_calls[0]
    assert tool_call.function.name == "write_files"
    assert "test.py" in tool_call.function.arguments


def test_salvage_unescaped_newlines():
    """Edge Case: Resolves raw newlines found in unescaped tool parameters."""
    broken_llama_output = """
    <function=run_terminal_command>{"cmd": "echo 'line1
    line2'"}</function>
    """
    response = salvage_groq_failed_generation(broken_llama_output)

    assert response is not None
    tool_call = response.choices[0].message.tool_calls[0]
    assert "\\n" in tool_call.function.arguments


def test_salvage_hallucinated_list():
    """Edge Case: Restructures list data if the model fails to wrap it inside the dictionary container."""
    broken_llama_output = """
    <function=write_files>[{"path": "test.py", "content": "print(1)"}]</function>
    """
    response = salvage_groq_failed_generation(broken_llama_output)

    assert response is not None
    tool_call = response.choices[0].message.tool_calls[0]
    assert '"files":' in tool_call.function.arguments


def test_salvage_complete_garbage():
    """If the LLM outputs garbage, the salvager should return None gracefully."""
    garbage_output = "I don't know how to do that."
    response = salvage_groq_failed_generation(garbage_output)
    assert response is None
