from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.dependencies import get_project_session
from backend.servicenow.service import ServiceNowService

router = APIRouter(prefix="/api/servicenow", tags=["ServiceNow"])


class IncidentCreate(BaseModel):
    incident_id: str
    title: str
    description: str | None = None
    severity: str = "Medium"
    status: str = "New"


@router.get("/incidents")
def list_incidents(db: Session = Depends(get_project_session)):
    return {"items": ServiceNowService.list_incidents(db)}


@router.post("/incidents")
def create_incident(payload: IncidentCreate, db: Session = Depends(get_project_session)):
    incident = ServiceNowService.create_incident(db, **payload.model_dump())
    return {"incident_id": incident.incident_id, "title": incident.title, "status": incident.status}


@router.get("/incidents/{incident_id}")
def get_incident(incident_id: str, db: Session = Depends(get_project_session)):
    incident = ServiceNowService.get_incident(db, incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    return {
        "incident_id": incident.incident_id,
        "title": incident.title,
        "description": incident.description,
        "severity": incident.severity,
        "status": incident.status,
    }


@router.get("/deployments")
def list_deployments(environment: str = "production", db: Session = Depends(get_project_session)):
    deployments = ServiceNowService.list_deployments(db, environment=environment, limit=100)
    return {"items": [
        {
            "deployment_id": deployment.deployment_id,
            "feature_name": deployment.feature_name,
            "version": deployment.version,
            "environment": deployment.environment,
            "status": deployment.status,
            "deployed_by": deployment.deployed_by,
            "deployed_at": deployment.deployed_at,
        }
        for deployment in deployments
    ]}
