"""Shared test fixtures for Phase 1 tests."""

import os
import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Override settings BEFORE importing app modules
_test_dir = None


@pytest.fixture(autouse=True)
def isolated_test_env(tmp_path, monkeypatch):
    """Isolate each test with its own temporary directory for DBs and project folders."""
    global _test_dir
    _test_dir = tmp_path

    # Patch settings.PROJECT_ROOT so all paths resolve to tmp
    monkeypatch.setattr("backend.config.settings.PROJECT_ROOT", tmp_path)
    monkeypatch.setattr("backend.config.settings.DATABASE_URL", f"sqlite:///{tmp_path / 'mahalo.db'}")

    # Patch the registry module's paths
    monkeypatch.setattr("backend.project_registry._REGISTRY_DB_PATH", tmp_path / "mahalo_registry.db")
    monkeypatch.setattr("backend.project_registry._PROJECTS_DIR", tmp_path / "projects")

    # Recreate registry engine for the test
    from backend.project_registry import RegistryBase

    test_registry_engine = create_engine(
        f"sqlite:///{tmp_path / 'mahalo_registry.db'}",
        connect_args={"check_same_thread": False},
    )
    test_registry_session = sessionmaker(autocommit=False, autoflush=False, bind=test_registry_engine)

    monkeypatch.setattr("backend.project_registry._registry_engine", test_registry_engine)
    monkeypatch.setattr("backend.project_registry.RegistrySessionLocal", test_registry_session)

    # Patch database module's project dir
    monkeypatch.setattr("backend.database._PROJECTS_DIR", tmp_path / "projects")

    # Clear engine cache between tests
    import backend.database as db_mod
    db_mod._project_engines.clear()

    # Create projects dir
    (tmp_path / "projects").mkdir(exist_ok=True)

    # Initialize registry tables
    RegistryBase.metadata.create_all(bind=test_registry_engine, checkfirst=True)

    yield tmp_path

    # Cleanup engine cache
    db_mod._project_engines.clear()


@pytest.fixture
def registry_db(isolated_test_env):
    """Yield a registry DB session for direct testing."""
    from backend.project_registry import RegistrySessionLocal

    db = RegistrySessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def api_client(isolated_test_env):
    """Create a FastAPI test client with isolated DB."""
    from api.main import app
    from backend.project_registry import get_registry_db, RegistrySessionLocal, init_registry_db

    # Ensure tables exist in the test registry DB
    init_registry_db()

    def _override_registry_db():
        db = RegistrySessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_registry_db] = _override_registry_db
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


@pytest.fixture
def sample_project_payload():
    """Standard project creation payload for tests."""
    return {
        "name": "HealthSync",
        "description_goal": "Build a healthcare scheduling platform",
        "description_users": "Doctors, patients, clinic administrators",
        "description_purpose": "Streamline appointment booking and patient management",
        "domain": "healthcare",
        "connection_mode": "local",
    }
