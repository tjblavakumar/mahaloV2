"""Phase 3 tests — LLM mock data generation and API endpoints."""

import json
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import text

from backend.database import get_project_db, init_project_db
from backend.utils.generate_project_data import (
    _extract_json,
    _insert_data,
    generate_mock_data,
    wipe_project_data,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

MOCK_LLM_RESPONSE = {
    "users": [
        {"username": "alice_dev", "full_name": "Alice Developer", "email": "alice@health.com", "role": "developer"},
        {"username": "bob_dev", "full_name": "Bob Developer", "email": "bob@health.com", "role": "developer"},
        {"username": "carol_pm", "full_name": "Carol PM", "email": "carol@health.com", "role": "product_manager"},
        {"username": "dave_qa", "full_name": "Dave QA", "email": "dave@health.com", "role": "qa"},
        {"username": "eve_exec", "full_name": "Eve Executive", "email": "eve@health.com", "role": "executive"},
    ],
    "stories": [
        {"title": f"Story {i}", "description": f"Description {i}", "story_points": 5, "priority": "Medium", "status": "Backlog", "sprint": "Sprint 1", "assignee_index": i % 5, "reporter_index": (i + 1) % 5}
        for i in range(10)
    ],
    "bugs": [
        {"title": f"Bug {i}", "description": f"Bug desc {i}", "severity": "High", "status": "Open", "related_story_index": i, "assignee_index": 0, "reporter_index": 3}
        for i in range(5)
    ],
    "sprints": [
        {"sprint_name": "Sprint 1", "goal": "Foundation", "velocity": 20, "completed_stories": 3, "total_stories": 6, "status": "Completed"},
        {"sprint_name": "Sprint 2", "goal": "Features", "velocity": 25, "completed_stories": 2, "total_stories": 5, "status": "Active"},
    ],
    "incidents": [
        {"title": f"Incident {i}", "description": f"Incident desc {i}", "severity": "Medium", "status": "Active", "assigned_group": "Platform"}
        for i in range(5)
    ],
    "deployments": [
        {"feature_name": f"Feature {i}", "version": f"v1.{i}.0", "environment": "production", "status": "Deployed", "deployed_by": "engineering"}
        for i in range(10)
    ],
    "logs": [
        {"source": "api-service", "level": "INFO" if i < 60 else ("WARN" if i < 85 else "ERROR"), "message": f"Log message {i}", "service": "api-service"}
        for i in range(100)
    ],
}


@pytest.fixture
def project_info():
    return {
        "name": "HealthSync",
        "key": "HSYNC",
        "description_goal": "Build a healthcare scheduling platform",
        "description_users": "Doctors, patients, clinic administrators",
        "description_purpose": "Streamline appointment booking",
        "domain": "healthcare",
    }


# ---------------------------------------------------------------------------
# Unit tests: _extract_json
# ---------------------------------------------------------------------------


class TestExtractJson:
    def test_plain_json(self):
        result = _extract_json('{"key": "value"}')
        assert result == {"key": "value"}

    def test_json_with_markdown_fences(self):
        text = '```json\n{"key": "value"}\n```'
        result = _extract_json(text)
        assert result == {"key": "value"}

    def test_json_with_bare_fences(self):
        text = '```\n{"key": "value"}\n```'
        result = _extract_json(text)
        assert result == {"key": "value"}

    def test_invalid_json_raises(self):
        with pytest.raises(json.JSONDecodeError):
            _extract_json("not json at all")


# ---------------------------------------------------------------------------
# Unit tests: _build_prompt
# ---------------------------------------------------------------------------


class TestProjectContext:
    def test_contains_project_details(self, project_info):
        from backend.utils.generate_project_data import _PROJECT_CONTEXT
        context = _PROJECT_CONTEXT.format(
            name=project_info["name"],
            key=project_info["key"],
            domain=project_info["domain"],
            goal=project_info["description_goal"],
            users=project_info["description_users"],
            purpose=project_info["description_purpose"],
        )
        assert "HealthSync" in context
        assert "HSYNC" in context
        assert "healthcare" in context
        assert "scheduling" in context


# ---------------------------------------------------------------------------
# Unit tests: _insert_data
# ---------------------------------------------------------------------------


class TestInsertData:
    def test_inserts_correct_counts(self, isolated_test_env, project_info):
        init_project_db("healthsync")
        counts = _insert_data("healthsync", "HSYNC", MOCK_LLM_RESPONSE)

        assert counts["users"] == 5
        assert counts["stories"] == 10
        assert counts["bugs"] == 5
        assert counts["sprints"] == 2
        assert counts["incidents"] == 5
        assert counts["deployments"] == 10
        assert counts["logs"] == 100

    def test_story_keys_use_project_prefix(self, isolated_test_env):
        init_project_db("healthsync")
        _insert_data("healthsync", "HSYNC", MOCK_LLM_RESPONSE)

        gen = get_project_db("healthsync")
        db = next(gen)
        try:
            result = db.execute(text("SELECT story_key FROM jira_stories ORDER BY id")).fetchall()
            keys = [row[0] for row in result]
            assert all(k.startswith("HSYNC-") for k in keys)
            assert "HSYNC-1" in keys
            assert "HSYNC-10" in keys
        finally:
            try:
                next(gen)
            except StopIteration:
                pass

    def test_bug_keys_use_project_prefix(self, isolated_test_env):
        init_project_db("healthsync")
        _insert_data("healthsync", "HSYNC", MOCK_LLM_RESPONSE)

        gen = get_project_db("healthsync")
        db = next(gen)
        try:
            result = db.execute(text("SELECT bug_key FROM jira_bugs ORDER BY id")).fetchall()
            keys = [row[0] for row in result]
            assert all(k.startswith("HSYNC-BUG-") for k in keys)
        finally:
            try:
                next(gen)
            except StopIteration:
                pass

    def test_incident_ids_use_project_prefix(self, isolated_test_env):
        init_project_db("healthsync")
        _insert_data("healthsync", "HSYNC", MOCK_LLM_RESPONSE)

        gen = get_project_db("healthsync")
        db = next(gen)
        try:
            result = db.execute(text("SELECT incident_id FROM servicenow_incidents")).fetchall()
            ids = [row[0] for row in result]
            assert all(i.startswith("HSYNC-INC-") for i in ids)
        finally:
            try:
                next(gen)
            except StopIteration:
                pass

    def test_handles_empty_data_gracefully(self, isolated_test_env):
        init_project_db("healthsync")
        empty_data = {"users": [], "stories": [], "bugs": [], "sprints": [], "incidents": [], "deployments": [], "logs": []}
        counts = _insert_data("healthsync", "HSYNC", empty_data)
        assert all(v == 0 for v in counts.values())


# ---------------------------------------------------------------------------
# Unit tests: generate_mock_data (with mocked LLM)
# ---------------------------------------------------------------------------


class TestGenerateMockData:
    @pytest.mark.asyncio
    async def test_success_with_mocked_llm(self, isolated_test_env, project_info):
        """Chunked generation succeeds when LLM returns valid arrays each time."""
        init_project_db("healthsync")

        # The new generate_mock_data calls _call_llm multiple times.
        # Each call expects a JSON array back.
        call_count = [0]
        responses = [
            json.dumps(MOCK_LLM_RESPONSE["users"]),           # users (5)
            json.dumps(MOCK_LLM_RESPONSE["stories"][:5]),     # stories batch 1 (5)
            json.dumps(MOCK_LLM_RESPONSE["stories"][5:]),     # stories batch 2 (5)
            json.dumps(MOCK_LLM_RESPONSE["bugs"]),            # bugs (5)
            json.dumps(MOCK_LLM_RESPONSE["sprints"]),         # sprints (2)
            json.dumps(MOCK_LLM_RESPONSE["incidents"]),       # incidents (5)
            json.dumps(MOCK_LLM_RESPONSE["deployments"][:5]), # deployments (5)
            json.dumps(MOCK_LLM_RESPONSE["logs"][:5]),        # logs INFO (5)
            json.dumps(MOCK_LLM_RESPONSE["logs"][60:65]),     # logs WARN (5)
            json.dumps(MOCK_LLM_RESPONSE["logs"][85:90]),     # logs ERROR (5)
        ]

        async def mock_completion(*args, **kwargs):
            mock_resp = AsyncMock()
            mock_resp.choices = [AsyncMock()]
            idx = min(call_count[0], len(responses) - 1)
            mock_resp.choices[0].message.content = responses[idx]
            call_count[0] += 1
            return mock_resp

        with patch("backend.utils.generate_project_data.one_min_ai_completion", side_effect=mock_completion):
            with patch("backend.utils.generate_project_data.settings") as mock_settings:
                mock_settings.ONE_MIN_AI_API_KEY = "test-key"
                result = await generate_mock_data("healthsync", project_info)

        assert result["success"] is True
        assert result["counts"]["users"] == 5
        assert result["counts"]["stories"] == 10
        assert result["counts"]["bugs"] == 5
        assert result["counts"]["sprints"] == 2
        assert result["counts"]["incidents"] == 5
        assert result["counts"]["deployments"] == 5
        assert result["counts"]["logs"] == 15  # 3 batches of 5

    @pytest.mark.asyncio
    async def test_no_api_key_returns_error(self, isolated_test_env, project_info):
        with patch("backend.utils.generate_project_data.settings") as mock_settings:
            mock_settings.ONE_MIN_AI_API_KEY = ""
            result = await generate_mock_data("healthsync", project_info)

        assert result["success"] is False
        assert "not configured" in result["error"]

    @pytest.mark.asyncio
    async def test_llm_failure_all_calls(self, isolated_test_env, project_info):
        """If all LLM calls fail, returns error with no data."""
        init_project_db("healthsync")

        with patch("backend.utils.generate_project_data.one_min_ai_completion", new_callable=AsyncMock) as mock_llm:
            mock_llm.side_effect = Exception("Connection timeout")
            with patch("backend.utils.generate_project_data.settings") as mock_settings:
                mock_settings.ONE_MIN_AI_API_KEY = "test-key"
                result = await generate_mock_data("healthsync", project_info)

        assert result["success"] is False
        assert "Users" in result["error"]

    @pytest.mark.asyncio
    async def test_partial_failure_still_saves_data(self, isolated_test_env, project_info):
        """If some batches fail, partial data is still committed."""
        init_project_db("healthsync")

        call_count = [0]

        async def mock_completion(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                # Users call succeeds
                mock_resp = AsyncMock()
                mock_resp.choices = [AsyncMock()]
                mock_resp.choices[0].message.content = json.dumps(MOCK_LLM_RESPONSE["users"])
                return mock_resp
            # All other calls fail
            raise Exception("Timeout")

        with patch("backend.utils.generate_project_data.one_min_ai_completion", side_effect=mock_completion):
            with patch("backend.utils.generate_project_data.settings") as mock_settings:
                mock_settings.ONE_MIN_AI_API_KEY = "test-key"
                result = await generate_mock_data("healthsync", project_info)

        # Partial success — users were saved
        assert result["success"] is True
        assert result["counts"]["users"] == 5
        assert result["counts"]["stories"] == 0
        assert "warnings" in result


# ---------------------------------------------------------------------------
# Unit tests: wipe_project_data
# ---------------------------------------------------------------------------


class TestWipeProjectData:
    def test_clears_all_tables(self, isolated_test_env):
        init_project_db("healthsync")
        _insert_data("healthsync", "HSYNC", MOCK_LLM_RESPONSE)

        # Verify data exists
        gen = get_project_db("healthsync")
        db = next(gen)
        try:
            count = db.execute(text("SELECT COUNT(*) FROM jira_stories")).scalar()
            assert count == 10
        finally:
            try:
                next(gen)
            except StopIteration:
                pass

        # Wipe
        wipe_project_data("healthsync")

        # Verify empty
        gen2 = get_project_db("healthsync")
        db2 = next(gen2)
        try:
            for table in ["jira_users", "jira_stories", "jira_bugs", "jira_sprints",
                          "servicenow_incidents", "servicenow_deployments", "splunk_logs"]:
                count = db2.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
                assert count == 0, f"Table {table} not empty after wipe"
        finally:
            try:
                next(gen2)
            except StopIteration:
                pass


# ---------------------------------------------------------------------------
# API endpoint tests
# ---------------------------------------------------------------------------


class TestGenerateDataAPI:
    def _mock_llm_chunked(self):
        """Create a mock that returns valid arrays for each chunked LLM call."""
        responses = [
            json.dumps(MOCK_LLM_RESPONSE["users"]),
            json.dumps(MOCK_LLM_RESPONSE["stories"][:5]),
            json.dumps(MOCK_LLM_RESPONSE["stories"][5:]),
            json.dumps(MOCK_LLM_RESPONSE["bugs"]),
            json.dumps(MOCK_LLM_RESPONSE["sprints"]),
            json.dumps(MOCK_LLM_RESPONSE["incidents"]),
            json.dumps(MOCK_LLM_RESPONSE["deployments"][:5]),
            json.dumps(MOCK_LLM_RESPONSE["logs"][:5]),
            json.dumps(MOCK_LLM_RESPONSE["logs"][:5]),
            json.dumps(MOCK_LLM_RESPONSE["logs"][:5]),
        ]
        call_count = [0]

        async def mock_completion(*args, **kwargs):
            mock_resp = AsyncMock()
            mock_resp.choices = [AsyncMock()]
            idx = min(call_count[0], len(responses) - 1)
            mock_resp.choices[0].message.content = responses[idx]
            call_count[0] += 1
            return mock_resp

        return mock_completion

    def test_generate_data_project_not_found(self, api_client):
        resp = api_client.post("/api/projects/nonexistent/generate-data")
        assert resp.status_code == 404

    def test_generate_data_real_mode_rejected(self, api_client, sample_project_payload):
        sample_project_payload["connection_mode"] = "real"
        sample_project_payload["jira_url"] = "https://jira.example.com"
        api_client.post("/api/projects", json=sample_project_payload)

        resp = api_client.post("/api/projects/healthsync/generate-data")
        assert resp.status_code == 400
        assert "local" in resp.json()["detail"].lower()

    def test_generate_data_success_mocked(self, api_client, sample_project_payload):
        api_client.post("/api/projects", json=sample_project_payload)

        with patch("backend.utils.generate_project_data.one_min_ai_completion", side_effect=self._mock_llm_chunked()):
            with patch("backend.utils.generate_project_data.settings") as mock_settings:
                mock_settings.ONE_MIN_AI_API_KEY = "test-key"
                resp = api_client.post("/api/projects/healthsync/generate-data")

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["counts"]["users"] == 5
        assert data["counts"]["stories"] == 10

    def test_generate_data_sets_flag(self, api_client, sample_project_payload):
        api_client.post("/api/projects", json=sample_project_payload)

        with patch("backend.utils.generate_project_data.one_min_ai_completion", side_effect=self._mock_llm_chunked()):
            with patch("backend.utils.generate_project_data.settings") as mock_settings:
                mock_settings.ONE_MIN_AI_API_KEY = "test-key"
                api_client.post("/api/projects/healthsync/generate-data")

        # Check data_generated flag
        resp = api_client.get("/api/projects/healthsync")
        assert resp.json()["data_generated"] is True


class TestResetDataAPI:
    def test_reset_data_project_not_found(self, api_client):
        resp = api_client.post("/api/projects/nonexistent/reset-data")
        assert resp.status_code == 404

    def test_reset_data_clears_and_resets_flag(self, api_client, sample_project_payload):
        api_client.post("/api/projects", json=sample_project_payload)

        # Insert some data using _insert_data (direct, no LLM)
        _insert_data("healthsync", "HSYNC", MOCK_LLM_RESPONSE)

        # Reset
        resp = api_client.post("/api/projects/healthsync/reset-data")
        assert resp.status_code == 200
        assert "reset" in resp.json()["message"].lower()

        # Check flag is reset
        resp = api_client.get("/api/projects/healthsync")
        assert resp.json()["data_generated"] is False
