"""
Intelligent correlation engine for cross-agent data analysis.
This module synthesizes insights from multiple agents before generating responses.
"""
from typing import Any
from collections import defaultdict


class CorrelationEngine:
    """Correlates and analyzes data from multiple agents to derive insights."""
    
    def __init__(self):
        self.insights: dict[str, Any] = {}
    
    def correlate_contexts(self, contexts: list[dict[str, Any]]) -> dict[str, Any]:
        """
        Perform intelligent correlation across all agent contexts.
        Returns enriched insights for the orchestrator to use.
        """
        # Extract data from each agent
        jira_data = self._extract_jira_data(contexts)
        servicenow_data = self._extract_servicenow_data(contexts)
        splunk_data = self._extract_splunk_data(contexts)
        
        # Perform cross-agent correlation
        insights = {
            "summary": self._generate_summary(jira_data, servicenow_data, splunk_data),
            "correlations": self._find_correlations(jira_data, servicenow_data, splunk_data),
            "gaps": self._identify_gaps(jira_data, servicenow_data, splunk_data),
            "priorities": self._calculate_priorities(jira_data, servicenow_data, splunk_data),
            "health_score": self._calculate_health_score(jira_data, servicenow_data, splunk_data),
            "recommendations": self._generate_recommendations(jira_data, servicenow_data, splunk_data),
        }
        
        self.insights = insights
        return insights
    
    def _extract_jira_data(self, contexts: list[dict[str, Any]]) -> dict[str, Any]:
        """Extract and structure JIRA data."""
        jira_context = next((c for c in contexts if c.get("source") == "JIRA"), None)
        if not jira_context or not jira_context.get("success"):
            return {"stories": [], "bugs": [], "summary": {}}
        
        data = jira_context.get("data", {})
        summary = jira_context.get("summary", {})
        
        return {
            "stories": data.get("items", []),
            "summary": summary,
            "success": True,
        }
    
    def _extract_servicenow_data(self, contexts: list[dict[str, Any]]) -> dict[str, Any]:
        """Extract and structure ServiceNow data."""
        sn_context = next((c for c in contexts if c.get("source") == "ServiceNow"), None)
        if not sn_context or not sn_context.get("success"):
            return {"incidents": [], "deployments": []}
        
        data = sn_context.get("data", {})
        
        # Handle both executive overview format and regular format
        if isinstance(data, dict) and "deployments" in data:
            return {
                "incidents": data.get("incidents", []),
                "deployments": data.get("deployments", []),
                "success": True,
            }
        else:
            return {
                "incidents": data.get("items", []),
                "deployments": [],
                "success": True,
            }
    
    def _extract_splunk_data(self, contexts: list[dict[str, Any]]) -> dict[str, Any]:
        """Extract and structure Splunk data."""
        splunk_context = next((c for c in contexts if c.get("source") == "Splunk"), None)
        if not splunk_context or not splunk_context.get("success"):
            return {"logs": [], "errors": [], "warnings": []}
        
        data = splunk_context.get("data", {})
        logs = data.get("items", [])
        
        # Categorize logs by level
        errors = [log for log in logs if log.get("level", "").upper() == "ERROR"]
        warnings = [log for log in logs if log.get("level", "").upper() == "WARN"]
        infos = [log for log in logs if log.get("level", "").upper() == "INFO"]
        
        # Categorize errors by theme
        error_themes = self._categorize_errors(errors)
        
        return {
            "logs": logs,
            "errors": errors,
            "warnings": warnings,
            "infos": infos,
            "error_themes": error_themes,
            "success": True,
        }
    
    def _categorize_errors(self, errors: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
        """Categorize errors by theme based on message content."""
        themes = defaultdict(list)
        
        for error in errors:
            message = error.get("message", "").lower()
            
            if "timeout" in message or "502" in message:
                themes["gateway_timeout"].append(error)
            elif "pool" in message or "connection" in message:
                themes["connection_pool"].append(error)
            elif "retry" in message or "queue" in message:
                themes["retry_capacity"].append(error)
            elif "fraud" in message:
                themes["fraud_scoring"].append(error)
            elif "reconciliation" in message or "balance" in message or "mismatch" in message:
                themes["reconciliation"].append(error)
            elif "latency" in message:
                themes["latency"].append(error)
            else:
                themes["other"].append(error)
        
        return dict(themes)
    
    def _generate_summary(self, jira_data: dict, servicenow_data: dict, splunk_data: dict) -> dict[str, Any]:
        """Generate high-level summary statistics."""
        stories = jira_data.get("stories", [])
        incidents = servicenow_data.get("incidents", [])
        deployments = servicenow_data.get("deployments", [])
        errors = splunk_data.get("errors", [])
        logs = splunk_data.get("logs", [])
        
        return {
            "total_stories": len(stories),
            "completed_stories": sum(1 for s in stories if s.get("status", "").lower() == "done"),
            "in_progress_stories": sum(1 for s in stories if s.get("status", "").lower() == "in progress"),
            "total_incidents": len(incidents),
            "active_incidents": sum(1 for i in incidents if i.get("status", "").lower() in {"new", "active", "monitoring"}),
            "total_deployments": len(deployments),
            "total_logs": len(logs),
            "total_errors": len(errors),
            "error_rate": (len(errors) / len(logs) * 100) if logs else 0,
        }
    
    def _find_correlations(self, jira_data: dict, servicenow_data: dict, splunk_data: dict) -> list[dict[str, Any]]:
        """Find correlations between errors, incidents, and stories."""
        correlations = []
        
        errors = splunk_data.get("errors", [])
        error_themes = splunk_data.get("error_themes", {})
        stories = jira_data.get("stories", [])
        incidents = servicenow_data.get("incidents", [])
        
        # Uncovered error themes are reported as gaps below, so they should not
        # also be emitted as correlations.

        # Correlation 1: Active incidents linked to production errors
        seen_incidents = set()
        for incident in incidents:
            if incident.get("status", "").lower() not in {"active", "new", "monitoring"}:
                continue
            
            incident_title = incident.get("title", "").lower()
            related_errors = [
                error for error in errors
                if self._error_relates_to_incident(error, incident)
            ]
            
            incident_key = incident.get("incident_id") or incident_title
            if related_errors and incident_key not in seen_incidents:
                seen_incidents.add(incident_key)
                correlations.append({
                    "type": "incident_with_errors",
                    "incident_id": incident.get("incident_id"),
                    "incident_title": incident.get("title"),
                    "related_errors": len(related_errors),
                    "severity": incident.get("severity", "Medium"),
                    "recommendation": "Investigate error logs for root cause",
                })
        
        # Correlation 2: Stories without test coverage for recurring errors
        for story in stories:
            if story.get("status", "").lower() == "done":
                story_theme = self._extract_theme_from_story(story)
                if story_theme and story_theme in error_themes:
                    theme_errors = error_themes[story_theme]
                    if len(theme_errors) > 0:
                        correlations.append({
                            "type": "completed_story_with_errors",
                            "story_key": story.get("story_key"),
                            "story_title": story.get("title"),
                            "error_count": len(theme_errors),
                            "severity": "high",
                            "recommendation": "Story may need additional work or error indicates regression",
                        })
        
        return correlations
    
    def _identify_gaps(self, jira_data: dict, servicenow_data: dict, splunk_data: dict) -> list[dict[str, Any]]:
        """Identify gaps in coverage, testing, or monitoring."""
        gaps = []
        
        error_themes = splunk_data.get("error_themes", {})
        stories = jira_data.get("stories", [])
        
        # Gap 1: Error themes without JIRA coverage
        for theme, theme_errors in error_themes.items():
            if theme == "other" or len(theme_errors) == 0:
                continue
            
            has_coverage = any(
                self._theme_matches_story(theme, story)
                for story in stories
            )
            
            if not has_coverage:
                gaps.append({
                    "type": "uncovered_errors",
                    "theme": theme.replace("_", " ").title(),
                    "error_count": len(theme_errors),
                    "impact": "high" if len(theme_errors) >= 3 else "medium",
                    "action": f"Create story to address {theme.replace('_', ' ')} reliability",
                })
        
        # Gap 2: Critical incidents without JIRA bug tracking
        incidents = servicenow_data.get("incidents", [])
        for incident in incidents:
            if incident.get("severity", "").lower() == "critical":
                # Check if there's a corresponding bug or story
                incident_id = incident.get("incident_id", "")
                has_jira_item = any(
                    story.get("description", "").find(incident_id) >= 0
                    for story in stories
                )
                
                if not has_jira_item:
                    gaps.append({
                        "type": "incident_without_jira",
                        "incident_id": incident_id,
                        "incident_title": incident.get("title"),
                        "impact": "critical",
                        "action": "Create JIRA bug to track resolution",
                    })
        
        # Gap 3: High error rate without monitoring stories
        summary = self._generate_summary(jira_data, servicenow_data, splunk_data)
        if summary["error_rate"] > 40:  # More than 40% errors
            has_monitoring_story = any(
                "monitor" in story.get("title", "").lower() or
                "observability" in story.get("description", "").lower()
                for story in stories
            )
            
            if not has_monitoring_story:
                gaps.append({
                    "type": "insufficient_monitoring",
                    "error_rate": summary["error_rate"],
                    "impact": "high",
                    "action": "Add observability and monitoring stories to backlog",
                })
        
        return gaps
    
    def _calculate_priorities(self, jira_data: dict, servicenow_data: dict, splunk_data: dict) -> list[dict[str, Any]]:
        """Calculate priority recommendations based on correlated data."""
        priorities = []
        
        error_themes = splunk_data.get("error_themes", {})
        stories = jira_data.get("stories", [])
        incidents = servicenow_data.get("incidents", [])
        
        # Priority 1: Most frequent error themes without stories
        for theme, theme_errors in sorted(error_themes.items(), key=lambda x: len(x[1]), reverse=True):
            if theme == "other":
                continue
            
            has_story = any(self._theme_matches_story(theme, story) for story in stories)
            
            if not has_story and len(theme_errors) >= 2:
                priorities.append({
                    "rank": len(priorities) + 1,
                    "theme": theme.replace("_", " ").title(),
                    "reason": f"{len(theme_errors)} error occurrences",
                    "story_points_estimate": 8 if len(theme_errors) >= 5 else 5,
                    "suggested_priority": "High" if len(theme_errors) >= 5 else "Medium",
                })
        
        # Priority 2: Critical incidents
        for incident in incidents:
            if incident.get("severity", "").lower() == "critical":
                priorities.append({
                    "rank": 1,  # Critical incidents go to the top
                    "theme": "Active Critical Incident",
                    "reason": incident.get("title"),
                    "incident_id": incident.get("incident_id"),
                    "story_points_estimate": 13,
                    "suggested_priority": "Critical",
                })
        
        # Re-rank after critical incidents
        priorities.sort(key=lambda x: (0 if x["suggested_priority"] == "Critical" else 1, x.get("rank", 999)))
        for i, priority in enumerate(priorities, 1):
            priority["rank"] = i
        
        return priorities[:5]  # Return top 5 priorities
    
    def _calculate_health_score(self, jira_data: dict, servicenow_data: dict, splunk_data: dict) -> dict[str, Any]:
        """Calculate overall system health score."""
        summary = self._generate_summary(jira_data, servicenow_data, splunk_data)
        
        # Delivery health (0-100)
        delivery_score = 0
        if summary["total_stories"] > 0:
            completion_rate = summary["completed_stories"] / summary["total_stories"]
            delivery_score = min(100, completion_rate * 100)
        
        # Operations health (0-100)
        operations_score = 100
        if summary["total_incidents"] > 0:
            active_rate = summary["active_incidents"] / summary["total_incidents"]
            operations_score = max(0, 100 - (active_rate * 100))
        
        # Reliability health (0-100)
        reliability_score = max(0, 100 - summary["error_rate"])
        
        # Overall health (weighted average)
        overall_score = (delivery_score * 0.3 + operations_score * 0.3 + reliability_score * 0.4)
        
        # Determine health status
        if overall_score >= 80:
            status = "Healthy"
            status_emoji = "[GREEN]"
        elif overall_score >= 60:
            status = "Warning"
            status_emoji = "[YELLOW]"
        else:
            status = "Critical"
            status_emoji = "[RED]"
        
        return {
            "overall_score": round(overall_score, 1),
            "status": status,
            "status_emoji": status_emoji,
            "delivery_score": round(delivery_score, 1),
            "operations_score": round(operations_score, 1),
            "reliability_score": round(reliability_score, 1),
        }
    
    def _generate_recommendations(self, jira_data: dict, servicenow_data: dict, splunk_data: dict) -> list[str]:
        """Generate actionable recommendations based on all insights."""
        recommendations = []
        
        gaps = self._identify_gaps(jira_data, servicenow_data, splunk_data)
        priorities = self._calculate_priorities(jira_data, servicenow_data, splunk_data)
        health = self._calculate_health_score(jira_data, servicenow_data, splunk_data)
        
        # Recommendation based on health
        if health["overall_score"] < 60:
            recommendations.append(
                f"System health is {health['status']}. Immediate focus required on production stability."
            )
        
        # Recommendations from gaps
        critical_gaps = [g for g in gaps if g.get("impact") == "critical"]
        if critical_gaps:
            recommendations.append(
                f"Address {len(critical_gaps)} critical gaps: {', '.join(g.get('theme', g.get('incident_id', 'unknown')) for g in critical_gaps[:3])}"
            )
        
        # Recommendations from priorities
        if priorities:
            top_priority = priorities[0]
            recommendations.append(
                f"Top priority: {top_priority['theme']} ({top_priority['reason']})"
            )
        
        # Reliability recommendation
        if health["reliability_score"] < 70:
            recommendations.append(
                f"Reliability score is {health['reliability_score']}%. Prioritize error reduction and monitoring improvements."
            )
        
        # Delivery recommendation
        summary = self._generate_summary(jira_data, servicenow_data, splunk_data)
        if summary["in_progress_stories"] > summary["completed_stories"] * 2:
            recommendations.append(
                "High work-in-progress. Consider limiting parallel work to improve flow."
            )
        
        return recommendations[:5]  # Top 5 recommendations
    
    # Helper methods
    
    def _theme_matches_story(self, theme: str, story: dict[str, Any]) -> bool:
        """Check if a story addresses a particular error theme."""
        story_text = f"{story.get('title', '')} {story.get('description', '')}".lower()
        
        theme_keywords = {
            "gateway_timeout": ["timeout", "gateway", "failover", "provider"],
            "connection_pool": ["connection", "pool", "capacity", "database"],
            "retry_capacity": ["retry", "backoff", "queue", "capacity"],
            "fraud_scoring": ["fraud", "scoring", "risk"],
            "reconciliation": ["reconciliation", "balance", "settlement", "mismatch"],
            "latency": ["latency", "performance", "slow", "response time"],
        }
        
        keywords = theme_keywords.get(theme, [])
        return any(keyword in story_text for keyword in keywords)
    
    def _error_relates_to_incident(self, error: dict[str, Any], incident: dict[str, Any]) -> bool:
        """Check if an error is related to an incident."""
        error_message = error.get("message", "").lower()
        incident_title = incident.get("title", "").lower()
        incident_desc = incident.get("description", "").lower()
        
        # Simple keyword matching
        error_keywords = set(error_message.split())
        incident_keywords = set((incident_title + " " + incident_desc).split())
        
        common_keywords = error_keywords & incident_keywords
        significant_keywords = {k for k in common_keywords if len(k) > 4}
        
        return len(significant_keywords) >= 2
    
    def _extract_theme_from_story(self, story: dict[str, Any]) -> str | None:
        """Extract the primary theme from a story."""
        story_text = f"{story.get('title', '')} {story.get('description', '')}".lower()
        
        if any(kw in story_text for kw in ["timeout", "gateway", "502"]):
            return "gateway_timeout"
        elif any(kw in story_text for kw in ["pool", "connection", "capacity"]):
            return "connection_pool"
        elif any(kw in story_text for kw in ["retry", "queue"]):
            return "retry_capacity"
        elif "fraud" in story_text:
            return "fraud_scoring"
        elif any(kw in story_text for kw in ["reconciliation", "balance", "settlement"]):
            return "reconciliation"
        elif "latency" in story_text:
            return "latency"
        
        return None
    
    def format_insights_for_llm(self) -> str:
        """Format insights in a structured way for LLM consumption."""
        if not self.insights:
            return "No insights available."
        
        parts = []
        
        # Summary
        summary = self.insights.get("summary", {})
        parts.append("SUMMARY:")
        parts.append(f"- Stories: {summary.get('total_stories')} total, {summary.get('completed_stories')} done, {summary.get('in_progress_stories')} in progress")
        parts.append(f"- Incidents: {summary.get('total_incidents')} total, {summary.get('active_incidents')} active")
        parts.append(f"- Errors: {summary.get('total_errors')} errors in {summary.get('total_logs')} logs ({summary.get('error_rate', 0):.1f}% error rate)")
        parts.append("")
        
        # Health Score
        health = self.insights.get("health_score", {})
        parts.append(f"HEALTH SCORE: {health.get('overall_score')}% {health.get('status_emoji')} ({health.get('status')})")
        parts.append(f"- Delivery: {health.get('delivery_score')}%")
        parts.append(f"- Operations: {health.get('operations_score')}%")
        parts.append(f"- Reliability: {health.get('reliability_score')}%")
        parts.append("")
        
        # Correlations
        correlations = self.insights.get("correlations", [])
        if correlations:
            parts.append(f"CORRELATIONS ({len(correlations)} found):")
            for corr in correlations[:5]:
                detail = corr.get("recommendation", "")
                if corr.get("incident_id") or corr.get("incident_title"):
                    incident = corr.get("incident_id") or "Incident"
                    title = corr.get("incident_title")
                    detail = f"{incident} ({title}) - {detail}" if title else f"{incident} - {detail}"
                parts.append(f"- {corr.get('type')}: {detail}")
            parts.append("")
        
        # Gaps
        gaps = self.insights.get("gaps", [])
        if gaps:
            parts.append(f"GAPS ({len(gaps)} identified):")
            for gap in gaps[:5]:
                parts.append(f"- [{gap.get('impact', 'unknown').upper()}] {gap.get('action', '')}")
            parts.append("")
        
        # Priorities
        priorities = self.insights.get("priorities", [])
        if priorities:
            parts.append("TOP PRIORITIES:")
            for priority in priorities[:5]:
                parts.append(f"{priority.get('rank')}. {priority.get('theme')} - {priority.get('reason')} ({priority.get('suggested_priority')} priority, ~{priority.get('story_points_estimate')} points)")
            parts.append("")
        
        # Recommendations
        recommendations = self.insights.get("recommendations", [])
        if recommendations:
            parts.append("RECOMMENDATIONS:")
            for i, rec in enumerate(recommendations, 1):
                parts.append(f"{i}. {rec}")
        
        return "\n".join(parts)
