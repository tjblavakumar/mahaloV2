from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional


class MCPToolType(str, Enum):
    FUNCTION = "function"


@dataclass
class MCPTool:
    name: str
    description: str
    input_schema: Dict[str, Any]
    handler: Optional[Callable[[Dict[str, Any]], Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": MCPToolType.FUNCTION,
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.input_schema,
            },
        }


@dataclass
class MCPResource:
    uri: str
    name: str
    description: str
    mime_type: str = "application/json"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "uri": self.uri,
            "name": self.name,
            "description": self.description,
            "mimeType": self.mime_type,
        }


class MCPServer:
    def __init__(self, name: str, version: str = "1.0.0"):
        self.name = name
        self.version = version
        self.tools: Dict[str, MCPTool] = {}
        self.resources: Dict[str, MCPResource] = {}

    def register_tool(self, tool: MCPTool):
        self.tools[tool.name] = tool

    def register_resource(self, resource: MCPResource):
        self.resources[resource.uri] = resource

    def list_tools(self) -> List[Dict[str, Any]]:
        return [tool.to_dict() for tool in self.tools.values()]

    def list_resources(self) -> List[Dict[str, Any]]:
        return [resource.to_dict() for resource in self.resources.values()]

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        if tool_name not in self.tools:
            raise ValueError(f"Tool '{tool_name}' not found")
        tool = self.tools[tool_name]
        if tool.handler is None:
            raise ValueError(f"Tool '{tool_name}' has no handler")
        result = tool.handler(arguments)
        if hasattr(result, "__await__"):
            return await result
        return result

    async def read_resource(self, uri: str) -> Dict[str, Any]:
        if uri not in self.resources:
            raise ValueError(f"Resource '{uri}' not found")
        resource = self.resources[uri]
        return {"uri": resource.uri, "name": resource.name, "description": resource.description}

    def get_server_info(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "tools_count": len(self.tools),
            "resources_count": len(self.resources),
        }


__all__ = ["MCPServer", "MCPTool", "MCPResource", "MCPToolType"]
