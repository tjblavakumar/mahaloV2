from __future__ import annotations

from typing import Any, Dict

import httpx


class JiraMCPTools:
    def __init__(self, jira_api_url: str = "http://localhost:5001"):
        self.jira_api_url = jira_api_url

    async def close(self):
        pass  # No client to close

    def _build_headers(self, arguments: Dict[str, Any]) -> Dict[str, str]:
        """Extract project_id from arguments and build headers dict."""
        headers = {}
        project_id = arguments.pop("project_id", None)
        if project_id:
            headers["X-Project-ID"] = project_id
        return headers

    async def create_story_handler(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        try:
            headers = self._build_headers(arguments)
            async with httpx.AsyncClient(timeout=10.0, trust_env=True) as client:
                response = await client.post(
                    f"{self.jira_api_url}/api/jira/stories",
                    json=arguments,
                    headers=headers,
                )
                response.raise_for_status()
                return {"success": True, "data": response.json()}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    async def search_stories_handler(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        try:
            headers = self._build_headers(arguments)
            async with httpx.AsyncClient(timeout=10.0, trust_env=True) as client:
                response = await client.get(
                    f"{self.jira_api_url}/api/jira/stories",
                    headers=headers,
                )
                response.raise_for_status()
                payload = response.json()
            query = str(arguments.get("query", "")).strip().lower()
            if query:
                terms = [term for term in query.split() if len(term) > 2]
                items = [
                    item for item in payload.get("items", [])
                    if any(
                        term in " ".join(
                            str(item.get(field, ""))
                            for field in ("story_key", "title", "description", "status", "sprint")
                        ).lower()
                        for term in terms
                    )
                ]
                payload = {**payload, "items": items}
            return {"success": True, "data": payload}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    async def get_story_handler(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        story_key = arguments.get("story_key")
        headers = self._build_headers(arguments)
        try:
            async with httpx.AsyncClient(timeout=10.0, trust_env=True) as client:
                response = await client.get(
                    f"{self.jira_api_url}/api/jira/stories/{story_key}",
                    headers=headers,
                )
                response.raise_for_status()
                return {"success": True, "data": response.json()}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    async def list_bugs_handler(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        try:
            headers = self._build_headers(arguments)
            async with httpx.AsyncClient(timeout=10.0, trust_env=True) as client:
                response = await client.get(
                    f"{self.jira_api_url}/api/jira/bugs",
                    headers=headers,
                )
                response.raise_for_status()
                payload = response.json()
            query = str(arguments.get("query", "")).strip().lower()
            if query:
                terms = [term for term in query.split() if len(term) > 2]
                items = [
                    item for item in payload.get("items", [])
                    if any(
                        term in " ".join(str(item.get(field, "")) for field in (
                            "bug_key", "title", "description", "severity", "status", "assignee_username", "related_story_key"
                        )).lower()
                        for term in terms
                    )
                ]
                payload = {**payload, "items": items}
            return {"success": True, "data": payload}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    async def update_story_handler(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        story_key = arguments.pop("story_key", None)
        if not story_key:
            return {"success": False, "error": "story_key is required"}
        headers = self._build_headers(arguments)
        try:
            async with httpx.AsyncClient(timeout=10.0, trust_env=True) as client:
                response = await client.patch(
                    f"{self.jira_api_url}/api/jira/stories/{story_key}",
                    json=arguments,
                    headers=headers,
                )
                response.raise_for_status()
                return {"success": True, "data": response.json()}
        except Exception as exc:
            return {"success": False, "error": str(exc)}
