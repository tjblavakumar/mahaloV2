import uvicorn

from backend.config import settings
from mcp_servers.mcp_base import MCPServer, MCPTool
from mcp_servers.http_server import create_mcp_app
from mcp_servers.splunk_mcp.tools import SplunkMCPTools


tools = SplunkMCPTools()
server = MCPServer("splunk-mcp")
server.register_tool(MCPTool("search_logs", "Search Splunk logs", {"type": "object", "properties": {"query": {"type": "string"}}}, tools.search_logs_handler))
server.register_tool(MCPTool("list_logs", "List Splunk logs", {"type": "object"}, tools.list_logs_handler))
app = create_mcp_app(server)


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=settings.SPLUNK_MCP_PORT)
