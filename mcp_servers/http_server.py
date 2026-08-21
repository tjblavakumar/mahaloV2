from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from mcp_servers.mcp_base import MCPServer


class ToolCall(BaseModel):
    arguments: dict[str, Any] = {}


def create_mcp_app(server: MCPServer) -> FastAPI:
    app = FastAPI(title=f"{server.name} MCP Server", version=server.version)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "healthy", "service": server.name}

    @app.get("/tools")
    def list_tools() -> dict[str, list[dict[str, Any]]]:
        return {"tools": server.list_tools()}

    @app.post("/tools/{tool_name}")
    async def call_tool(tool_name: str, request: ToolCall) -> dict[str, Any]:
        try:
            return await server.call_tool(tool_name, request.arguments)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    return app
