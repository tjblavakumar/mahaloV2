import json
import re
from asyncio import gather
from typing import Any

from litellm import completion as _litellm_completion

from backend.config import settings
from backend.llm_adapter import one_min_ai_completion
from backend.utils.code_saver import CodeSaver
from backend.project_registry import get_project, RegistrySessionLocal, init_registry_db
from agents.jira_agent import JiraAgent
from agents.servicenow_agent import ServiceNowAgent
from agents.splunk_agent import SplunkAgent
from agents.intent_classifier import IntentClassifier
from agents.correlation_engine import CorrelationEngine


class OrchestratorAgent:
    """Simple orchestrator that uses the configured LLM provider."""

    # Intents that skip the interpretation/confirmation layer
    _SKIP_CONFIRMATION_INTENTS = frozenset({
        "greeting", "review_pending_stories", "confirm_create_story",
        "implement_code", "save_code",
    })

    # Keywords that indicate the user is confirming a pending action
    _CONFIRMATION_KEYWORDS = frozenset({
        "yes", "yeah", "yep", "sure", "go ahead", "proceed", "do it",
        "ok", "okay", "confirm", "approved", "approve", "correct",
    })

    # Keywords that indicate the user is rejecting a pending action
    _REJECTION_KEYWORDS = frozenset({
        "no", "nope", "cancel", "nevermind", "never mind", "stop",
        "don't", "do not", "scratch that", "forget it", "skip",
    })

    def __init__(self, jira_agent=None, servicenow_agent=None, splunk_agent=None):
        self.jira_agent = jira_agent or JiraAgent()
        self.servicenow_agent = servicenow_agent or ServiceNowAgent()
        self.splunk_agent = splunk_agent or SplunkAgent()
        self.last_agents_used: list[str] = []
        self.last_contexts: list[dict[str, Any]] = []
        self.pending_stories: list[dict[str, Any]] = []
        self.intent_classifier = IntentClassifier()
        self.last_intent: dict[str, Any] = {}
        self.correlation_engine = CorrelationEngine()
        self.last_insights: dict[str, Any] = {}
        # Interpretation layer state
        self.pending_action: dict[str, Any] | None = None
        # Code generation state — tracks the last generated code for save_code
        self.last_generated_code: str | None = None
        self.last_code_story_key: str | None = None
        self.last_code_story_title: str | None = None
        self.last_code_query: str | None = None

    # ===== INTERPRETATION LAYER HELPERS =====

    def _is_user_confirming(self, query: str) -> bool:
        """Check if the user message is a confirmation of a pending action."""
        normalized = query.strip().lower().rstrip("!?.")
        # Direct match on short confirmations
        if normalized in self._CONFIRMATION_KEYWORDS:
            return True
        # Check if any confirmation phrase appears at the start
        return any(normalized.startswith(kw) for kw in self._CONFIRMATION_KEYWORDS)

    def _is_user_rejecting(self, query: str) -> bool:
        """Check if the user message is a rejection of a pending action."""
        normalized = query.strip().lower().rstrip("!?.")
        if normalized in self._REJECTION_KEYWORDS:
            return True
        return any(normalized.startswith(kw) for kw in self._REJECTION_KEYWORDS)

    async def _handle_save_code(self, persona: str) -> str:
        """Handle the save_code intent — write last generated code to the project's code/ folder."""
        if not self.last_generated_code:
            return f"{persona}, there's no generated code to save. Ask me to implement a story first (e.g., \"write python code to implement MPS-2\")."

        if not self._current_project_id:
            return f"{persona}, no project is selected. Please select a project first so I know where to save the code."

        # Look up the project's folder path from the registry
        try:
            init_registry_db()
            db = RegistrySessionLocal()
            project = get_project(db, self._current_project_id)
            db.close()
        except Exception as e:
            return f"{persona}, I couldn't access the project registry: {e}"

        if not project:
            return f"{persona}, I couldn't find project '{self._current_project_id}' in the registry."

        folder_path = project.folder_path
        story_key = self.last_code_story_key or "UNKNOWN"

        # Save using CodeSaver
        saver = CodeSaver(folder_path)
        result = saver.save(
            code_content=self.last_generated_code,
            story_key=story_key,
            story_title=self.last_code_story_title or "",
            user_query=self.last_code_query or "",
        )

        if result["success"]:
            file_list = "\n".join(f"  - `{f}`" for f in result["files"])
            return (
                f"{persona}, done! Saved {result['file_count']} file(s) to:\n"
                f"📁 `{result['directory']}`\n\n"
                f"**Files created:**\n{file_list}\n\n"
                f"A `manifest.json` with metadata was also created in the same folder."
            )
        else:
            error_text = "; ".join(result["errors"])
            return f"{persona}, there were errors saving the code: {error_text}"

    def _build_interpretation_message(self, persona: str, intent: dict[str, Any], query: str) -> str:
        """Build a human-readable interpretation of what the orchestrator understands."""
        intent_name = intent.get("intent", "general_sdlc")
        agents = intent.get("agents", [])
        confidence = intent.get("confidence", 0.5)

        # Map intent to human-readable description
        intent_descriptions = {
            "executive_overview": "get a high-level executive overview of the project",
            "analyze_errors": "analyze production errors and failure patterns",
            "suggest_features": "suggest features or stories based on production signals",
            "suggest_work_item": "find an easy or low-effort item for you to pick up next",
            "count_deployments": "check what has been deployed to production",
            "check_velocity": "review team velocity and sprint progress",
            "story_detail": "look up details for a specific JIRA story",
            "create_story": "create a new JIRA story",
            "draft_user_story": "draft a user story based on your requirements",
            "write_test_case": "write a test case for a story",
            "incident_status": "check the current incident status",
            "update_story": "update an existing JIRA story",
            "implement_code": "generate implementation code for a JIRA story",
            "save_code": "save the previously generated code to your project folder",
            "general_sdlc": "answer a general question about the delivery lifecycle",
        }

        description = intent_descriptions.get(intent_name, f"help with: {intent_name}")
        agents_text = ", ".join(agents) if agents else "my built-in knowledge"
        entity_info = ""
        entities = intent.get("entities", {})
        if entities.get("story_key"):
            entity_info = f" (targeting {entities['story_key']})"

        confidence_note = ""
        if confidence < 0.7:
            confidence_note = " Let me know if I've misunderstood."

        # Special formatting for update_story to show planned changes
        if intent_name == "update_story" and entities.get("update_fields"):
            fields_desc = ", ".join(f"{k} → {v}" for k, v in entities["update_fields"].items())
            return (
                f"{persona}, here's what I understand:\n\n"
                f"**Your request:** {query}\n"
                f"**My interpretation:** You want to update {entities.get('story_key', 'a story')}: {fields_desc}.\n"
                f"**I'll consult:** {agents_text}\n\n"
                f"Shall I proceed?{confidence_note}"
            )

        # Special formatting for draft_user_story to show extracted topic
        if intent_name == "draft_user_story" and entities.get("topic"):
            topic = entities["topic"]
            return (
                f"{persona}, here's what I understand:\n\n"
                f"**Your request:** {query}\n"
                f"**My interpretation:** You want me to draft a user story about: *{topic}*.\n"
                f"**I'll consult:** {agents_text}\n\n"
                f"Shall I proceed, or do you have additional details to refine the story?{confidence_note}"
            )

        return (
            f"{persona}, here's what I understand:\n\n"
            f"**Your request:** {query}\n"
            f"**My interpretation:** You want to {description}{entity_info}.\n"
            f"**I'll consult:** {agents_text}\n\n"
            f"Shall I proceed?{confidence_note}"
        )

    def _should_skip_confirmation(self, intent: dict[str, Any], user_query: str, conversation_history: list[dict[str, str]] | None) -> bool:
        """Determine if this query should bypass the interpretation layer."""
        intent_name = intent.get("intent", "")
        # Always skip for exempt intents
        if intent_name in self._SKIP_CONFIRMATION_INTENTS:
            return True
        # Skip if there's already a pending action (we're in confirmation flow)
        if self.pending_action:
            return True
        # Skip for follow-up on pending stories (elaborate, expand, etc.)
        user_query_lower = user_query.lower()
        if self.pending_stories and any(
            term in user_query_lower for term in (
                "elaborate", "expand", "acceptance criteria", "complete details",
                "review", "suggested use case", "suggested stories",
            )
        ):
            return True
        # Skip for explicit JIRA write confirmations (handled by existing logic)
        if self.pending_stories and (
            intent_name == "confirm_create_story"
            or (
                "jira" in user_query_lower
                and any(action in user_query_lower for action in ("create", "save", "write", "add"))
            )
        ):
            return True
        return False

    async def _execute_confirmed_action(self, action: dict[str, Any]) -> str:
        """Execute a previously confirmed action by re-running process_query with confirmation bypass."""
        persona = action["persona"]
        query = action["query"]
        intent = action["intent"]
        history = action.get("conversation_history")

        # Set the intent so the downstream logic uses it
        self.last_intent = intent

        # Now execute the core logic that was deferred
        user_query_lower = query.lower()

        # Handle update_story intent
        if intent.get("intent") == "update_story":
            entities = intent.get("entities", {})
            story_key = entities.get("story_key")
            update_fields = entities.get("update_fields", {})
            if story_key and update_fields:
                result = await self.jira_agent.update_story(story_key, update_fields)
                if result.get("success"):
                    updated_data = result.get("data", {})
                    return f"{persona}, done. {story_key} has been updated: {', '.join(f'{k}={v}' for k, v in update_fields.items())}."
                return f"{persona}, the update failed: {result.get('error', 'unknown error')}."
            return f"{persona}, I couldn't determine which story to update or what fields to change. Could you clarify?"

        # Handle draft_user_story intent — use LLM to generate a proper story draft
        if intent.get("intent") == "draft_user_story":
            topic = intent.get("entities", {}).get("topic", "")
            return await self._execute_llm_story_draft(persona, query, topic)

        # Handle implement_code intent
        if intent.get("intent") == "implement_code":
            entities = intent.get("entities", {})
            story_key = entities.get("story_key")
            story_result = await self.jira_agent.retrieve_context(f"story detail {story_key}", project_id=self._current_project_id) if story_key else {}
            code_context = json.dumps([story_result], default=str)
            # Try to extract story title
            story_title = ""
            if story_result:
                story_data = story_result.get("data", {})
                if isinstance(story_data, dict):
                    story_title = story_data.get("title", "") or story_data.get("summary", "")
                    if not story_title and story_data.get("items"):
                        items = story_data["items"]
                        if items and isinstance(items[0], dict):
                            story_title = items[0].get("title", "") or items[0].get("summary", "")

            if settings.ONE_MIN_AI_API_KEY:
                try:
                    response = await one_min_ai_completion(
                        model=settings.LITELLM_MODEL,
                        messages=[
                            {
                                "role": "system",
                                "content": (
                                    "You are MAHALO's code generation assistant. The user wants you to write "
                                    "implementation code for a JIRA story/task.\n\n"
                                    f"{self._role_system_instructions(persona)}\n\n"
                                    "INSTRUCTIONS:\n"
                                    "1. Read the story/task details from the context below.\n"
                                    "2. Write clean, working code that implements the described feature or fix.\n"
                                    "3. Use the programming language specified by the user (default: Python).\n"
                                    "4. Include clear comments explaining your implementation approach.\n"
                                    "5. Structure the code properly (imports, classes/functions, main logic).\n"
                                    "6. If the story lacks enough detail, state your assumptions and proceed.\n"
                                    "7. Do NOT save or create files — just present the code for the user to review.\n"
                                    "8. If generating multiple files, use a header like '**`filename.py`**:' before each code block."
                                )
                            },
                            {
                                "role": "user",
                                "content": (
                                    f"Request: {query}\n"
                                    f"Target story: {story_key or 'Not specified'}\n\n"
                                    f"=== STORY/TASK CONTEXT ===\n{code_context}"
                                )
                            },
                        ],
                        temperature=0.3,
                        max_tokens=2000,
                    )
                    generated_code = response.choices[0].message.content
                    # Store for save_code follow-up
                    self.last_generated_code = generated_code
                    self.last_code_story_key = story_key
                    self.last_code_story_title = story_title
                    self.last_code_query = query
                    save_hint = f"\n\n---\n*Code ready for review. Say **\"save the code\"** when you'd like me to save it to your project.*"
                    return generated_code + save_hint
                except Exception:
                    pass
            return f"{persona}, I found the story details for {story_key} but couldn't generate code right now. Please try again."

        # Follow-up on pending stories
        follow_up = (
            self.pending_stories and
            any(term in user_query_lower for term in (
                "suggested use case", "suggested stories", "complete details",
                "acceptance criteria", "expand", "review"
            ))
        ) or (
            "elaborate" in user_query_lower and
            ("story" in user_query_lower or "stories" in user_query_lower) and
            self.pending_stories
        ) or (
            self.pending_stories and intent.get("intent") == "review_pending_stories"
        )

        review_first = any(term in user_query_lower for term in ("review", "before you create", "before creating", "do not create", "don't create", "first"))
        explicit_jira_write = not review_first and (
            (
                "jira" in user_query_lower and
                any(action_term in user_query_lower for action_term in ("create", "save", "write", "add"))
            ) or intent.get("intent") == "confirm_create_story"
        )

        if (follow_up or explicit_jira_write) and self.pending_stories:
            if explicit_jira_write:
                results = [await self.jira_agent.create_story(story, project_id=self._current_project_id) for story in self.pending_stories]
                created = [r.get("data", {}).get("story_key", "new story") for r in results if r.get("success")]
                if len(created) == len(results):
                    self.pending_stories = []
                    return f"{persona}, created {len(created)} stories in JIRA: {', '.join(created)}."
                return f"{persona}, created {len(created)} stories, but some writes failed."
            if any(term in user_query_lower for term in ("elaborate", "expand")):
                selected_story = self._select_pending_story(query)
                if "priority" in user_query_lower:
                    return self._format_priority_explanation(persona, selected_story)
                return self._format_story_draft(persona, selected_story)
            return self._format_story_drafts(persona, self.pending_stories)

        # Retrieve context and produce response
        context_query = "executive overview" if self._is_top_issue_request(query) else query
        context_intent = (
            {"agents": ["JIRA Agent", "ServiceNow Agent", "Splunk Agent"]}
            if self._is_top_issue_request(query)
            else intent
        )
        agents_used, contexts = await self.retrieve_context(context_query, context_intent, project_id=self._current_project_id)

        # Correlation
        insights = self.correlation_engine.correlate_contexts(contexts)
        self.last_insights = insights

        if self._is_top_issue_request(query):
            priorities = insights.get("priorities", [])
            if priorities:
                top = priorities[0]
                incident = f" ({top['incident_id']})" if top.get("incident_id") else ""
                return (
                    f"{persona}, the top issue is {top.get('theme', 'the highest-priority issue')}{incident}.\n"
                    f"Why: {top.get('reason', 'It has the highest current impact.')}\n"
                    f"Priority: {top.get('suggested_priority', 'High')}\n"
                    f"Estimated effort: {top.get('story_points_estimate', 'Not estimated')} story points."
                )
            return f"{persona}, I could not identify a current top issue from the available project data."

        # Story analysis / suggestion
        if ("analyze" in user_query_lower or "analyse" in user_query_lower) and ("story" in user_query_lower or "stories" in user_query_lower):
            self.pending_stories = self._draft_stories_from_context(contexts)
        if ("suggest" in user_query_lower or "recommend" in user_query_lower) and ("story" in user_query_lower or "stories" in user_query_lower):
            self.pending_stories = self._draft_stories_from_context(contexts)
        if follow_up or (("create" in user_query_lower or "stories" in user_query_lower) and "story" in user_query_lower and self.last_contexts):
            wants_multiple = "stories" in user_query_lower or "these user stories" in user_query_lower
            self.pending_stories = self._draft_stories_from_context(self.last_contexts) if wants_multiple else [self._story_from_context(self.last_contexts)]
            return self._format_story_drafts(persona, self.pending_stories)

        # LLM synthesis
        context_text = json.dumps(contexts, default=str)
        insights_text = self.correlation_engine.format_insights_for_llm()

        # Detect if user is asking for code/implementation help
        is_code_request = any(term in query.lower() for term in (
            "code", "sample code", "implement", "fix code", "how to fix", "snippet",
            "example code", "write code", "solution code", "patch",
        ))
        max_tokens = 1200 if is_code_request else 600

        code_instruction = ""
        if is_code_request:
            code_instruction = (
                "\n\nIMPORTANT: The user is explicitly asking for CODE. "
                "After a brief 1-2 line diagnosis, provide working sample code that addresses the issue. "
                "Use appropriate programming language (Python unless specified otherwise). "
                "Include comments explaining the fix. Keep analysis minimal — focus on the code solution."
            )

        if settings.ONE_MIN_AI_API_KEY:
            try:
                response = await one_min_ai_completion(
                    model=settings.LITELLM_MODEL,
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "You are MAHALO's reasoning orchestrator. Interpret the user's underlying goal; "
                                "do not treat every phrase as a literal search term or repeat empty tool results.\n"
                                "Use the available evidence to answer the question directly, synthesize across tools, "
                                "and explain uncertainty when the evidence is insufficient.\n\n"
                                f"{self._role_system_instructions(persona)}\n\n"
                                f"Classified intent: {intent.get('intent')} (confidence: {intent.get('confidence', 0.5)})\n\n"
                                "Be specific, be analytical, be helpful. Don't just list data - interpret it!\n"
                                "If the user asks for code, sample code, or implementation help, provide concrete "
                                f"code examples based on the bug/story context. Use appropriate language and patterns.{code_instruction}"
                            )
                        },
                        {
                            "role": "user",
                            "content": (
                                f"Request: {query}\n\n"
                                f"=== INTELLIGENT INSIGHTS (USE THIS FIRST) ===\n{insights_text}\n\n"
                                f"=== RAW TOOL CONTEXT (FOR DETAILS) ===\n{context_text}"
                            )
                        },
                    ],
                    temperature=0.4,
                    max_tokens=max_tokens,
                )
                llm_text = response.choices[0].message.content
                # Skip grounding check for code requests — code can't be "grounded" in JIRA data
                if is_code_request or self._llm_response_is_grounded(query, llm_text, contexts):
                    return llm_text
            except Exception:
                pass

        return self._fallback_response(persona, query, contexts)

    def route_query(self, user_query: str) -> str:
        q = user_query.lower()
        if "story" in q or "stories" in q or "backlog" in q or "sprint" in q or "bug" in q:
            return "JIRA Agent: route to stories and sprint status."
        if "incident" in q or "outage" in q or "ticket" in q:
            return "ServiceNow Agent: route to incident management and service health."
        if "log" in q or "error" in q or "latency" in q or "monitor" in q:
            return "Splunk Agent: route to log search and monitoring insights."
        return "Orchestrator: route to the relevant project workflow."

    def _agents_for_query(self, user_query: str, intent: dict[str, Any] | None = None):
        if intent and intent.get("agents"):
            available = {
                "JIRA Agent": self.jira_agent,
                "ServiceNow Agent": self.servicenow_agent,
                "Splunk Agent": self.splunk_agent,
            }
            return [(name, available[name]) for name in intent["agents"] if name in available]
        query = user_query.lower()
        agents = []
        if any(term in query for term in ("story", "stories", "backlog", "sprint", "bug", "velocity")):
            agents.append(("JIRA Agent", self.jira_agent))
        if any(term in query for term in ("incident", "outage", "ticket", "service")):
            agents.append(("ServiceNow Agent", self.servicenow_agent))
        if "deploy" in query or "production" in query:
            if ("ServiceNow Agent", self.servicenow_agent) not in agents:
                agents.append(("ServiceNow Agent", self.servicenow_agent))
        if any(term in query for term in ("log", "error", "latency", "monitor")):
            agents.append(("Splunk Agent", self.splunk_agent))
        return agents or [("Orchestrator", None)]

    async def retrieve_context(self, user_query: str, intent: dict[str, Any] | None = None, project_id: str | None = None) -> tuple[list[str], list[dict[str, Any]]]:
        selected = self._agents_for_query(user_query, intent)
        calls = [agent.retrieve_context(user_query, project_id=project_id) for _, agent in selected if agent]
        results = await gather(*calls, return_exceptions=True)
        contexts = []
        agents_used = []
        for (agent_name, _), result in zip(selected, results):
            if isinstance(result, Exception):
                contexts.append({"source": agent_name, "success": False, "error": str(result)})
            else:
                contexts.append(result)
            agents_used.append(agent_name)
        self.last_agents_used = agents_used
        self.last_contexts = contexts
        return agents_used, contexts

    def _story_from_context(self, contexts: list[dict[str, Any]]) -> dict[str, Any]:
        logs = []
        for context in contexts:
            if context.get("source") != "Splunk":
                continue
            data = context.get("data", {})
            logs.extend(data.get("items", []) if isinstance(data, dict) else data if isinstance(data, list) else [])
        messages = " ".join(log.get("message", "") for log in logs).lower()
        # Derive title and description from actual log content
        error_logs = [log for log in logs if log.get("level", "").upper() == "ERROR"]
        if error_logs:
            # Use the first error message as the basis for the story
            primary_error = error_logs[0].get("message", "production error")
            service = error_logs[0].get("service", "service")
            title = f"Resolve {service} reliability issue"
            description = f"Address the recurring error: {primary_error}. Implement proper error handling, monitoring, and recovery."
        elif "timeout" in messages or "502" in messages:
            title = "Improve service timeout recovery"
            description = "Handle timeouts with bounded retries, safe failure states, and provider failover."
        elif "latency" in messages:
            title = "Reduce service latency"
            description = "Optimize the service to meet latency targets and improve user experience."
        else:
            title = "Improve system reliability"
            description = "Address production issues identified in logs to improve system stability."
        return {
            "title": title,
            "description": description,
            "story_points": 8,
            "priority": "High",
            "status": "Backlog",
            "sprint": "Sprint 24",
            "acceptance_criteria": [
                f"The root cause of the issue is identified and resolved.",
                "Solution is tested in staging environment.",
                "Monitoring is in place to detect regressions.",
                "Documentation is updated.",
                "Automated tests cover the fix.",
            ],
            "evidence": [log.get("message", "") for log in logs[:5]],
        }

    def _format_story_draft(self, persona: str, story: dict[str, Any]) -> str:
        criteria = "\n".join(f"- {item}" for item in story["acceptance_criteria"])
        evidence = "\n".join(f"- {item}" for item in story.get("evidence", [])) or "- Based on the previous log analysis."
        user_story = story.get("user_story", f"As a user, I want to {story['title'].lower()}, so that the system works reliably.")
        return (
            f"{persona}, here is the complete JIRA story draft:\n\n"
            f"Title: {story['title']}\nDescription: {story['description']}\n"
            f"Priority: {story['priority']}\nStory points: {story['story_points']}\nSprint: {story['sprint']}\n"
            f"User story: {user_story}\n"
            f"Acceptance criteria:\n{criteria}\nEvidence:\n{evidence}\n\n"
            "This is still a draft. Say 'create this story in JIRA' to save it."
        )

    def _format_story_drafts(self, persona: str, stories: list[dict[str, Any]]) -> str:
        return (
            f"{persona}, I prepared {len(stories)} JIRA story drafts for your review:\n\n"
            + "\n\n".join(self._format_story_draft(persona, story) for story in stories)
            + "\n\nNo stories have been created yet. Say 'create these stories in JIRA' after you approve them."
        )

    @staticmethod
    def _role_system_instructions(persona: str) -> str:
        role_instructions = {
            "Executive": (
                "ROLE: Executive / VP-level stakeholder\n"
                "DECISION FRAMEWORK: You make go/no-go decisions, allocate budget, escalate risks, "
                "and set strategic priorities. You need to know: What is the business impact? "
                "What is the risk if we do nothing? What is the cost of delay? Is this on track?\n"
                "COMMUNICATION STYLE:\n"
                "- Lead with a one-line status verdict (on-track / at-risk / blocked).\n"
                "- Use traffic-light indicators: GREEN (healthy), AMBER (needs attention), RED (blocked/critical).\n"
                "- Quantify with KPIs: revenue impact, customer-facing SLA, delivery velocity, defect escape rate.\n"
                "- Keep technical detail to one sentence unless it changes the business decision.\n"
                "- End with a clear recommendation or decision needed.\n"
                "RELEVANT ACTIONS: escalate, deprioritize, fund, approve, request status update, set deadline."
            ),
            "Product Manager": (
                "ROLE: Product Manager\n"
                "DECISION FRAMEWORK: You prioritize the backlog, estimate effort, define acceptance criteria, "
                "and balance customer value against engineering cost. You need to know: What should we build next? "
                "What is the customer impact? How does this fit the roadmap? What are the dependencies?\n"
                "COMMUNICATION STYLE:\n"
                "- Frame findings as user stories or backlog recommendations.\n"
                "- Provide impact/effort assessments (e.g., High Impact / Medium Effort).\n"
                "- Include acceptance criteria when suggesting work items.\n"
                "- Mention dependencies, risks, and sprint fit.\n"
                "- Use story-point estimates with brief justification.\n"
                "- Reference customer segments or personas affected.\n"
                "RELEVANT ACTIONS: create stories, reprioritize backlog, define scope, estimate effort, "
                "split epics, set acceptance criteria, schedule for sprint."
            ),
            "Developer": (
                "ROLE: Software Developer / Engineer\n"
                "DECISION FRAMEWORK: You need technical root cause, affected code paths, implementation options, "
                "and trade-offs. You decide: What is the fix? What is the safest approach? "
                "What are the edge cases? What tests should cover this?\n"
                "COMMUNICATION STYLE:\n"
                "- Lead with the technical root cause or diagnosis.\n"
                "- Identify affected components, services, and code paths.\n"
                "- Present implementation options with trade-offs (performance, complexity, risk).\n"
                "- Include relevant log evidence, error patterns, and stack traces.\n"
                "- Suggest concrete engineering next steps (PRs, config changes, architecture decisions).\n"
                "- Mention edge cases and failure modes.\n"
                "RELEVANT ACTIONS: investigate root cause, implement fix, refactor, add monitoring, "
                "write unit tests, deploy hotfix, review architecture."
            ),
            "QA": (
                "ROLE: QA Engineer / Test Lead\n"
                "DECISION FRAMEWORK: You assess release readiness, regression risk, and test coverage. "
                "You need to know: Can we reproduce this? What is the blast radius? "
                "What tests are missing? Is this safe to release?\n"
                "COMMUNICATION STYLE:\n"
                "- Assess reproducibility and defect scope first.\n"
                "- Identify regression scenarios and affected test suites.\n"
                "- Present risk-based test coverage recommendations.\n"
                "- Include expected vs. actual results for defects.\n"
                "- Provide release-readiness verdicts with evidence.\n"
                "- Suggest test matrices for new features or fixes.\n"
                "RELEVANT ACTIONS: write test cases, flag regressions, assess release readiness, "
                "define test scenarios, report defect severity, validate fixes, update test coverage."
            ),
        }
        role = persona if persona in role_instructions else "Executive"
        return f"=== ACTIVE PERSONA ===\n{role_instructions[role]}"

    def _draft_stories_from_context(self, contexts: list[dict[str, Any]]) -> list[dict[str, Any]]:
        primary = self._story_from_context(contexts)
        logs = []
        for context in contexts:
            if context.get("source") == "Splunk":
                data = context.get("data", {})
                logs.extend(data.get("items", []) if isinstance(data, dict) else data if isinstance(data, list) else [])
        error_logs = [log for log in logs if log.get("level", "").upper() == "ERROR"]
        drafts = [primary]
        # Generate additional stories from distinct error patterns
        seen_services = {primary.get("title", "")}
        for log in error_logs[1:4]:  # up to 3 additional stories
            service = log.get("service", "service")
            title = f"Resolve {service} error: {log.get('message', '')[:60]}"
            if title not in seen_services:
                seen_services.add(title)
                drafts.append({
                    **primary,
                    "title": title,
                    "description": f"Address the error in {service}: {log.get('message', '')}",
                    "story_points": 5,
                    "priority": "Medium",
                    "acceptance_criteria": [
                        f"Root cause of the {service} error is identified.",
                        "Fix is deployed and verified in staging.",
                        "Monitoring alerts are configured.",
                        "Automated tests cover the scenario.",
                    ],
                })
        return drafts

    def _select_pending_story(self, query: str) -> dict[str, Any]:
        normalized = re.sub(r"[^a-z0-9 ]", " ", query.lower())
        stop_words = {"elaborate", "expand", "title", "why", "is", "it", "the", "story", "priority", "on", "this"}
        query_words = {word for word in normalized.split() if len(word) > 3 and word not in stop_words}
        best_story = self.pending_stories[0]
        best_score = 0
        for story in self.pending_stories:
            title_words = {word for word in re.findall(r"[a-z0-9]+", story.get("title", "").lower()) if len(word) > 3}
            score = len(query_words & title_words)
            if story.get("title", "").lower() in query.lower():
                score += 100
            if score > best_score:
                best_story, best_score = story, score
        return best_story

    def _format_priority_explanation(self, persona: str, story: dict[str, Any]) -> str:
        priority_reason = {
            "High": "It addresses recurring production failures and has direct customer and operational impact.",
            "Medium": "It improves operational quality and reduces risk, but is less urgent than active production failures.",
            "Low": "It is useful backlog improvement work, but does not currently indicate immediate production risk.",
        }.get(story.get("priority", "Medium"), "Its priority is based on the observed production impact and delivery risk.")
        return f"{persona}, **{story['title']}** is marked {story['priority']} priority. {priority_reason} It is estimated at {story['story_points']} story points."

    @staticmethod
    def _estimate_story_points(story: dict[str, Any]) -> tuple[int, str]:
        """Heuristic story-point estimate for stories JIRA has not yet sized."""
        text = f"{story.get('title', '')} {story.get('description', '')}".lower()
        priority = str(story.get("priority", "Medium")).lower()
        low_complexity_terms = ("typo", "label", "copy change", "minor", "small tweak")
        high_complexity_terms = (
            "automation", "reconciliation", "integration", "migration",
            "failover", "fraud", "security", "compliance", "settlement",
        )
        if any(term in text for term in low_complexity_terms):
            return 2, "the description points to a small, low-risk change"
        if any(term in text for term in high_complexity_terms) or priority == "high":
            return 8, "it involves cross-system integration or high-priority production risk"
        return 5, "it is a standard-scope backlog item without unusual complexity signals"

    def _format_story_point_estimate(self, persona: str, story: dict[str, Any], story_key: str) -> str:
        """Answer 'estimate the story points' requests, whether or not JIRA already has a value."""
        key = story.get("story_key", story_key)
        current_points = story.get("story_points") or 0
        if current_points:
            return f"{persona}, {key} is already estimated at {current_points} story points in JIRA."
        points, reason = self._estimate_story_points(story)
        return (
            f"{persona}, {key} is not yet estimated in JIRA. Based on its title and description, "
            f"I'd suggest **{points} story points** — {reason}. "
            "This is a suggested estimate; confirm with the team before updating JIRA."
        )

    # ===== BUG #1: FORMAT RESPONSE FIX =====
    
    @staticmethod
    def _contains_phrase(text: str, phrases: list[str]) -> bool:
        """Whole-word/phrase match so short keywords (e.g. "how") don't match inside unrelated words (e.g. "show")."""
        return any(re.search(rf"\b{re.escape(phrase)}\b", text) for phrase in phrases)

    def _is_formatting_request(self, query: str, conversation_history: list[dict[str, str]] | None = None) -> bool:
        """Detect if the query is a request to reformat/explain the previous response."""
        query_lower = query.lower()
        
        formatting_keywords = [
            "format", "reformat", "better format", "formatted",
            "structure", "restructure", "organize", "reorganize",
            "cleaner", "more readable", "easier to read"
        ]
        
        response_references = [
            "your response", "that response", "the response", "your answer",
            "that answer", "the answer", "the output", "your output", "that"
        ]
        
        has_formatting = self._contains_phrase(query_lower, formatting_keywords)
        has_reference = self._contains_phrase(query_lower, response_references)
        
        is_short_formatting_query = (
            has_formatting and
            len(query.split()) <= 5 and
            conversation_history and len(conversation_history) > 0
        )
        
        return (has_formatting and has_reference) or is_short_formatting_query

    def _reformat_last_response(self, persona: str, conversation_history: list[dict[str, str]] | None = None) -> str:
        """Reformat the last assistant response in a more structured way."""
        if not conversation_history or len(conversation_history) == 0:
            return f"{persona}, I don't have a previous response to format. Please ask a question first."
        
        last_response = None
        for message in reversed(conversation_history):
            if message.get("role") == "assistant":
                last_response = message.get("content", "")
                break
        
        if not last_response:
            return f"{persona}, I couldn't find a previous response to format."
        
        if "features are deployed in production" in last_response.lower():
            return self._format_deployment_list(persona, last_response)
        
        if "executive update" in last_response.lower() or "mahalo" in last_response.lower():
            return self._format_executive_overview(persona, last_response)
        
        return self._format_generic_response(persona, last_response)

    def _format_deployment_list(self, persona: str, response: str) -> str:
        """Format deployment list in a clean table-like structure."""
        pattern = r'([^,]+?)\s*\(([v\d.]+)\)'
        matches = re.findall(pattern, response)
        
        if not matches:
            return response
        
        formatted = f"{persona}, here are the production deployments:\n\n"
        formatted += "| # | Feature | Version |\n"
        formatted += "|---|---------|---------|\n"
        
        for i, (feature, version) in enumerate(matches, 1):
            feature_clean = feature.strip().strip(',').strip()
            formatted += f"| {i} | {feature_clean} | {version} |\n"
        
        formatted += f"\n**Total: {len(matches)} features deployed in production**"
        
        return formatted

    def _format_executive_overview(self, persona: str, response: str) -> str:
        """Format executive overview with better structure."""
        lines = response.split('\n')
        
        formatted = f"{persona}, here is the Executive Overview:\n\n"
        formatted += "## Key Metrics\n\n"
        
        for line in lines:
            line = line.strip()
            if line.startswith('-'):
                formatted += f"{line}\n"
            elif line and not any(x in line.lower() for x in ['executive', 'mahalo', 'priority']):
                formatted += f"{line}\n"
        
        priority_lines = [l for l in lines if 'priority' in l.lower()]
        if priority_lines:
            formatted += "\n## Priority Recommendations\n\n"
            for line in priority_lines:
                formatted += f"{line.strip()}\n"
        
        return formatted

    def _format_generic_response(self, persona: str, response: str) -> str:
        """Format generic response with better structure."""
        if response.count('\n') >= 3 or '|' in response or response.startswith(persona):
            return response
        
        formatted = f"{persona}, here's a formatted version:\n\n"
        
        if '.' in response and response.count('.') >= 2:
            sentences = [s.strip() for s in response.split('.') if s.strip()]
            for sentence in sentences:
                if sentence:
                    formatted += f"• {sentence}.\n"
        elif ',' in response and response.count(',') >= 3:
            items = [s.strip() for s in response.split(',') if s.strip()]
            for item in items:
                formatted += f"• {item}\n"
        else:
            formatted += response
        
        return formatted

    # ===== BUG #2: ELABORATION REQUEST FIX =====
    
    def _is_elaboration_request(self, query: str, conversation_history: list[dict[str, str]] | None = None) -> bool:
        """Detect if the query is requesting elaboration/explanation of previous response."""
        query_lower = query.lower()
        
        elaboration_keywords = [
            "why", "how", "explain", "elaborate", "clarify", "justify",
            "what do you mean", "can you explain", "tell me more",
            "give me more details", "provide more details", "break down",
            "walk me through"
        ]
        
        response_references = [
            "this", "that", "your recommendation", "your answer",
            "your response", "the recommendation", "the score",
            "that recommendation", "that score", "this score"
        ]
        
        has_elaboration = self._contains_phrase(query_lower, elaboration_keywords)
        has_reference = self._contains_phrase(query_lower, response_references)
        
        is_short_elaboration = (
            has_elaboration and
            len(query.split()) <= 10 and
            conversation_history and len(conversation_history) > 0
        )
        
        return (has_elaboration and has_reference) or is_short_elaboration

    def _elaborate_last_response(self, persona: str, conversation_history: list[dict[str, str]] | None = None) -> str:
        """Provide detailed elaboration of the last assistant response."""
        if not conversation_history or len(conversation_history) == 0:
            return f"{persona}, I don't have a previous response to elaborate on."
        
        last_response = None
        for message in reversed(conversation_history):
            if message.get("role") == "assistant":
                last_response = message.get("content", "")
                break
        
        if not last_response:
            return f"{persona}, I couldn't find a previous response to elaborate on."
        
        if "reliability score" in last_response.lower() or "health score" in last_response.lower():
            return self._elaborate_health_score(persona)
        
        if "prioritize" in last_response.lower() or "priority" in last_response.lower():
            return self._elaborate_priority_recommendation(persona)
        
        return self._elaborate_generic_response(persona, last_response)

    def _elaborate_health_score(self, persona: str) -> str:
        """Elaborate on health/reliability score calculation."""
        if not self.last_insights:
            return f"{persona}, I don't have detailed health metrics available."
        
        summary = self.last_insights.get("summary", {})
        health = self.last_insights.get("health_score", {})
        gaps = self.last_insights.get("gaps", [])
        correlations = self.last_insights.get("correlations", [])
        
        response = f"{persona}, here's the detailed breakdown of the reliability score:\n\n"
        
        response += "## Score Calculation\n\n"
        response += f"**Overall Score: {health.get('overall_score', 0)}%** ({health.get('status', 'Unknown')})\n\n"
        response += "This is calculated from three components:\n\n"
        response += f"1. **Delivery Health: {health.get('delivery_score', 0)}%**\n"
        response += f"   - {summary.get('completed_stories', 0)} of {summary.get('total_stories', 0)} stories completed\n"
        response += f"   - Completion rate drives this metric\n\n"
        
        response += f"2. **Operations Health: {health.get('operations_score', 0)}%**\n"
        response += f"   - {summary.get('active_incidents', 0)} of {summary.get('total_incidents', 0)} incidents active\n"
        response += f"   - Lower active incidents = higher score\n\n"
        
        response += f"3. **Reliability Health: {health.get('reliability_score', 0)}%**\n"
        response += f"   - {summary.get('total_errors', 0)} errors in {summary.get('total_logs', 0)} logs\n"
        response += f"   - Error rate: {summary.get('error_rate', 0):.1f}%\n"
        response += f"   - **This is why the overall score is low**\n\n"
        
        response += "## Why Prioritize Error Reduction\n\n"
        response += f"With an error rate of {summary.get('error_rate', 0):.1f}% and reliability at {health.get('reliability_score', 0)}%, "
        response += "the system has identified significant production issues:\n\n"
        
        if gaps:
            response += "**Identified Gaps:**\n"
            for gap in gaps[:3]:
                response += f"- {gap.get('theme', 'Unknown issue')}: {gap.get('error_count', 0)} errors\n"
            response += "\n"
        
        if correlations:
            response += "**Cross-System Correlations:**\n"
            for corr in correlations[:3]:
                response += f"- {corr.get('recommendation', 'Unknown correlation')}\n"
            response += "\n"
        
        response += "These recurring patterns indicate systematic reliability problems that should be addressed before expanding features."
        
        return response

    def _elaborate_priority_recommendation(self, persona: str) -> str:
        """Elaborate on why something is prioritized."""
        if not self.last_insights:
            return f"{persona}, I don't have detailed priority reasoning available."
        
        priorities = self.last_insights.get("priorities", [])
        
        if not priorities:
            return f"{persona}, I don't have specific priority recommendations available."
        
        response = f"{persona}, here's why these items are prioritized:\n\n"
        
        for priority in priorities[:3]:
            response += f"**{priority.get('rank')}. {priority.get('theme')}**\n"
            response += f"- Reason: {priority.get('reason')}\n"
            response += f"- Priority: {priority.get('suggested_priority')}\n"
            response += f"- Estimated effort: {priority.get('story_points_estimate')} story points\n\n"
        
        response += "\nPriorities are ranked based on:\n"
        response += "1. Error frequency and impact\n"
        response += "2. Customer-facing severity\n"
        response += "3. Current backlog coverage (gaps are prioritized)\n"
        response += "4. Cross-system correlations\n"
        
        return response

    def _elaborate_generic_response(self, persona: str, response: str) -> str:
        """Generic elaboration when specific type isn't detected."""
        elaboration = f"{persona}, let me elaborate on that:\n\n"
        elaboration += "Based on the previous analysis, the recommendation considers:\n"
        elaboration += "- Current system health metrics\n"
        elaboration += "- Error patterns and frequency\n"
        elaboration += "- Gaps in current backlog coverage\n"
        elaboration += "- Cross-system correlations\n\n"
        elaboration += "For more specific details, you can ask about:\n"
        elaboration += "- Specific error themes\n"
        elaboration += "- Individual health scores\n"
        elaboration += "- Priority calculations\n"
        
        return elaboration

    # ===== BUG #3: STORY DRAFTING ASSISTANCE FIX =====
    
    def _is_story_drafting_request(self, query: str) -> bool:
        """Detect if user is asking for help drafting a user story."""
        query_lower = query.lower()
        
        drafting_keywords = [
            "help me write",
            "help me create",
            "help me draft",
            "draft a",
            "write a",
            "create a",
            "generate a",
        ]
        
        story_terms = [
            "user story",
            "story",
            "backlog item",
            "feature",
        ]
        
        has_drafting = any(keyword in query_lower for keyword in drafting_keywords)
        has_story = any(term in query_lower for term in story_terms)

        # Exclude test case requests — "write a test case for story X" is NOT story drafting
        if "test case" in query_lower or "test scenario" in query_lower:
            return False

        # Exclude follow-up requests on pending stories (review/create existing drafts)
        if self.pending_stories and any(
            term in query_lower for term in ("review", "these stories", "these user stories", "before you create", "let me review")
        ):
            return False
        
        return has_drafting and has_story

    def _extract_story_topic(self, query: str) -> str:
        """Extract the specific topic/feature from the query."""
        query_lower = query.lower()

        # 1. If the user references something they said earlier ("you said X", "you mentioned X"),
        #    extract X as the topic directly. This handles queries like
        #    "you said system health is critical. can you create a user story for me"
        reference_match = re.search(
            r"(?:you|as you)\s+(?:said|mentioned|noted|told me|indicated)\s+([^.!?]+)",
            query_lower,
        )
        if reference_match:
            topic = reference_match.group(1).strip(".:,;!? ").strip()
            if topic and len(topic) >= 3:
                return topic

        # 2. Strip conversational preambles (e.g., "can you", "please", "i need")
        preamble_patterns = [
            r"^can you\s+",
            r"^could you\s+",
            r"^please\s+",
            r"^would you\s+",
            r"^do you think you can\s+",
            r"^help me\s+",
            r"^i (need|want|would like|am looking for|need you to)\s+",
        ]
        topic = query_lower
        for pattern in preamble_patterns:
            topic = re.sub(pattern, "", topic)
        
        # 3. Strip known drafting prefixes
        prefixes = [
            "help me write a user story for",
            "help me write a story for",
            "help me create a user story for",
            "help me create a story for",
            "help me to create a new user story to",
            "help me to create a user story to",
            "help me to create a new user story for",
            "help me to create a user story for",
            "to create a new user story to",
            "to create a new user story for",
            "to create a user story to",
            "to create a user story for",
            "create a new user story to",
            "create a new user story for",
            "create a user story to",
            "draft a user story for",
            "draft a story for",
            "write a user story for",
            "write a story for",
            "create a user story for",
            "create a story for",
            "help me write the user story for",
            "help me to write a user story for",
            "help me to write the user story for",
            "this high priority item",
            "this",
        ]
        for prefix in prefixes:
            if topic.startswith(prefix):
                topic = topic[len(prefix):].strip()

        # 4. Strip trailing filler / conversational noise
        trailing_patterns = [
            r"\.\s*let me know if you have any questions?.*$",
            r"\.\s*let me know.*$",
            r"\.\s*do you have any questions?.*$",
            r"\.\s*any questions?\??.*$",
            r"\s*(please|for me|for us|me|thanks|thank you|now|then|ok|okay|right away|asap)?\s*[.!?]*$",
        ]
        for pattern in trailing_patterns:
            topic = re.sub(pattern, "", topic, flags=re.IGNORECASE)

        # 5. Clean up remaining punctuation and whitespace
        topic = topic.strip(".:,;!?")
        topic = topic.strip()
        # 6. Validate: reject empty or purely conversational topics
        if not topic or len(topic) < 3:
            return None
        return topic

    @staticmethod
    def _extract_incident_id(query: str) -> str | None:
        match = re.search(r"\bINC\d+\b", query, re.IGNORECASE)
        return match.group(0).upper() if match else None

    async def _execute_llm_story_draft(self, persona: str, query: str, topic: str) -> str:
        """Use LLM to generate a proper user story draft based on the user's request."""
        # Gather any relevant context from agents
        incident_id = self._extract_incident_id(topic)
        context_intent = {"agents": ["ServiceNow Agent", "Splunk Agent"]} if incident_id else {"agents": ["JIRA Agent"]}
        agents_used, contexts = await self.retrieve_context(query, context_intent, project_id=self._current_project_id)
        self.last_agents_used = agents_used
        context_text = json.dumps(contexts, default=str) if contexts else "No additional context available."

        if settings.ONE_MIN_AI_API_KEY:
            try:
                response = await one_min_ai_completion(
                    model=settings.LITELLM_MODEL,
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "You are MAHALO's story drafting assistant. The user (a Product Manager) wants you "
                                "to draft a JIRA user story based on their request.\n\n"
                                f"{self._role_system_instructions(persona)}\n\n"
                                "INSTRUCTIONS:\n"
                                "1. Carefully read the user's request to understand the feature/offer they want to build.\n"
                                "2. Draft a complete JIRA story with:\n"
                                "   - A clear, concise title\n"
                                "   - A description that captures the business context\n"
                                "   - A user story in 'As a [persona], I want [goal], so that [benefit]' format\n"
                                "   - Priority (based on business urgency)\n"
                                "   - Story point estimate with brief justification\n"
                                "   - Sprint suggestion\n"
                                "   - Acceptance criteria (specific, testable conditions)\n"
                                "3. If the user's request includes specific details (dates, pricing, limits), use them accurately.\n"
                                "4. Ask clarifying questions at the end if the request is ambiguous on key points.\n"
                                "5. Format the output clearly with labeled sections.\n"
                                "6. Do NOT use generic/templated content — make every field specific to the user's request."
                            )
                        },
                        {
                            "role": "user",
                            "content": (
                                f"Request: {query}\n"
                                f"Extracted topic: {topic}\n\n"
                                f"=== AVAILABLE PROJECT CONTEXT ===\n{context_text}"
                            )
                        },
                    ],
                    temperature=0.4,
                    max_tokens=800,
                )
                llm_story_text = response.choices[0].message.content
                # Store a structured version for potential JIRA creation later
                self.pending_stories = [{
                    "title": topic[:80],
                    "description": llm_story_text,
                    "story_points": 5,
                    "priority": "Medium",
                    "status": "Backlog",
                    "sprint": "Sprint 24",
                    "acceptance_criteria": [],
                    "evidence": [],
                    "_llm_generated": True,
                }]
                return llm_story_text
            except Exception:
                pass

        # Fallback: use the existing template-based approach if LLM is unavailable
        return self._draft_story_for_topic(persona, topic, contexts)

    def _draft_story_for_topic(self, persona: str, topic: str, contexts: list[dict[str, Any]]) -> str:
        """Draft a user story for a specific topic using relevant context."""
        incident_id = self._extract_incident_id(topic)
        incident = None
        for context in contexts:
            if context.get("source") != "ServiceNow" or not context.get("success"):
                continue
            data = context.get("data", {})
            items = data.get("items", []) if isinstance(data, dict) else []
            incident = next(
                (item for item in items if str(item.get("incident_id", "")).upper() == incident_id),
                None,
            )
            if incident:
                break

        splunk_context = next((ctx for ctx in contexts if ctx.get("source") == "Splunk"), None)
        logs = []
        if splunk_context and splunk_context.get("success"):
            data = splunk_context.get("data", {})
            logs = data.get("items", []) if isinstance(data, dict) else data if isinstance(data, list) else []
        
        topic_keywords = topic.lower().split()
        relevant_logs = [
            log for log in logs
            if any(keyword in log.get("message", "").lower() for keyword in topic_keywords)
        ]
        
        if not relevant_logs and logs:
            relevant_logs = logs
        
        story = self._build_story_from_incident(incident, relevant_logs) if incident else self._build_story_from_topic(topic, relevant_logs)
        self.pending_stories = [story]
        
        return self._format_story_draft(persona, story)

    def _build_story_from_incident(self, incident: dict[str, Any], logs: list[dict[str, Any]]) -> dict[str, Any]:
        incident_id = incident.get("incident_id", "the incident")
        title = incident.get("title", "production incident")
        description = incident.get("description", "")
        severity = str(incident.get("severity", "High")).title()
        story_title = f"Resolve {title.lower()}"
        acceptance_criteria = [
            f"The cause of {incident_id} is identified and the service remains healthy under load",
            "API failures return a safe, actionable response without data loss",
            "Monitoring alerts the operations team before error rates impact customers",
            "Staging and load tests cover the failure and recovery scenarios",
            "Automated tests and operational documentation are updated",
        ]
        evidence = [f"{incident_id}: {title} ({severity}, {incident.get('status', 'Active')})"]
        if description:
            evidence.append(description)
        evidence.extend(log.get("message", "") for log in logs[:3] if log.get("message"))
        return {
            "title": story_title,
            "description": f"Resolve {title.lower()} and improve service reliability. {description}".strip(),
            "story_points": 8 if severity in {"Critical", "High"} else 5,
            "priority": severity if severity in {"Critical", "High", "Medium", "Low"} else "High",
            "status": "Backlog",
            "sprint": "Sprint 24",
            "acceptance_criteria": acceptance_criteria,
            "evidence": evidence,
        }

    def _build_story_from_topic(self, topic: str, logs: list[dict[str, Any]]) -> dict[str, Any]:
        """Build a story structure based on the specified topic."""
        topic_lower = topic.lower()
        # Also check log messages for keywords when topic itself is generic
        log_messages = " ".join(log.get("message", "") for log in logs).lower()
        search_text = topic_lower + " " + log_messages
        
        if "timeout" in search_text or "failover" in search_text:
            title = "Improve service timeout recovery and failover"
            description = (
                "Handle service timeouts with bounded retries, safe failure states, "
                "and failover to ensure system reliability."
            )
            acceptance_criteria = [
                "Timeouts use bounded retries with exponential backoff",
                "Automatic failover when primary service times out",
                "Retries do not duplicate successful operations",
                "Timeout events are logged with full context",
                "Monitoring alerts when failover rate exceeds threshold",
                "Automated tests cover timeout, retry, and recovery scenarios",
            ]
        elif "pool" in search_text or "capacity" in search_text:
            title = "Protect system capacity during traffic spikes"
            description = (
                "Implement connection-pool protection, retry backoff, and capacity "
                "monitoring to prevent service degradation during high load."
            )
            acceptance_criteria = [
                "Connection-pool saturation is monitored with alerting",
                "Retry backoff prevents retry storms",
                "Capacity alerts reach the operations team",
                "Circuit breakers protect downstream services",
                "Load tests cover traffic spikes and recovery",
            ]
        elif "latency" in search_text:
            title = "Reduce service processing latency"
            description = (
                "Optimize service processing to meet SLA targets "
                "while maintaining accuracy and reliability."
            )
            acceptance_criteria = [
                "Latency is measured against defined targets",
                "Operations complete within SLA",
                "Accuracy is maintained or improved",
                "Latency metrics are visible in dashboards",
                "Automated tests validate performance",
            ]
        else:
            # Clean the topic for a natural story title
            clean_topic = re.sub(
                r"\s+(is|are|was|were|has|have|being)\s+[a-z]+$",
                "",
                topic_lower,
            ).strip()
            if not clean_topic or len(clean_topic) < 3:
                clean_topic = topic_lower
            title = f"Improve {clean_topic}"
            description = f"Address production reliability issues related to {clean_topic} to improve system stability and customer experience."
            acceptance_criteria = [
                f"Production issues related to {clean_topic} are resolved",
                "Solution is tested in staging environment",
                "Monitoring is in place to detect regressions",
                "Documentation is updated",
                "Automated tests cover the fix",
            ]
        
        evidence = [log.get("message", "") for log in logs[:5]]
        
        return {
            "title": title,
            "description": description,
            "story_points": 8,
            "priority": "High",
            "status": "Backlog",
            "sprint": "Sprint 24",
            "acceptance_criteria": acceptance_criteria,
            "evidence": evidence,
        }

    # ===== BUG #4: COMPOUND QUERY FIX =====
    
    def _is_compound_query(self, query: str) -> bool:
        """Detect if query contains multiple distinct questions."""
        query_lower = query.lower()
        
        indicators = [
            " and ",
            " and also ",
            ", and ",
            " as well as ",
            " plus ",
        ]
        
        has_indicator = any(ind in query_lower for ind in indicators)
        
        # Check for multiple question patterns
        question_words = ["what", "show", "tell", "list", "give"]
        question_count = sum(1 for word in question_words if query_lower.count(word) >= 1)
        
        return has_indicator and question_count >= 1

    def _split_compound_query(self, query: str) -> list[str]:
        """Split compound query into individual sub-queries."""
        query_lower = query.lower()
        
        split_patterns = [" and ", ", and ", " and also ", " as well as "]
        
        for pattern in split_patterns:
            if pattern in query_lower:
                parts = query.split(pattern, 1)
                return [part.strip() for part in parts if part.strip()]
        
        return [query]

    async def _get_pending_stories(self) -> dict[str, Any]:
        """Get stories that are pending (backlog, to do, ready)."""
        result = await self.jira_agent.retrieve_context("backlog stories")
        
        if not result.get("success"):
            return {"success": False, "data": {"items": []}}
        
        stories = result.get("data", {}).get("items", [])
        
        pending_statuses = ["backlog", "to do", "ready", "open"]
        pending_stories = [
            story for story in stories
            if story.get("status", "").lower() in pending_statuses
        ]
        
        priority_order = {"high": 1, "medium": 2, "low": 3}
        pending_stories.sort(
            key=lambda s: (
                priority_order.get(s.get("priority", "medium").lower(), 4),
                -s.get("story_points", 0)
            )
        )
        
        return {
            "success": True,
            "data": {"items": pending_stories},
            "summary": {
                "total_pending": len(pending_stories),
                "high_priority": sum(1 for s in pending_stories if s.get("priority", "").lower() == "high"),
                "total_points": sum(s.get("story_points", 0) for s in pending_stories),
            }
        }

    def _format_production_and_pending(self, persona: str, deployments: list[dict], pending_stories: list[dict]) -> str:
        """Format response for 'what's in production and what's pending' query."""
        response = f"{persona}, here's your production and pending status:\n\n"
        
        response += f"## In Production ({len(deployments)} features)\n\n"
        
        if deployments:
            response += "| # | Feature | Version |\n"
            response += "|---|---------|---------|\n"
            for i, dep in enumerate(deployments[:10], 1):
                feature = dep.get("feature_name", "Unknown")
                version = dep.get("version", "Unknown")
                response += f"| {i} | {feature} | {version} |\n"
            
            if len(deployments) > 10:
                response += f"\n_[{len(deployments) - 10} more deployments...]_\n"
        else:
            response += "_No deployments found._\n"
        
        response += "\n"
        
        response += f"## Pending in Backlog ({len(pending_stories)} stories)\n\n"
        
        if pending_stories:
            high_priority = [s for s in pending_stories if s.get("priority", "").lower() == "high"]
            medium_priority = [s for s in pending_stories if s.get("priority", "").lower() == "medium"]
            
            if high_priority:
                response += "**High Priority:**\n"
                for story in high_priority[:5]:
                    key = story.get("story_key", "???")
                    title = story.get("title", "Unknown")
                    points = story.get("story_points", 0)
                    response += f"- {key}: {title} ({points} pts)\n"
                response += "\n"
            
            if medium_priority:
                response += "**Medium Priority:**\n"
                for story in medium_priority[:3]:
                    key = story.get("story_key", "???")
                    title = story.get("title", "Unknown")
                    points = story.get("story_points", 0)
                    response += f"- {key}: {title} ({points} pts)\n"
                response += "\n"
            
            total_points = sum(s.get("story_points", 0) for s in pending_stories)
            response += f"_Total pending work: {total_points} story points_\n"
        else:
            response += "_No pending stories in backlog._\n"
        
        return response

    def _wants_formatting(self, query: str) -> str | None:
        """Detect if user wants specific formatting (bullet, numbered, table)."""
        query_lower = query.lower()
        
        if any(term in query_lower for term in ("bullet", "bullets", "bullet point", "bullet points")):
            return "bullet"
        if any(term in query_lower for term in ("numbered", "numbered list", "number", "numbers")):
            return "numbered"
        if any(term in query_lower for term in ("table", "tabular", "in a table")):
            return "table"
        if any(term in query_lower for term in ("format", "formatted", "better format", "clean format")):
            return "structured"
        
        return None

    def _generate_priority_story_recommendations(self, persona: str, contexts: list[dict[str, Any]]) -> str:
        """Generate intelligent recommendations for priority stories based on error analysis."""
        # Use correlation engine insights if available
        if self.last_insights:
            gaps = self.last_insights.get("gaps", [])
            priorities = self.last_insights.get("priorities", [])
            summary = self.last_insights.get("summary", {})
            
            if gaps or priorities:
                response = f"{persona}, based on analysis of {summary.get('total_errors', 0)} errors across {summary.get('total_logs', 0)} logs, here are the priority user stories:\n\n"
                
                if priorities:
                    response += "**Recommended Priority Stories:**\n\n"
                    for priority in priorities[:5]:
                        response += f"{priority['rank']}. **{priority['theme']}** ({priority['suggested_priority']} Priority)\n"
                        response += f"   - Reason: {priority['reason']}\n"
                        response += f"   - Estimated: {priority['story_points_estimate']} story points\n\n"
                
                if gaps:
                    response += "\n**Identified Gaps (need stories):**\n\n"
                    for gap in gaps[:3]:
                        response += f"• {gap.get('theme', 'Unknown')}: {gap.get('action', '')} ({gap.get('error_count', 0)} errors)\n"
                
                return response
        
        # Fallback to basic analysis
        splunk_context = next((c for c in contexts if c.get("source") == "Splunk"), None)
        if splunk_context:
            logs = splunk_context.get("data", {}).get("items", [])
            error_logs = [log for log in logs if log.get("level", "").upper() == "ERROR"]
            
            # Categorize errors
            themes = self._categorize_error_themes(error_logs)
            
            response = f"{persona}, based on {len(error_logs)} errors, I recommend these priority stories:\n\n"
            
            rank = 1
            for theme, count in sorted(themes.items(), key=lambda x: x[1], reverse=True):
                if count >= 2:
                    response += f"{rank}. **{theme.replace('_', ' ').title()}** (High Priority)\n"
                    response += f"   - {count} error occurrences detected\n"
                    response += f"   - Estimated: {8 if count >= 5 else 5} story points\n\n"
                    rank += 1
            
            return response
        
        return f"{persona}, I found error data but couldn't analyze it for story recommendations. Please rephrase your query."

    def _estimate_stories_needed(self, persona: str, contexts: list[dict[str, Any]]) -> str:
        """Estimate number of stories needed to address all errors."""
        # Use correlation engine insights
        if self.last_insights:
            gaps = self.last_insights.get("gaps", [])
            priorities = self.last_insights.get("priorities", [])
            summary = self.last_insights.get("summary", {})
            
            total_errors = summary.get("total_errors", 0)
            story_count = len(gaps) + len(priorities)
            total_points = sum(p.get("story_points_estimate", 5) for p in priorities[:5])
            
            response = f"{persona}, to address {total_errors} errors, I recommend creating **{story_count} user stories**:\n\n"
            
            if priorities:
                response += "**Story Breakdown:**\n\n"
                for priority in priorities[:5]:
                    response += f"• {priority['theme']}: {priority['story_points_estimate']} pts ({priority['suggested_priority']} priority)\n"
            
            response += f"\n**Total Estimated Effort:** {total_points} story points\n\n"
            response += "**Rationale:** Errors have been grouped by theme. Each theme requires 1 story. "
            response += "Related errors are consolidated to avoid duplication.\n\n"
            response += "**Next Steps:**\n"
            response += "1. Review the prioritized list above\n"
            response += "2. Start with High priority items first\n"
            response += "3. Consider creating all stories in a single sprint planning session\n"
            
            return response
        
        # Fallback analysis
        splunk_context = next((c for c in contexts if c.get("source") == "Splunk"), None)
        if splunk_context:
            logs = splunk_context.get("data", {}).get("items", [])
            error_logs = [log for log in logs if log.get("level", "").upper() == "ERROR"]
            
            themes = self._categorize_error_themes(error_logs)
            significant_themes = {k: v for k, v in themes.items() if v >= 2}
            
            story_count = len(significant_themes)
            total_points = sum(8 if count >= 5 else 5 for count in significant_themes.values())
            
            response = f"{persona}, to address {len(error_logs)} errors, I recommend creating **{story_count} user stories**:\n\n"
            response += "**Error Themes Identified:**\n"
            for theme, count in sorted(significant_themes.items(), key=lambda x: x[1], reverse=True):
                points = 8 if count >= 5 else 5
                response += f"• {theme.replace('_', ' ').title()}: {count} errors → {points} pts\n"
            
            response += f"\n**Total:** {story_count} stories, {total_points} story points\n"
            return response
        
        return f"{persona}, I found error data but need more context to estimate story count. Can you be more specific?"

    def _categorize_error_themes(self, errors: list[dict[str, Any]]) -> dict[str, int]:
        """Categorize errors by theme and return counts."""
        themes = {}
        
        for error in errors:
            message = error.get("message", "").lower()
            
            if "timeout" in message or "502" in message:
                themes["gateway_timeout"] = themes.get("gateway_timeout", 0) + 1
            elif "pool" in message or "connection" in message:
                themes["connection_pool"] = themes.get("connection_pool", 0) + 1
            elif "retry" in message or "queue" in message:
                themes["retry_capacity"] = themes.get("retry_capacity", 0) + 1
            elif "fraud" in message:
                themes["fraud_scoring"] = themes.get("fraud_scoring", 0) + 1
            elif "reconciliation" in message or "balance" in message:
                themes["reconciliation"] = themes.get("reconciliation", 0) + 1
            elif "latency" in message:
                themes["latency"] = themes.get("latency", 0) + 1
            else:
                themes["other"] = themes.get("other", 0) + 1
        
        return themes

    def _format_deployments_bullet(self, persona: str, deployments: list[dict]) -> str:
        """Format deployments as bullet points."""
        response = f"{persona}, {len(deployments)} features are deployed in production:\n\n"
        for item in deployments:
            response += f"• {item.get('feature_name')} ({item.get('version')})\n"
        return response

    def _format_deployments_numbered(self, persona: str, deployments: list[dict]) -> str:
        """Format deployments as numbered list."""
        response = f"{persona}, {len(deployments)} features are deployed in production:\n\n"
        for i, item in enumerate(deployments, 1):
            response += f"{i}. {item.get('feature_name')} ({item.get('version')})\n"
        return response

    def _format_deployments_table(self, persona: str, deployments: list[dict]) -> str:
        """Format deployments as markdown table."""
        response = f"{persona}, {len(deployments)} features are deployed in production:\n\n"
        response += "| # | Feature | Version |\n"
        response += "|---|---------|---------|\n"
        for i, item in enumerate(deployments, 1):
            response += f"| {i} | {item.get('feature_name')} | {item.get('version')} |\n"
        return response

    def _format_deployments_default(self, persona: str, deployments: list[dict]) -> str:
        """Format deployments as comma-separated (default/fallback)."""
        return f"{persona}, {len(deployments)} features are deployed in production: " + ", ".join(
            f"{item.get('feature_name')} ({item.get('version')})"
            for item in deployments
        ) + "."

    @staticmethod
    def _is_top_issue_request(query: str) -> bool:
        query_lower = query.lower()
        return (
            any(phrase in query_lower for phrase in ("top issue", "biggest issue", "most important issue", "top problem"))
            and any(term in query_lower for term in ("project", "current", "overall", "system"))
        )

    def _fallback_response(self, persona: str, query: str, contexts: list[dict[str, Any]]) -> str:
        query_lower = query.lower()
        successful = [context for context in contexts if context.get("success")]

        if self._is_top_issue_request(query):
            priorities = self.last_insights.get("priorities", [])
            if not priorities:
                return f"{persona}, I could not identify a current top issue from the available project data."
            top = priorities[0]
            incident = f" ({top['incident_id']})" if top.get("incident_id") else ""
            return (
                f"{persona}, the top issue is {top.get('theme', 'the highest-priority issue')}{incident}.\n"
                f"Why: {top.get('reason', 'It has the highest current impact.')}\n"
                f"Priority: {top.get('suggested_priority', 'High')}\n"
                f"Estimated effort: {top.get('story_points_estimate', 'Not estimated')} story points."
            )
        
        # === PRIORITY HANDLING: Story Planning Queries ===
        # These need intelligent analysis, not just data listing
        
        if ("priority" in query_lower or "prioritize" in query_lower or "priorit" in query_lower) and \
           ("story" in query_lower or "stories" in query_lower or "user stor" in query_lower) and \
           ("error" in query_lower or "based on" in query_lower):
            # User is asking for prioritized stories based on errors
            return self._generate_priority_story_recommendations(persona, contexts)
        
        if ("how many" in query_lower or "how much" in query_lower) and \
           ("story" in query_lower or "stories" in query_lower) and \
           ("error" in query_lower or "address" in query_lower or "fix" in query_lower or "create" in query_lower):
            # User is asking how many stories needed to address errors
            return self._estimate_stories_needed(persona, contexts)
        
        # Detect desired formatting
        format_type = self._wants_formatting(query)
        
        # PRIORITY FIX: Handle deployment/production queries BEFORE executive overview
        # Check for deployment-specific queries (production features, what's deployed, etc.)
        is_deployment_query = (
            ("production" in query_lower or "deployed" in query_lower) and
            ("feature" in query_lower or "how many" in query_lower) and
            not ("pending" in query_lower or "backlog" in query_lower)
        )
        
        if is_deployment_query:
            context = next((item for item in successful if item.get("record_type") == "deployments"), None)
            if context:
                deployments = context.get("data", {}).get("items", [])
                
                # Apply requested formatting
                if format_type == "bullet":
                    return self._format_deployments_bullet(persona, deployments)
                elif format_type == "numbered":
                    return self._format_deployments_numbered(persona, deployments)
                elif format_type == "table":
                    return self._format_deployments_table(persona, deployments)
                else:
                    # Default: check if it's a re-ask for formatting
                    if any(term in query_lower for term in ("give me", "show me", "format", "list")):
                        return self._format_deployments_bullet(persona, deployments)
                    return self._format_deployments_default(persona, deployments)
        
        # For executive overview, use correlation insights if available
        if (self.last_intent.get("intent") == "executive_overview" or 
            "executive" in query_lower or 
            "overview" in query_lower or
            ("summary" in query_lower and "project" in query_lower)):
            
            # Use correlation engine insights if available
            if self.last_insights:
                insights_text = self.correlation_engine.format_insights_for_llm()
                return f"{persona}, here is the executive update:\n\n{insights_text}"
            
            # Fallback to basic summary
            jira_context = next((context for context in successful if context.get("source") == "JIRA"), None)
            servicenow_context = next((context for context in successful if context.get("source") == "ServiceNow"), None)
            splunk_context = next((context for context in successful if context.get("source") == "Splunk"), None)
            stories = jira_context.get("data", {}).get("items", []) if jira_context else []
            service_data = servicenow_context.get("data", {}) if servicenow_context else {}
            deployments = service_data.get("deployments", [])
            incidents = service_data.get("incidents", [])
            logs = splunk_context.get("data", {}).get("items", []) if splunk_context else []
            errors = [log for log in logs if log.get("level", "").upper() == "ERROR"]
            done = sum(story.get("status", "").lower() == "done" for story in stories)
            active_incidents = sum(incident.get("status", "").lower() in {"new", "active", "monitoring"} for incident in incidents)
            return (
                f"{persona}, here is the executive update:\n"
                f"- Delivery: {len(stories)} tracked stories, {done} completed.\n"
                f"- Production: {len(deployments)} deployed features.\n"
                f"- Operations: {active_incidents} active or monitoring incidents.\n"
                f"- Reliability: {len(errors)} error logs out of {len(logs)} total logs.\n"
                "Priority: review the recurring production signals before expanding the roadmap."
            )

        story_detail_context = next(
            (item for item in successful if item.get("record_type") == "story_detail"),
            None,
        )
        if story_detail_context:
            story_key = story_detail_context.get("story_key", "the requested story")
            story = story_detail_context.get("data", {})
            if story:
                # Check if user wants a test case for this story (before returning story details)
                if any(term in query_lower for term in ("test case", "test cases", "qa test", "write a test")):
                    return (
                        f"{persona}, here is a QA test case for {story.get('story_key', 'the story')}:\n\n"
                        f"Test case: Verify {story.get('title', 'the story')}\n"
                        f"Objective: Confirm the implementation meets the story requirements.\n"
                        "Preconditions:\n- Test environment is available.\n- Required test data and service stubs are configured.\n\n"
                        "Steps:\n"
                        "1. Submit a representative request to the service.\n"
                        "2. Simulate the primary provider failure or timeout described by the story.\n"
                        "3. Observe retry, failover, monitoring, and final transaction state.\n"
                        "4. Repeat with a successful provider response after the failure.\n\n"
                        "Expected results:\n"
                        "- The failure is handled according to the story acceptance criteria.\n"
                        "- Retries are bounded and do not duplicate a successful transaction.\n"
                        "- Monitoring and alerts contain actionable diagnostic context.\n"
                        "- The final transaction state is correct and auditable.\n\n"
                        "Pass criteria: all expected results pass and no duplicate, lost, or incorrectly settled transaction is observed."
                    )
                wants_point_estimate = "estimate" in query_lower and "point" in query_lower
                if wants_point_estimate:
                    return self._format_story_point_estimate(persona, story, story_key)
                return (
                    f"{persona}, here are the details for {story.get('story_key', story_key)}:\n\n"
                    f"Title: {story.get('title', 'Untitled story')}\n"
                    f"Status: {story.get('status', 'Unknown')}\n"
                    f"Description: {story.get('description', 'No description available.')}\n"
                    f"Assignee: {story.get('assignee_username') or 'Unassigned'}\n"
                    f"Story points: {story.get('story_points', 'Not estimated')}"
                )
            return f"{persona}, I could not find {story_key} in the current JIRA data."
        # Note: Deployment queries are now handled earlier in this function
        if any(term in query_lower for term in ("test case", "test cases", "qa test", "write a test")):
            context = next((item for item in successful if item.get("record_type") == "story_detail"), None)
            story = context.get("data", {}) if context else {}
            if story:
                return (
                    f"{persona}, here is a QA test case for {story.get('story_key', 'the story')}:\n\n"
                    f"Test case: Verify {story.get('title', 'the story')}\n"
                    f"Objective: Confirm the implementation meets the story requirements.\n"
                    "Preconditions:\n- Test environment is available.\n- Required test data and service stubs are configured.\n\n"
                    "Steps:\n"
                    "1. Submit a representative request to the service.\n"
                    "2. Simulate the primary provider failure or timeout described by the story.\n"
                    "3. Observe retry, failover, monitoring, and final transaction state.\n"
                    "4. Repeat with a successful provider response after the failure.\n\n"
                    "Expected results:\n"
                    "- The failure is handled according to the story acceptance criteria.\n"
                    "- Retries are bounded and do not duplicate a successful transaction.\n"
                    "- Monitoring and alerts contain actionable diagnostic context.\n"
                    "- The final transaction state is correct and auditable.\n\n"
                    "Pass criteria: all expected results pass and no duplicate, lost, or incorrectly settled transaction is observed."
                )
            detail_context = next((item for item in contexts if item.get("record_type") == "story_detail"), None)
            if detail_context and not detail_context.get("success"):
                story_key = detail_context.get("story_key", "the requested story")
                return (
                    f"{persona}, I could not find {story_key} in the current JIRA data. "
                    "The demo reset may have removed a previously generated story. "
                    "Use an existing key such as STORY-101, or create the story again before requesting its test case."
                )
        if ("feature" in query_lower or "focus" in query_lower or "next" in query_lower) and any(term in query_lower for term in ("error", "errors", "log", "logs")) and "quarter" not in query_lower and "velocity" not in query_lower:
            splunk_context = next((context for context in successful if context.get("source") == "Splunk"), None)
            logs = splunk_context.get("data", {}).get("items", []) if splunk_context else []
            error_logs = [log for log in logs if log.get("level", "").upper() == "ERROR"]
            messages = " ".join(log.get("message", "") for log in error_logs).lower()
            if error_logs:
                if "timeout" in messages or "502" in messages:
                    feature = "service timeout recovery and failover"
                    reason = "repeated gateway timeout and downstream provider failure signals"
                elif "pool" in messages or "retry" in messages:
                    feature = "capacity protection and retry backoff"
                    reason = "connection-pool exhaustion and retry saturation signals"
                elif "latency" in messages:
                    feature = "latency observability and performance controls"
                    reason = "repeated latency threshold breaches"
                else:
                    feature = "production error resilience and observability"
                    reason = "the recurring production error pattern"
                return (
                    f"{persona}, the next feature to focus on is **{feature}**.\n\n"
                    f"I found {len(error_logs)} error logs. The recommendation is driven by {reason}.\n"
                    "Suggested outcome: reduce customer-facing failures, add actionable monitoring, and verify recovery with automated tests.\n"
                    "Recommended story size: 8 points, High priority."
                )
        compound_planning = (
            "velocity" in query_lower
            and ("error" in query_lower or "log" in query_lower or "feature" in query_lower or "stories" in query_lower)
            and ("quarter" in query_lower or "how many" in query_lower or "need" in query_lower)
        )
        if compound_planning:
            jira_context = next((context for context in successful if context.get("source") == "JIRA"), None)
            splunk_context = next((context for context in successful if context.get("source") == "Splunk"), None)
            summary = jira_context.get("summary", {}) if jira_context else {}
            stories = jira_context.get("data", {}).get("items", []) if jira_context else []
            logs = splunk_context.get("data", {}).get("items", []) if splunk_context else []
            error_logs = [log for log in logs if log.get("level", "").upper() == "ERROR"]
            messages = " ".join(log.get("message", "") for log in error_logs).lower()
            current_story_text = " ".join(
                f"{story.get('title', '')} {story.get('description', '')}" for story in stories
            ).lower()
            gaps = []
            if any(term in messages for term in ("timeout", "502")) and not any(term in current_story_text for term in ("failover", "timeout", "recovery")):
                gaps.append(("Service timeout recovery and failover", 8))
            if any(term in messages for term in ("pool", "retry")) and not any(term in current_story_text for term in ("retry", "capacity", "pool")):
                gaps.append(("Connection-pool protection and retry backoff", 8))
            if any(term in messages for term in ("latency", "mismatch")):
                gaps.append(("Latency monitoring and reconciliation safeguards", 5))
            completed_points = summary.get("completed_story_points", 0)
            total_points = summary.get("total_story_points", 0)
            remaining_points = max(total_points - completed_points, 0)
            quarter_capacity = completed_points * 6
            proposed_points = sum(points for _, points in gaps)
            capacity_text = (
                f"At the current throughput of {completed_points} completed points per sprint, a six-sprint quarter is approximately {quarter_capacity} points. "
                f"The suggested work is about {proposed_points} points, so there is enough capacity in principle, subject to dependencies and team availability."
            )
            if gaps:
                gap_text = "\n".join(f"- {title} ({points} points)" for title, points in gaps)
                return (
                    f"{persona}, yes. I found {len(error_logs)} error logs across {len(logs)} relevant logs. "
                    f"The current sprint has completed {completed_points} of {total_points} points, with {remaining_points} points remaining in the current plan.\n\n"
                    f"Recommended feature work:\n{gap_text}\n\n{capacity_text}"
                )
            return f"{persona}, I found {len(error_logs)} error logs, but the current stories appear to cover their themes. {capacity_text}"
        if "velocity" in query_lower:
            summary = next((context.get("summary") for context in successful if context.get("source") == "JIRA"), None)
            if summary:
                return (
                    f"{persona}, the current sprint has completed {summary['completed_story_points']} of "
                    f"{summary['total_story_points']} story points ({summary['completion_percent']}%). "
                    f"That is {summary['completed_stories']} completed, {summary['in_progress_stories']} in progress, "
                    f"and {summary['backlog_stories']} in backlog across {summary['total_stories']} stories."
                )
        if "bug" in query_lower:
            summary = next((context.get("summary") for context in successful if context.get("record_type") == "bugs"), None)
            bugs = next((context.get("data", {}).get("items", []) for context in successful if context.get("record_type") == "bugs"), [])
            if summary:
                assignments = ", ".join(
                    f"{bug.get('bug_key')} ({bug.get('assignee_username') or 'unassigned'})"
                    for bug in bugs
                )
                return (
                    f"{persona}, JIRA has {summary['total_bugs']} bugs: {summary['critical_bugs']} critical and "
                    f"{summary['open_bugs']} open or in progress. Assigned work: {assignments}."
                )
        if "error" in query_lower and any(term in query_lower for term in ("how many", "count", "number of")):
            summary = next((context.get("summary") for context in successful if context.get("record_type") == "error_logs"), None)
            if summary:
                return f"{persona}, Splunk contains {summary['error_count']} error logs."
        if ("story" in query_lower or "stories" in query_lower) and any(term in query_lower for term in ("analyze", "analyse")) and any(term in query_lower for term in ("log", "logs", "error", "errors")):
            splunk_context = next((context for context in successful if context.get("source") == "Splunk"), None)
            jira_context = next((context for context in successful if context.get("source") == "JIRA"), None)
            logs = splunk_context.get("data", {}).get("items", []) if splunk_context else []
            stories = jira_context.get("data", {}).get("items", []) if jira_context else []
            if logs:
                error_count = sum(log.get("level", "").upper() == "ERROR" for log in logs)
                story_text = " ".join(
                    f"{story.get('title', '')} {story.get('description', '')}" for story in stories
                ).lower()
                gaps = []
                if any(term in " ".join(log.get("message", "") for log in logs).lower() for term in ("timeout", "502")) and not any(term in story_text for term in ("failover", "timeout", "recovery")):
                    gaps.append("gateway timeout and provider failover handling")
                if any(term in " ".join(log.get("message", "") for log in logs).lower() for term in ("pool", "retry")) and not any(term in story_text for term in ("retry", "capacity", "pool")):
                    gaps.append("connection-pool protection and retry backoff")
                if any(term in " ".join(log.get("message", "") for log in logs).lower() for term in ("latency", "mismatch")):
                    gaps.append("latency monitoring and reconciliation safeguards")
                if gaps:
                    return (
                        f"{persona}, yes. I found {len(logs)} relevant logs, including {error_count} errors, and the current backlog does not fully cover these areas:\n"
                        + "\n".join(f"- Create a story for {gap}." for gap in gaps)
                        + "\nThese should be prioritized from the recurring error patterns before adding unrelated backlog work."
                    )
                return f"{persona}, the logs show {error_count} errors, but the current JIRA stories appear to cover the detected themes. I would monitor the trend before creating more stories."
        if ("story" in query_lower or "stories" in query_lower) and any(term in query_lower for term in ("suggest", "recommend", "few")):
            logs = next((context.get("data", {}).get("items", []) for context in successful if context.get("source") == "Splunk"), [])
            if logs:
                evidence_by_type = {}
                for log in logs:
                    message = log.get("message", "")
                    key = "service reliability"
                    if "pool" in message.lower() or "retry" in message.lower():
                        key = "capacity and retries"
                    elif "fraud" in message.lower():
                        key = "fraud decision latency"
                    elif "reconciliation" in message.lower() or "balance" in message.lower():
                        key = "reconciliation accuracy"
                    evidence_by_type.setdefault(key, message)
                suggestions = [
                    ("Improve service timeout recovery", "Handle timeouts with safe retries and clear failure states.", "Timeouts and intermittent failures are visible in Splunk."),
                    ("Protect system capacity during traffic spikes", "Add connection-pool protection, retry backoff, and saturation alerts.", "Connection-pool exhaustion and retry-queue saturation are visible in Splunk."),
                    ("Reduce processing latency", "Improve service latency and detect issues before they impact users.", "Latency and error patterns are visible in Splunk."),
                ]
                response_lines = [f"{persona}, here are three user stories based on the error logs:"]
                for index, (title, description, evidence) in enumerate(suggestions, start=1):
                    response_lines.extend([
                        f"{index}. Title: {title}",
                        f"   Description: {description}",
                        f"   Evidence: {evidence}",
                        "   Acceptance criteria: the failure is handled safely, monitored, and covered by an automated test.",
                    ])
                return "\n".join(response_lines)
        if "assigned" in query_lower or "who is working" in query_lower:
            story_context = next((context for context in successful if context.get("source") == "JIRA" and context.get("record_type") != "bugs"), None)
            stories = story_context.get("data", {}).get("items", []) if story_context else []
            if stories:
                assignments = ", ".join(
                    f"{story.get('story_key')} is assigned to {story.get('assignee_username') or 'nobody'}"
                    for story in stories
                )
                return f"{persona}, {assignments}."
        if ("story" in query_lower or "stories" in query_lower) and any(term in query_lower for term in ("create", "fix", "based on")):
            logs = next((context.get("data", {}).get("items", []) for context in successful if context.get("source") == "Splunk"), [])
            if logs:
                evidence = "; ".join(log.get("message", "") for log in logs[:3])
                return (
                    f"{persona}, I recommend this user story:\n"
                    "Title: Improve service reliability\n"
                    "Description: Reduce service failures by handling timeouts, protecting the connection pool, "
                    "and improving retry behavior.\n"
                    f"Evidence from Splunk: {evidence}\n"
                    "Acceptance criteria: timeout failures are retried safely, connection-pool exhaustion is monitored, "
                    "and failed transactions produce actionable alerts."
                )
        lines = []
        for context in successful:
            source = context["source"]
            items = context.get("data", {}).get("items", [])
            if source == "JIRA":
                if context.get("record_type") == "bugs":
                    lines.append("JIRA found " + ", ".join(
                        f"{item.get('bug_key', 'unknown')} assigned to {item.get('assignee_username') or 'nobody'}"
                        for item in items[:5]
                    ))
                else:
                    lines.append(f"JIRA found {len(items)} matching stories: " + ", ".join(item.get("story_key", "unknown") for item in items[:5]))
            elif source == "ServiceNow":
                lines.append(f"ServiceNow found {len(items)} matching incidents: " + ", ".join(item.get("incident_id", "unknown") for item in items[:5]))
            elif source == "Splunk":
                lines.append(f"Splunk found {len(items)} matching logs: " + ", ".join(item.get("message", "") for item in items[:3]))
        if lines:
            return f"{persona}, here is what I found:\n" + "\n".join(f"- {line}" for line in lines)
        return f"{persona}, I could not retrieve matching records from the connected tools."

    def _llm_response_is_grounded(self, query: str, response: str, contexts: list[dict[str, Any]]) -> bool:
        response_lower = response.lower()
        if "found 0 matching logs" in response_lower:
            splunk_items = next(
                (context.get("data", {}).get("items", []) for context in contexts if context.get("source") == "Splunk"),
                [],
            )
            if splunk_items:
                return False
        query_lower = query.lower()
        if "velocity" in query_lower and ("quarter" in query_lower or "how many" in query_lower) and any(term in query_lower for term in ("error", "log", "feature", "story", "stories")):
            if not any(term in response_lower for term in ("error", "feature", "capacity", "points")):
                return False
        if ("story" in query_lower or "stories" in query_lower) and any(term in query_lower for term in ("analyze", "analyse")):
            splunk_items = next(
                (context.get("data", {}).get("items", []) for context in contexts if context.get("source") == "Splunk"),
                [],
            )
            if splunk_items and not any(term in response_lower for term in ("yes", "no", "create", "monitor")):
                return False
        if ("story" in query_lower or "stories" in query_lower) and any(term in query_lower for term in ("suggest", "recommend", "few")):
            splunk_items = next(
                (context.get("data", {}).get("items", []) for context in contexts if context.get("source") == "Splunk"),
                [],
            )
            if splunk_items:
                return False
        if ("story" in query_lower or "stories" in query_lower) and "based on" in query_lower:
            splunk_items = next(
                (context.get("data", {}).get("items", []) for context in contexts if context.get("source") == "Splunk"),
                [],
            )
            return bool(splunk_items) and any(keyword in response_lower for keyword in ("title", "acceptance criteria", "description"))
        return True

    async def process_query(self, user_persona: str, user_query: str, conversation_history: list[dict[str, str]] | None = None, project_id: str | None = None):
        self._current_project_id = project_id
        user_query_lower = user_query.lower()
        
        # ===== LAYER 1: META-COMMAND DETECTION (BUGS #1, #2, #3) =====
        
        # Bug #1: Formatting requests
        if self._is_formatting_request(user_query, conversation_history):
            return self._reformat_last_response(user_persona, conversation_history)
        
        # Bug #2: Elaboration/justification requests
        if self._is_elaboration_request(user_query, conversation_history):
            return self._elaborate_last_response(user_persona, conversation_history)
        
        # Bug #3: Story drafting assistance
        # Instead of immediately generating a hardcoded story, route through the
        # interpretation layer so the system shows understanding and asks confirmation.
        if self._is_story_drafting_request(user_query):
            topic = self._extract_story_topic(user_query)
            if topic:
                # Build a synthetic intent for story drafting so it flows through Layer 5
                story_draft_intent = {
                    "intent": "draft_user_story",
                    "agents": ["JIRA Agent"],
                    "entities": {"topic": topic},
                    "requires_confirmation": True,
                    "confidence": 0.9,
                }
                self.last_intent = story_draft_intent
                self.pending_action = {
                    "intent": story_draft_intent,
                    "query": user_query,
                    "persona": user_persona,
                    "conversation_history": conversation_history,
                }
                return self._build_interpretation_message(user_persona, story_draft_intent, user_query)
            else:
                return f"{user_persona}, I'd be happy to help you write a user story. What feature or issue should the story address?"
        
        # ===== LAYER 2: COMPOUND QUERY DETECTION (BUG #4) =====
        
        # Special case: Production + Pending/Priority query
        # Handles queries like:
        # - "what is in production and what is pending"
        # - "what is in production now and what is high priority next"
        # - "show me deployed features and backlog"
        if (("production" in user_query_lower or "deployed" in user_query_lower) and
            ("pending" in user_query_lower or "backlog" in user_query_lower or 
             "priority" in user_query_lower or "next" in user_query_lower)):
            
            sn_result = await self.servicenow_agent.retrieve_context("production deployments")
            deployments = sn_result.get("data", {}).get("items", [])
            if not deployments:
                # Try alternate data structure
                deployments = sn_result.get("data", {}).get("deployments", [])
            
            pending_result = await self._get_pending_stories()
            pending_stories = pending_result.get("data", {}).get("items", [])
            
            return self._format_production_and_pending(user_persona, deployments, pending_stories)
        
        # ===== LAYER 3: CONFIRMATION HANDLING =====
        # If we have a pending action, check if user is confirming or rejecting
        if self.pending_action:
            if self._is_user_confirming(user_query):
                # User confirmed — execute the stored action
                action = self.pending_action
                self.pending_action = None
                return await self._execute_confirmed_action(action)
            elif self._is_user_rejecting(user_query):
                # User rejected — clear and ask what else they need
                self.pending_action = None
                return f"{user_persona}, understood. What else can I help you with?"
            else:
                # User sent a new query instead of confirming — clear pending and proceed with new query
                self.pending_action = None

        # ===== LAYER 4: INTENT CLASSIFICATION =====
        
        self.last_intent = self.intent_classifier.classify(
            user_query,
            conversation_history=conversation_history,
            has_pending_stories=bool(self.pending_stories),
        )
        if self.last_intent.get("intent") == "greeting":
            return f"Hello, {user_persona}. I’m MAHALO, your SDLC assistant. Ask me about delivery, incidents, deployments, logs, or production planning."

        # ===== LAYER 5: INTERPRETATION BEFORE ACTION =====
        # Handle save_code directly — no need for interpretation layer
        if self.last_intent.get("intent") == "save_code":
            return await self._handle_save_code(user_persona)

        # Present understanding and ask for confirmation (unless exempt)
        if not self._should_skip_confirmation(self.last_intent, user_query, conversation_history):
            self.pending_action = {
                "intent": self.last_intent,
                "query": user_query,
                "persona": user_persona,
                "conversation_history": conversation_history,
            }
            return self._build_interpretation_message(user_persona, self.last_intent, user_query)

        # ===== LAYER 6: DIRECT EXECUTION (exempt intents or follow-ups) =====
        # Check for follow-up on pending stories (must be specific to avoid false positives)
        follow_up = (
            self.pending_stories and  # Only if we have pending stories
            any(term in user_query_lower for term in (
                "suggested use case", "suggested stories", "complete details", 
                "acceptance criteria", "expand", "review"
            ))
        ) or (
            # "elaborate" only if clearly about stories, not general overview
            "elaborate" in user_query_lower and 
            ("story" in user_query_lower or "stories" in user_query_lower) and
            self.pending_stories
        ) or (
            self.pending_stories and self.last_intent.get("intent") == "review_pending_stories"
        )
        review_first = any(term in user_query_lower for term in ("review", "before you create", "before creating", "do not create", "don't create", "first"))
        explicit_jira_write = not review_first and (
            (
                "jira" in user_query_lower and
                any(action in user_query_lower for action in ("create", "save", "write", "add"))
            ) or self.last_intent.get("intent") == "confirm_create_story"
        )
        if (follow_up or explicit_jira_write) and self.pending_stories:
            if explicit_jira_write:
                results = [await self.jira_agent.create_story(story, project_id=self._current_project_id) for story in self.pending_stories]
                created = [result.get("data", {}).get("story_key", "new story") for result in results if result.get("success")]
                if len(created) == len(results):
                    self.pending_stories = []
                    return f"{user_persona}, created {len(created)} stories in JIRA: {', '.join(created)}."
                return f"{user_persona}, created {len(created)} stories, but some writes failed."
            if any(term in user_query_lower for term in ("elaborate", "expand")):
                selected_story = self._select_pending_story(user_query)
                if any(term in user_query_lower for term in ("2nd", "second", "story 2", "story two")):
                    selected_story = self.pending_stories[min(1, len(self.pending_stories) - 1)]
                if "priority" in user_query_lower:
                    return self._format_priority_explanation(user_persona, selected_story)
                return self._format_story_draft(user_persona, selected_story)
            return self._format_story_drafts(user_persona, self.pending_stories)
        context_query = "executive overview" if self._is_top_issue_request(user_query) else user_query
        context_intent = (
            {"agents": ["JIRA Agent", "ServiceNow Agent", "Splunk Agent"]}
            if self._is_top_issue_request(user_query)
            else self.last_intent
        )
        agents_used, contexts = await self.retrieve_context(context_query, context_intent, project_id=self._current_project_id)
        
        # Perform intelligent correlation across agent contexts
        insights = self.correlation_engine.correlate_contexts(contexts)
        self.last_insights = insights
        if self._is_top_issue_request(user_query):
            priorities = insights.get("priorities", [])
            if priorities:
                top = priorities[0]
                incident = f" ({top['incident_id']})" if top.get("incident_id") else ""
                return (
                    f"{user_persona}, the top issue is {top.get('theme', 'the highest-priority issue')}{incident}.\n"
                    f"Why: {top.get('reason', 'It has the highest current impact.')}\n"
                    f"Priority: {top.get('suggested_priority', 'High')}\n"
                    f"Estimated effort: {top.get('story_points_estimate', 'Not estimated')} story points."
                )
            return f"{user_persona}, I could not identify a current top issue from the available project data."
        if ("analyze" in user_query_lower or "analyse" in user_query_lower) and ("story" in user_query_lower or "stories" in user_query_lower):
            self.pending_stories = self._draft_stories_from_context(contexts)
        if ("suggest" in user_query_lower or "recommend" in user_query_lower) and ("story" in user_query_lower or "stories" in user_query_lower):
            self.pending_stories = self._draft_stories_from_context(contexts)
        if follow_up or (("create" in user_query_lower or "stories" in user_query_lower) and "story" in user_query_lower and self.last_contexts):
            wants_multiple = "stories" in user_query_lower or "these user stories" in user_query_lower
            self.pending_stories = self._draft_stories_from_context(self.last_contexts) if wants_multiple else [self._story_from_context(self.last_contexts)]
            if explicit_jira_write:
                results = [await self.jira_agent.create_story(story, project_id=self._current_project_id) for story in self.pending_stories]
                created = [result.get("data", {}).get("story_key", "new story") for result in results if result.get("success")]
                if len(created) == len(results):
                    self.pending_stories = []
                    return f"{user_persona}, created {len(created)} stories in JIRA: {', '.join(created)}."
            return self._format_story_drafts(user_persona, self.pending_stories)
        # Generate enriched context with correlation insights
        context_text = json.dumps(contexts, default=str)
        insights_text = self.correlation_engine.format_insights_for_llm()

        # Handle implement_code intent — fetch story details and generate code
        if self.last_intent.get("intent") == "implement_code":
            story_key = self.last_intent.get("entities", {}).get("story_key")
            code_context = context_text
            story_title = ""
            if story_key:
                # Ensure we have story details in context
                story_result = await self.jira_agent.retrieve_context(f"story detail {story_key}", project_id=self._current_project_id)
                code_context = json.dumps([story_result] + contexts, default=str)
                # Try to extract story title from context
                story_data = story_result.get("data", {})
                if isinstance(story_data, dict):
                    story_title = story_data.get("title", "") or story_data.get("summary", "")
                    if not story_title and story_data.get("items"):
                        items = story_data["items"]
                        if items and isinstance(items[0], dict):
                            story_title = items[0].get("title", "") or items[0].get("summary", "")

            if settings.ONE_MIN_AI_API_KEY:
                try:
                    response = await one_min_ai_completion(
                        model=settings.LITELLM_MODEL,
                        messages=[
                            {
                                "role": "system",
                                "content": (
                                    "You are MAHALO's code generation assistant. The user wants you to write "
                                    "implementation code for a JIRA story/task.\n\n"
                                    f"{self._role_system_instructions(user_persona)}\n\n"
                                    "INSTRUCTIONS:\n"
                                    "1. Read the story/task details from the context below.\n"
                                    "2. Write clean, working code that implements the described feature or fix.\n"
                                    "3. Use the programming language specified by the user (default: Python).\n"
                                    "4. Include clear comments explaining your implementation approach.\n"
                                    "5. Structure the code properly (imports, classes/functions, main logic).\n"
                                    "6. If the story lacks enough detail, state your assumptions and proceed.\n"
                                    "7. Do NOT save or create files — just present the code for the user to review.\n"
                                    "8. If generating multiple files, use a header like '**`filename.py`**:' before each code block."
                                )
                            },
                            {
                                "role": "user",
                                "content": (
                                    f"Request: {user_query}\n"
                                    f"Target story: {story_key or 'Not specified'}\n\n"
                                    f"=== STORY/TASK CONTEXT ===\n{code_context}"
                                )
                            },
                        ],
                        temperature=0.3,
                        max_tokens=2000,
                    )
                    generated_code = response.choices[0].message.content
                    # Store for save_code follow-up
                    self.last_generated_code = generated_code
                    self.last_code_story_key = story_key
                    self.last_code_story_title = story_title
                    self.last_code_query = user_query
                    # Append a hint about saving
                    save_hint = f"\n\n---\n*Code ready for review. Say **\"save the code\"** when you'd like me to save it to your project.*"
                    return generated_code + save_hint
                except Exception:
                    pass
            return f"{user_persona}, I found the story details for {story_key} but couldn't generate code right now. Please try again."
        
        if settings.ONE_MIN_AI_API_KEY:
            try:
                response = await one_min_ai_completion(
                    model=settings.LITELLM_MODEL,
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "You are MAHALO's reasoning orchestrator. Interpret the user's underlying goal; "
                                "do not treat every phrase as a literal search term or repeat empty tool results.\n"
                                "Use the available evidence to answer the question directly, synthesize across tools, "
                                "and explain uncertainty when the evidence is insufficient. Distinguish requests for "
                                "status, diagnosis, prioritization, recommendation, story drafting, and execution. "
                                "Never claim an action was performed unless a write tool succeeded.\n\n"
                                f"{self._role_system_instructions(user_persona)}\n\n"
                                f"=== CLASSIFIED INTENT ===\n"
                                f"Intent: {self.last_intent.get('intent', 'general_sdlc')}\n"
                                f"Confidence: {self.last_intent.get('confidence', 0.5)}\n"
                                f"Target agents: {', '.join(self.last_intent.get('agents', []))}\n\n"
                                "CRITICAL INSTRUCTIONS:\n"
                                "1. When asked about 'priority' or 'how many stories', ANALYZE the error patterns and provide intelligent recommendations\n"
                                "2. Group similar errors into themes (e.g., timeout errors, connection pool errors, latency errors)\n"
                                "3. Estimate story counts based on error complexity and themes (typically 1-3 stories per major theme)\n"
                                "4. Provide priority rankings based on error frequency, severity, and business impact\n"
                                "5. Give specific, actionable recommendations with story titles and justifications\n\n"
                                "You have access to:\n"
                                "- Intelligent correlation insights (health scores, gaps, priorities)\n"
                                "- Raw error logs and JIRA stories\n\n"
                                "Be specific, be analytical, be helpful. Don't just list data - interpret it!"
                            )
                        },
                        {
                            "role": "user",
                            "content": (
                                f"Request: {user_query}\n\n"
                                f"=== INTELLIGENT INSIGHTS (USE THIS FIRST) ===\n{insights_text}\n\n"
                                f"=== RAW TOOL CONTEXT (FOR DETAILS) ===\n{context_text}"
                            )
                        },
                    ],
                    temperature=0.4,  # Slightly higher for more creative analysis
                    max_tokens=1200 if any(t in user_query.lower() for t in ("code", "sample code", "implement", "fix code", "how to fix", "snippet", "example code", "write code", "solution code", "patch")) else 600,
                )
                llm_text = response.choices[0].message.content
                is_code_req = any(t in user_query.lower() for t in ("code", "sample code", "implement", "fix code", "how to fix", "snippet", "example code", "write code", "solution code", "patch"))
                if is_code_req or self._llm_response_is_grounded(user_query, llm_text, contexts):
                    return llm_text
            except Exception:
                pass

        return self._fallback_response(user_persona, user_query, contexts)
