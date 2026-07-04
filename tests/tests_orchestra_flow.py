import unittest
from unittest.mock import patch, MagicMock

# Import the error handler directly from its module
from engine.handle_permissions import _detect_tool_error
# Import the refactored background helpers
import tools.orchestra_tools as ot

class TestToolErrorDetection(unittest.TestCase):
    """Verifies that the structured tool execution error detection behaves correctly."""

    def test_string_outputs(self):
        # Case A: Output starts with "Error:" (should flag as failure)
        self.assertTrue(_detect_tool_error("run_terminal_command", "Error: command timed out."))

        # Case B: Output contains "Error:" inside the text, but doesn't start with it (should NOT flag as failure)
        self.assertFalse(_detect_tool_error("run_terminal_command", "Compilation complete. Found 0 Error: occurrences."))

    def test_explicit_error_dicts(self):
        # Case C: Dictionary contains a dedicated 'error' key (should flag as failure)
        self.assertTrue(_detect_tool_error("read_files", {"error": "Expected a list of paths."}))

    def test_batch_file_outputs(self):
        # Case D: Batch operations where individual entries failed with prefix (should flag as failure)
        bad_batch = {
            "src/main.py": "Success: File written successfully.",
            "src/config.py": "Error: Path is outside the allowed workspace."
        }
        self.assertTrue(_detect_tool_error("write_files", bad_batch))

    def test_batch_file_outputs_success(self):
        # Case E: Batch operations where entry contains "Error:" in the middle of content (should NOT flag as failure)
        good_batch_with_error_content = {
            "logs.txt": "Line 1: Normal statement.\nLine 2: Error: database reconnecting...\nLine 3: Success."
        }
        self.assertFalse(_detect_tool_error("read_files", good_batch_with_error_content))


class TestBackgroundOrchestration(unittest.TestCase):
    """Verifies the execution flow of each decomposed modular background orchestra function."""

    @patch("tools.orchestra_tools.AgentTemplate.spawn")
    @patch("tools.orchestra_tools._evaluate_with_critic")
    @patch("tools.orchestra_tools.parse_json_safely")
    def test_generate_and_validate_plan(self, mock_parse, mock_evaluate, mock_spawn):
        # Setup mocks
        mock_agent = MagicMock()
        mock_agent.send_message.return_value = '{"chunk_title": "Phase 1"}'
        mock_spawn.return_value = mock_agent
        mock_evaluate.return_value = {"approved": True, "feedback": ""}
        mock_parse.return_value = [{"chunk_title": "Phase 1", "sub_tasks": ["Task A"]}]

        # Call the planning function
        chunks = ot._generate_and_validate_plan("Build website", planner_conv_id=100)

        # Assertions
        mock_spawn.assert_called_once_with("planner", autonomous=True)
        mock_agent.send_message.assert_called_once()
        mock_evaluate.assert_called_once()
        mock_parse.assert_called_once_with('{"chunk_title": "Phase 1"}')
        self.assertEqual(chunks, [{"chunk_title": "Phase 1", "sub_tasks": ["Task A"]}])

    @patch("tools.orchestra_tools.create_task")
    @patch("tools.orchestra_tools.create_sub_task")
    def test_save_plan_to_database(self, mock_create_sub, mock_create_task):
        # Setup mocks
        mock_create_task.return_value = {"id": 200}
        chunks_input = [
            {
                "chunk_title": "Phase 1: Setup",
                "role_persona": "Software Engineer",
                "acceptance_criteria": "Task completes without errors.",
                "sub_tasks": ["Create requirements.txt", "Initialize folder"]
            }
        ]

        # Call the DB manager
        queue = ot._save_plan_to_database(project_id=1, chunks=chunks_input)

        # Assertions
        mock_create_task.assert_called_once_with(1, "Phase 1: Setup", description="Persona: Software Engineer")
        self.assertEqual(mock_create_sub.call_count, 2)
        self.assertEqual(queue, [(200, "Phase 1: Setup", "Software Engineer", "Task completes without errors.")])

    @patch("tools.orchestra_tools.update_task_status")
    @patch("tools.orchestra_tools.save_assistant_message")
    @patch("tools.orchestra_tools.get_sub_tasks_by_task")
    @patch("tools.orchestra_tools.update_sub_task_status")
    @patch("tools.orchestra_tools.start_new_conversation")
    @patch("tools.orchestra_tools.create_message")
    @patch("tools.orchestra_tools.AgentTemplate.spawn")
    @patch("tools.orchestra_tools._evaluate_with_critic")
    def test_execute_chunk_with_critic(self, mock_evaluate, mock_spawn, mock_create_msg, mock_start_conv, mock_sub_status, mock_get_subs, mock_save_msg, mock_task_status):
        # Setup mocks
        mock_get_subs.return_value = [{"id": 301, "description": "Step 1"}]
        mock_start_conv.return_value = {"id": 101}
        mock_agent = MagicMock()
        mock_agent.send_message.return_value = "Tasks completed successfully"
        mock_spawn.return_value = mock_agent
        mock_evaluate.return_value = {"approved": True, "summary": "Subtask steps verified successfully."}

        # Call chunk executor
        summary = ot._execute_chunk_with_critic(
            conversation_id=42,
            task_id=200,
            chunk_title="Phase 1: Setup",
            role_persona="Software Engineer",
            acceptance_criteria="Task completes without errors.",
            previous_summaries=""
        )

        # Assertions
        mock_task_status.assert_any_call(200, "in_progress")
        mock_get_subs.assert_called_once_with(200)
        mock_sub_status.assert_any_call(301, "in_progress")
        mock_spawn.assert_called_once_with("executor", autonomous=True)
        mock_agent.send_message.assert_called_once()
        mock_evaluate.assert_called_once()
        mock_sub_status.assert_any_call(301, "completed")
        mock_task_status.assert_any_call(200, "completed")
        self.assertEqual(summary, "Subtask steps verified successfully.")

    @patch("tools.orchestra_tools.ensure_project_id")
    @patch("tools.orchestra_tools._generate_and_validate_plan")
    @patch("tools.orchestra_tools._save_plan_to_database")
    @patch("tools.orchestra_tools._execute_chunk_with_critic")
    @patch("tools.orchestra_tools.save_assistant_message")
    @patch("tools.orchestra_tools.start_new_conversation")
    @patch("tools.orchestra_tools.create_message")
    def test_run_background_orchestra_success_lifecycle(self, mock_create_msg, mock_start_conv, mock_save_msg, mock_execute, mock_save_db, mock_plan, mock_project):
        # Setup mocks
        mock_project.return_value = 1
        mock_start_conv.return_value = {"id": 100}
        mock_plan.return_value = [{"chunk_title": "Phase 1"}]
        mock_save_db.return_value = [(200, "Phase 1", "Software Engineer", "Criteria")]
        mock_execute.return_value = "Summary of phase 1"

        # Run main loop orchestration
        ot._run_background_orchestra(conversation_id=42, task="Automate script execution")

        # Assertions (Verifying that operations occur sequentially in order)
        mock_project.assert_called_once()
        mock_start_conv.assert_called_once_with(user_id=None, title="[System] Background Planning")
        mock_create_msg.assert_called_once()
        mock_plan.assert_called_once_with("Automate script execution", 100)
        mock_save_db.assert_called_once_with(1, [{"chunk_title": "Phase 1"}])
        mock_execute.assert_called_once_with(42, 200, "Phase 1", "Software Engineer", "Criteria", previous_summaries="")
        mock_save_msg.assert_any_call(42, "[BACKGROUND SYSTEM COMPLETED]: All planned task chunks have been executed and approved by the Critic!")

    @patch("tools.orchestra_tools.ensure_project_id")
    @patch("tools.orchestra_tools._generate_and_validate_plan")
    @patch("tools.orchestra_tools.save_assistant_message")
    @patch("tools.orchestra_tools.start_new_conversation")
    @patch("tools.orchestra_tools.create_message")
    def test_run_background_orchestra_failure_lifecycle(self, mock_create_msg, mock_start_conv, mock_save_msg, mock_plan, mock_project):
        # Setup mocks to trigger an exception
        mock_project.return_value = 1
        mock_start_conv.return_value = {"id": 100}
        mock_plan.side_effect = Exception("Model service timeout.")

        # Run main loop orchestration
        ot._run_background_orchestra(conversation_id=42, task="Automate script execution")

        # Assertions (Verifying safety exception logs to conversation state)
        mock_project.assert_called_once()
        mock_save_msg.assert_called_once_with(
            42,
            "[BACKGROUND ORCHESTRA ERROR]: Execution failed: Model service timeout."
        )

if __name__ == "__main__":
    unittest.main()