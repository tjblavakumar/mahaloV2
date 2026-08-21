from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Text

from backend.database import Base


class ServiceNowIncident(Base):
    __tablename__ = "servicenow_incidents"

    id = Column(Integer, primary_key=True, index=True)
    incident_id = Column(String(50), unique=True, index=True, nullable=False)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    severity = Column(String(20), default="Medium")
    status = Column(String(30), default="New")
    assigned_group = Column(String(80), default="Platform")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ServiceNowDeployment(Base):
    __tablename__ = "servicenow_deployments"

    id = Column(Integer, primary_key=True, index=True)
    deployment_id = Column(String(50), unique=True, index=True, nullable=False)
    feature_name = Column(String(200), nullable=False)
    version = Column(String(50), nullable=False)
    environment = Column(String(30), default="production", index=True)
    status = Column(String(30), default="Deployed")
    deployed_by = Column(String(100), nullable=True)
    deployed_at = Column(DateTime, default=datetime.utcnow)
