"""Tests for backend/project_registry.py — CRUD operations and filesystem setup."""

from pathlib import Path

import pytest

from backend.project_registry import (
    _generate_key,
    _slugify,
    create_project,
    delete_project,
    get_project,
    list_projects,
)


class TestSlugify:
    def test_basic(self):
        assert _slugify("HealthSync") == "healthsync"

    def test_spaces(self):
        assert _slugify("My Cool Project") == "my-cool-project"

    def test_special_chars(self):
        assert _slugify("Project #1 (Beta)") == "project-1-beta"

    def test_trailing_spaces(self):
        assert _slugify("  Hello World  ") == "hello-world"

    def test_empty_fallback(self):
        assert _slugify("---") == "project"


class TestGenerateKey:
    def test_multi_word(self):
        assert _generate_key("HealthSync App") == "HA"

    def test_three_words(self):
        assert _generate_key("Health Sync App") == "HSA"

    def test_two_words(self):
        assert _generate_key("MahaloPay") == "MAHA"

    def test_single_word(self):
        assert _generate_key("Finance") == "FINA"

    def test_long_name(self):
        key = _generate_key("A B C D E F G H")
        assert len(key) <= 6

    def test_minimum_length(self):
        key = _generate_key("X")
        assert len(key) >= 2


class TestCreateProject:
    def test_creates_project_entry(self, registry_db, isolated_test_env):
        project = create_project(
            db=registry_db,
            name="HealthSync",
            description_goal="Build scheduling platform",
            description_users="Doctors, patients",
            description_purpose="Streamline appointments",
            domain="healthcare",
        )
        assert project.id == "healthsync"
        assert project.key == "HEAL"
        assert project.name == "HealthSync"
        assert project.domain == "healthcare"
        assert project.connection_mode == "local"
        assert project.data_generated is False

    def test_creates_project_folder(self, registry_db, isolated_test_env):
        project = create_project(
            db=registry_db,
            name="HealthSync",
            description_goal="Goal",
            description_users="Users",
            description_purpose="Purpose",
        )
        folder = Path(project.folder_path)
        assert folder.exists()
        assert folder.is_dir()

    def test_creates_project_db(self, registry_db, isolated_test_env):
        project = create_project(
            db=registry_db,
            name="HealthSync",
            description_goal="Goal",
            description_users="Users",
            description_purpose="Purpose",
        )
        db_path = Path(project.folder_path) / "project.db"
        assert db_path.exists()

    def test_project_db_has_tables(self, registry_db, isolated_test_env):
        from sqlalchemy import inspect

        from backend.database import get_project_engine

        project = create_project(
            db=registry_db,
            name="HealthSync",
            description_goal="Goal",
            description_users="Users",
            description_purpose="Purpose",
        )
        eng, _ = get_project_engine("healthsync")
        inspector = inspect(eng)
        tables = inspector.get_table_names()
        assert "jira_users" in tables
        assert "jira_stories" in tables
        assert "jira_bugs" in tables
        assert "jira_sprints" in tables
        assert "servicenow_incidents" in tables
        assert "servicenow_deployments" in tables
        assert "splunk_logs" in tables

    def test_duplicate_raises_error(self, registry_db, isolated_test_env):
        create_project(
            db=registry_db,
            name="HealthSync",
            description_goal="Goal",
            description_users="Users",
            description_purpose="Purpose",
        )
        with pytest.raises(ValueError, match="already exists"):
            create_project(
                db=registry_db,
                name="HealthSync",
                description_goal="Goal 2",
                description_users="Users 2",
                description_purpose="Purpose 2",
            )

    def test_custom_key(self, registry_db, isolated_test_env):
        project = create_project(
            db=registry_db,
            name="HealthSync",
            description_goal="Goal",
            description_users="Users",
            description_purpose="Purpose",
            project_key="HSYNC",
        )
        assert project.key == "HSYNC"

    def test_custom_id(self, registry_db, isolated_test_env):
        project = create_project(
            db=registry_db,
            name="HealthSync",
            description_goal="Goal",
            description_users="Users",
            description_purpose="Purpose",
            project_id="my-health-app",
        )
        assert project.id == "my-health-app"


class TestListProjects:
    def test_empty(self, registry_db, isolated_test_env):
        projects = list_projects(registry_db)
        assert projects == []

    def test_returns_all(self, registry_db, isolated_test_env):
        create_project(
            db=registry_db,
            name="Project A",
            description_goal="G",
            description_users="U",
            description_purpose="P",
        )
        create_project(
            db=registry_db,
            name="Project B",
            description_goal="G",
            description_users="U",
            description_purpose="P",
        )
        projects = list_projects(registry_db)
        assert len(projects) == 2


class TestGetProject:
    def test_exists(self, registry_db, isolated_test_env):
        create_project(
            db=registry_db,
            name="HealthSync",
            description_goal="G",
            description_users="U",
            description_purpose="P",
        )
        project = get_project(registry_db, "healthsync")
        assert project is not None
        assert project.name == "HealthSync"

    def test_not_found(self, registry_db, isolated_test_env):
        project = get_project(registry_db, "nonexistent")
        assert project is None


class TestDeleteProject:
    def test_deletes_entry(self, registry_db, isolated_test_env):
        create_project(
            db=registry_db,
            name="HealthSync",
            description_goal="G",
            description_users="U",
            description_purpose="P",
        )
        result = delete_project(registry_db, "healthsync")
        assert result is True
        assert get_project(registry_db, "healthsync") is None

    def test_deletes_folder(self, registry_db, isolated_test_env):
        project = create_project(
            db=registry_db,
            name="HealthSync",
            description_goal="G",
            description_users="U",
            description_purpose="P",
        )
        folder = Path(project.folder_path)
        assert folder.exists()
        delete_project(registry_db, "healthsync")
        assert not folder.exists()

    def test_not_found_returns_false(self, registry_db, isolated_test_env):
        result = delete_project(registry_db, "nonexistent")
        assert result is False
