"""LLM-powered mock data generation for projects.

Generates domain-appropriate JIRA stories, bugs, incidents, deployments,
and Splunk logs based on the project description.

Uses chunked LLM calls (small batches) to avoid timeouts and commits
data to the DB immediately after each batch.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from typing import Any

from backend.config import settings
from backend.database import get_project_db, init_project_db
from backend.llm_adapter import one_min_ai_completion
from backend.models.jira_models import JiraBug, JiraSprint, JiraStory, JiraUser
from backend.models.servicenow_models import ServiceNowDeployment, ServiceNowIncident
from backend.models.splunk_models import SplunkLog


# ---------------------------------------------------------------------------
# LLM Prompt Templates (chunked — small batches)
# ---------------------------------------------------------------------------

_PROJECT_CONTEXT = """Project: {name} ({key})
Domain: {domain}
Goal: {goal}
Users: {users}
Purpose: {purpose}"""

_PROMPT_USERS = """Generate exactly 5 team members for this project as a JSON array.
Each object: {{"username": "firstname_role", "full_name": "First Last", "email": "first@company.com", "role": "developer|product_manager|qa|executive"}}
Roles: 2 developers, 1 product_manager, 1 qa, 1 executive.
Use names and emails appropriate for the domain.
Return ONLY a JSON array, no explanation."""

_PROMPT_STORIES = """Generate exactly 5 user stories for this project as a JSON array.
Each object: {{"title": "short title", "description": "2-3 sentence description", "story_points": 1-13, "priority": "Critical|High|Medium|Low", "status": "Done|In Progress|Backlog", "sprint": "Sprint 1|Sprint 2", "assignee_index": 0-4, "reporter_index": 0-4}}
Status mix: 1 Done, 2 In Progress, 2 Backlog. Vary priorities.
Content must be specific to the {domain} domain.
Return ONLY a JSON array, no explanation."""

_PROMPT_BUGS = """Generate exactly 5 bugs for this project as a JSON array.
Each object: {{"title": "bug title", "description": "technical description", "severity": "Critical|High|Medium|Low", "status": "Open|In Progress|Resolved", "related_story_index": 0-4, "assignee_index": 0-4, "reporter_index": 0-4}}
Vary severity and status. Bugs should be realistic for a {domain} project.
Return ONLY a JSON array, no explanation."""

_PROMPT_SPRINTS = """Generate exactly 2 sprints for this project as a JSON array.
Each object: {{"sprint_name": "Sprint N", "goal": "sprint goal", "velocity": 15-30, "completed_stories": 2-5, "total_stories": 5-8, "status": "Active|Completed"}}
First: Completed. Second: Active. Goals related to the project.
Return ONLY a JSON array, no explanation."""

_PROMPT_INCIDENTS = """Generate exactly 5 ServiceNow incidents for this project as a JSON array.
Each object: {{"title": "incident title", "description": "incident description", "severity": "Critical|High|Medium|Low", "status": "Active|Monitoring|Resolved", "assigned_group": "team name"}}
Incidents should be realistic production issues for a {domain} project.
Return ONLY a JSON array, no explanation."""

_PROMPT_DEPLOYMENTS = """Generate exactly 5 deployments for this project as a JSON array.
Each object: {{"feature_name": "feature name", "version": "vX.Y.Z", "environment": "production|staging", "status": "Deployed|Rolling Back|In Progress", "deployed_by": "team-name"}}
4 production, 1 staging. Mostly Deployed. Features relevant to {domain}.
Return ONLY a JSON array, no explanation."""

_PROMPT_LOGS = """Generate exactly 5 Splunk log entries for this project as a JSON array.
Each object: {{"source": "service-name", "level": "{level}", "message": "realistic log message", "service": "service-name"}}
Use 2-3 service names relevant to the {domain} domain.
Messages should be technical and realistic. Level for all entries: {level}.
Return ONLY a JSON array, no explanation."""


# ---------------------------------------------------------------------------
# JSON Parsing
# ---------------------------------------------------------------------------


def _extract_json(text: str) -> Any:
    """Extract JSON from LLM response, handling potential markdown fences."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
        text = text.strip()
    return json.loads(text)


# ---------------------------------------------------------------------------
# LLM Call Helper
# ---------------------------------------------------------------------------


async def _call_llm(system: str, user_prompt: str) -> str:
    """Make a single LLM call and return the text content."""
    response = await one_min_ai_completion(
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.7,
        max_tokens=2000,
    )
    return response.choices[0].message.content


# ---------------------------------------------------------------------------
# Data Insertion (immediate commit per batch)
# ---------------------------------------------------------------------------


def _get_db_session(project_id: str):
    """Get a DB session for the project. Returns (db, generator)."""
    init_project_db(project_id)
    gen = get_project_db(project_id)
    db = next(gen)
    return db, gen


def _close_db(gen):
    """Close a DB generator."""
    try:
        next(gen)
    except StopIteration:
        pass


def _insert_users(project_id: str, users_data: list[dict]) -> list[JiraUser]:
    """Insert users and commit immediately. Returns user objects with IDs."""
    db, gen = _get_db_session(project_id)
    try:
        user_objects = []
        for u in users_data:
            user = JiraUser(
                username=u.get("username", f"user_{len(user_objects)}"),
                full_name=u.get("full_name", "Unknown User"),
                email=u.get("email"),
                role=u.get("role", "developer"),
            )
            db.add(user)
            user_objects.append(user)
        db.commit()
        # Refresh to get IDs
        for u in user_objects:
            db.refresh(u)
        return user_objects
    except Exception:
        db.rollback()
        raise
    finally:
        _close_db(gen)


def _insert_stories(project_id: str, project_key: str, stories_data: list[dict], user_ids: list[int], start_index: int = 0) -> list[JiraStory]:
    """Insert stories and commit immediately. Returns story objects with IDs."""
    db, gen = _get_db_session(project_id)
    try:
        story_objects = []
        for idx, s in enumerate(stories_data):
            assignee_id = user_ids[s.get("assignee_index", 0) % len(user_ids)] if user_ids else None
            reporter_id = user_ids[s.get("reporter_index", 1) % len(user_ids)] if user_ids else None
            story = JiraStory(
                story_key=f"{project_key}-{start_index + idx + 1}",
                title=s.get("title", f"Story {start_index + idx + 1}"),
                description=s.get("description", ""),
                assignee_id=assignee_id,
                reporter_id=reporter_id,
                story_points=s.get("story_points", 3),
                priority=s.get("priority", "Medium"),
                sprint=s.get("sprint", "Sprint 1"),
                status=s.get("status", "Backlog"),
            )
            db.add(story)
            story_objects.append(story)
        db.commit()
        for s in story_objects:
            db.refresh(s)
        return story_objects
    except Exception:
        db.rollback()
        raise
    finally:
        _close_db(gen)


def _insert_bugs(project_id: str, project_key: str, bugs_data: list[dict], user_ids: list[int], story_ids: list[int]):
    """Insert bugs and commit immediately."""
    db, gen = _get_db_session(project_id)
    try:
        for idx, b in enumerate(bugs_data):
            assignee_id = user_ids[b.get("assignee_index", 0) % len(user_ids)] if user_ids else None
            reporter_id = user_ids[b.get("reporter_index", 2) % len(user_ids)] if user_ids else None
            related_story_id = story_ids[b.get("related_story_index", 0) % len(story_ids)] if story_ids else None
            bug = JiraBug(
                bug_key=f"{project_key}-BUG-{idx + 1}",
                title=b.get("title", f"Bug {idx + 1}"),
                description=b.get("description", ""),
                assignee_id=assignee_id,
                reporter_id=reporter_id,
                severity=b.get("severity", "Medium"),
                status=b.get("status", "Open"),
                related_story_id=related_story_id,
            )
            db.add(bug)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        _close_db(gen)


def _insert_sprints(project_id: str, sprints_data: list[dict]):
    """Insert sprints and commit immediately."""
    db, gen = _get_db_session(project_id)
    try:
        for sp in sprints_data:
            sprint = JiraSprint(
                sprint_name=sp.get("sprint_name", f"Sprint {1}"),
                goal=sp.get("goal", ""),
                velocity=sp.get("velocity", 20),
                completed_stories=sp.get("completed_stories", 3),
                total_stories=sp.get("total_stories", 6),
                status=sp.get("status", "Active"),
            )
            db.add(sprint)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        _close_db(gen)


def _insert_incidents(project_id: str, project_key: str, incidents_data: list[dict]):
    """Insert incidents and commit immediately."""
    db, gen = _get_db_session(project_id)
    try:
        for idx, inc in enumerate(incidents_data):
            incident = ServiceNowIncident(
                incident_id=f"{project_key}-INC-{idx + 1:03d}",
                title=inc.get("title", f"Incident {idx + 1}"),
                description=inc.get("description", ""),
                severity=inc.get("severity", "Medium"),
                status=inc.get("status", "Active"),
                assigned_group=inc.get("assigned_group", "Platform"),
                created_at=datetime.utcnow() - timedelta(days=idx),
            )
            db.add(incident)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        _close_db(gen)


def _insert_deployments(project_id: str, project_key: str, deployments_data: list[dict]):
    """Insert deployments and commit immediately."""
    db, gen = _get_db_session(project_id)
    try:
        for idx, dep in enumerate(deployments_data):
            deployment = ServiceNowDeployment(
                deployment_id=f"{project_key}-DEP-{idx + 1:03d}",
                feature_name=dep.get("feature_name", f"Feature {idx + 1}"),
                version=dep.get("version", f"v1.{idx}.0"),
                environment=dep.get("environment", "production"),
                status=dep.get("status", "Deployed"),
                deployed_by=dep.get("deployed_by", "engineering"),
                deployed_at=datetime.utcnow() - timedelta(hours=idx * 12),
            )
            db.add(deployment)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        _close_db(gen)


def _insert_logs(project_id: str, logs_data: list[dict], time_offset: int = 0):
    """Insert logs and commit immediately."""
    db, gen = _get_db_session(project_id)
    try:
        for idx, log in enumerate(logs_data):
            splunk_log = SplunkLog(
                source=log.get("source", "app-service"),
                level=log.get("level", "INFO"),
                message=log.get("message", f"Log entry {time_offset + idx + 1}"),
                service=log.get("service", "app-service"),
                timestamp=datetime.utcnow() - timedelta(minutes=(time_offset + idx) * 5),
            )
            db.add(splunk_log)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        _close_db(gen)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def generate_mock_data(project_id: str, project_info: dict[str, Any]) -> dict[str, Any]:
    """Generate and insert mock data for a project using chunked LLM calls.

    Makes multiple small LLM calls (5 records each) and commits to DB
    immediately after each batch. This avoids timeouts and ensures partial
    data is saved even if a later call fails.

    Args:
        project_id: The project's slug ID.
        project_info: Dict with keys: name, key, description_goal, description_users,
                      description_purpose, domain.

    Returns:
        Dict with "success", "counts", and optionally "error".
    """
    project_key = project_info.get("key", "PROJ")
    domain = project_info.get("domain", "other")

    if not settings.ONE_MIN_AI_API_KEY:
        return {
            "success": False,
            "error": "LLM API key not configured. Set ONE_MIN_AI_API_KEY or LLM_API_KEY in .env",
            "counts": {},
        }

    # Initialize project DB
    init_project_db(project_id)

    context = _PROJECT_CONTEXT.format(
        name=project_info.get("name", ""),
        key=project_key,
        domain=domain,
        goal=project_info.get("description_goal", ""),
        users=project_info.get("description_users", ""),
        purpose=project_info.get("description_purpose", ""),
    )
    system_msg = f"You are a JSON data generator. Return only valid JSON arrays.\n\n{context}"

    counts = {
        "users": 0,
        "stories": 0,
        "bugs": 0,
        "sprints": 0,
        "incidents": 0,
        "deployments": 0,
        "logs": 0,
    }
    errors = []

    # --- Step 1: Users (5) ---
    try:
        raw = await _call_llm(system_msg, _PROMPT_USERS)
        users_data = _extract_json(raw)
        user_objects = _insert_users(project_id, users_data)
        user_ids = [u.id for u in user_objects]
        counts["users"] = len(user_objects)
    except Exception as exc:
        errors.append(f"Users: [{type(exc).__name__}] {exc}")
        user_ids = []

    # --- Step 2: Stories batch 1 (5) ---
    story_ids = []
    try:
        raw = await _call_llm(system_msg, _PROMPT_STORIES.format(domain=domain))
        stories_data = _extract_json(raw)
        story_objects = _insert_stories(project_id, project_key, stories_data, user_ids, start_index=0)
        story_ids.extend([s.id for s in story_objects])
        counts["stories"] += len(story_objects)
    except Exception as exc:
        errors.append(f"Stories batch 1: [{type(exc).__name__}] {exc}")

    # --- Step 3: Stories batch 2 (5) ---
    try:
        raw = await _call_llm(system_msg, _PROMPT_STORIES.format(domain=domain))
        stories_data = _extract_json(raw)
        story_objects = _insert_stories(project_id, project_key, stories_data, user_ids, start_index=5)
        story_ids.extend([s.id for s in story_objects])
        counts["stories"] += len(story_objects)
    except Exception as exc:
        errors.append(f"Stories batch 2: [{type(exc).__name__}] {exc}")

    # --- Step 4: Bugs (5) ---
    try:
        raw = await _call_llm(system_msg, _PROMPT_BUGS.format(domain=domain))
        bugs_data = _extract_json(raw)
        _insert_bugs(project_id, project_key, bugs_data, user_ids, story_ids)
        counts["bugs"] = len(bugs_data)
    except Exception as exc:
        errors.append(f"Bugs: [{type(exc).__name__}] {exc}")

    # --- Step 5: Sprints (2) ---
    try:
        raw = await _call_llm(system_msg, _PROMPT_SPRINTS)
        sprints_data = _extract_json(raw)
        _insert_sprints(project_id, sprints_data)
        counts["sprints"] = len(sprints_data)
    except Exception as exc:
        errors.append(f"Sprints: [{type(exc).__name__}] {exc}")

    # --- Step 6: Incidents (5) ---
    try:
        raw = await _call_llm(system_msg, _PROMPT_INCIDENTS.format(domain=domain))
        incidents_data = _extract_json(raw)
        _insert_incidents(project_id, project_key, incidents_data)
        counts["incidents"] = len(incidents_data)
    except Exception as exc:
        errors.append(f"Incidents: [{type(exc).__name__}] {exc}")

    # --- Step 7: Deployments (5) ---
    try:
        raw = await _call_llm(system_msg, _PROMPT_DEPLOYMENTS.format(domain=domain))
        deployments_data = _extract_json(raw)
        _insert_deployments(project_id, project_key, deployments_data)
        counts["deployments"] = len(deployments_data)
    except Exception as exc:
        errors.append(f"Deployments: [{type(exc).__name__}] {exc}")

    # --- Step 8-10: Logs in 3 batches of 5 (INFO, WARN, ERROR) ---
    log_batches = [
        ("INFO", 0),
        ("WARN", 5),
        ("ERROR", 10),
    ]
    for level, offset in log_batches:
        try:
            prompt = _PROMPT_LOGS.format(domain=domain, level=level)
            raw = await _call_llm(system_msg, prompt)
            logs_data = _extract_json(raw)
            _insert_logs(project_id, logs_data, time_offset=offset)
            counts["logs"] += len(logs_data)
        except Exception as exc:
            errors.append(f"Logs ({level}): [{type(exc).__name__}] {exc}")

    # --- Result ---
    if errors and counts["users"] == 0:
        # Total failure — nothing was generated
        return {
            "success": False,
            "error": "; ".join(errors),
            "counts": counts,
        }

    if errors:
        # Partial success — some batches failed but data was saved
        return {
            "success": True,
            "counts": counts,
            "warnings": errors,
        }

    return {"success": True, "counts": counts}


def wipe_project_data(project_id: str) -> None:
    """Delete all data from a project's database tables (preserves schema)."""
    init_project_db(project_id)
    gen = get_project_db(project_id)
    db = next(gen)
    try:
        db.query(JiraBug).delete()
        db.query(JiraStory).delete()
        db.query(JiraSprint).delete()
        db.query(JiraUser).delete()
        db.query(ServiceNowIncident).delete()
        db.query(ServiceNowDeployment).delete()
        db.query(SplunkLog).delete()
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        try:
            next(gen)
        except StopIteration:
            pass


# ---------------------------------------------------------------------------
# Legacy compatibility — used by tests with pre-built data dicts
# ---------------------------------------------------------------------------


def _insert_data(project_id: str, project_key: str, data: dict[str, Any]) -> dict[str, int]:
    """Insert a complete data dict into the project's database (single transaction).

    Used by tests that provide pre-built mock data. For LLM generation,
    use generate_mock_data() which does chunked inserts.
    """
    init_project_db(project_id)
    gen = get_project_db(project_id)
    db = next(gen)

    counts = {"users": 0, "stories": 0, "bugs": 0, "sprints": 0, "incidents": 0, "deployments": 0, "logs": 0}

    try:
        # Users
        users_data = data.get("users", [])
        user_objects = []
        for u in users_data:
            user = JiraUser(username=u.get("username", f"user_{counts['users']}"), full_name=u.get("full_name", "Unknown"), email=u.get("email"), role=u.get("role", "developer"))
            db.add(user)
            user_objects.append(user)
            counts["users"] += 1
        db.flush()

        # Stories
        stories_data = data.get("stories", [])
        story_objects = []
        for idx, s in enumerate(stories_data):
            assignee_idx = s.get("assignee_index", 0) % len(user_objects) if user_objects else 0
            reporter_idx = s.get("reporter_index", 1) % len(user_objects) if user_objects else 0
            story = JiraStory(story_key=f"{project_key}-{idx + 1}", title=s.get("title", f"Story {idx + 1}"), description=s.get("description", ""), assignee_id=user_objects[assignee_idx].id if user_objects else None, reporter_id=user_objects[reporter_idx].id if user_objects else None, story_points=s.get("story_points", 3), priority=s.get("priority", "Medium"), sprint=s.get("sprint", "Sprint 1"), status=s.get("status", "Backlog"))
            db.add(story)
            story_objects.append(story)
            counts["stories"] += 1
        db.flush()

        # Bugs
        for idx, b in enumerate(data.get("bugs", [])):
            assignee_idx = b.get("assignee_index", 0) % len(user_objects) if user_objects else 0
            reporter_idx = b.get("reporter_index", 2) % len(user_objects) if user_objects else 0
            related_story_idx = b.get("related_story_index", 0) % len(story_objects) if story_objects else 0
            db.add(JiraBug(bug_key=f"{project_key}-BUG-{idx + 1}", title=b.get("title", f"Bug {idx + 1}"), description=b.get("description", ""), assignee_id=user_objects[assignee_idx].id if user_objects else None, reporter_id=user_objects[reporter_idx].id if user_objects else None, severity=b.get("severity", "Medium"), status=b.get("status", "Open"), related_story_id=story_objects[related_story_idx].id if story_objects else None))
            counts["bugs"] += 1

        # Sprints
        for sp in data.get("sprints", []):
            db.add(JiraSprint(sprint_name=sp.get("sprint_name", "Sprint 1"), goal=sp.get("goal", ""), velocity=sp.get("velocity", 20), completed_stories=sp.get("completed_stories", 3), total_stories=sp.get("total_stories", 6), status=sp.get("status", "Active")))
            counts["sprints"] += 1

        # Incidents
        for idx, inc in enumerate(data.get("incidents", [])):
            db.add(ServiceNowIncident(incident_id=f"{project_key}-INC-{idx + 1:03d}", title=inc.get("title", f"Incident {idx + 1}"), description=inc.get("description", ""), severity=inc.get("severity", "Medium"), status=inc.get("status", "Active"), assigned_group=inc.get("assigned_group", "Platform"), created_at=datetime.utcnow() - timedelta(days=idx)))
            counts["incidents"] += 1

        # Deployments
        for idx, dep in enumerate(data.get("deployments", [])):
            db.add(ServiceNowDeployment(deployment_id=f"{project_key}-DEP-{idx + 1:03d}", feature_name=dep.get("feature_name", f"Feature {idx + 1}"), version=dep.get("version", f"v1.{idx}.0"), environment=dep.get("environment", "production"), status=dep.get("status", "Deployed"), deployed_by=dep.get("deployed_by", "engineering"), deployed_at=datetime.utcnow() - timedelta(hours=idx * 12)))
            counts["deployments"] += 1

        # Logs
        for idx, log in enumerate(data.get("logs", [])):
            db.add(SplunkLog(source=log.get("source", "app-service"), level=log.get("level", "INFO"), message=log.get("message", f"Log {idx + 1}"), service=log.get("service", "app-service"), timestamp=datetime.utcnow() - timedelta(minutes=idx * 5)))
            counts["logs"] += 1

        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        try:
            next(gen)
        except StopIteration:
            pass

    return counts
