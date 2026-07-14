# import pytest
# from unittest.mock import patch, MagicMock
# from datetime import datetime, timezone, timedelta
# from optional_docker_extension.sandbox_lifecycle import enforce_sandbox_lifecycle_policy

# @pytest.fixture
# def mock_docker_containers():
#     """Returns three mock container instances with variable create dates."""
#     c1 = MagicMock()
#     c1.name = "local_agent_sandbox_conv_1"
#     c1.status = "running"
#     # Inspect creation dates
#     c1.attrs = {"Created": "2026-07-07T12:00:00.000000Z"}  # Oldest

#     c2 = MagicMock()
#     c2.name = "local_agent_sandbox_conv_2"
#     c2.status = "running"
#     c2.attrs = {"Created": "2026-07-07T12:15:00.000000Z"}  # Middle

#     c3 = MagicMock()
#     c3.name = "local_agent_sandbox_conv_3"
#     c3.status = "running"
#     c3.attrs = {"Created": "2026-07-07T12:30:00.000000Z"}  # Newest (Currently Executing)

#     return c1, c2, c3


# @patch("tools.sandbox_lifecycle.get_conversation_sandboxes")
# @patch("tools.sandbox_lifecycle.execute_read")
# @patch("tools.sandbox_lifecycle.config_manager")
# def test_lifecycle_idle_timeout_execution(mock_config, mock_execute_read, mock_get_sandboxes, mock_docker_containers):
#     """Verify containers idle beyond limits are stopped automatically, protecting active sessions."""
#     c1, c2, c3 = mock_docker_containers
#     mock_get_sandboxes.return_value = [(1, c1), (2, c2), (3, c3)]

#     # 1. Configure settings: 15-minute idle limit
#     mock_config.get_max_active_containers.return_value = 5
#     mock_config.get_max_total_containers.return_value = 10
#     mock_config.get_container_idle_timeout.return_value = 15.0

#     # 2. Mock last active execution lookups from SQLite:
#     # Set mock current time inside lifecycle calculations as: 2026-07-07 12:45:00 (UTC)
#     now_simulated = datetime(2026, 7, 7, 12, 45, 0, tzinfo=timezone.utc)

#     def db_time_mock_side_effect(query, params, fetch_one):
#         conv_id = params[0]
#         if conv_id == 1:
#             # Idle for 45 mins (12:00:00 to 12:45:00). Exceeds 15m. Should stop.
#             return {"created_at": "2026-07-07 12:00:00"}
#         if conv_id == 2:
#             # Idle for 10 mins (12:35:00 to 12:45:00). Under 15m limit. Leave running.
#             return {"created_at": "2026-07-07 12:35:00"}
#         # Active container (ID 3) has no executions yet, falls back to metadata (12:30:00). Idle for 15m (equals limit). Leave running.
#         return None

#     mock_execute_read.side_effect = db_time_mock_side_effect

#     # 3. Execute under mock date delta frame
#     with patch("tools.sandbox_lifecycle.datetime") as mock_datetime:
#         mock_datetime.now.return_value = now_simulated
#         mock_datetime.strptime = datetime.strptime
#         enforce_sandbox_lifecycle_policy(MagicMock(), active_conversation_id=3)

#     # Assertions:
#     # Container 1 (idle over threshold) must be stopped
#     c1.stop.assert_called_once_with(timeout=2)
#     # Container 2 (under threshold) remains running
#     c2.stop.assert_not_called()
#     # Container 3 (currently active session) is protected and remains running
#     c3.stop.assert_not_called()


# @patch("tools.sandbox_lifecycle.get_conversation_sandboxes")
# @patch("tools.sandbox_lifecycle.execute_read")
# @patch("tools.sandbox_lifecycle.config_manager")
# def test_lifecycle_concurrency_ceiling_throttle(mock_config, mock_execute_read, mock_get_sandboxes, mock_docker_containers):
#     """Verify oldest running containers are stopped when the concurrent running limit is breached."""
#     c1, c2, c3 = mock_docker_containers
#     mock_get_sandboxes.return_value = [(1, c1), (2, c2), (3, c3)]

#     # Configure ceiling: Max active allowed concurrently is 2. (We have 3 running)
#     mock_config.get_max_active_containers.return_value = 2
#     mock_config.get_max_total_containers.return_value = 10
#     # High idle threshold so idle timer doesn't trigger
#     mock_config.get_container_idle_timeout.return_value = 120.0

#     # Set mock db timeline
#     now_simulated = datetime(2026, 7, 7, 12, 45, 0, tzinfo=timezone.utc)
#     mock_execute_read.side_effect = lambda q, p, f: {
#         1: {"created_at": "2026-07-07 12:10:00"}, # LRU (Oldest Active)
#         2: {"created_at": "2026-07-07 12:20:00"}, # Newer Active
#         3: {"created_at": "2026-07-07 12:30:00"}  # Active Session
#     }.get(p[0])

#     with patch("tools.sandbox_lifecycle.datetime") as mock_datetime:
#         mock_datetime.now.return_value = now_simulated
#         mock_datetime.strptime = datetime.strptime
#         # Execute while active conversation is room ID 3
#         enforce_sandbox_lifecycle_policy(MagicMock(), active_conversation_id=3)

#     # Assertions:
#     # 1. c1 (oldest running container) is stopped to reduce active count to 2
#     c1.stop.assert_called_once_with(timeout=2)
#     # 2. c2 (under ceiling threshold) remains running
#     c2.stop.assert_not_called()
#     # 3. c3 (active room container) is protected and remains running
#     c3.stop.assert_not_called()


# @patch("tools.sandbox_lifecycle.get_conversation_sandboxes")
# @patch("tools.sandbox_lifecycle.execute_read")
# @patch("tools.sandbox_lifecycle.config_manager")
# def test_lifecycle_disk_pruning_lru_removal(mock_config, mock_execute_read, mock_get_sandboxes, mock_docker_containers):
#     """Verify oldest containers on disk (stopped or running) are purged when total storage capacity is reached."""
#     c1, c2, c3 = mock_docker_containers

#     # Configure total ceiling: Max total containers allowed on disk is 2. (We have 3 on disk)
#     mock_config.get_max_active_containers.return_value = 5
#     mock_config.get_max_total_containers.return_value = 2
#     mock_config.get_container_idle_timeout.return_value = 120.0

#     mock_get_sandboxes.return_value = [(1, c1), (2, c2), (3, c3)]

#     now_simulated = datetime(2026, 7, 7, 12, 45, 0, tzinfo=timezone.utc)
#     mock_execute_read.side_effect = lambda q, p, f: {
#         1: {"created_at": "2026-07-07 12:10:00"}, # Oldest Stopped Sandbox
#         2: {"created_at": "2026-07-07 12:20:00"},
#         3: {"created_at": "2026-07-07 12:30:00"}  # Active
#     }.get(p[0])

#     with patch("tools.sandbox_lifecycle.datetime") as mock_datetime:
#         mock_datetime.now.return_value = now_simulated
#         mock_datetime.strptime = datetime.strptime
#         enforce_sandbox_lifecycle_policy(MagicMock(), active_conversation_id=3)

#     # Assertions:
#     # c1 (oldest historical log) is completely stop-checked and forcefully purged with its volume layers
#     c1.stop.assert_called_once_with(timeout=2)
#     c1.remove.assert_called_once_with(v=True)

#     # c2 and c3 are protected inside the retention quota of 2
#     c2.remove.assert_not_called()
#     c3.remove.assert_not_called()

# this test is testing the lifecycle of docker containers
