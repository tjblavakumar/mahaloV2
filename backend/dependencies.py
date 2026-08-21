"""Shared FastAPI dependencies for project-aware database routing."""

from __future__ import annotations

from fastapi import Request

from backend.database import get_db, get_project_db


def get_project_session(request: Request):
    """Resolve the correct database session based on X-Project-ID header.

    If the header is present, yields a session for that project's isolated DB.
    Otherwise, falls back to the legacy shared database (backward compat).
    """
    project_id = request.headers.get("X-Project-ID")
    if project_id:
        yield from get_project_db(project_id)
    else:
        yield from get_db()
