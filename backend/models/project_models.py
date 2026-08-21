"""Project registry model — stored in the central mahalo_registry.db."""

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, String, Text

from backend.project_registry import RegistryBase


class Project(RegistryBase):
    __tablename__ = "projects"

    id = Column(String(120), primary_key=True, index=True)  # slug from name
    name = Column(String(120), nullable=False)
    key = Column(String(20), unique=True, nullable=False)  # e.g., "HSYNC"
    description_goal = Column(Text, nullable=False)
    description_users = Column(Text, nullable=False)
    description_purpose = Column(Text, nullable=False)
    domain = Column(String(50), default="other")
    connection_mode = Column(String(10), default="local")  # "local" or "real"
    jira_url = Column(String(200), nullable=True)
    jira_token = Column(String(200), nullable=True)
    servicenow_url = Column(String(200), nullable=True)
    servicenow_credentials = Column(String(200), nullable=True)
    splunk_url = Column(String(200), nullable=True)
    splunk_token = Column(String(200), nullable=True)
    folder_path = Column(String(300), nullable=False)
    data_generated = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
