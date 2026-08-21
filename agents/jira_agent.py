from typing import Any
import re

from mcp_servers.jira_mcp.tools import JiraMCPTools


class JiraAgent:
    def __init__(self, tools: JiraMCPTools | None = None):
        self.tools = tools or JiraMCPTools()

    async def retrieve_context(self, query: str, project_id: str | None = None) -> dict[str, Any]:
        query_lower = query.lower()
        story_match = re.search(r"\bstory[- ]?(\d+)\b", query_lower)
        if story_match:
            story_key = f"STORY-{story_match.group(1)}"
            result = await self.tools.get_story_handler({"story_key": story_key, "project_id": project_id})
            return {"source": "JIRA", "query": query, "story_key": story_key, "record_type": "story_detail", **result}
        
        if "bug" in query_lower or "bugs" in query_lower:
            result = await self.tools.list_bugs_handler({"query": "", "project_id": project_id})
            if result.get("success"):
                bugs = result.get("data", {}).get("items", [])
                result["summary"] = {
                    "total_bugs": len(bugs),
                    "open_bugs": sum(bug.get("status", "").lower() in {"open", "in progress"} for bug in bugs),
                    "critical_bugs": sum(bug.get("severity", "").lower() == "critical" for bug in bugs),
                }
            return {"source": "JIRA", "query": query, "record_type": "bugs", **result}

        # Check if user wants all stories (summary/overview queries)
        get_all_stories = any(term in query_lower for term in (
            "velocity", "executive", "overview", "overall", "summary", "summarize",
            "all stories", "list stories", "show stories", "all", "everything"
        ))
        search_query = "" if get_all_stories else query
        result = await self.tools.search_stories_handler({"query": search_query, "project_id": project_id})
        if result.get("success"):
            stories = result.get("data", {}).get("items", [])
            completed = [story for story in stories if story.get("status", "").lower() == "done"]
            total_points = sum(story.get("story_points", 0) or 0 for story in stories)
            completed_points = sum(story.get("story_points", 0) or 0 for story in completed)
            result["summary"] = {
                "total_stories": len(stories),
                "completed_stories": len(completed),
                "in_progress_stories": sum(story.get("status") == "In Progress" for story in stories),
                "backlog_stories": sum(story.get("status") == "Backlog" for story in stories),
                "total_story_points": total_points,
                "completed_story_points": completed_points,
                "completion_percent": round((completed_points / total_points) * 100, 1) if total_points else 0,
            }
        return {"source": "JIRA", "query": query, **result}

    async def create_story(self, story: dict[str, Any], project_id: str | None = None) -> dict[str, Any]:
        """Create a story in JIRA, mapping rich orchestrator fields to backend-accepted schema."""
        payload = {
            "title": story.get("title", "Untitled Story"),
            "description": self._build_description(story),
            "story_points": story.get("story_points", 0),
            "priority": story.get("priority", "Medium"),
            "sprint": story.get("sprint"),
            "status": story.get("status", "Backlog"),
            "project_id": project_id,
        }
        # Only include optional fields if they have values
        if story.get("assignee_username"):
            payload["assignee_username"] = story["assignee_username"]
        if story.get("reporter_username"):
            payload["reporter_username"] = story["reporter_username"]
        return await self.tools.create_story_handler(payload)

    async def update_story(self, story_key: str, fields: dict[str, Any], project_id: str | None = None) -> dict[str, Any]:
        """Update an existing JIRA story with the given fields."""
        return await self.tools.update_story_handler({"story_key": story_key, "project_id": project_id, **fields})

    @staticmethod
    def _build_description(story: dict[str, Any]) -> str:
        """Combine description, user_story, acceptance_criteria, and evidence into a single description string."""
        parts = []
        if story.get("description"):
            parts.append(story["description"])
        if story.get("user_story"):
            parts.append(f"\nUser Story: {story['user_story']}")
        if story.get("acceptance_criteria"):
            parts.append("\nAcceptance Criteria:")
            for criterion in story["acceptance_criteria"]:
                parts.append(f"- {criterion}")
        if story.get("evidence"):
            parts.append("\nEvidence:")
            for item in story["evidence"]:
                if item:  # Skip empty evidence items
                    parts.append(f"- {item}")
        return "\n".join(parts) if parts else "No description provided."

    def process_query(self, query: str) -> str:
        return "JIRA Agent: I would inspect payment stories, sprint status, and backlog."
