# Phase 1: Project Registry Foundation

**Status:** ✅ Complete

**Goal:** Establish the project registry database, API endpoints, and filesystem structure. At the end of this phase, you can create, list, and delete projects via API — each with its own folder and isolated SQLite database.

---

## Task 1: Create the Project Registry Database and Model

**Status:** ⬜ Not Started

**Objective:** Build the central registry that stores project metadata.

**Implementation:**

- [ ] Create `backend/models/project_models.py` with Project model:
  ```
  Fields:
  - id: String (slug from name, primary key)
  - name: String(120), required
  - key: String(20), unique (e.g., "HSYNC")
  - description_goal: Text, required
  - description_users: Text, required
  - description_purpose: Text, required
  - domain: String(50) (e.g., "healthcare", "fintech")
  - connection_mode: String(10), default="local" (values: "local" or "real")
  - jira_url: String(200), nullable
  - jira_token: String(200), nullable
  - servicenow_url: String(200), nullable
  - servicenow_credentials: String(200), nullable
  - splunk_url: String(200), nullable
  - splunk_token: String(200), nullable
  - folder_path: String(300), required
  - data_generated: Boolean, default=False
  - created_at: DateTime
  - updated_at: DateTime
  ```

- [ ] Create `backend/project_registry.py`:
  - Separate SQLAlchemy engine pointing to `mahalo_registry.db` in project root
  - `init_registry_db()` — creates the projects table
  - `get_registry_db()` — session dependency
  - CRUD functions: `create_project()`, `list_projects()`, `get_project()`, `delete_project()`

- [ ] On `create_project()`:
  - Auto-generate `id` as slug from project name (e.g., "HealthSync" → "healthsync")
  - Auto-generate `key` from name (first letters of words, uppercase, max 6 chars)
  - Create directory: `projects/<id>/`
  - Create empty project database: `projects/<id>/project.db` with all tables

- [ ] On `delete_project()`:
  - Remove registry entry
  - Delete `projects/<id>/` folder and contents

**Tests:** `tests/test_project_registry.py`
- [ ] Test creating a project → registry entry exists, folder exists, project.db has correct tables
- [ ] Test listing projects returns all created projects
- [ ] Test getting a project by ID
- [ ] Test deleting a project removes folder and DB entry
- [ ] Test duplicate name/key handling
- [ ] Test slug generation edge cases

---

## Task 2: Project API Routes

**Status:** ⬜ Not Started

**Objective:** Expose REST endpoints for project management.

**Implementation:**

- [ ] Create `api/routes/projects.py`:
  ```
  POST /api/projects — Create project
    Body: { name, description_goal, description_users, description_purpose, domain, connection_mode, jira_url?, ... }
    Response: { id, name, key, folder_path, created_at }
    
  GET /api/projects — List all projects
    Response: { projects: [...], count: N }
    
  GET /api/projects/{project_id} — Get project details
    Response: full project object
    
  DELETE /api/projects/{project_id} — Delete project
    Response: { message: "Deleted", id }
  ```

- [ ] Register router in `api/main.py`

- [ ] Validation:
  - name, description_goal, description_users, description_purpose are required
  - Return 422 for missing fields
  - Return 409 if project with same name/key already exists

**Tests:** `tests/test_project_api.py`
- [ ] Test POST creates project and returns correct response
- [ ] Test GET /projects lists all
- [ ] Test GET /projects/{id} returns detail
- [ ] Test DELETE removes project
- [ ] Test validation errors (missing fields → 422)
- [ ] Test duplicate name → 409

---

## Task 3: Per-Project Database Resolution

**Status:** ⬜ Not Started

**Objective:** Modify the database layer to support routing to project-specific databases.

**Implementation:**

- [ ] Modify `backend/database.py`:
  - Add `_project_engines: dict[str, Engine]` cache
  - Add `get_project_engine(project_id: str) -> Engine` — resolves to `projects/<project_id>/project.db`
  - Add `get_project_db(project_id: str)` — yields a session for the project's DB
  - Add `init_project_db(project_id: str)` — creates all tables in the project's DB
  - Keep existing `get_db()` for backward compat

- [ ] Engine cache prevents creating new engine per request

**Tests:** `tests/test_project_database.py`
- [ ] Test `get_project_engine` returns different engines for different project_ids
- [ ] Test `get_project_engine` returns same cached engine for same project_id
- [ ] Test `init_project_db` creates all expected tables
- [ ] Test data isolation: write to project A, read from project B → empty
- [ ] Test invalid project_id handling

---

## Phase 1 Validation Checklist

- [ ] Can create a project via `POST /api/projects` with required fields
- [ ] Project folder `projects/<id>/` is created on disk
- [ ] Project database `projects/<id>/project.db` exists with all tables (empty)
- [ ] Can list all projects via `GET /api/projects`
- [ ] Can get single project details via `GET /api/projects/{id}`
- [ ] Can delete a project — folder and DB file removed
- [ ] Registry DB (`mahalo_registry.db`) persists across restarts
- [ ] Two projects have completely isolated databases
- [ ] All tests pass
