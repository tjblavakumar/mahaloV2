"""Phase 4 tests — MahaloPay migration to multi-project structure."""

from pathlib import Path

import pytest
from sqlalchemy import text

import backend.project_registry as registry
from backend.database import get_project_db, init_project_db
from backend.utils.bootstrap import ensure_default_project
from backend.utils.reset_data import reset_demo_data


# ---------------------------------------------------------------------------
# Task 9: Bootstrap / ensure_default_project
# ---------------------------------------------------------------------------


class TestEnsureDefaultProject:
    def test_creates_mahalopay_when_empty(self, isolated_test_env):
        """First boot with no projects creates MahaloPay."""
        ensure_default_project()

        db = registry.RegistrySessionLocal()
        try:
            projects = registry.list_projects(db)
            assert len(projects) == 1
            assert projects[0].id == "mahalopay"
            assert projects[0].name == "MahaloPay"
            assert projects[0].key == "MPAY"
            assert projects[0].domain == "fintech"
            assert projects[0].data_generated is True
        finally:
            db.close()

    def test_creates_project_folder(self, isolated_test_env):
        """MahaloPay project folder is created on disk."""
        ensure_default_project()

        folder = isolated_test_env / "projects" / "mahalopay"
        assert folder.exists()
        assert (folder / "project.db").exists()

    def test_seeds_demo_data(self, isolated_test_env):
        """MahaloPay is seeded with demo data."""
        ensure_default_project()

        gen = get_project_db("mahalopay")
        db = next(gen)
        try:
            users = db.execute(text("SELECT COUNT(*) FROM jira_users")).scalar()
            stories = db.execute(text("SELECT COUNT(*) FROM jira_stories")).scalar()
            bugs = db.execute(text("SELECT COUNT(*) FROM jira_bugs")).scalar()
            incidents = db.execute(text("SELECT COUNT(*) FROM servicenow_incidents")).scalar()
            deployments = db.execute(text("SELECT COUNT(*) FROM servicenow_deployments")).scalar()
            logs = db.execute(text("SELECT COUNT(*) FROM splunk_logs")).scalar()

            assert users == 5
            assert stories == 3
            assert bugs == 2
            assert incidents == 2
            assert deployments == 3
            assert logs == 8
        finally:
            try:
                next(gen)
            except StopIteration:
                pass

    def test_idempotent_does_not_duplicate(self, isolated_test_env):
        """Calling ensure_default_project twice does not create duplicates."""
        ensure_default_project()
        ensure_default_project()

        db = registry.RegistrySessionLocal()
        try:
            projects = registry.list_projects(db)
            assert len(projects) == 1
        finally:
            db.close()

    def test_skips_when_projects_exist(self, isolated_test_env):
        """If projects already exist, MahaloPay is NOT auto-created."""
        db = registry.RegistrySessionLocal()
        try:
            registry.create_project(
                db=db,
                name="Other Project",
                description_goal="Goal",
                description_users="Users",
                description_purpose="Purpose",
            )
        finally:
            db.close()

        ensure_default_project()

        db = registry.RegistrySessionLocal()
        try:
            projects = registry.list_projects(db)
            names = [p.name for p in projects]
            assert "MahaloPay" not in names
            assert len(projects) == 1
        finally:
            db.close()


# ---------------------------------------------------------------------------
# Task 9: reset_demo_data with project_id
# ---------------------------------------------------------------------------


class TestResetDemoDataProjectAware:
    def test_seeds_into_project_db(self, isolated_test_env):
        """reset_demo_data(project_id) seeds data into the project's DB."""
        init_project_db("test-project")
        reset_demo_data(project_id="test-project")

        gen = get_project_db("test-project")
        db = next(gen)
        try:
            users = db.execute(text("SELECT COUNT(*) FROM jira_users")).scalar()
            stories = db.execute(text("SELECT COUNT(*) FROM jira_stories")).scalar()
            assert users == 5
            assert stories == 3
        finally:
            try:
                next(gen)
            except StopIteration:
                pass

    def test_story_keys_use_mpay_prefix(self, isolated_test_env):
        """Seeded stories use MPAY-* keys."""
        init_project_db("test-project")
        reset_demo_data(project_id="test-project")

        gen = get_project_db("test-project")
        db = next(gen)
        try:
            keys = [row[0] for row in db.execute(text("SELECT story_key FROM jira_stories")).fetchall()]
            assert all(k.startswith("MPAY-") for k in keys)
        finally:
            try:
                next(gen)
            except StopIteration:
                pass

    def test_is_idempotent(self, isolated_test_env):
        """Calling reset_demo_data twice resets cleanly (no duplicates)."""
        init_project_db("test-project")
        reset_demo_data(project_id="test-project")
        reset_demo_data(project_id="test-project")

        gen = get_project_db("test-project")
        db = next(gen)
        try:
            users = db.execute(text("SELECT COUNT(*) FROM jira_users")).scalar()
            assert users == 5  # Not 10
        finally:
            try:
                next(gen)
            except StopIteration:
                pass


# ---------------------------------------------------------------------------
# Task 10: Admin routes in multi-project context
# ---------------------------------------------------------------------------


class TestAdminRoutesMultiProject:
    def test_status_shows_project_count(self, api_client, sample_project_payload):
        """GET /api/admin/status includes project count."""
        api_client.post("/api/projects", json=sample_project_payload)

        resp = api_client.get("/api/admin/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "projects" in data
        assert data["projects"]["count"] >= 1

    def test_stats_shows_project_info(self, api_client, sample_project_payload):
        """GET /api/admin/stats includes project stats."""
        api_client.post("/api/projects", json=sample_project_payload)

        resp = api_client.get("/api/admin/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert "projects" in data
        assert "count" in data["projects"]

    def test_reset_data_with_project_id(self, api_client, isolated_test_env):
        """POST /api/admin/reset-data?project_id=X resets that project."""
        # Create a project first
        api_client.post("/api/projects", json={
            "name": "ResetTest",
            "description_goal": "Goal",
            "description_users": "Users",
            "description_purpose": "Purpose",
        })

        # Seed some data manually
        init_project_db("resettest")
        gen = get_project_db("resettest")
        db = next(gen)
        try:
            db.execute(text(
                "INSERT INTO jira_users (username, full_name, role) VALUES ('test', 'Test User', 'developer')"
            ))
            db.commit()
        finally:
            try:
                next(gen)
            except StopIteration:
                pass

        # Reset via admin endpoint
        resp = api_client.post("/api/admin/reset-data?project_id=resettest")
        assert resp.status_code == 200
        assert "reset" in resp.json()["message"].lower()

    def test_reset_data_project_not_found(self, api_client):
        """POST /api/admin/reset-data?project_id=nonexistent returns 404."""
        resp = api_client.post("/api/admin/reset-data?project_id=nonexistent")
        assert resp.status_code == 404

    def test_reset_data_mahalopay_default(self, api_client, isolated_test_env):
        """POST /api/admin/reset-data without project_id targets mahalopay."""
        # Bootstrap MahaloPay first
        ensure_default_project()

        resp = api_client.post("/api/admin/reset-data")
        assert resp.status_code == 200
        assert resp.json()["project_id"] == "mahalopay"
