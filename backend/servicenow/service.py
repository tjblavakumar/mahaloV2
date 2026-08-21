from typing import List, Optional

from sqlalchemy.orm import Session

from backend.models.servicenow_models import ServiceNowDeployment, ServiceNowIncident


class ServiceNowService:
    @staticmethod
    def list_deployments(db: Session, environment: Optional[str] = None, limit: int = 100) -> List[ServiceNowDeployment]:
        query = db.query(ServiceNowDeployment)
        if environment:
            query = query.filter(ServiceNowDeployment.environment == environment)
        return query.limit(limit).all()

    @staticmethod
    def create_incident(
        db: Session,
        incident_id: str,
        title: str,
        description: Optional[str] = None,
        severity: str = "Medium",
        status: str = "New",
    ) -> ServiceNowIncident:
        incident = ServiceNowIncident(
            incident_id=incident_id,
            title=title,
            description=description,
            severity=severity,
            status=status,
        )
        db.add(incident)
        db.commit()
        db.refresh(incident)
        return incident

    @staticmethod
    def list_incidents(db: Session, limit: int = 100) -> List[ServiceNowIncident]:
        return db.query(ServiceNowIncident).limit(limit).all()

    @staticmethod
    def get_incident(db: Session, incident_id: str) -> Optional[ServiceNowIncident]:
        return db.query(ServiceNowIncident).filter(ServiceNowIncident.incident_id == incident_id).first()
