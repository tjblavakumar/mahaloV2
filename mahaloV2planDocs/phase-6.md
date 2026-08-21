# Phase 6: Project-Scoped Conversations and Final Integration

**Status:** ✅ Complete

**Goal:** Conversations are isolated per project. Full end-to-end flow works seamlessly.

---

## Task 14: Project-Scoped Conversation History

**Status:** ⬜ Not Started

**Objective:** Conversation history is namespaced by project.

**Implementation:**

- [ ] Modify `agents/context_manager.py`:
  - Change internal storage to be keyed by `project_id`
  - `add_message(role, content, metadata)` — metadata must include `project_id`
  - `get_conversation_history(project_id, last_n=10)` — returns only messages for that project
  - `clear(project_id=None)` — clears specific project or all

- [ ] Update `api/routes/chat.py`:
  - Pass project_id into context_manager calls
  - `/api/chat/history/{conversation_id}` — filter by project_id (query param)

**Tests:** `tests/test_context_manager_project.py`
- [ ] Messages in project A don't appear in project B's history
- [ ] Clear project A doesn't affect project B
- [ ] History retrieval with project filter works

---

## Task 15: End-to-End Integration Test and Polish

**Status:** ⬜ Not Started

**Objective:** Validate complete flow and clean up.

**Implementation:**

- [ ] Write `tests/test_e2e_multiproject.py`:
  1. Boot system → MahaloPay exists
  2. Create "HealthSync" project via API
  3. Generate mock data for HealthSync
  4. Chat as Executive to HealthSync → healthcare-themed response
  5. Chat as Developer to MahaloPay → payment-themed response
  6. Verify no cross-contamination
  7. Delete HealthSync → gone from list, folder removed

- [ ] Update `scripts/start_all.sh`:
  - Ensure `projects/` directory exists on startup
  - Call bootstrap on first boot

- [ ] Update documentation (`START_HERE.md`):
  - How to create a project
  - How project isolation works
  - How to generate mock data
  - Connection mode explanation

- [ ] Clean up deprecated root `mahalo.db` references

**Tests:**
- [ ] Full E2E test passes
- [ ] Fresh boot works cleanly
- [ ] All phase validations still pass

---

## Phase 6 Validation Checklist

- [ ] Conversations isolated per project
- [ ] Switching projects shows fresh conversation
- [ ] Complete flow: create → generate → chat → correct responses
- [ ] MahaloPay still works as default
- [ ] Deleting project cleans everything
- [ ] System starts fresh from scratch
- [ ] Documentation updated
- [ ] All tests pass across all phases

---

## Project Complete Checklist

When all phases are done, verify:
- [ ] Fresh system start → MahaloPay auto-created
- [ ] Create new project "HealthSync" (healthcare domain)
- [ ] Generate mock data → healthcare-themed data
- [ ] Chat in HealthSync → relevant healthcare responses
- [ ] Switch to MahaloPay → payment-themed responses
- [ ] No data leakage between projects
- [ ] Delete HealthSync → completely removed
- [ ] All automated tests pass
- [ ] Documentation is current
