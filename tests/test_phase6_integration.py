"""Phase 6 tests — project-scoped conversations and integration."""

import pytest

from agents.context_manager import ContextManager


# ---------------------------------------------------------------------------
# Task 14: Project-scoped conversation history
# ---------------------------------------------------------------------------


class TestContextManagerProjectScoped:
    def test_messages_isolated_by_project(self):
        """Messages added to project A are not visible in project B."""
        cm = ContextManager()
        cm.add_message("user", "Hello from A", project_id="project-a")
        cm.add_message("user", "Hello from B", project_id="project-b")

        history_a = cm.get_conversation_history(project_id="project-a")
        history_b = cm.get_conversation_history(project_id="project-b")

        assert len(history_a) == 1
        assert history_a[0]["content"] == "Hello from A"
        assert len(history_b) == 1
        assert history_b[0]["content"] == "Hello from B"

    def test_no_project_uses_global(self):
        """Messages without project_id go to global history."""
        cm = ContextManager()
        cm.add_message("user", "Global message")
        cm.add_message("user", "Project message", project_id="proj")

        global_history = cm.get_conversation_history()
        proj_history = cm.get_conversation_history(project_id="proj")

        assert len(global_history) == 1
        assert global_history[0]["content"] == "Global message"
        assert len(proj_history) == 1
        assert proj_history[0]["content"] == "Project message"

    def test_clear_specific_project(self):
        """Clearing project A does not affect project B."""
        cm = ContextManager()
        cm.add_message("user", "A msg", project_id="a")
        cm.add_message("user", "B msg", project_id="b")

        cm.clear(project_id="a")

        assert len(cm.get_conversation_history(project_id="a")) == 0
        assert len(cm.get_conversation_history(project_id="b")) == 1

    def test_clear_all(self):
        """Clearing without project_id wipes everything."""
        cm = ContextManager()
        cm.add_message("user", "A msg", project_id="a")
        cm.add_message("user", "B msg", project_id="b")
        cm.add_message("user", "Global msg")

        cm.clear()

        assert len(cm.get_conversation_history(project_id="a")) == 0
        assert len(cm.get_conversation_history(project_id="b")) == 0
        assert len(cm.get_conversation_history()) == 0

    def test_last_n_limit(self):
        """last_n parameter limits results per project."""
        cm = ContextManager()
        for i in range(15):
            cm.add_message("user", f"msg {i}", project_id="proj")

        history = cm.get_conversation_history(last_n=5, project_id="proj")
        assert len(history) == 5
        assert history[0]["content"] == "msg 10"
        assert history[-1]["content"] == "msg 14"

    def test_metadata_preserved(self):
        """Metadata is stored and retrievable."""
        cm = ContextManager()
        cm.add_message("user", "test", metadata={"conv": "123"}, project_id="proj")

        msg = cm.get_conversation_history(project_id="proj")[0]
        assert msg["metadata"] == {"conv": "123"}

    def test_max_history_per_project(self):
        """Each project respects the max_history limit."""
        cm = ContextManager(max_history=5)
        for i in range(10):
            cm.add_message("user", f"msg {i}", project_id="proj")

        history = cm.get_conversation_history(last_n=None, project_id="proj")
        assert len(history) == 5
        assert history[0]["content"] == "msg 5"  # oldest retained


# ---------------------------------------------------------------------------
# Task 14: Chat route passes project_id to context_manager
# ---------------------------------------------------------------------------


class TestChatRouteProjectScoped:
    def test_message_stored_under_project(self, api_client, isolated_test_env):
        """Sending a message with project_id stores it under that project's history."""
        from agents.context_manager import context_manager

        context_manager.clear()

        api_client.post("/api/chat/message", json={
            "persona": "Executive",
            "message": "test message",
            "project_id": "test-proj",
        })

        # Check history for that project
        proj_history = context_manager.get_conversation_history(project_id="test-proj")
        # Should have at least the user message and the assistant response
        roles = [m["role"] for m in proj_history]
        assert "user" in roles
        assert "assistant" in roles

    def test_messages_not_shared_across_projects(self, api_client, isolated_test_env):
        """Messages from project A are not in project B's history."""
        from agents.context_manager import context_manager

        context_manager.clear()

        api_client.post("/api/chat/message", json={
            "persona": "Developer",
            "message": "hello from A",
            "project_id": "proj-a",
        })

        history_b = context_manager.get_conversation_history(project_id="proj-b")
        assert len(history_b) == 0

    def test_history_endpoint_filters_by_project(self, api_client, isolated_test_env):
        """GET /api/chat/history/{id}?project_id=X filters correctly."""
        from agents.context_manager import context_manager

        context_manager.clear()

        # Send a message to get a conversation_id
        resp = api_client.post("/api/chat/message", json={
            "persona": "Executive",
            "message": "hello",
            "project_id": "proj-x",
            "conversation_id": "conv-test-123",
        })
        assert resp.status_code == 200

        # Fetch history for that conversation + project
        resp = api_client.get("/api/chat/history/conv-test-123?project_id=proj-x")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] >= 1

        # Different project should have nothing
        resp = api_client.get("/api/chat/history/conv-test-123?project_id=other-proj")
        assert resp.status_code == 200
        assert resp.json()["count"] == 0
