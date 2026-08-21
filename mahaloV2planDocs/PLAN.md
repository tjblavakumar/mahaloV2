# MAHALO V2 — Multi-Project Configuration Implementation Plan

## Problem Statement
MAHALO currently operates as a single-project system hardcoded around "MahaloPay" with one shared SQLite database. We need to make it multi-project capable, where an executive can create new projects from a configuration page, each project gets isolated services (its own database, filesystem folder), and users select their active project before interacting with the chat.

## Requirements
- Multi-project support with project selector in sidebar
- Each project gets: its own SQLite DB, its own filesystem folder
- A common/registry database tracks all projects
- Project creation form with structured description (goal, users, purpose, domain)
- Connection mode toggle: Local (simulated) vs Real (placeholder for credentials)
- LLM-powered mock data generation based on project description
- Projects start empty, with optional "Generate Mock Data" button
- MahaloPay auto-created on first boot as a deletable default
- Conversation history is project-scoped
- Project ID passed from frontend (localStorage) with each API request

## Architecture

```mermaid
graph TD
    FE[Frontend - Project Selector + Config Page] -->|project_id in payload| API[Main API :8000]
    API -->|project_id| ORCH[Orchestrator]
    ORCH --> AGENTS[Agents - project-aware]
    AGENTS --> MCP[MCP Tools - forwards project_id]
    MCP -->|HTTP + X-Project-ID header| MOCK_APIS[Mock APIs :5001-5003]
    MOCK_APIS -->|resolve DB per request| PROJECT_DB[projects/project_id/project.db]
    
    API --> PROJECTS_API[/api/projects routes]
    PROJECTS_API --> REGISTRY_DB[mahalo_registry.db]
    
    PROJECTS_API -->|Generate Mock Data| LLM[LLM - generates domain data]
    LLM --> PROJECT_DB
```

## Key Design Decision: Request-Scoped Project Routing

When a user switches projects in the frontend:
1. Frontend stores `project_id` in localStorage
2. Every API call includes `project_id` in the payload
3. Orchestrator passes `project_id` to agents
4. Agents pass `project_id` to MCP tools
5. MCP tools send `X-Project-ID` header to mock APIs
6. Mock APIs resolve the correct database file per request

Nothing restarts or reconnects. Same services serve all projects — routed per request.

## Phases Overview

| Phase | Focus | Status |
|-------|-------|--------|
| [Phase 1](./phase-1.md) | Project Registry Foundation | ✅ Complete |
| [Phase 2](./phase-2.md) | Backend Services Project-Aware | ✅ Complete |
| [Phase 3](./phase-3.md) | LLM Mock Data Generation | ✅ Complete |
| [Phase 4](./phase-4.md) | MahaloPay Migration | ✅ Complete |
| [Phase 5](./phase-5.md) | Frontend UI (Selector + Config) | ✅ Complete |
| [Phase 6](./phase-6.md) | Conversations + Integration | ✅ Complete |

## Progress Log
<!-- Update this section as phases are completed -->
- **Start Date:** _TBD_
- **Phase 1 Completed:** _TBD_
- **Phase 2 Completed:** _TBD_
- **Phase 3 Completed:** _TBD_
- **Phase 4 Completed:** _TBD_
- **Phase 5 Completed:** _TBD_
- **Phase 6 Completed:** _TBD_
