# MAHALO V2 — Multi-Project AI SDLC Assistant

## What is MAHALO?

MAHALO (Model-based AI Harness for Agile Lifecycle Operations) is an AI-powered assistant that queries and correlates data across JIRA, ServiceNow, and Splunk using natural language. It supports multiple projects with isolated databases, each configurable via a web UI.

## Quick Start (5 Minutes)

### 1. Set up the environment

```bash
cd /path/to/mahaloV2
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure your LLM key

Edit `.env` and set your API key:

```bash
ONE_MIN_AI_API_KEY=your_api_key_here
# Or use OpenAI-compatible:
# OPENAI_API_KEY=your_key
# OPENAI_BASE_URL=https://api.openai.com/v1
LITELLM_MODEL=gpt-4o-mini
```

### 3. Start all services

```bash
source venv/bin/activate
scripts/start_all.sh
```

This starts:
- JIRA Mock API on port 5001
- ServiceNow Mock API on port 5002
- Splunk Mock API on port 5003
- Main API Gateway on port 8000
- Frontend on port 3000

### 4. Open the UI

Visit: http://localhost:3000

On first boot, MAHALO auto-creates a **MahaloPay** demo project with sample data. You'll see it in the project dropdown.

---

## Multi-Project System

### How it works

Each project gets:
- Its own SQLite database (`projects/<id>/project.db`)
- Its own filesystem folder
- Isolated conversation history
- Independent JIRA stories, bugs, incidents, deployments, and logs

A central registry database (`mahalo_registry.db`) tracks all projects.

### Creating a new project

1. Click **"+ New Project"** in the sidebar dropdown
2. Fill in the form:
   - **Project Name** (required)
   - **Goal** — What the project aims to achieve
   - **Target Users** — Who uses this system
   - **Purpose** — Business context
   - **Domain** — Healthcare, Fintech, E-commerce, etc.
   - **Connection Mode** — Local (simulated) or Real (credentials)
3. Click **Create Project**
4. Optionally click **Generate Mock Data** to populate with LLM-generated domain-appropriate data

### Switching projects

Use the dropdown in the sidebar. Switching clears the conversation and loads data from the selected project's database.

### Connection modes

- **Local** — Data lives in a local SQLite database. Use "Generate Mock Data" to populate.
- **Real** — Placeholder for real JIRA/ServiceNow/Splunk credentials (future feature).

---

## Architecture

```
Frontend (React :3000)
  → Main API (FastAPI :8000)
    → Orchestrator Agent
      → JIRA Agent → MCP Tools → JIRA Mock API (:5001) → project.db
      → ServiceNow Agent → MCP Tools → ServiceNow Mock API (:5002) → project.db
      → Splunk Agent → MCP Tools → Splunk Mock API (:5003) → project.db
    → Correlation Engine
    → LLM (synthesis)
  → Project API (/api/projects)
    → Registry DB (mahalo_registry.db)
```

Request routing: Every request includes a `project_id` (via `X-Project-ID` header to mock APIs). The backend resolves the correct database file per request.

---

## Project Structure

```
mahaloV2/
├── api/                        # Main API gateway (FastAPI :8000)
│   ├── main.py
│   └── routes/
│       ├── admin.py            # System status, reset
│       ├── chat.py             # Chat/query endpoint
│       └── projects.py         # Project CRUD + data generation
│
├── agents/                     # AI agents
│   ├── orchestrator.py         # Central brain
│   ├── jira_agent.py
│   ├── servicenow_agent.py
│   ├── splunk_agent.py
│   ├── context_manager.py      # Project-scoped conversation history
│   ├── intent_classifier.py
│   └── correlation_engine.py
│
├── backend/                    # Backend services and data layer
│   ├── config.py               # Settings (ports, LLM, etc.)
│   ├── database.py             # Per-project DB resolution
│   ├── project_registry.py     # Central registry CRUD
│   ├── dependencies.py         # FastAPI shared dependencies
│   ├── models/                 # SQLAlchemy models
│   ├── jira/                   # JIRA mock API (:5001)
│   ├── servicenow/             # ServiceNow mock API (:5002)
│   ├── splunk/                 # Splunk mock API (:5003)
│   └── utils/
│       ├── bootstrap.py        # Auto-creates MahaloPay on first boot
│       ├── generate_project_data.py  # LLM mock data generator
│       └── reset_data.py       # MahaloPay demo data seeder
│
├── mcp_servers/                # MCP tool layer (HTTP bridge)
│   ├── jira_mcp/
│   ├── servicenow_mcp/
│   └── splunk_mcp/
│
├── frontend/                   # React + Vite UI
│   └── src/
│       ├── App.jsx
│       ├── components/
│       │   ├── ProjectSelector.jsx
│       │   └── ProjectConfig.jsx
│       └── services/api.js
│
├── projects/                   # Per-project data (auto-created)
│   └── mahalopay/
│       └── project.db
│
├── mahaloV2planDocs/            # Implementation plan (reference)
├── tests/                      # Pytest test suite (107 tests)
├── scripts/                    # Start/stop scripts
├── .env                        # Environment configuration
├── requirements.txt
└── mahalo_registry.db          # Central project registry
```

---

## API Endpoints

### Projects
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/projects` | List all projects |
| POST | `/api/projects` | Create a new project |
| GET | `/api/projects/{id}` | Get project details |
| DELETE | `/api/projects/{id}` | Delete project (folder + DB) |
| POST | `/api/projects/{id}/generate-data` | Generate LLM mock data |
| POST | `/api/projects/{id}/reset-data` | Wipe project data |

### Chat
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/chat/personas` | List available personas |
| POST | `/api/chat/message` | Send a message (includes project_id) |
| GET | `/api/chat/history/{id}` | Get conversation history |

### Admin
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/admin/status` | System health + project count |
| GET | `/api/admin/stats` | Conversation + project stats |
| POST | `/api/admin/reset-data` | Reset project data |

---

## Running Tests

```bash
source venv/bin/activate
python -m pytest tests/ -v
```

All 107 tests should pass.

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MAIN_API_PORT` | 8000 | Main API gateway port |
| `JIRA_API_PORT` | 5001 | JIRA mock API port |
| `SERVICENOW_API_PORT` | 5002 | ServiceNow mock API port |
| `SPLUNK_API_PORT` | 5003 | Splunk mock API port |
| `FRONTEND_PORT` | 3000 | Frontend dev server port |
| `DATABASE_URL` | sqlite:///./mahalo.db | Legacy DB (backward compat) |
| `ONE_MIN_AI_API_KEY` | — | LLM API key (required for chat + data gen) |
| `ONE_MIN_AI_BASE_URL` | https://api.1min.ai/v1 | LLM API base URL |
| `LITELLM_MODEL` | gpt-4o-mini | LLM model name |

---

## Troubleshooting

**Services won't start:**
```bash
# Check if ports are in use
lsof -i :5001 -i :5002 -i :5003 -i :8000
```

**No data in project:**
- Check if you've generated mock data (click "Generate Mock Data" in the config page)
- Or call: `POST /api/projects/{id}/generate-data`

**LLM not responding:**
- Verify `ONE_MIN_AI_API_KEY` is set in `.env`
- Check the model name matches your provider

**Frontend can't reach API:**
- Ensure Main API is running on port 8000
- Check CORS settings in `api/main.py`
