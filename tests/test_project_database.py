"""Tests for per-project database resolution in backend/database.py."""

from pathlib import Path

import pytest
from sqlalchemy import inspect, text

from backend.database import (
    get_project_db,
    get_project_engine,
    init_project_db,
    remove_project_engine,
)


class TestGetProjectEngine:
    def test_returns_engine_and_session(self, isolated_test_env):
        init_project_db("test-project")
        engine, session_local = get_project_engine("test-project")
        assert engine is not None
        assert session_local is not None

    def test_caches_engine(self, isolated_test_env):
        init_project_db("test-project")
        result1 = get_project_engine("test-project")
        result2 = get_project_engine("test-project")
        assert result1[0] is result2[0]  # Same engine object

    def test_different_projects_different_engines(self, isolated_test_env):
        init_project_db("project-a")
        init_project_db("project-b")
        engine_a, _ = get_project_engine("project-a")
        engine_b, _ = get_project_engine("project-b")
        assert engine_a is not engine_b


class TestInitProjectDb:
    def test_creates_all_tables(self, isolated_test_env):
        init_project_db("test-project")
        engine, _ = get_project_engine("test-project")
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        expected_tables = [
            "jira_users",
            "jira_stories",
            "jira_bugs",
            "jira_sprints",
            "servicenow_incidents",
            "servicenow_deployments",
            "splunk_logs",
        ]
        for table in expected_tables:
            assert table in tables, f"Missing table: {table}"

    def test_creates_db_file(self, isolated_test_env):
        init_project_db("test-project")
        db_path = isolated_test_env / "projects" / "test-project" / "project.db"
        assert db_path.exists()

    def test_idempotent(self, isolated_test_env):
        """Calling init_project_db twice should not error."""
        init_project_db("test-project")
        init_project_db("test-project")  # Should not raise


class TestDataIsolation:
    def test_write_to_a_not_visible_in_b(self, isolated_test_env):
        """Data written to project A should not be visible in project B."""
        init_project_db("project-a")
        init_project_db("project-b")

        # Write a record to project A
        gen_a = get_project_db("project-a")
        db_a = next(gen_a)
        try:
            db_a.execute(
                text("INSERT INTO jira_users (username, full_name, role) VALUES ('alice', 'Alice Dev', 'developer')")
            )
            db_a.commit()
        finally:
            try:
                next(gen_a)
            except StopIteration:
                pass

        # Read from project B — should be empty
        gen_b = get_project_db("project-b")
        db_b = next(gen_b)
        try:
            result = db_b.execute(text("SELECT COUNT(*) FROM jira_users")).scalar()
            assert result == 0
        finally:
            try:
                next(gen_b)
            except StopIteration:
                pass

        # Read from project A — should have the record
        gen_a2 = get_project_db("project-a")
        db_a2 = next(gen_a2)
        try:
            result = db_a2.execute(text("SELECT COUNT(*) FROM jira_users")).scalar()
            assert result == 1
        finally:
            try:
                next(gen_a2)
            except StopIteration:
                pass


class TestRemoveProjectEngine:
    def test_removes_from_cache(self, isolated_test_env):
        import backend.database as db_mod

        init_project_db("test-project")
        assert "test-project" in db_mod._project_engines
        remove_project_engine("test-project")
        assert "test-project" not in db_mod._project_engines

    def test_nonexistent_no_error(self, isolated_test_env):
        """Removing a non-cached project should not raise."""
        remove_project_engine("nonexistent")
