from typing import Any
from asyncio import gather
import re

from mcp_servers.splunk_mcp.tools import SplunkMCPTools


class SplunkAgent:
    def __init__(self, tools: SplunkMCPTools | None = None):
        self.tools = tools or SplunkMCPTools()

    async def retrieve_context(self, query: str, project_id: str | None = None) -> dict[str, Any]:
        query_lower = query.lower()
        overview_request = any(term in query_lower for term in ("executive", "overview", "overall update"))
        error_count_request = any(term in query_lower for term in ("error", "errors", "error logs", "failures"))
        count_request = any(term in query_lower for term in ("how many", "count", "number of"))
        story_from_logs_request = ("story" in query_lower or "stories" in query_lower) and error_count_request
        story_analysis_request = ("story" in query_lower or "stories" in query_lower or "feature" in query_lower) and any(
            term in query_lower for term in ("analyze", "analyse", "need", "more", "next", "focus", "recommend")
        ) and any(term in query_lower for term in ("log", "logs", "error", "errors", "quarter", "velocity"))
        ignored_terms = {
            "show", "find", "search", "logs", "log", "errors", "error", "for", "the", "and", "with",
            "based", "on", "help", "me", "create", "a", "user", "story", "stories", "to", "fix", "it", "please",
            "suggest", "suggestion", "suggestions", "few", "recommend", "recommendation", "recommendations",
        }
        words = re.findall(r"[a-z0-9_-]+", query_lower)
        terms = [term for term in words if len(term) > 2 and term not in ignored_terms]
        
        # For error-focused queries or summaries, retrieve all logs (don't search by terms)
        summary_request = any(term in query_lower for term in ("summary", "summarize", "all"))
        if overview_request or error_count_request or summary_request or story_from_logs_request or story_analysis_request:
            terms = []
        results = await gather(
            *(self.tools.search_logs_handler({"query": term, "project_id": project_id}) for term in (terms or [""])),
            return_exceptions=True,
        )
        items = []
        errors = []
        for result in results:
            if isinstance(result, Exception):
                errors.append(str(result))
                continue
            if result.get("success"):
                items.extend(result.get("data", {}).get("items", []))
            else:
                errors.append(result.get("error", "Unknown Splunk error"))
        unique_items = {item.get("id", repr(item)): item for item in items}.values()
        unique_items = list(unique_items)
        if error_count_request:
            unique_items = [item for item in unique_items if item.get("level", "").upper() == "ERROR"]
        response: dict[str, Any] = {"success": not errors, "data": {"items": unique_items}}
        if error_count_request:
            response["record_type"] = "error_logs"
            response["summary"] = {"error_count": len(unique_items)}
        if overview_request:
            response["record_type"] = "executive_overview"
            response["summary"] = {
                "total_logs": len(unique_items),
                "error_count": sum(item.get("level", "").upper() == "ERROR" for item in unique_items),
            }
        if errors:
            response["error"] = "; ".join(errors)
        return {"source": "Splunk", "query": query, **response}

    def process_query(self, query: str) -> str:
        return "Splunk Agent: I would search payment-service logs for errors, latency spikes, and anomalies."
