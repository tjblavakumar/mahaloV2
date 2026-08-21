"""Bootstrap — ensures default MahaloPay project exists on first boot."""

from __future__ import annotations

import backend.project_registry as registry


_MAHALOPAY_CONFIG = {
    "name": "MahaloPay",
    "project_id": "mahalopay",
    "project_key": "MPAY",
    "description_goal": (
        "Build a modern payment processing platform with secure transactions, "
        "fraud detection, and automated reconciliation"
    ),
    "description_users": (
        "Merchants, consumers, financial institutions, internal platform teams"
    ),
    "description_purpose": (
        "Process payments securely and reliably at scale, detect fraud, "
        "and maintain accurate financial records"
    ),
    "domain": "fintech",
    "connection_mode": "local",
}


def ensure_default_project() -> None:
    """Create MahaloPay as the default project if no projects exist.

    Called during application startup. Idempotent — does nothing if
    projects already exist in the registry.
    """
    registry.init_registry_db()
    db = registry.RegistrySessionLocal()
    try:
        # Check if any projects exist
        projects = registry.list_projects(db)
        if projects:
            return  # Projects exist, nothing to do

        # Create MahaloPay
        project = registry.create_project(
            db=db,
            name=_MAHALOPAY_CONFIG["name"],
            description_goal=_MAHALOPAY_CONFIG["description_goal"],
            description_users=_MAHALOPAY_CONFIG["description_users"],
            description_purpose=_MAHALOPAY_CONFIG["description_purpose"],
            domain=_MAHALOPAY_CONFIG["domain"],
            connection_mode=_MAHALOPAY_CONFIG["connection_mode"],
            project_id=_MAHALOPAY_CONFIG["project_id"],
            project_key=_MAHALOPAY_CONFIG["project_key"],
        )

        # Seed with demo data
        from backend.utils.reset_data import reset_demo_data

        reset_demo_data(project_id=project.id)

        # Mark as data_generated
        project.data_generated = True
        db.commit()

        print(f"[BOOTSTRAP] Created default project: {project.name} ({project.id})")
    except Exception as e:
        print(f"[BOOTSTRAP] Warning during default project creation: {e}")
        db.rollback()
    finally:
        db.close()
