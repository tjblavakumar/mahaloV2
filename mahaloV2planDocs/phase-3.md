# Phase 3: LLM-Powered Mock Data Generation

**Status:** ✅ Complete

**Goal:** When a user creates a project and clicks "Generate Mock Data," the system uses the LLM to produce domain-appropriate data and inserts it into the project's database.

---

## Task 7: Build the Data Generation Service

**Status:** ⬜ Not Started

**Objective:** Create a service that generates realistic mock data via LLM based on project description.

**Implementation:**

- [ ] Create `backend/utils/generate_project_data.py`:
  - Function `generate_mock_data(project_id: str, project_info: dict) -> dict`
  - `project_info` contains: name, key, description_goal, description_users, description_purpose, domain

- [ ] Construct LLM prompt for structured JSON output:
  ```
  Generate mock data for a software project:
  - Name: {name}
  - Domain: {domain}
  - Goal: {goal}
  - Users: {users}
  - Purpose: {purpose}
  
  Generate exactly:
  - 5 team members (realistic names, roles: developer, product_manager, qa, executive)
  - 10 user stories (title, description, story_points 1-13, priority, status mix)
  - 5 bugs (related to stories, varying severity)
  - 2 sprints (one active, one completed)
  - 5 ServiceNow incidents (domain-relevant)
  - 10 deployments (feature releases)
  - 100 Splunk logs (mix of INFO/WARN/ERROR, domain-realistic messages)
  
  Return as JSON: { users, stories, bugs, sprints, incidents, deployments, logs }
  ```

- [ ] Parse LLM JSON response

- [ ] Insert data into project's DB using existing service classes via `get_project_db(project_id)`:
  - Use project's `key` as prefix for story_keys (e.g., "HSYNC-1"), bug_keys, incident_ids, deployment_ids

- [ ] Error handling: if LLM fails or returns invalid JSON, return clear error

- [ ] Mark `project.data_generated = True` in registry after success

**Tests:** `tests/test_data_generation.py`
- [ ] Mock LLM response with valid JSON fixture → all records inserted correctly
- [ ] Verify counts: 5 users, 10 stories, 5 bugs, 2 sprints, 5 incidents, 10 deployments, 100 logs
- [ ] Story_keys use project key prefix
- [ ] Malformed LLM response → graceful error
- [ ] `data_generated` flag set in registry

---

## Task 8: Wire Data Generation to API

**Status:** ⬜ Not Started

**Objective:** Connect the generate endpoint to the data generation service.

**Implementation:**

- [ ] Implement `POST /api/projects/{project_id}/generate-data` in `api/routes/projects.py`:
  - Validate project exists
  - Validate connection_mode is "local"
  - Call `generate_mock_data(project_id, project_info)`
  - Return success with summary (record counts)
  - If data already generated, allow re-generation (wipe first)

- [ ] Add `POST /api/projects/{project_id}/reset-data`:
  - Wipe all tables in project's DB
  - Reset `data_generated = False` in registry

**Tests:** `tests/test_generate_api.py`
- [ ] Test generate-data on valid project → data in project DB
- [ ] Test generate-data on non-existent project → 404
- [ ] Test generate-data on "real" mode project → 400
- [ ] Test re-generation (wipe + regenerate)

---

## Phase 3 Validation Checklist

- [ ] `POST /api/projects/{id}/generate-data` works
- [ ] LLM called with project description context
- [ ] Generated data in project's SQLite DB
- [ ] Correct counts: 5 users, 10 stories, 5 bugs, 2 sprints, 5 incidents, 10 deployments, 100 logs
- [ ] Story keys use project key prefix (e.g., HSYNC-1)
- [ ] Data is domain-appropriate
- [ ] Error handling works when LLM unavailable
- [ ] Can chat with project after data generation and get relevant responses
- [ ] Registry shows `data_generated: true`
