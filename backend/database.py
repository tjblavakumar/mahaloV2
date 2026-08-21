from __future__ import annotations

from pathlib import Path
from threading import Lock

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from backend.config import settings

Base = declarative_base()

# ---------------------------------------------------------------------------
# Legacy single-database engine (backward compatibility)
# ---------------------------------------------------------------------------

engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db() -> None:
    from backend.models import jira_models, servicenow_models, splunk_models  # noqa: F401

    try:
        Base.metadata.create_all(bind=engine, checkfirst=True)
    except Exception as e:
        # Log the error but don't crash if tables already exist
        print(f"Warning during database initialization: {e}")
        # Tables likely already exist, continue anyway
        pass


def get_db():
    init_db()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Per-project database resolution
# ---------------------------------------------------------------------------

_PROJECTS_DIR = settings.PROJECT_ROOT / "projects"
_project_engines: dict[str, tuple] = {}  # project_id -> (engine, SessionLocal)
_engine_lock = Lock()


def get_project_engine(project_id: str):
    """Get or create a cached SQLAlchemy engine for a project's database.

    Returns a tuple of (engine, SessionMaker).
    """
    if project_id in _project_engines:
        return _project_engines[project_id]

    with _engine_lock:
        # Double-check after acquiring lock
        if project_id in _project_engines:
            return _project_engines[project_id]

        db_path = _PROJECTS_DIR / project_id / "project.db"
        if not db_path.parent.exists():
            db_path.parent.mkdir(parents=True, exist_ok=True)

        project_engine = create_engine(
            f"sqlite:///{db_path}",
            connect_args={"check_same_thread": False},
        )
        project_session_local = sessionmaker(
            autocommit=False, autoflush=False, bind=project_engine
        )
        _project_engines[project_id] = (project_engine, project_session_local)
        return _project_engines[project_id]


def get_project_db(project_id: str):
    """FastAPI dependency — yields a session for a specific project's database."""
    proj_engine, ProjectSessionLocal = get_project_engine(project_id)
    db = ProjectSessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_project_db(project_id: str) -> None:
    """Create all tables in a project's database."""
    from backend.models import jira_models, servicenow_models, splunk_models  # noqa: F401

    proj_engine, _ = get_project_engine(project_id)
    try:
        Base.metadata.create_all(bind=proj_engine, checkfirst=True)
    except Exception as e:
        print(f"Warning during project DB initialization for '{project_id}': {e}")


def remove_project_engine(project_id: str) -> None:
    """Remove a project's engine from the cache (used when deleting a project)."""
    with _engine_lock:
        entry = _project_engines.pop(project_id, None)
        if entry:
            engine_obj, _ = entry
            engine_obj.dispose()
