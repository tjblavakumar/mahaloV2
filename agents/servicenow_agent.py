from typing import Any

from mcp_servers.servicenow_mcp.tools import ServiceNowMCPTools


class ServiceNowAgent:
    def __init__(self, tools: ServiceNowMCPTools | None = None):
        self.tools = tools or ServiceNowMCPTools()

    async def retrieve_context(self, query: str, project_id: str | None = None) -> dict[str, Any]:
        query_lower = query.lower()
        
        # Check for executive/overview requests (get all data)
        get_all_data = any(term in query_lower for term in (
            "executive", "overview", "overall", "summary", "summarize", "all"
        ))
        
        if get_all_data:
            deployments = await self.tools.list_deployments_handler({"environment": "production", "project_id": project_id})
            incidents = await self.tools.list_incidents_handler({"query": "", "project_id": project_id})
            return {
                "source": "ServiceNow",
                "record_type": "executive_overview",
                "query": query,
                "success": deployments.get("success") and incidents.get("success"),
                "data": {
                    "deployments": deployments.get("data", {}).get("items", []),
                    "incidents": incidents.get("data", {}).get("items", []),
                },
            }
        
        if "deploy" in query_lower or "production" in query_lower:
            result = await self.tools.list_deployments_handler({"environment": "production", "project_id": project_id})
            if result.get("success"):
                result["summary"] = {"deployment_count": len(result.get("data", {}).get("items", []))}
            return {"source": "ServiceNow", "record_type": "deployments", "query": query, **result}
        
        # For incident queries, check if user wants all incidents or filtered
        if any(term in query_lower for term in ("all incidents", "list incidents", "show incidents")):
            result = await self.tools.list_incidents_handler({"query": "", "project_id": project_id})
        else:
            result = await self.tools.list_incidents_handler({"query": query, "project_id": project_id})
        
        return {"source": "ServiceNow", "query": query, **result}

    def process_query(self, query: str) -> str:
        return "ServiceNow Agent: I would check incidents related to payment-service outages and latency."
