# Phase 5: Frontend — Project Selector and Configuration Page

**Status:** ✅ Complete

**Goal:** Users can see, select, and create projects from the UI. Chat is project-scoped.

---

## Task 11: Frontend API Service Updates

**Status:** ⬜ Not Started

**Objective:** Add project-related API calls to the frontend service layer.

**Implementation:**

- [ ] Add to `frontend/src/services/api.js`:
  ```javascript
  export function getProjects() { return request('/api/projects'); }
  export function getProject(id) { return request(`/api/projects/${id}`); }
  export function createProject(payload) { 
    return request('/api/projects', { method: 'POST', body: JSON.stringify(payload) }); 
  }
  export function deleteProject(id) { 
    return request(`/api/projects/${id}`, { method: 'DELETE' }); 
  }
  export function generateProjectData(id) { 
    return request(`/api/projects/${id}/generate-data`, { method: 'POST' }); 
  }
  ```

- [ ] Modify `sendMessage()` to include `project_id` in payload

**Tests:**
- [ ] Verify each function makes correct HTTP call (network tab or fetch mock)

---

## Task 12: Project Selector in Sidebar

**Status:** ⬜ Not Started

**Objective:** Add a dropdown in the sidebar for selecting the active project.

**Implementation:**

- [ ] In `App.jsx` or new `components/ProjectSelector.jsx`:
  - Fetch projects on mount via `getProjects()`
  - Render dropdown above persona section in sidebar
  - Store selected `project_id` in localStorage and React state
  - On project switch: clear messages, reset conversation_id
  - Show "+ New Project" button below dropdown
  - On mount: restore from localStorage, default to first available

- [ ] Pass `project_id` into every `sendMessage()` call

- [ ] Show project name in workspace header

**Tests:**
- [ ] Project list renders correctly
- [ ] Selecting project updates localStorage
- [ ] Switching projects clears conversation
- [ ] project_id included in chat API calls
- [ ] Page refresh restores selected project

---

## Task 13: Project Configuration Page / Modal

**Status:** ⬜ Not Started

**Objective:** Build the form for creating a new project.

**Implementation:**

- [ ] Create `frontend/src/components/ProjectConfig.jsx`:
  - Form fields:
    - Project Name (text, required)
    - Project Key (auto-generated from name, editable, max 6 chars uppercase)
    - Goal (textarea, required, placeholder: "What is this project trying to achieve?")
    - Target Users (textarea, required, placeholder: "Who are the end users?")
    - Purpose / Business Context (textarea, required, placeholder: "Why does this project exist?")
    - Domain (select: Healthcare, Fintech, E-commerce, SaaS, DevOps, Other)
    - Connection Mode (toggle: Local Simulation | Real Services)
    - Real mode fields (disabled when Local):
      - JIRA URL, JIRA API Token
      - ServiceNow URL, ServiceNow Credentials
      - Splunk URL, Splunk Token
  
  - Auto-generate key as user types name
  - Submit button: "Create Project"
  - On success: show confirmation with "Generate Mock Data" button
  - Generate Mock Data: call API, show spinner, on complete → navigate to chat
  - Cancel button returns to chat

- [ ] Navigation: "+ New Project" in sidebar opens this component

- [ ] State: use `view` state in App.jsx ("chat" | "config")

**Tests:**
- [ ] Form renders all fields
- [ ] Required field validation
- [ ] Key auto-generation
- [ ] Connection mode toggle shows/hides credential fields
- [ ] Successful submission creates project
- [ ] Generate mock data shows progress
- [ ] After creation, returns to chat with new project active

---

## Phase 5 Validation Checklist

- [ ] Sidebar shows project dropdown with all projects
- [ ] Switching projects clears chat and updates context
- [ ] "+ New Project" opens configuration form
- [ ] Form validates required fields
- [ ] Creating project via form calls API successfully
- [ ] "Generate Mock Data" button works with loading state
- [ ] After creation, new project auto-selected in dropdown
- [ ] Chat messages include project_id
- [ ] Page refresh preserves selected project
- [ ] MahaloPay appears in dropdown on first boot
