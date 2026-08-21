"""Project management API routes."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from backend.project_registry import (
    create_project,
    delete_project,
    get_project,
    get_registry_db,
    list_projects,
)

router = APIRouter(prefix="/api/projects", tags=["Projects"])


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------


class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    description_goal: str = Field(..., min_length=1)
    description_users: str = Field(..., min_length=1)
    description_purpose: str = Field(..., min_length=1)
    domain: str = Field(default="other", max_length=50)
    connection_mode: str = Field(default="local", pattern=r"^(local|real)$")
    # Optional overrides
    project_key: Optional[str] = Field(default=None, max_length=20)
    # Real-mode placeholders
    jira_url: Optional[str] = None
    jira_token: Optional[str] = None
    servicenow_url: Optional[str] = None
    servicenow_credentials: Optional[str] = None
    splunk_url: Optional[str] = None
    splunk_token: Optional[str] = None


class ProjectResponse(BaseModel):
    id: str
    name: str
    key: str
    description_goal: str
    description_users: str
    description_purpose: str
    domain: str
    connection_mode: str
    jira_url: Optional[str] = None
    jira_token: Optional[str] = None
    servicenow_url: Optional[str] = None
    servicenow_credentials: Optional[str] = None
    splunk_url: Optional[str] = None
    splunk_token: Optional[str] = None
    folder_path: str
    data_generated: bool
    created_at: str
    updated_at: str

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("", response_model=ProjectResponse, status_code=201)
def create_new_project(
    payload: ProjectCreate,
    db: Session = Depends(get_registry_db),
):
    """Create a new project with its own folder and database."""
    try:
        project = create_project(
            db=db,
            name=payload.name,
            description_goal=payload.description_goal,
            description_users=payload.description_users,
            description_purpose=payload.description_purpose,
            domain=payload.domain,
            connection_mode=payload.connection_mode,
            jira_url=payload.jira_url,
            jira_token=payload.jira_token,
            servicenow_url=payload.servicenow_url,
            servicenow_credentials=payload.servicenow_credentials,
            splunk_url=payload.splunk_url,
            splunk_token=payload.splunk_token,
            project_key=payload.project_key,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    return _project_to_response(project)


@router.get("")
def list_all_projects(db: Session = Depends(get_registry_db)):
    """List all registered projects."""
    projects = list_projects(db)
    return {
        "projects": [_project_to_response(p) for p in projects],
        "count": len(projects),
    }


@router.get("/{project_id}", response_model=ProjectResponse)
def get_project_detail(project_id: str, db: Session = Depends(get_registry_db)):
    """Get details for a single project."""
    project = get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found.")
    return _project_to_response(project)


class ProjectUpdate(BaseModel):
    description_goal: Optional[str] = None
    description_users: Optional[str] = None
    description_purpose: Optional[str] = None
    domain: Optional[str] = None
    connection_mode: Optional[str] = Field(default=None, pattern=r"^(local|real)$")
    jira_url: Optional[str] = None
    jira_token: Optional[str] = None
    servicenow_url: Optional[str] = None
    servicenow_credentials: Optional[str] = None
    splunk_url: Optional[str] = None
    splunk_token: Optional[str] = None


@router.patch("/{project_id}", response_model=ProjectResponse)
def update_project(project_id: str, payload: ProjectUpdate, db: Session = Depends(get_registry_db)):
    """Update a project's configuration (description, domain, credentials)."""
    project = get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found.")

    update_fields = payload.model_dump(exclude_unset=True)
    for field, value in update_fields.items():
        setattr(project, field, value)

    db.commit()
    db.refresh(project)
    return _project_to_response(project)


@router.delete("/{project_id}")
def delete_existing_project(project_id: str, db: Session = Depends(get_registry_db)):
    """Delete a project — removes registry entry, database, and folder."""
    deleted = delete_project(db, project_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found.")
    return {"message": "Project deleted successfully.", "id": project_id}


@router.post("/{project_id}/generate-data")
async def generate_project_data(project_id: str, db: Session = Depends(get_registry_db)):
    """Generate LLM-powered mock data for a project.

    Only works for projects in 'local' connection mode.
    If data already exists, wipes it first before regenerating.
    """
    from backend.utils.generate_project_data import generate_mock_data, wipe_project_data

    project = get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found.")

    if project.connection_mode != "local":
        raise HTTPException(
            status_code=400,
            detail="Data generation is only available for projects in 'local' connection mode.",
        )

    # Wipe existing data if regenerating
    if project.data_generated:
        wipe_project_data(project_id)

    # Generate new data
    project_info = {
        "name": project.name,
        "key": project.key,
        "description_goal": project.description_goal,
        "description_users": project.description_users,
        "description_purpose": project.description_purpose,
        "domain": project.domain,
    }
    result = await generate_mock_data(project_id, project_info)

    if result["success"]:
        # Mark project as having generated data
        project.data_generated = True
        db.commit()

    return result


@router.post("/{project_id}/reset-data")
def reset_project_data(project_id: str, db: Session = Depends(get_registry_db)):
    """Wipe all data from a project's database (preserves schema)."""
    from backend.utils.generate_project_data import wipe_project_data

    project = get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found.")

    wipe_project_data(project_id)

    # Reset the data_generated flag
    project.data_generated = False
    db.commit()

    return {"message": "Project data reset successfully.", "id": project_id}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _project_to_response(project) -> dict:
    """Convert a Project ORM object to a response dict."""
    return {
        "id": project.id,
        "name": project.name,
        "key": project.key,
        "description_goal": project.description_goal,
        "description_users": project.description_users,
        "description_purpose": project.description_purpose,
        "domain": project.domain,
        "connection_mode": project.connection_mode,
        "jira_url": project.jira_url,
        "jira_token": project.jira_token,
        "servicenow_url": project.servicenow_url,
        "servicenow_credentials": project.servicenow_credentials,
        "splunk_url": project.splunk_url,
        "splunk_token": project.splunk_token,
        "folder_path": project.folder_path,
        "data_generated": project.data_generated,
        "created_at": str(project.created_at),
        "updated_at": str(project.updated_at),
    }
