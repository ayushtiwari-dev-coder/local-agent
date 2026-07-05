# FILE: tests/test_config_manager.py
import unittest
import tempfile
import os
from unittest.mock import patch
import utils.config_manager as cm


class TestConfigManager(unittest.TestCase):
    """Verifies config loading defaults, local file writing, environment variables, and edge cases."""

    def setUp(self):
        # Sandbox CONFIG_PATH using a temporary JSON file to protect the user's home config
        self.temp_config = tempfile.NamedTemporaryFile(delete=False)
        self.temp_config_path = self.temp_config.name
        self.temp_config.close()

        # Patch the module-level configuration path constant
        self.path_patcher = patch(
            "utils.config.core.CONFIG_PATH", self.temp_config_path
        )
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
        self.assertIn("thinking_level", config["settings"])

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

    def test_custom_system_instruction_persistence(self):
        """Verifies that setting a custom instruction writes to the config, and clearing it returns None."""
        # 1. Set Custom
        cm.set_system_instruction("You are a helpful coding assistant.")
        self.assertEqual(
            cm.get_system_instruction(), "You are a helpful coding assistant."
        )

        # 2. Clear (set to None or empty)
        cm.set_system_instruction("")
        self.assertIsNone(cm.get_system_instruction())

        cm.set_system_instruction(None)
        self.assertIsNone(cm.get_system_instruction())

    def test_embedding_model_persistence(self):
        """Verifies we can dynamically update embedding models per provider."""
        # Test Gemini
        cm.set_embedding_model("gemini", "custom-gemini-embed-v2")
        self.assertEqual(cm.get_embedding_model("gemini"), "custom-gemini-embed-v2")

        # Test Groq
        cm.set_embedding_model("groq", "custom-nomic-v3")
        self.assertEqual(cm.get_embedding_model("groq"), "custom-nomic-v3")

    def test_sandbox_environment_persistence(self):
        """Verifies Docker image and Workspace path overrides."""
        # Docker Image
        cm.set_docker_image("node:18-alpine")
        self.assertEqual(cm.get_docker_image(), "node:18-alpine")

        # Workspace Path
        cm.set_workspace_path("/custom/dev/folder")
        # get_workspace_path returns an absolute expanded path, so we verify it ends correctly
        self.assertTrue(
            cm.get_workspace_path().endswith("custom/dev/folder".replace("/", os.sep))
        )


if __name__ == "__main__":
    unittest.main()
