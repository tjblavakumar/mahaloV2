from __future__ import annotations

import json
import logging
import re
from typing import Any

from litellm import completion as _litellm_completion

from backend.config import settings
from backend.llm_adapter import completion as one_min_completion

logger = logging.getLogger(__name__)


INTENT_SCHEMA = {
    "intent": (
        "One of: greeting, executive_overview, analyze_errors, suggest_features, suggest_work_item, "
        "count_deployments, check_velocity, story_detail, create_story, confirm_create_story, "
        "review_pending_stories, write_test_case, incident_status, update_story, general_sdlc"
    ),
    "agents": ["JIRA Agent", "ServiceNow Agent", "Splunk Agent"],
    "entities": {"story_key": "optional STORY-* or PROJ-* key", "environment": "optional environment"},
    "requires_confirmation": False,
    "confidence": "0.0 to 1.0, how certain you are about this classification",
}

# Few-shot examples shown to the LLM so it classifies free-form phrasing consistently.
FEW_SHOT_EXAMPLES = [
    {"query": "hey there", "intent": "greeting", "agents": [], "requires_confirmation": False, "confidence": 0.95},
    {"query": "give me the executive summary for the project", "intent": "executive_overview",
     "agents": ["JIRA Agent", "ServiceNow Agent", "Splunk Agent"], "requires_confirmation": False, "confidence": 0.9},
    {"query": "what should we build next based on the production failures", "intent": "suggest_features",
     "agents": ["JIRA Agent", "Splunk Agent"], "requires_confirmation": False, "confidence": 0.85},
    {"query": "why are we seeing so many errors in the payment logs", "intent": "analyze_errors",
     "agents": ["JIRA Agent", "Splunk Agent"], "requires_confirmation": False, "confidence": 0.85},
    {"query": "how many features shipped to production this month", "intent": "count_deployments",
     "agents": ["ServiceNow Agent"], "requires_confirmation": False, "confidence": 0.85},
    {"query": "how is the team's velocity trending this quarter", "intent": "check_velocity",
     "agents": ["JIRA Agent"], "requires_confirmation": False, "confidence": 0.85},
    {"query": "what is STORY-142", "intent": "story_detail", "agents": ["JIRA Agent"],
     "entities": {"story_key": "STORY-142"}, "requires_confirmation": False, "confidence": 0.9},
    {"query": "please save this as a new story in JIRA", "intent": "create_story", "agents": ["JIRA Agent"],
     "requires_confirmation": True, "confidence": 0.9},
    {"query": "yes go ahead and create those stories", "intent": "confirm_create_story", "agents": ["JIRA Agent"],
     "requires_confirmation": True, "confidence": 0.8},
    {"query": "can you expand the second story with acceptance criteria", "intent": "review_pending_stories",
     "agents": [], "requires_confirmation": False, "confidence": 0.8},
    {"query": "write a test case for story 8", "intent": "write_test_case", "agents": ["JIRA Agent"],
     "entities": {"story_key": "STORY-8"}, "requires_confirmation": False, "confidence": 0.9},
    {"query": "is there an active incident right now", "intent": "incident_status", "agents": ["ServiceNow Agent"],
     "requires_confirmation": False, "confidence": 0.85},
    {"query": "move STORY-5 to In Progress", "intent": "update_story", "agents": ["JIRA Agent"],
     "entities": {"story_key": "STORY-5", "update_fields": {"status": "In Progress"}}, "requires_confirmation": True, "confidence": 0.9},
    {"query": "change the priority of STORY-3 to Critical", "intent": "update_story", "agents": ["JIRA Agent"],
     "entities": {"story_key": "STORY-3", "update_fields": {"priority": "Critical"}}, "requires_confirmation": True, "confidence": 0.9},
    {"query": "update STORY-8 status to Done", "intent": "update_story", "agents": ["JIRA Agent"],
     "entities": {"story_key": "STORY-8", "update_fields": {"status": "Done"}}, "requires_confirmation": True, "confidence": 0.9},
    {"query": "which is the easy bug to fix", "intent": "suggest_work_item", "agents": ["JIRA Agent"],
     "requires_confirmation": False, "confidence": 0.85},
    {"query": "suggest a low effort story to pick up", "intent": "suggest_work_item", "agents": ["JIRA Agent"],
     "requires_confirmation": False, "confidence": 0.85},
    {"query": "what would be the story points for the pool size issue", "intent": "story_detail", "agents": ["JIRA Agent"],
     "requires_confirmation": False, "confidence": 0.8},
    {"query": "how much effort is the timeout fix", "intent": "story_detail", "agents": ["JIRA Agent"],
     "requires_confirmation": False, "confidence": 0.8},
    {"query": "list all bugs and estimate story points for each", "intent": "analyze_errors", "agents": ["JIRA Agent"],
     "requires_confirmation": False, "confidence": 0.85},
    {"query": "look at jira bugs and tell me the effort for each", "intent": "analyze_errors", "agents": ["JIRA Agent"],
     "requires_confirmation": False, "confidence": 0.85},
]

SYSTEM_PROMPT = (
    "Classify the user request for MAHALO SDLC orchestration. Return JSON only, matching the schema. "
    "Use the recent conversation turns (if any) to resolve follow-up questions and pronouns. "
    "Never authorize a write; set requires_confirmation true for create/save/write actions. "
    "Set confidence low (below 0.5) whenever the request is ambiguous, off-topic, or does not clearly match one intent. "
    f"Schema: {json.dumps(INTENT_SCHEMA)}\n"
    f"Examples: {json.dumps(FEW_SHOT_EXAMPLES)}"
)

ALLOWED_INTENTS = {
    "analyze_errors", "suggest_features", "count_deployments", "check_velocity",
    "story_detail", "create_story", "confirm_create_story", "review_pending_stories",
    "write_test_case", "incident_status", "executive_overview", "greeting", "general_sdlc",
    "update_story", "suggest_work_item",
}

# Below this confidence, prefer the deterministic keyword fallback over the LLM's guess.
# Only used if the fallback also has higher confidence than the LLM.
CONFIDENCE_THRESHOLD = 0.4

# History turns are truncated to keep prompts small; only recent context matters for follow-ups.
MAX_HISTORY_TURNS = 6
MAX_HISTORY_CHARS = 500


class IntentClassifier:
    def classify(
        self,
        query: str,
        conversation_history: list[dict[str, str]] | None = None,
        has_pending_stories: bool = False,
    ) -> dict[str, Any]:
        normalized = query.lower()
        fallback = self._fallback(normalized, has_pending_stories)
        if not settings.ONE_MIN_AI_API_KEY:
            return fallback
        try:
            response = one_min_completion(
                model=settings.LITELLM_MODEL,
                messages=self._build_messages(query, conversation_history, has_pending_stories),
                temperature=0,
                max_tokens=220,
            )
            content = response.choices[0].message.content.strip()
            # Strip markdown code blocks if present
            if content.startswith("```"):
                content = content.split("```json")[-1] if "```json" in content else content.split("```")[1]
                content = content.split("```")[0].strip()
            parsed = json.loads(content)
            validated = self._validate(parsed, fallback)
            # If LLM confidence is very low, use fallback
            if validated["confidence"] < CONFIDENCE_THRESHOLD:
                logger.info(
                    "Low-confidence LLM intent %r (%.2f) for query=%r; using fallback intent %r",
                    validated["intent"], validated["confidence"], query, fallback["intent"],
                )
                return fallback
            # If fallback has higher confidence than LLM, prefer fallback
            # (keyword rules are precise; they should win over uncertain LLM)
            if fallback["confidence"] > validated["confidence"]:
                logger.info(
                    "Fallback intent %r (%.2f) stronger than LLM %r (%.2f) for query=%r",
                    fallback["intent"], fallback["confidence"], validated["intent"], validated["confidence"], query,
                )
                return fallback
            return validated
        except Exception:
            logger.exception("Intent classification via LLM failed for query=%r; using keyword fallback", query)
            return fallback

    def _build_messages(
        self,
        query: str,
        conversation_history: list[dict[str, str]] | None,
        has_pending_stories: bool,
    ) -> list[dict[str, str]]:
        system_content = SYSTEM_PROMPT
        if has_pending_stories:
            system_content += (
                "\nContext: the user currently has draft JIRA stories awaiting review/confirmation. "
                "Requests to expand, review, or approve them should use confirm_create_story or review_pending_stories."
            )
        messages = [{"role": "system", "content": system_content}]
        for turn in (conversation_history or [])[-MAX_HISTORY_TURNS:]:
            role = turn.get("role")
            content = turn.get("content", "")
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": content[:MAX_HISTORY_CHARS]})
        messages.append({"role": "user", "content": query})
        return messages

    def _validate(self, result: dict[str, Any], fallback: dict[str, Any]) -> dict[str, Any]:
        if result.get("intent") not in ALLOWED_INTENTS:
            return fallback
        result["agents"] = [agent for agent in result.get("agents", []) if agent in INTENT_SCHEMA["agents"]]
        result.setdefault("entities", {})
        result["requires_confirmation"] = bool(result.get("requires_confirmation", False))
        if result["intent"] in {"create_story", "confirm_create_story"}:
            result["requires_confirmation"] = True
        try:
            confidence = float(result.get("confidence", 0.5))
        except (TypeError, ValueError):
            confidence = 0.5
        result["confidence"] = max(0.0, min(1.0, confidence))
        return result

    def _fallback(self, query: str, has_pending_stories: bool = False) -> dict[str, Any]:
        story_match = re.search(r"\b(?:story[- ]?(\d+)|([a-z]{2,10}-\d+))\b", query)
        story_key = None
        if story_match:
            story_key = f"STORY-{story_match.group(1)}" if story_match.group(1) else story_match.group(2).upper()
        if query.strip(" !?,.") in {"hi", "hello", "hey", "good morning", "good afternoon", "good evening"}:
            return self._result("greeting", [])
        if has_pending_stories and any(
            term in query for term in ("go ahead", "yes create", "create these", "create this story", "confirm", "approve")
        ):
            return self._result("confirm_create_story", ["JIRA Agent"], requires_confirmation=True, confidence=0.8)
        if has_pending_stories and any(
            term in query for term in ("elaborate", "expand", "acceptance criteria", "complete details", "review", "second story", "2nd")
        ):
            return self._result("review_pending_stories", [], confidence=0.75)
        if any(term in query for term in ("executive update", "executive summary", "executive overview", "overall update", "overall status")):
            return self._result("executive_overview", ["JIRA Agent", "ServiceNow Agent", "Splunk Agent"])
        if any(term in query for term in ("write a test", "test case", "qa test", "validate")):
            return self._result("write_test_case", ["JIRA Agent"], story_key=story_key)
        if story_key:
            # Check if this is an update request with a story key
            # Use word-boundary-aware matching to avoid false positives (e.g., "assigned" != "assign")
            update_verbs = ("move ", "update ", "change ", "set ", "assign ", "transition ")
            if any(verb in query + " " for verb in update_verbs) and not any(
                q_word in query for q_word in ("who is", "what is", "is assigned", "was assigned", "are assigned")
            ):
                update_fields = self._extract_update_fields(query)
                if update_fields:  # Only classify as update if we can extract meaningful fields
                    return self._result("update_story", ["JIRA Agent"], story_key=story_key, requires_confirmation=True, confidence=0.85, update_fields=update_fields)
            return self._result("story_detail", ["JIRA Agent"], story_key=story_key)
        # Update without explicit story key pattern (e.g., "move story 5 to done")
        if any(term in query for term in ("move ", "update ", "change ", "set ", "transition ")) and any(term in query for term in ("story", "status", "priority")):
            update_fields = self._extract_update_fields(query)
            if update_fields:
                return self._result("update_story", ["JIRA Agent"], requires_confirmation=True, confidence=0.7, update_fields=update_fields)
        if any(term in query for term in ("create", "save", "write", "add")) and "story" in query:
            return self._result("create_story", ["JIRA Agent", "Splunk Agent"], requires_confirmation=True)
        if "deploy" in query or ("production" in query and "feature" in query):
            return self._result("count_deployments", ["ServiceNow Agent"], environment="production")
        if any(term in query for term in ("suggest", "recommend", "next feature", "focus", "prioritize")) and any(term in query for term in ("error", "log", "feature", "failure", "production")):
            return self._result("suggest_features", ["JIRA Agent", "Splunk Agent"])
        if any(term in query for term in ("error", "errors", "failure", "failures", "production failures")) and any(term in query for term in ("feature", "story", "stories", "next", "focus", "logs", "quarter")):
            return self._result("analyze_errors", ["JIRA Agent", "Splunk Agent"])
        if "velocity" in query and any(term in query for term in ("quarter", "sprint", "story", "feature")):
            return self._result("check_velocity", ["JIRA Agent"])
        if any(term in query for term in ("analyze", "analyse", "based on")) and any(term in query for term in ("error", "log", "story", "feature")):
            return self._result("analyze_errors", ["JIRA Agent", "Splunk Agent"])
        # Suggest work item — user wants a recommendation on what to pick up next
        if any(term in query for term in ("easy", "simple", "quick", "low effort", "small", "starter", "beginner", "pick up", "work on", "start with")) and any(
            term in query for term in ("bug", "story", "issue", "task", "fix", "ticket", "item", "suggest", "recommend")
        ):
            return self._result("suggest_work_item", ["JIRA Agent"], confidence=0.85)
        if any(term in query for term in ("suggest", "recommend", "which")) and any(
            term in query for term in ("easy", "simple", "quick", "low", "small", "first", "next")
        ) and any(term in query for term in ("bug", "story", "issue", "task", "fix", "ticket", "work")):
            return self._result("suggest_work_item", ["JIRA Agent"], confidence=0.8)
        # Broader error/log analysis detection for natural language queries
        # Exclude "easy/simple to fix" patterns which are work-item suggestions, not error analysis
        if any(term in query for term in ("log", "logs", "error", "errors", "issue", "issues", "failure", "failures")) and any(
            term in query for term in ("priority", "high priority", "critical", "important", "urgent", "address", "fix", "resolve", "investigate", "check", "read", "show", "tell me", "what are")
        ) and not any(term in query for term in ("easy", "simple", "quick", "low effort", "pick up", "work on", "suggest me", "recommend")):
            return self._result("analyze_errors", ["Splunk Agent", "JIRA Agent"])
        if "incident" in query or "outage" in query:
            return self._result("incident_status", ["ServiceNow Agent"])
        return self._result("general_sdlc", ["JIRA Agent", "ServiceNow Agent", "Splunk Agent"], confidence=0.3)

    @staticmethod
    def _extract_update_fields(query: str) -> dict[str, str]:
        """Extract update fields from a natural language update request."""
        fields: dict[str, str] = {}
        q = query.lower()

        # Status extraction
        status_map = {
            "done": "Done",
            "in progress": "In Progress",
            "in-progress": "In Progress",
            "backlog": "Backlog",
            "to do": "To Do",
            "todo": "To Do",
            "blocked": "Blocked",
            "ready": "Ready",
            "review": "In Review",
            "in review": "In Review",
        }
        for keyword, status in status_map.items():
            if keyword in q and any(term in q for term in ("move", "status", "to", "transition")):
                fields["status"] = status
                break

        # Priority extraction
        priority_map = {
            "critical": "Critical",
            "high": "High",
            "medium": "Medium",
            "low": "Low",
        }
        for keyword, priority in priority_map.items():
            if keyword in q and any(term in q for term in ("priority", "change", "set", "update")):
                fields["priority"] = priority
                break

        # Sprint extraction
        sprint_match = re.search(r"sprint\s*(\d+)", q)
        if sprint_match and any(term in q for term in ("move", "assign", "set", "change")):
            fields["sprint"] = f"Sprint {sprint_match.group(1)}"

        return fields

    @staticmethod
    def _result(
        intent: str,
        agents: list[str],
        story_key: str | None = None,
        environment: str | None = None,
        requires_confirmation: bool = False,
        confidence: float = 0.9,
        update_fields: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        entities: dict[str, Any] = {}
        if story_key:
            entities["story_key"] = story_key
        if environment:
            entities["environment"] = environment
        if update_fields:
            entities["update_fields"] = update_fields
        return {
            "intent": intent,
            "agents": agents,
            "entities": entities,
            "requires_confirmation": requires_confirmation,
            "confidence": confidence,
        }
