"""LangChain MCP client for the Earth Observation MCP server."""

from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient

from eve_agent.settings import MCP_SERVER_URL


async def load_mcp_tools() -> list[BaseTool]:
    """Load tools from the running Earth Observation MCP server."""
    client = MultiServerMCPClient(
        {
            "earth_observation": {
                "transport": "streamable_http",
                "url": MCP_SERVER_URL,
            }
        }
    )
    return await client.get_tools()
