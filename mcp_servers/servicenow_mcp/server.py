import uvicorn

from backend.config import settings
from mcp_servers.http_server import create_mcp_app
from mcp_servers.mcp_base import MCPServer, MCPTool
from mcp_servers.servicenow_mcp.tools import ServiceNowMCPTools


tools = ServiceNowMCPTools()
server = MCPServer("servicenow-mcp")
server.register_tool(MCPTool("list_incidents", "List ServiceNow incidents", {"type": "object"}, tools.list_incidents_handler))
server.register_tool(MCPTool("get_incident", "Get a ServiceNow incident by ID", {"type": "object", "properties": {"incident_id": {"type": "string"}}}, tools.get_incident_handler))
server.register_tool(MCPTool("list_deployments", "List deployments by environment", {"type": "object", "properties": {"environment": {"type": "string"}}}, tools.list_deployments_handler))
app = create_mcp_app(server)


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=settings.SERVICENOW_MCP_PORT)
