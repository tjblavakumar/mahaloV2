from __future__ import annotations

from typing import Any, Dict

import httpx


class SplunkMCPTools:
    def __init__(self, api_url: str = "http://localhost:5003"):
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

    async def search_logs_handler(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        query = arguments.get("query", "")
        headers = self._build_headers(arguments)
        try:
            async with httpx.AsyncClient(timeout=10.0, trust_env=True) as client:
                response = await client.get(
                    f"{self.api_url}/api/splunk/search",
                    params={"query": query},
                    headers=headers,
                )
                response.raise_for_status()
                return {"success": True, "data": response.json()}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    async def list_logs_handler(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        headers = self._build_headers(arguments)
        try:
            async with httpx.AsyncClient(timeout=10.0, trust_env=True) as client:
                response = await client.get(
                    f"{self.api_url}/api/splunk/logs",
                    headers=headers,
                )
                response.raise_for_status()
                return {"success": True, "data": response.json()}
        except Exception as exc:
            return {"success": False, "error": str(exc)}
