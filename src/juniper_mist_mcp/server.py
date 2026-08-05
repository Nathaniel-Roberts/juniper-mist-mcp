"""MCP server instance shared by all tool modules."""

from mcp.server import MCPServer
from mcp.types import ToolAnnotations

from .api import _lifespan

# Initialize MCP server
mcp = MCPServer("Juniper Mist", lifespan=_lifespan)

# All tools in this server are read-only (Phase 1)
READ_ONLY = ToolAnnotations(readOnlyHint=True)
