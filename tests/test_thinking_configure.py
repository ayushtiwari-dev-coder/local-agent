# tests/test_thinking_configure.py

import unittest
from unittest.mock import patch, MagicMock
from engine.thinking_configure import supports_thinking, get_thinking_config


class TestThinkingConfigure(unittest.TestCase):
    """Verifies support checks and enum/string fallback mappings for thinking configurations."""

    def test_supports_thinking_logic(self):
        # Check models that support reasoning natively
        self.assertTrue(supports_thinking("gemini-3.1-flash-lite"))
        self.assertTrue(supports_thinking("gemma-4-26b-a4b-it"))

        # Check models that do not support reasoning
        self.assertFalse(supports_thinking("gemini-2.5-flash"))

    def test_get_thinking_config_off(self):
        # Setting level to off should return None immediately
        config = get_thinking_config("gemini-3.1-flash-lite", level="off")
        self.assertIsNone(config)

    @patch("engine.thinking_configure.types")
    def test_get_thinking_config_enum_mapping(self, mock_types):
        # Setup mock enum values inside the types module
        mock_types.ThinkingLevel.LOW = "MOCK_LOW_ENUM"
        mock_types.ThinkingConfig = MagicMock(return_value="SUCCESSFUL_CONFIG_OBJECT")

        # Test valid mapping
        config = get_thinking_config("gemini-3.1-flash-lite", level="low")
        mock_types.ThinkingConfig.assert_called_with(thinking_level="MOCK_LOW_ENUM")
        self.assertEqual(config, "SUCCESSFUL_CONFIG_OBJECT")

    @patch("engine.thinking_configure.types")
    def test_get_thinking_config_fallback_string_mapping(self, mock_types):
        # Trigger AttributeError to simulate a different SDK version missing enums
        del mock_types.ThinkingLevel
        mock_types.ThinkingConfig = MagicMock(return_value="FALLBACK_CONFIG_OBJECT")

        # Test that fallback catches AttributeError and maps to standard strings
        config = get_thinking_config("gemini-3.1-flash-lite", level="high")
        mock_types.ThinkingConfig.assert_called_with(thinking_level="HIGH")
        self.assertEqual(config, "FALLBACK_CONFIG_OBJECT")


if __name__ == "__main__":
    unittest.main()
