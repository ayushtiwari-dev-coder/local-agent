# FILE: tests/test_user_manager.py
import unittest
from unittest.mock import patch
from managers.user_manager import register_user


class TestUserManager(unittest.TestCase):
    @patch("managers.user_manager.create_user")
    def test_register_user_success(self, mock_create):
        """Verifies valid names and usernames pass constraints and are cleaned."""
        mock_create.return_value = {"id": 1, "name": "John_Doe", "username": "johndoe"}

        # Display name must contain no spaces to pass the whitelist
        user = register_user(" John_Doe ", "JohnDoe")

        mock_create.assert_called_once_with("John_Doe", "johndoe")
        self.assertEqual(user["username"], "johndoe")

    def test_register_user_length_limits(self):
        """Edge Case: Fails if name or username is empty or exceeds 25 chars."""
        with self.assertRaisesRegex(ValueError, "must be between 1 and 25"):
            register_user("", "valid_user")

        with self.assertRaisesRegex(ValueError, "must be between 1 and 25"):
            register_user("valid_name", "")

        with self.assertRaisesRegex(ValueError, "must be between 1 and 25"):
            register_user("A" * 26, "valid_user")

    def test_register_user_invalid_characters(self):
        """Edge Case: Whitelist validation blocks special characters and spaces in username."""
        invalid_names = ["Ayush@123", "Ayush!", "Ayush#"]
        for name in invalid_names:
            with self.assertRaisesRegex(ValueError, "Name contains invalid characters"):
                register_user(name, "valid_user")

        invalid_usernames = ["ayush tiwari", "ayush@tiwari", "ayush/tiwari"]
        for uname in invalid_usernames:
            with self.assertRaisesRegex(
                ValueError, "Username contains invalid characters"
            ):
                # Use "Valid_Name" (with underscore) so the username validation block is reached
                register_user("Valid_Name", uname)


if __name__ == "__main__":
    unittest.main()
