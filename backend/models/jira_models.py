from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from backend.database import Base


class JiraUser(Base):
    __tablename__ = "jira_users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(80), unique=True, index=True, nullable=False)
    full_name = Column(String(120), nullable=False)
    email = Column(String(120), nullable=True)
    role = Column(String(50), default="developer")
    created_at = Column(DateTime, default=datetime.utcnow)

    stories = relationship("JiraStory", foreign_keys="JiraStory.assignee_id", overlaps="assignee")
    reporter_stories = relationship("JiraStory", foreign_keys="JiraStory.reporter_id", overlaps="reporter")
    bugs = relationship("JiraBug", foreign_keys="JiraBug.assignee_id", overlaps="assignee")


class JiraStory(Base):
    __tablename__ = "jira_stories"

    id = Column(Integer, primary_key=True, index=True)
    story_key = Column(String(50), unique=True, index=True, nullable=False)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    assignee_id = Column(Integer, ForeignKey("jira_users.id"), nullable=True)
    reporter_id = Column(Integer, ForeignKey("jira_users.id"), nullable=True)
    story_points = Column(Integer, default=0)
    priority = Column(String(30), default="Medium")
    sprint = Column(String(50), default="Sprint 23")
    status = Column(String(30), default="Backlog")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    assignee = relationship("JiraUser", foreign_keys=[assignee_id], overlaps="stories")
    reporter = relationship("JiraUser", foreign_keys=[reporter_id], overlaps="reporter_stories")


class JiraBug(Base):
    __tablename__ = "jira_bugs"

    id = Column(Integer, primary_key=True, index=True)
    bug_key = Column(String(50), unique=True, index=True, nullable=False)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    assignee_id = Column(Integer, ForeignKey("jira_users.id"), nullable=True)
    reporter_id = Column(Integer, ForeignKey("jira_users.id"), nullable=True)
    severity = Column(String(30), default="Medium")
    status = Column(String(30), default="Open")
    related_story_id = Column(Integer, ForeignKey("jira_stories.id"), nullable=True)
    servicenow_incident_id = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    assignee = relationship("JiraUser", foreign_keys=[assignee_id], overlaps="bugs")
    reporter = relationship("JiraUser", foreign_keys=[reporter_id])
    related_story = relationship("JiraStory", foreign_keys=[related_story_id])


class JiraSprint(Base):
    __tablename__ = "jira_sprints"

    id = Column(Integer, primary_key=True, index=True)
    sprint_name = Column(String(80), unique=True, nullable=False)
    goal = Column(Text, nullable=True)
    start_date = Column(DateTime, default=datetime.utcnow)
    end_date = Column(DateTime, default=datetime.utcnow)
    velocity = Column(Integer, default=0)
    completed_stories = Column(Integer, default=0)
    total_stories = Column(Integer, default=0)
    status = Column(String(30), default="Planned")
