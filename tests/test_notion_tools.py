# tests/test_notion_tools.py
"""
HK's Rigorous Test Suite for Notion Tools
Covers:
  - 100% Happy Path execution for all 7 Agent Tools
  - Helper logic: URL cleaning, DB ID fetching, Name->ID resolution
  - Edge cases: Bad Enums, Duplicate Projects, Missing Keys, Notion API Failures, Network Exceptions
"""

import pytest
from unittest.mock import patch, MagicMock
import requests

from tools.notion_tools import (
    _clean_id,
    _get_db_id,
    _notion_api_request,
    _get_project_id,
    list_active_projects,
    create_project,
    complete_project,
    log_project_reasoning,
    log_knowledge,
    brain_dump,
    log_idea,
)

# Mock DB configuration dictionary
MOCK_DBS = {
    "db_projects": "d81215fcbfa0495b90004be9fee17cea",
    "db_reasoning": "957921fe979f4d9f8ef5c377acfa3516",
    "db_knowledge": "e942ad48a11e4c83b1fe1cd491049c4d",
    "db_brain_dumps": "9bd6325fcdc340aea98bffcf09a057eb",
    "db_ideas": "352415e91119406294103bd0ae7cf6b8",
}


@pytest.fixture(autouse=True)
def mock_config_manager():
    """Autouse fixture to mock config_manager for all tests."""
    with patch("tools.notion_tools.config_manager") as mock_cm:
        mock_cm.get_tool_api_key.return_value = "ntn_secret_test_key_999"
        mock_cm.get_notion_dbs.return_value = MOCK_DBS
        yield mock_cm


# =====================================================================
# SECTION 1: HK's RIGOROUS HELPER & ID CLEANING TESTS
# =====================================================================

class TestIDCleaningAndConfigHelpers:
    
    def test_clean_id_raw_32_chars(self):
        """Clean 32-char hex string passes through unchanged."""
        raw = "d81215fcbfa0495b90004be9fee17cea"
        assert _clean_id(raw) == "d81215fcbfa0495b90004be9fee17cea"

    def test_clean_id_uuid_with_hyphens(self):
        """UUID with hyphens gets stripped down to 32 hex chars."""
        raw = "d81215fc-bfa0-495b-9000-4be9fee17cea"
        assert _clean_id(raw) == "d81215fcbfa0495b90004be9fee17cea"

    def test_clean_id_full_notion_url_with_query_params(self):
        """Full copy-pasted Notion URL with query params is perfectly parsed."""
        raw = "https://app.notion.com/p/d81215fcbfa0495b90004be9fee17cea?v=79450c5c9dfe4548a5a200a211c8715a&source=copy_link"
        assert _clean_id(raw) == "d81215fcbfa0495b90004be9fee17cea"

    def test_clean_id_empty_and_none(self):
        """Handles empty or None strings safely."""
        assert _clean_id("") == ""
        assert _clean_id(None) == ""

    def test_get_db_id_valid_key(self):
        """Retrieves and cleans DB ID from config."""
        assert _get_db_id("db_projects") == "d81215fcbfa0495b90004be9fee17cea"

    def test_get_db_id_missing_key(self, mock_config_manager):
        """Raises ValueError if DB key is missing in config."""
        mock_config_manager.get_notion_dbs.return_value = {}
        with pytest.raises(ValueError, match="Missing Notion Database ID"):
            _get_db_id("db_projects")


# =====================================================================
# SECTION 2: HK's RIGOROUS API REQUEST HELPER TESTS
# =====================================================================

class TestNotionAPIRequestHelper:

    @patch("tools.notion_tools.requests.post")
    def test_api_request_post_success(self, mock_post):
        """200 OK POST request returns success status and json data."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"id": "page-123", "object": "page"}
        mock_post.return_value = mock_resp

        res = _notion_api_request("pages", method="POST", payload={"parent": "test"})
        assert res["status"] == "success"
        assert res["data"]["id"] == "page-123"

    @patch("tools.notion_tools.requests.patch")
    def test_api_request_patch_success(self, mock_patch):
        """200 OK PATCH request returns success status."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"id": "page-123"}
        mock_patch.return_value = mock_resp

        res = _notion_api_request("pages/page-123", method="PATCH", payload={"properties": {}})
        assert res["status"] == "success"

    def test_api_request_missing_api_key(self, mock_config_manager):
        """Fails gracefully if API key is not configured."""
        mock_config_manager.get_tool_api_key.return_value = None
        res = _notion_api_request("pages")
        assert res["status"] == "error"
        assert "Notion API key is missing" in res["message"]

    @patch("tools.notion_tools.requests.post")
    def test_api_request_http_error_code(self, mock_post):
        """Captures Notion 400/401/404 errors gracefully."""
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_resp.json.return_value = {"message": "Could not find database with id test-id"}
        mock_post.return_value = mock_resp

        res = _notion_api_request("databases/test-id/query")
        assert res["status"] == "error"
        assert "Could not find database" in res["message"]

    @patch("tools.notion_tools.requests.post")
    def test_api_request_network_exception(self, mock_post):
        """Captures low-level network timeout / connection exceptions."""
        mock_post.side_effect = requests.exceptions.ConnectionError("Network timeout")
        res = _notion_api_request("pages")
        assert res["status"] == "error"
        assert "Request failed: Network timeout" in res["message"]

    def test_api_request_unsupported_method(self):
        """Rejects unsupported HTTP methods like DELETE or PUT."""
        res = _notion_api_request("pages", method="DELETE")
        assert res["status"] == "error"
        assert "Unsupported method: DELETE" in res["message"]


# =====================================================================
# SECTION 3: HK's RIGOROUS NAME -> ID RESOLVER TESTS
# =====================================================================

class TestProjectIDResolver:

    @patch("tools.notion_tools._notion_api_request")
    def test_get_project_id_exact_single_match(self, mock_api_req):
        """Resolves project name to page ID when exactly 1 match exists."""
        mock_api_req.return_value = {
            "status": "success",
            "data": {"results": [{"id": "page-uuid-1111"}]}
        }
        res = _get_project_id("Life OS Agent")
        assert res == "page-uuid-1111"

    @patch("tools.notion_tools._notion_api_request")
    def test_get_project_id_zero_matches(self, mock_api_req):
        """Returns clean error if project does not exist."""
        mock_api_req.return_value = {
            "status": "success",
            "data": {"results": []}
        }
        res = _get_project_id("Non Existent Project")
        assert res.startswith("Error:")
        assert "No project found with the exact name" in res

    @patch("tools.notion_tools._notion_api_request")
    def test_get_project_id_duplicate_matches(self, mock_api_req):
        """Returns error if multiple projects match the same name (ambiguity check)."""
        mock_api_req.return_value = {
            "status": "success",
            "data": {"results": [{"id": "p1"}, {"id": "p2"}]}
        }
        res = _get_project_id("Ambiguous Project")
        assert res.startswith("Error:")
        assert "Multiple projects found" in res

    @patch("tools.notion_tools.config_manager")
    def test_get_project_id_missing_config_db(self, mock_cm):
        """Handles missing database configuration gracefully."""
        mock_cm.get_notion_dbs.return_value = {}
        res = _get_project_id("Life OS Agent")
        assert res.startswith("Error:")
        assert "Missing Notion Database ID" in res


# =====================================================================
# SECTION 4: ALL 7 AGENT TOOLS — HAPPY PATHS & EDGE CASES
# =====================================================================

class TestListActiveProjectsTool:

    @patch("tools.notion_tools._notion_api_request")
    def test_list_active_projects_happy_path(self, mock_api_req):
        """Happy Path: Retrieves list of active projects."""
        mock_api_req.return_value = {
            "status": "success",
            "data": {
                "results": [
                    {"properties": {"Name": {"title": [{"plain_text": "Life OS Agent"}]}}},
                    {"properties": {"Name": {"title": [{"plain_text": "CLI Refactor"}]}}},
                ]
            }
        }
        res = list_active_projects()
        assert "Active Projects: Life OS Agent, CLI Refactor" in res

    @patch("tools.notion_tools._notion_api_request")
    def test_list_active_projects_empty(self, mock_api_req):
        """Handles empty database response."""
        mock_api_req.return_value = {"status": "success", "data": {"results": []}}
        assert list_active_projects() == "No active projects found."


class TestCreateProjectTool:

    @patch("tools.notion_tools._notion_api_request")
    def test_create_project_happy_path(self, mock_api_req):
        """Happy Path: Creates project with valid fields and status."""
        mock_api_req.return_value = {"status": "success"}
        res = create_project("New App", "Description", "Core reasoning", "Active")
        assert res == "Success: Project created."

        # Verify correct Notion properties schema
        payload = mock_api_req.call_args[1]["payload"]
        assert payload["properties"]["Name"]["title"][0]["text"]["content"] == "New App"
        assert payload["properties"]["Status"]["select"]["name"] == "Active"

    def test_create_project_invalid_status_enum(self):
        """Edge Case: Rejects invalid Status enum value before calling API."""
        res = create_project("New App", "Desc", "Reasoning", "In_Progress")
        assert res.startswith("Error:")
        assert "Status must be 'Active', 'Paused', or 'Completed'" in res


class TestCompleteProjectTool:

    @patch("tools.notion_tools._get_project_id")
    @patch("tools.notion_tools._notion_api_request")
    def test_complete_project_happy_path(self, mock_api_req, mock_get_id):
        """Happy Path: Marks project Completed and stamps today's End Date."""
        mock_get_id.return_value = "project-uuid-999"
        mock_api_req.return_value = {"status": "success"}

        res = complete_project("Life OS Agent")
        assert res == "Success: Project 'Life OS Agent' marked as completed."

        # Verify PATCH payload contains Status='Completed' and End Date
        payload = mock_api_req.call_args[1]["payload"]
        assert payload["properties"]["Status"]["select"]["name"] == "Completed"
        assert "End Date" in payload["properties"]

    @patch("tools.notion_tools._get_project_id")
    def test_complete_project_not_found(self, mock_get_id):
        """Fails gracefully if project is not found."""
        mock_get_id.return_value = "Error: No project found with the exact name 'Ghost'."
        res = complete_project("Ghost")
        assert res.startswith("Error:")


class TestLogProjectReasoningTool:

    @patch("tools.notion_tools._get_project_id")
    @patch("tools.notion_tools._notion_api_request")
    def test_log_project_reasoning_happy_path(self, mock_api_req, mock_get_id):
        """Happy Path: Resolves project ID and logs reasoning."""
        mock_get_id.return_value = "project-uuid-999"
        mock_api_req.return_value = {"status": "success"}

        res = log_project_reasoning("Life OS Agent", "Replaced 9 tables with 5", "notion_tools.py", "Architecture")
        assert res == "Success: Reasoning logged."

        # Verify payload contains relation to project-uuid-999
        payload = mock_api_req.call_args[1]["payload"]
        assert payload["properties"]["Type"]["select"]["name"] == "Architecture"
        assert payload["properties"]["Project"]["relation"][0]["id"] == "project-uuid-999"

    def test_log_project_reasoning_invalid_type_enum(self):
        """Edge Case: Rejects invalid Type enum value."""
        res = log_project_reasoning("Life OS Agent", "Thought", "Context", "RandomType")
        assert res.startswith("Error:")
        assert "Type must be 'Architecture', 'Bug Fix', or 'Feature'" in res


class TestLogKnowledgeTool:

    @patch("tools.notion_tools._get_project_id")
    @patch("tools.notion_tools._notion_api_request")
    def test_log_knowledge_happy_path(self, mock_api_req, mock_get_id):
        """Happy Path: Logs skill/knowledge tied to project ID."""
        mock_get_id.return_value = "project-uuid-999"
        mock_api_req.return_value = {"status": "success"}

        res = log_knowledge("Life OS Agent", "Notion API Data Source IDs", "Master", "Fixed 404 errors")
        assert res == "Success: Knowledge logged."

        payload = mock_api_req.call_args[1]["payload"]
        assert payload["properties"]["Proficiency"]["select"]["name"] == "Master"
        assert payload["properties"]["Project"]["relation"][0]["id"] == "project-uuid-999"

    def test_log_knowledge_invalid_proficiency_enum(self):
        """Edge Case: Rejects invalid Proficiency enum value."""
        res = log_knowledge("Life OS Agent", "Topic", "Expert", "Reasoning")
        assert res.startswith("Error:")
        assert "Proficiency must be 'Learning', 'Medium', or 'Master'" in res


class TestIsolatedTools:

    @patch("tools.notion_tools._notion_api_request")
    def test_brain_dump_happy_path(self, mock_api_req):
        """Happy Path: Captures unstructured thought without relations."""
        mock_api_req.return_value = {"status": "success"}
        res = brain_dump("Feeling great that HK's testing suite is complete!")
        assert res == "Success: Brain dump saved."

        payload = mock_api_req.call_args[1]["payload"]
        assert payload["properties"]["Raw Text"]["title"][0]["text"]["content"] == "Feeling great that HK's testing suite is complete!"

    @patch("tools.notion_tools._notion_api_request")
    def test_log_idea_happy_path(self, mock_api_req):
        """Happy Path: Captures standalone idea and reasoning."""
        mock_api_req.return_value = {"status": "success"}
        res = log_idea("Build a CLI shortcut for fast dumping", "Reduces friction")
        assert res == "Success: Idea saved."

        payload = mock_api_req.call_args[1]["payload"]
        assert payload["properties"]["Idea"]["title"][0]["text"]["content"] == "Build a CLI shortcut for fast dumping"
        assert payload["properties"]["Reasoning"]["rich_text"][0]["text"]["content"] == "Reduces friction"