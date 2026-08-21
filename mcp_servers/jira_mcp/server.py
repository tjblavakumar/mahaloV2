import uvicorn

from backend.config import settings
from mcp_servers.http_server import create_mcp_app
from mcp_servers.jira_mcp.tools import JiraMCPTools
from mcp_servers.mcp_base import MCPServer, MCPTool


tools = JiraMCPTools()
server = MCPServer("jira-mcp")
server.register_tool(MCPTool("create_story", "Create a JIRA story", {"type": "object"}, tools.create_story_handler))
server.register_tool(MCPTool("search_stories", "List JIRA stories", {"type": "object"}, tools.search_stories_handler))
server.register_tool(MCPTool("get_story", "Get a JIRA story by key", {"type": "object", "properties": {"story_key": {"type": "string"}}}, tools.get_story_handler))
server.register_tool(MCPTool("list_bugs", "List JIRA bugs with assignment details", {"type": "object"}, tools.list_bugs_handler))
app = create_mcp_app(server)


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=settings.JIRA_MCP_PORT)
