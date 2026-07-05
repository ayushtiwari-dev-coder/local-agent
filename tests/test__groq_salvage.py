# tests/test_groq_salvage.py
import unittest
from llm.providers.groq import salvage_groq_failed_generation


class TestGroqSalvageParser(unittest.TestCase):

    def test_salvage_xml_wrapped_json(self):
        """Tests if the regex correctly extracts the tool name and JSON from Llama's XML hallucination."""
        broken_llama_output = """
        I will write the file for you now.
        <function=write_files>{"files_json": "{\\"path\\": \\"test.py\\", \\"content\\": \\"print(1)\\"}"}</function>
        """
        response = salvage_groq_failed_generation(broken_llama_output)

        self.assertIsNotNone(response)
        # Verify it mocked the response correctly
        tool_call = response.choices[0].message.tool_calls[0]
        self.assertEqual(tool_call.function.name, "write_files")
        self.assertIn("test.py", tool_call.function.arguments)

    def test_salvage_unescaped_newlines(self):
        """Edge Case: Llama forgets to escape newlines in JSON strings."""
        # Notice the raw newline inside the content string, which breaks standard json.loads()
        broken_llama_output = """
        <function=run_terminal_command>{"cmd": "echo 'line1
        line2'"}</function>
        """
        response = salvage_groq_failed_generation(broken_llama_output)

        self.assertIsNotNone(response)
        tool_call = response.choices[0].message.tool_calls[0]
        # The salvager should have replaced the raw newline with a literal '\n'
        self.assertIn("\\n", tool_call.function.arguments)

    def test_salvage_hallucinated_list(self):
        """Edge Case: Llama passes a list instead of a dictionary for write_files."""
        broken_llama_output = """
        <function=write_files>[{"path": "test.py", "content": "print(1)"}]</function>
        """
        response = salvage_groq_failed_generation(broken_llama_output)

        self.assertIsNotNone(response)
        tool_call = response.choices[0].message.tool_calls[0]
        # The salvager should have wrapped the list in the {"files": ...} dictionary
        self.assertIn('"files":', tool_call.function.arguments)

    def test_salvage_complete_garbage(self):
        """If the LLM outputs total garbage, the salvager should return None gracefully."""
        garbage_output = "I don't know how to do that."
        response = salvage_groq_failed_generation(garbage_output)
        self.assertIsNone(response)


if __name__ == "__main__":
    unittest.main()
