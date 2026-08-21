"""Central project registry — manages project metadata in mahalo_registry.db."""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from backend.config import settings

RegistryBase = declarative_base()

_REGISTRY_DB_PATH = settings.PROJECT_ROOT / "mahalo_registry.db"
_PROJECTS_DIR = settings.PROJECT_ROOT / "projects"

_registry_engine = create_engine(
    f"sqlite:///{_REGISTRY_DB_PATH}",
    connect_args={"check_same_thread": False},
)
RegistrySessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_registry_engine)


def init_registry_db() -> None:
    """Create the registry tables if they don't exist."""
    from backend.models.project_models import Project  # noqa: F401

    RegistryBase.metadata.create_all(bind=_registry_engine, checkfirst=True)


def get_registry_db():
    """FastAPI dependency — yields a session for the registry DB."""
    init_registry_db()
    db = RegistrySessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _slugify(name: str) -> str:
    """Convert a project name to a URL/folder-safe slug."""
    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    return slug or "project"


def _generate_key(name: str) -> str:
    """Generate a short uppercase project key from the name.

    Takes the first letter of each word, uppercase, max 6 characters.
    Falls back to first 4 chars uppercase if single word.
    Ensures minimum 2 characters.
    """
    words = name.strip().split()
    if len(words) >= 2:
        key = "".join(w[0] for w in words if w).upper()[:6]
    else:
        key = name.strip()[:4].upper()
    # Ensure at least 2 chars by padding from name
    if len(key) < 2:
        key = (name.strip().upper() + "XX")[:4]
    return key


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


def create_project(
    db: Session,
    name: str,
    description_goal: str,
    description_users: str,
    description_purpose: str,
    domain: str = "other",
    connection_mode: str = "local",
    jira_url: Optional[str] = None,
    jira_token: Optional[str] = None,
    servicenow_url: Optional[str] = None,
    servicenow_credentials: Optional[str] = None,
    splunk_url: Optional[str] = None,
    splunk_token: Optional[str] = None,
    project_id: Optional[str] = None,
    project_key: Optional[str] = None,
) -> "Project":  # type: ignore[name-defined]
    """Create a new project in the registry and set up its folder + DB."""
    from backend.models.project_models import Project
    from backend.database import init_project_db

    # Generate id and key
    proj_id = project_id or _slugify(name)
    proj_key = project_key or _generate_key(name)

    # Check for duplicates
    existing = db.query(Project).filter(
        (Project.id == proj_id) | (Project.key == proj_key)
    ).first()
    if existing:
        raise ValueError(
            f"Project with id '{proj_id}' or key '{proj_key}' already exists."
        )

    # Create project folder
    project_folder = _PROJECTS_DIR / proj_id
    project_folder.mkdir(parents=True, exist_ok=True)

    # Create the project record
    project = Project(
        id=proj_id,
        name=name,
        key=proj_key,
        description_goal=description_goal,
        description_users=description_users,
        description_purpose=description_purpose,
        domain=domain,
        connection_mode=connection_mode,
        jira_url=jira_url,
        jira_token=jira_token,
        servicenow_url=servicenow_url,
        servicenow_credentials=servicenow_credentials,
        splunk_url=splunk_url,
        splunk_token=splunk_token,
        folder_path=str(project_folder),
        data_generated=False,
    )
    db.add(project)
    db.commit()
    db.refresh(project)

    # Initialize the project's own database with all tables
    init_project_db(proj_id)

    return project


def list_projects(db: Session) -> list:
    """Return all projects in the registry."""
    from backend.models.project_models import Project

    return db.query(Project).order_by(Project.created_at.desc()).all()


def get_project(db: Session, project_id: str) -> Optional["Project"]:  # type: ignore[name-defined]
    """Get a single project by ID."""
    from backend.models.project_models import Project

    return db.query(Project).filter(Project.id == project_id).first()


def delete_project(db: Session, project_id: str) -> bool:
    """Delete a project — removes registry entry and folder from disk."""
    from backend.models.project_models import Project
    from backend.database import remove_project_engine

    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        return False

    # Remove from DB engine cache
    remove_project_engine(project_id)

    # Delete folder from disk
    project_folder = Path(project.folder_path)
    if project_folder.exists():
        shutil.rmtree(project_folder, ignore_errors=True)

    # Remove registry entry
    db.delete(project)
    db.commit()
    return True
