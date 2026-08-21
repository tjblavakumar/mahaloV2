"""Phase 2 tests — project-aware backend services, MCP tools, and agents."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient
from sqlalchemy import text

from backend.database import get_project_db, init_project_db


# ---------------------------------------------------------------------------
# Task 4: Mock API routes accept X-Project-ID header
# ---------------------------------------------------------------------------


class TestProjectAwareMockAPIs:
    """Test that mock APIs route to correct project DB based on X-Project-ID header."""

    def _seed_jira_data(self, project_id, isolated_test_env):
        """Insert a JIRA user and story into a project's DB."""
        init_project_db(project_id)
        gen = get_project_db(project_id)
        db = next(gen)
        try:
            db.execute(text(
                "INSERT INTO jira_users (id, username, full_name, role) VALUES (1, 'alice', 'Alice Dev', 'developer')"
            ))
            db.execute(text(
                "INSERT INTO jira_stories (id, story_key, title, status, assignee_id, story_points, priority, sprint) "
                "VALUES (1, 'TEST-1', 'Test Story', 'Backlog', 1, 5, 'High', 'Sprint 1')"
            ))
            db.commit()
        finally:
            try:
                next(gen)
            except StopIteration:
                pass

    def _seed_servicenow_data(self, project_id, isolated_test_env):
        """Insert a ServiceNow incident into a project's DB."""
        init_project_db(project_id)
        gen = get_project_db(project_id)
        db = next(gen)
        try:
            db.execute(text(
                "INSERT INTO servicenow_incidents (id, incident_id, title, severity, status, assigned_group) "
                "VALUES (1, 'INC001', 'Test Incident', 'High', 'Active', 'Platform')"
            ))
            db.execute(text(
                "INSERT INTO servicenow_deployments (id, deployment_id, feature_name, version, environment, status, deployed_by) "
                "VALUES (1, 'DEP001', 'Feature X', 'v1.0', 'production', 'Deployed', 'engineer')"
            ))
            db.commit()
        finally:
            try:
                next(gen)
            except StopIteration:
                pass

    def _seed_splunk_data(self, project_id, isolated_test_env):
        """Insert Splunk logs into a project's DB."""
        init_project_db(project_id)
        gen = get_project_db(project_id)
        db = next(gen)
        try:
            db.execute(text(
                "INSERT INTO splunk_logs (id, source, level, message, service) "
                "VALUES (1, 'api-service', 'ERROR', 'Connection timeout', 'api-service')"
            ))
            db.commit()
        finally:
            try:
                next(gen)
            except StopIteration:
                pass

    def test_jira_routes_with_project_header(self, isolated_test_env):
        """JIRA routes return data from the correct project DB."""
        from backend.jira.app import app

        self._seed_jira_data("project-a", isolated_test_env)
        init_project_db("project-b")  # empty

        client = TestClient(app)

        # Project A has data
        resp = client.get("/api/jira/stories", headers={"X-Project-ID": "project-a"})
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) == 1
        assert items[0]["story_key"] == "TEST-1"

        # Project B is empty
        resp = client.get("/api/jira/stories", headers={"X-Project-ID": "project-b"})
        assert resp.status_code == 200
        assert resp.json()["items"] == []

    def test_servicenow_routes_with_project_header(self, isolated_test_env):
        """ServiceNow routes return data from the correct project DB."""
        from backend.servicenow.app import app

        self._seed_servicenow_data("project-a", isolated_test_env)
        init_project_db("project-b")

        client = TestClient(app)

        # Project A has incident
        resp = client.get("/api/servicenow/incidents", headers={"X-Project-ID": "project-a"})
        assert resp.status_code == 200
        assert len(resp.json()["items"]) == 1

        # Project B is empty
        resp = client.get("/api/servicenow/incidents", headers={"X-Project-ID": "project-b"})
        assert resp.status_code == 200
        assert resp.json()["items"] == []

        # Deployments
        resp = client.get("/api/servicenow/deployments", headers={"X-Project-ID": "project-a"})
        assert resp.status_code == 200
        assert len(resp.json()["items"]) == 1

    def test_splunk_routes_with_project_header(self, isolated_test_env):
        """Splunk routes return data from the correct project DB."""
        from backend.splunk.app import app

        self._seed_splunk_data("project-a", isolated_test_env)
        init_project_db("project-b")

        client = TestClient(app)

        # Project A has logs
        resp = client.get("/api/splunk/logs", headers={"X-Project-ID": "project-a"})
        assert resp.status_code == 200
        assert len(resp.json()["items"]) == 1

        # Project B is empty
        resp = client.get("/api/splunk/logs", headers={"X-Project-ID": "project-b"})
        assert resp.status_code == 200
        assert resp.json()["items"] == []

    def test_jira_routes_without_header_backward_compat(self, isolated_test_env):
        """Without X-Project-ID header, routes fall back to legacy DB without crashing."""
        from backend.jira.app import app

        client = TestClient(app)
        # Should not crash — uses legacy DB
        resp = client.get("/api/jira/stories")
        assert resp.status_code == 200
        # Response has "items" key regardless of content
        assert "items" in resp.json()

    def test_data_isolation_between_projects(self, isolated_test_env):
        """Data written to one project is not visible from another."""
        from backend.jira.app import app

        init_project_db("project-a")
        init_project_db("project-b")

        client = TestClient(app)

        # Create a story in project A
        resp = client.post(
            "/api/jira/stories",
            json={"title": "Story in A", "description": "Only in A"},
            headers={"X-Project-ID": "project-a"},
        )
        assert resp.status_code == 200

        # Verify it's in project A
        resp = client.get("/api/jira/stories", headers={"X-Project-ID": "project-a"})
        assert len(resp.json()["items"]) == 1

        # Verify project B is still empty
        resp = client.get("/api/jira/stories", headers={"X-Project-ID": "project-b"})
        assert resp.json()["items"] == []


# ---------------------------------------------------------------------------
# Task 5: MCP tools forward X-Project-ID header
# ---------------------------------------------------------------------------


class TestMCPToolsProjectHeader:
    """Test that MCP tool classes include X-Project-ID header in HTTP requests."""

    @pytest.mark.asyncio
    async def test_jira_tools_send_header(self):
        """JiraMCPTools sends X-Project-ID header when project_id in arguments."""
        from mcp_servers.jira_mcp.tools import JiraMCPTools

        tools = JiraMCPTools()

        with patch("httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.raise_for_status = MagicMock()
            mock_response.json.return_value = {"items": []}
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            MockClient.return_value = mock_client

            await tools.search_stories_handler({"query": "test", "project_id": "my-project"})

            mock_client.get.assert_called_once()
            call_kwargs = mock_client.get.call_args
            assert call_kwargs.kwargs.get("headers") == {"X-Project-ID": "my-project"} or \
                   call_kwargs[1].get("headers") == {"X-Project-ID": "my-project"}

    @pytest.mark.asyncio
    async def test_jira_tools_no_header_when_no_project(self):
        """JiraMCPTools sends empty headers when project_id not in arguments."""
        from mcp_servers.jira_mcp.tools import JiraMCPTools

        tools = JiraMCPTools()

        with patch("httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.raise_for_status = MagicMock()
            mock_response.json.return_value = {"items": []}
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            MockClient.return_value = mock_client

            await tools.search_stories_handler({"query": "test"})

            mock_client.get.assert_called_once()
            call_kwargs = mock_client.get.call_args
            headers = call_kwargs.kwargs.get("headers") or call_kwargs[1].get("headers", {})
            assert headers == {}

    @pytest.mark.asyncio
    async def test_servicenow_tools_send_header(self):
        """ServiceNowMCPTools sends X-Project-ID header."""
        from mcp_servers.servicenow_mcp.tools import ServiceNowMCPTools

        tools = ServiceNowMCPTools()

        with patch("httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.raise_for_status = MagicMock()
            mock_response.json.return_value = {"items": []}
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            MockClient.return_value = mock_client

            await tools.list_incidents_handler({"query": "", "project_id": "health-app"})

            mock_client.get.assert_called_once()
            call_kwargs = mock_client.get.call_args
            headers = call_kwargs.kwargs.get("headers") or call_kwargs[1].get("headers", {})
            assert headers == {"X-Project-ID": "health-app"}

    @pytest.mark.asyncio
    async def test_splunk_tools_send_header(self):
        """SplunkMCPTools sends X-Project-ID header."""
        from mcp_servers.splunk_mcp.tools import SplunkMCPTools

        tools = SplunkMCPTools()

        with patch("httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.raise_for_status = MagicMock()
            mock_response.json.return_value = {"items": []}
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            MockClient.return_value = mock_client

            await tools.search_logs_handler({"query": "error", "project_id": "fintech"})

            mock_client.get.assert_called_once()
            call_kwargs = mock_client.get.call_args
            headers = call_kwargs.kwargs.get("headers") or call_kwargs[1].get("headers", {})
            assert headers == {"X-Project-ID": "fintech"}


# ---------------------------------------------------------------------------
# Task 6: Agents pass project_id to tools
# ---------------------------------------------------------------------------


class TestAgentsPassProjectId:
    """Test that agents pass project_id through to their MCP tool calls."""

    @pytest.mark.asyncio
    async def test_jira_agent_passes_project_id(self):
        """JiraAgent.retrieve_context passes project_id to tool handlers."""
        from agents.jira_agent import JiraAgent

        mock_tools = AsyncMock()
        mock_tools.search_stories_handler = AsyncMock(return_value={
            "success": True, "data": {"items": []}
        })
        agent = JiraAgent(tools=mock_tools)

        await agent.retrieve_context("show stories", project_id="my-project")

        mock_tools.search_stories_handler.assert_called_once()
        args = mock_tools.search_stories_handler.call_args[0][0]
        assert args["project_id"] == "my-project"

    @pytest.mark.asyncio
    async def test_jira_agent_no_project_id(self):
        """JiraAgent.retrieve_context works without project_id (backward compat)."""
        from agents.jira_agent import JiraAgent

        mock_tools = AsyncMock()
        mock_tools.search_stories_handler = AsyncMock(return_value={
            "success": True, "data": {"items": []}
        })
        agent = JiraAgent(tools=mock_tools)

        await agent.retrieve_context("show stories")

        args = mock_tools.search_stories_handler.call_args[0][0]
        assert args["project_id"] is None

    @pytest.mark.asyncio
    async def test_servicenow_agent_passes_project_id(self):
        """ServiceNowAgent.retrieve_context passes project_id."""
        from agents.servicenow_agent import ServiceNowAgent

        mock_tools = AsyncMock()
        mock_tools.list_incidents_handler = AsyncMock(return_value={
            "success": True, "data": {"items": []}
        })
        agent = ServiceNowAgent(tools=mock_tools)

        await agent.retrieve_context("show incidents", project_id="health-app")

        mock_tools.list_incidents_handler.assert_called_once()
        args = mock_tools.list_incidents_handler.call_args[0][0]
        assert args["project_id"] == "health-app"

    @pytest.mark.asyncio
    async def test_splunk_agent_passes_project_id(self):
        """SplunkAgent.retrieve_context passes project_id."""
        from agents.splunk_agent import SplunkAgent

        mock_tools = AsyncMock()
        mock_tools.search_logs_handler = AsyncMock(return_value={
            "success": True, "data": {"items": []}
        })
        agent = SplunkAgent(tools=mock_tools)

        await agent.retrieve_context("show errors", project_id="fintech")

        mock_tools.search_logs_handler.assert_called()
        # At least one call should have project_id
        for call in mock_tools.search_logs_handler.call_args_list:
            args = call[0][0]
            assert args["project_id"] == "fintech"


# ---------------------------------------------------------------------------
# Task 6: Chat API passes project_id to orchestrator
# ---------------------------------------------------------------------------


class TestChatAPIProjectId:
    """Test that the chat API accepts and forwards project_id."""

    def test_chat_message_accepts_project_id(self, api_client, isolated_test_env):
        """POST /api/chat/message accepts project_id field."""
        # This will fail to get real data (no mock APIs running) but should not 422
        response = api_client.post("/api/chat/message", json={
            "persona": "Executive",
            "message": "hello",
            "project_id": "test-project",
        })
        # Should not be 422 (validation error)
        assert response.status_code != 422

    def test_chat_message_works_without_project_id(self, api_client, isolated_test_env):
        """POST /api/chat/message still works without project_id (backward compat)."""
        response = api_client.post("/api/chat/message", json={
            "persona": "Executive",
            "message": "hello",
        })
        assert response.status_code != 422
