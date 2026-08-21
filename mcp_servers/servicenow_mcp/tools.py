from __future__ import annotations

from typing import Any, Dict

import httpx


class ServiceNowMCPTools:
    def __init__(self, api_url: str = "http://localhost:5002"):
        self.api_url = api_url

    async def close(self):
        pass  # No client to close

    def _build_headers(self, arguments: Dict[str, Any]) -> Dict[str, str]:
        """Extract project_id from arguments and build headers dict."""
        headers = {}
        project_id = arguments.pop("project_id", None)
        if project_id:
            headers["X-Project-ID"] = project_id
        return headers

    async def list_incidents_handler(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        try:
            headers = self._build_headers(arguments)
            async with httpx.AsyncClient(timeout=10.0, trust_env=True) as client:
                response = await client.get(
                    f"{self.api_url}/api/servicenow/incidents",
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
                            for field in ("incident_id", "title", "description", "severity", "status")
                        ).lower()
                        for term in terms
                    )
                ]
                payload = {**payload, "items": items}
            return {"success": True, "data": payload}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    async def get_incident_handler(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        incident_id = arguments.get("incident_id")
        headers = self._build_headers(arguments)
        try:
            async with httpx.AsyncClient(timeout=10.0, trust_env=True) as client:
                response = await client.get(
                    f"{self.api_url}/api/servicenow/incidents/{incident_id}",
                    headers=headers,
                )
                response.raise_for_status()
                return {"success": True, "data": response.json()}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    async def list_deployments_handler(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        try:
            headers = self._build_headers(arguments)
            async with httpx.AsyncClient(timeout=10.0, trust_env=True) as client:
                response = await client.get(
                    f"{self.api_url}/api/servicenow/deployments",
                    params={"environment": arguments.get("environment", "production")},
                    headers=headers,
                )
                response.raise_for_status()
                return {"success": True, "data": response.json()}
        except Exception as exc:
            return {"success": False, "error": str(exc)}
