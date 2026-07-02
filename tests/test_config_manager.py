# tests/test_config_manager.py

import unittest
import tempfile
import os
from unittest.mock import patch

# Import the config manager module to test
import utils.config_manager as cm

class TestConfigManager(unittest.TestCase):
    """Verifies config loading defaults, local file writing, and environment variables fallbacks."""

    def setUp(self):
        # Sandbox CONFIG_PATH using a temporary JSON file to protect the user's home config
        self.temp_config = tempfile.NamedTemporaryFile(delete=False)
        self.temp_config_path = self.temp_config.name
        self.temp_config.close()
        
        # Patch the module-level configuration path constant
        self.path_patcher = patch("utils.config_manager.CONFIG_PATH", self.temp_config_path)
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
        self.assertEqual(config["default_provider"], "gemini")
        self.assertEqual(config["thinking_level"], "high")
        self.assertIn("orchestra", config)

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

    def test_get_and_set_orchestra_routing(self):
        # Update routing properties for executor role
        cm.set_orchestra_route("executor", "groq", "llama-3.1-8b-instant")
        
        # Retrieve and verify updated route
        route = cm.get_orchestra_route("executor")
        self.assertEqual(route["provider"], "groq")
        self.assertEqual(route["model"], "llama-3.1-8b-instant")


if __name__ == "__main__":
    unittest.main()