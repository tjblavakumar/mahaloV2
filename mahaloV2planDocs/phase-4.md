# Phase 4: Migrate MahaloPay to Multi-Project Structure

**Status:** ✅ Complete

**Goal:** The existing MahaloPay demo data becomes a regular project. On first boot, MahaloPay is auto-created. Root `mahalo.db` is no longer the primary data source.

---

## Task 9: Auto-Create MahaloPay on First Boot

**Status:** ⬜ Not Started

**Objective:** When the system starts with no projects, auto-create MahaloPay as the default.

**Implementation:**

- [ ] Create `backend/utils/bootstrap.py`:
  - Function `ensure_default_project()`:
    - Check if registry DB has any projects
    - If empty, create "MahaloPay" project:
      - name: "MahaloPay"
      - key: "MPAY"
      - description_goal: "Build a modern payment processing platform with secure transactions, fraud detection, and automated reconciliation"
      - description_users: "Merchants, consumers, financial institutions, internal platform teams"
      - description_purpose: "Process payments securely and reliably at scale, detect fraud, and maintain accurate financial records"
      - domain: "fintech"
      - connection_mode: "local"
    - Seed with existing `reset_demo_data()` content (adapted for project DB)
    - Mark data_generated = True

- [ ] Call `ensure_default_project()` during Main API startup (lifespan event)

- [ ] Adapt `backend/utils/reset_data.py`:
  - Accept `project_id` parameter: `reset_demo_data(project_id="mahalopay")`
  - Write to project's DB instead of root DB
  - Keep backward compat during transition

**Tests:** `tests/test_bootstrap.py`
- [ ] Fresh boot (no registry) → MahaloPay project created
- [ ] Boot with existing projects → no duplicate MahaloPay
- [ ] MahaloPay data in `projects/mahalopay/project.db`
- [ ] MahaloPay queryable through project-aware APIs

---

## Task 10: Update Admin Routes for Multi-Project

**Status:** ⬜ Not Started

**Objective:** Admin endpoints work in multi-project context.

**Implementation:**

- [ ] Modify `api/routes/admin.py`:
  - `POST /api/admin/reset-data` → accept optional `project_id` param
  - `GET /api/admin/status` → report project count
  - `GET /api/admin/stats` → include project-level stats

- [ ] Remove dependency on root `mahalo.db` from operational code paths

**Tests:**
- [ ] Test admin/reset-data with project_id resets correct project
- [ ] Test admin/status shows project count
- [ ] Test system operates without root mahalo.db

---

## Phase 4 Validation Checklist

- [ ] First boot with empty system → MahaloPay auto-created
- [ ] MahaloPay data lives in `projects/mahalopay/project.db`
- [ ] Chatting with project_id="mahalopay" returns familiar MahaloPay responses
- [ ] Admin reset works per-project
- [ ] System no longer depends on root `mahalo.db`
- [ ] Existing functionality (chat, personas, all agents) works as before
- [ ] MahaloPay can be deleted like any other project
