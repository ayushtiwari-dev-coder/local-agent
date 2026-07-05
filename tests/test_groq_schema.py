# tests/test_groq_schema.py

import unittest
from llm.providers.groq import _function_to_schema


class TestGroqSchema(unittest.TestCase):
    """Verifies that Python functions are correctly parsed into OpenAI/Groq JSON-schemas."""

    def test_function_to_schema_mapping(self):
        # 1. Define a dummy tool function with varied types and default args
        def write_report(filepath: str, lines_count: int, append: bool = False) -> str:
            """Writes lines of content to a specified local file path."""
            pass

        # 2. Convert to schema
        schema = _function_to_schema(write_report)

        # 3. Assertions
        self.assertEqual(schema["type"], "function")
        func_details = schema["function"]
        self.assertEqual(func_details["name"], "write_report")
        self.assertEqual(
            func_details["description"],
            "Writes lines of content to a specified local file path.",
        )

        params = func_details["parameters"]
        self.assertEqual(params["type"], "object")

        properties = params["properties"]
        self.assertEqual(properties["filepath"]["type"], "string")
        self.assertEqual(properties["lines_count"]["type"], "integer")
        self.assertEqual(properties["append"]["type"], "boolean")

        # Required fields check (append has a default value, so it should not be required)
        required_fields = params["required"]
        self.assertIn("filepath", required_fields)
        self.assertIn("lines_count", required_fields)
        self.assertNotIn("append", required_fields)


if __name__ == "__main__":
    unittest.main()
