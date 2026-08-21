from datetime import datetime
from typing import List, Optional

from sqlalchemy.orm import Session

from backend.models.jira_models import JiraBug, JiraStory, JiraUser


class JiraService:
    @staticmethod
    def create_user(
        db: Session,
        username: str,
        full_name: str,
        email: Optional[str] = None,
        role: str = "developer",
    ) -> JiraUser:
        user = JiraUser(username=username, full_name=full_name, email=email, role=role)
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    @staticmethod
    def get_user_by_username(db: Session, username: str) -> Optional[JiraUser]:
        return db.query(JiraUser).filter(JiraUser.username == username).first()

    @staticmethod
    def list_all_users(db: Session) -> List[JiraUser]:
        return db.query(JiraUser).all()

    @staticmethod
    def create_story(
        db: Session,
        title: str,
        description: Optional[str] = None,
        assignee_username: Optional[str] = None,
        reporter_username: Optional[str] = None,
        story_points: int = 0,
        priority: str = "Medium",
        sprint: Optional[str] = None,
        status: str = "Backlog",
    ) -> JiraStory:
        last_story = db.query(JiraStory).order_by(JiraStory.id.desc()).first()
        next_id = (last_story.id + 1) if last_story else 1
        story_key = f"STORY-{next_id}"

        assignee_id = None
        reporter_id = None
        if assignee_username:
            assignee = JiraService.get_user_by_username(db, assignee_username)
            assignee_id = assignee.id if assignee else None
        if reporter_username:
            reporter = JiraService.get_user_by_username(db, reporter_username)
            reporter_id = reporter.id if reporter else None

        story = JiraStory(
            story_key=story_key,
            title=title,
            description=description,
            assignee_id=assignee_id,
            reporter_id=reporter_id,
            story_points=story_points,
            priority=priority,
            sprint=sprint or "Sprint 23",
            status=status,
        )
        db.add(story)
        db.commit()
        db.refresh(story)
        return story

    @staticmethod
    def get_story_by_key(db: Session, story_key: str) -> Optional[JiraStory]:
        return db.query(JiraStory).filter(JiraStory.story_key == story_key).first()

    @staticmethod
    def update_story(
        db: Session,
        story_key: str,
        title: Optional[str] = None,
        description: Optional[str] = None,
        assignee_username: Optional[str] = None,
        reporter_username: Optional[str] = None,
        story_points: Optional[int] = None,
        priority: Optional[str] = None,
        sprint: Optional[str] = None,
        status: Optional[str] = None,
    ) -> Optional[JiraStory]:
        story = db.query(JiraStory).filter(JiraStory.story_key == story_key).first()
        if not story:
            return None
        if title is not None:
            story.title = title
        if description is not None:
            story.description = description
        if story_points is not None:
            story.story_points = story_points
        if priority is not None:
            story.priority = priority
        if sprint is not None:
            story.sprint = sprint
        if status is not None:
            story.status = status
        if assignee_username is not None:
            assignee = JiraService.get_user_by_username(db, assignee_username)
            story.assignee_id = assignee.id if assignee else None
        if reporter_username is not None:
            reporter = JiraService.get_user_by_username(db, reporter_username)
            story.reporter_id = reporter.id if reporter else None
        db.commit()
        db.refresh(story)
        return story

    @staticmethod
    def list_all_stories(db: Session, limit: int = 100) -> List[JiraStory]:
        return db.query(JiraStory).limit(limit).all()

    @staticmethod
    def list_all_bugs(db: Session, limit: int = 100) -> List[JiraBug]:
        return db.query(JiraBug).limit(limit).all()

    @staticmethod
    def create_bug(
        db: Session,
        title: str,
        description: Optional[str] = None,
        assignee_username: Optional[str] = None,
        reporter_username: Optional[str] = None,
        severity: str = "Medium",
        related_story_key: Optional[str] = None,
        servicenow_incident_id: Optional[str] = None,
        status: str = "Open",
    ) -> JiraBug:
        last_bug = db.query(JiraBug).order_by(JiraBug.id.desc()).first()
        next_id = (last_bug.id + 1) if last_bug else 1
        bug_key = f"BUG-{next_id}"

        assignee_id = None
        reporter_id = None
        if assignee_username:
            assignee = JiraService.get_user_by_username(db, assignee_username)
            assignee_id = assignee.id if assignee else None
        if reporter_username:
            reporter = JiraService.get_user_by_username(db, reporter_username)
            reporter_id = reporter.id if reporter else None

        related_story_id = None
        if related_story_key:
            story = JiraService.get_story_by_key(db, related_story_key)
            related_story_id = story.id if story else None

        bug = JiraBug(
            bug_key=bug_key,
            title=title,
            description=description,
            assignee_id=assignee_id,
            reporter_id=reporter_id,
            severity=severity,
            related_story_id=related_story_id,
            servicenow_incident_id=servicenow_incident_id,
            status=status,
        )
        db.add(bug)
        db.commit()
        db.refresh(bug)
        return bug
