"""Admin routes — system status, stats, and data reset."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.config import settings
from backend.project_registry import get_registry_db, list_projects, get_project
from backend.utils.reset_data import reset_demo_data
from backend.utils.generate_project_data import wipe_project_data
from agents.context_manager import context_manager

router = APIRouter(prefix="/api/admin", tags=["Admin"])


@router.get("/status")
def status(db: Session = Depends(get_registry_db)):
    projects = list_projects(db)
    return {
        "overall_status": "healthy",
        "healthy_services": 1,
        "total_services": 1,
        "services": {"main_api": {"status": "healthy", "port": settings.MAIN_API_PORT}},
        "projects": {
            "count": len(projects),
            "names": [p.name for p in projects],
        },
    }


@router.get("/info")
def info():
    return {
        "name": "MAHALO",
        "version": "2.0.0",
        "description": "AI Harness for SDLC — Multi-Project",
        "demo_reset_enabled": True,
    }


@router.post("/reset-data")
def reset_data(project_id: Optional[str] = None, db: Session = Depends(get_registry_db)):
    """Reset data for a specific project or the default MahaloPay project.

    If project_id is provided, resets that project's data.
    If not provided, resets the 'mahalopay' project (backward compat).
    """
    target_id = project_id or "mahalopay"

    project = get_project(db, target_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project '{target_id}' not found.")

    if target_id == "mahalopay":
        # Use the original demo seeder for MahaloPay
        reset_demo_data(project_id=target_id)
    else:
        # For other projects, just wipe data
        wipe_project_data(target_id)
        project.data_generated = False
        db.commit()

    context_manager.clear()
    return {"message": f"Data reset successful for project '{target_id}'.", "status": "success", "project_id": target_id}


@router.get("/stats")
def stats(db: Session = Depends(get_registry_db)):
    history = context_manager.get_conversation_history(last_n=None)
    projects = list_projects(db)
    return {
        "conversations": {
            "total_messages": len(history),
            "user_messages": sum(message["role"] == "user" for message in history),
            "assistant_messages": sum(message["role"] == "assistant" for message in history),
        },
        "projects": {
            "count": len(projects),
            "with_data": sum(1 for p in projects if p.data_generated),
        },
    }
