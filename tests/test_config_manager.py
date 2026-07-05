# tests/test_config_manager.py
import unittest
import tempfile
import os
from unittest.mock import patch

# Import the config manager module to test
import utils.config_manager as cm

class TestConfigManager(unittest.TestCase):
    """Verifies config loading defaults, local file writing, environment variables, and edge cases."""

    def setUp(self):
        # Sandbox CONFIG_PATH using a temporary JSON file to protect the user's home config
        self.temp_config = tempfile.NamedTemporaryFile(delete=False)
        self.temp_config_path = self.temp_config.name
        self.temp_config.close()

        # Patch the module-level configuration path constant
        self.path_patcher = patch("utils.config.core.CONFIG_PATH", self.temp_config_path)
        self.path_patcher.start()

    def tearDown(self):
        self.path_patcher.stop()
        try:
            os.remove(self.temp_config_path)
        except OSError:
            pass

    def test_load_config_fallback_when_file_missing(self):
        # If config file is missing, verify it safely returns standard default dictionary
        if os.path.exists(self.temp_config_path):
            os.remove(self.temp_config_path)
        
        config = cm.load_config()
        self.assertEqual(config["models"]["default_provider"], "gemini")
        self.assertEqual(config["settings"]["thinking_level"], "high")

    def test_set_and_get_provider_api_key_interaction(self):
        # Store key inside the mock json config
        cm.set_provider_api_key("gemini", "mock-gemini-key")
        
        # Retrieve and verify key matches
        key = cm.get_provider_api_key("gemini")
        self.assertEqual(key, "mock-gemini-key")

    @patch.dict(os.environ, {"GROQ_API_KEY": "fallback-groq-key"})
    def test_get_provider_api_key_environment_fallback(self):
        # Ensure config holds None for groq key
        cm.set_provider_api_key("groq", None)
        
        # Retrieval should fall back to mapped system environment variables
        key = cm.get_provider_api_key("groq")
        self.assertEqual(key, "fallback-groq-key")

    def test_loop_guard_edge_cases(self):
        """Verifies that invalid loop guard inputs gracefully fall back to None in the schema."""
        # 1. Test Valid Inputs (Standard Usage)
        cm.set_loop_guard(max_failed=5, max_success=10)
        lg = cm.get_loop_guard()
        self.assertEqual(lg["max_failed_attempts"], 5)
        self.assertEqual(lg["max_success_attempts"], 10)

        # 2. Test Zero and None (Clearing the configuration)
        cm.set_loop_guard(max_failed=0, max_success=None)
        lg_reset = cm.get_loop_guard()
        self.assertIsNone(lg_reset["max_failed_attempts"])
        self.assertIsNone(lg_reset["max_success_attempts"])

        # 3. Test Negative Values (Malicious / Accidental Inputs)
        cm.set_loop_guard(max_failed=-5, max_success=-1)
        lg_negative = cm.get_loop_guard()
        self.assertIsNone(lg_negative["max_failed_attempts"])
        self.assertIsNone(lg_negative["max_success_attempts"])


if __name__ == "__main__":
    unittest.main()