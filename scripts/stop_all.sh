#!/usr/bin/env bash
# Stop all MAHALO services

echo "============================================================"
echo " MAHALO - Stopping All Services"
echo "============================================================"

echo "Stopping MAHALO backend and frontend processes..."

pkill -f "uvicorn backend.jira.app:app" 2>/dev/null || true
pkill -f "uvicorn backend.servicenow.app:app" 2>/dev/null || true
pkill -f "uvicorn backend.splunk.app:app" 2>/dev/null || true
pkill -f "mcp_servers.jira_mcp.server" 2>/dev/null || true
pkill -f "mcp_servers.servicenow_mcp.server" 2>/dev/null || true
pkill -f "mcp_servers.splunk_mcp.server" 2>/dev/null || true
pkill -f "uvicorn api.main:app" 2>/dev/null || true
pkill -f "node.*vite" 2>/dev/null || true
pkill -f "npm start" 2>/dev/null || true

for port in 5001 5002 5003 6001 6002 6003 8000 3000; do
  if command -v lsof >/dev/null 2>&1; then
    lsof -ti tcp:$port 2>/dev/null | xargs -r kill -9 2>/dev/null || true
  fi
done

echo "All MAHALO services stopped."
