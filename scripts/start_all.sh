#!/usr/bin/env bash
# Start all MAHALO services in background

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
mkdir -p "$ROOT_DIR/logs"
mkdir -p "$ROOT_DIR/projects"

echo "============================================================"
echo " MAHALO - Starting All Services"
echo "============================================================"

if [ ! -f "$ROOT_DIR/venv/bin/activate" ]; then
  echo "[ERROR] Virtual environment not found."
  echo "Create it with: python3 -m venv venv"
  echo "Then run: source venv/bin/activate && pip install -r requirements.txt"
  exit 1
fi

source "$ROOT_DIR/venv/bin/activate" || true
echo "Python: $(python --version 2>&1)"
echo ""

ECHO_PREFIX="[INFO]"

nohup python -m uvicorn backend.jira.app:app --host 0.0.0.0 --port 5001 > "$ROOT_DIR/logs/jira_api.log" 2>&1 &
echo "$ECHO_PREFIX Started JIRA Mock API on port 5001"

nohup python -m uvicorn backend.servicenow.app:app --host 0.0.0.0 --port 5002 > "$ROOT_DIR/logs/servicenow_api.log" 2>&1 &
echo "$ECHO_PREFIX Started ServiceNow Mock API on port 5002"

nohup python -m uvicorn backend.splunk.app:app --host 0.0.0.0 --port 5003 > "$ROOT_DIR/logs/splunk_api.log" 2>&1 &
echo "$ECHO_PREFIX Started Splunk Mock API on port 5003"

nohup python -m mcp_servers.jira_mcp.server > "$ROOT_DIR/logs/jira_mcp.log" 2>&1 &
echo "$ECHO_PREFIX Started JIRA MCP Server on port 6001"

nohup python -m mcp_servers.servicenow_mcp.server > "$ROOT_DIR/logs/servicenow_mcp.log" 2>&1 &
echo "$ECHO_PREFIX Started ServiceNow MCP Server on port 6002"

nohup python -m mcp_servers.splunk_mcp.server > "$ROOT_DIR/logs/splunk_mcp.log" 2>&1 &
echo "$ECHO_PREFIX Started Splunk MCP Server on port 6003"

nohup python -m uvicorn api.main:app --host 0.0.0.0 --port 8000 > "$ROOT_DIR/logs/main_api.log" 2>&1 &
echo "$ECHO_PREFIX Started Main API Gateway on port 8000"

if [ -d "$ROOT_DIR/frontend" ]; then
  (cd "$ROOT_DIR/frontend" && nohup npm start > "$ROOT_DIR/logs/frontend.log" 2>&1 &)
  echo "$ECHO_PREFIX Started Frontend on port 3000"
fi

echo ""
echo "============================================================"
echo " All services started in background!"
echo "============================================================"
echo ""
echo "Services:"
echo "  - JIRA API:       http://localhost:5001/docs"
echo "  - ServiceNow API: http://localhost:5002/docs"
echo "  - Splunk API:     http://localhost:5003/docs"
echo "  - Main API:       http://localhost:8000/docs"
echo "  - Frontend:       http://localhost:3000"
echo ""
echo "Logs: $ROOT_DIR/logs/"
