# Phase 2: Make Backend Services Project-Aware

**Status:** ✅ Complete

**Goal:** The mock APIs (JIRA :5001, ServiceNow :5002, Splunk :5003) accept a project_id with each request and route to the correct database. Existing functionality still works.

---

## Task 4: Add Project-ID Header Support to Mock APIs

**Status:** ⬜ Not Started

**Objective:** Modify JIRA, ServiceNow, and Splunk mock API routes to read `X-Project-ID` header and resolve the correct database.

**Implementation:**

- [ ] Create `backend/dependencies.py` — shared FastAPI dependency:
  ```python
  from fastapi import Request, Depends
  from backend.database import get_project_db, get_db

  def get_project_session(request: Request):
      project_id = request.headers.get("X-Project-ID")
      if project_id:
          yield from get_project_db(project_id)
      else:
          yield from get_db()
  ```

- [ ] Modify `backend/jira/routes.py`:
  - Change all `db: Session = Depends(get_db)` to `db: Session = Depends(get_project_session)`

- [ ] Modify `backend/servicenow/routes.py` — same change

- [ ] Modify `backend/splunk/routes.py` — same change

- [ ] No changes to service logic (JiraService, etc.) — they already take `db` as parameter

**Tests:** `tests/test_project_aware_apis.py`
- [ ] Test JIRA routes with `X-Project-ID: projectA` → data goes to projectA's DB
- [ ] Test JIRA routes with `X-Project-ID: projectB` → isolated from projectA
- [ ] Test routes without header → backward compat with legacy DB
- [ ] Test ServiceNow routes with project header
- [ ] Test Splunk routes with project header
- [ ] Test invalid project_id → appropriate error

---

## Task 5: Make MCP Tools Forward Project-ID

**Status:** ⬜ Not Started

**Objective:** MCP tool classes forward the project_id as a header with every HTTP request to mock APIs.

**Implementation:**

- [ ] Modify `mcp_servers/jira_mcp/tools.py` (`JiraMCPTools`):
  - Extract `project_id` from arguments dict before making HTTP call
  - Include as header: `headers={"X-Project-ID": project_id}` when present
  - No header when project_id is absent (backward compat)

- [ ] Same changes for `mcp_servers/servicenow_mcp/tools.py` (`ServiceNowMCPTools`)

- [ ] Same changes for `mcp_servers/splunk_mcp/tools.py` (`SplunkMCPTools`)

**Design Decision:** Pass project_id per-call via arguments dict rather than constructor. This avoids needing to recreate tool instances when projects switch.

**Tests:** `tests/test_mcp_tools_project.py`
- [ ] Test JiraMCPTools sends `X-Project-ID` header when project_id is in arguments
- [ ] Test ServiceNowMCPTools same
- [ ] Test SplunkMCPTools same
- [ ] Test omitting project_id sends no header (backward compat)

---

## Task 6: Make Agents and Orchestrator Project-Aware

**Status:** ⬜ Not Started

**Objective:** Pass project context through Orchestrator → Agents → MCP Tools.

**Implementation:**

- [ ] Modify `agents/jira_agent.py`:
  - `retrieve_context(query, project_id=None)` — includes project_id in arguments to tool handlers

- [ ] Modify `agents/servicenow_agent.py` — same pattern

- [ ] Modify `agents/splunk_agent.py` — same pattern

- [ ] Modify `agents/orchestrator.py`:
  - `process_query(user_persona, user_query, conversation_history, project_id=None)`
  - Pass project_id to all agent `retrieve_context()` calls

- [ ] Modify `api/routes/chat.py`:
  - Add `project_id: Optional[str] = None` to `ChatMessage` model
  - Pass to `orchestrator.process_query()`

**Tests:** `tests/test_orchestrator_project.py`
- [ ] Test process_query with project_id="healthsync" queries healthsync's data
- [ ] Test process_query with project_id="mahalopay" returns MahaloPay data
- [ ] Test no project_id falls back gracefully
- [ ] End-to-end: seed two projects, chat with each, verify correct responses

---

## Phase 2 Validation Checklist

- [ ] Mock APIs accept `X-Project-ID` header and route to correct DB
- [ ] Without the header, APIs still work (backward compat)
- [ ] MCP tools forward project_id as header
- [ ] Agents pass project_id through to tools
- [ ] Orchestrator receives project_id from chat API and passes it down
- [ ] Chat with project_id="A" returns data from project A's DB
- [ ] Chat with project_id="B" returns data from project B's DB
- [ ] No cross-project data leakage
- [ ] All existing tests still pass
