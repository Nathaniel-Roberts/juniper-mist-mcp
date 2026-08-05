"""End-to-end test: run the server as a real stdio subprocess."""

import os
import sys

import pytest

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

pytestmark = pytest.mark.anyio


async def test_stdio_initialize_and_list_tools():
    params = StdioServerParameters(
        command=sys.executable,
        args=["-c", "import juniper_mist_mcp; juniper_mist_mcp.main()"],
        env={**os.environ, "MIST_API_TOKEN": "test-token"},
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            info = await session.initialize()
            assert info.server_info.name == "Juniper Mist"
            tools = await session.list_tools()
            assert len(tools.tools) >= 47
            assert all(
                t.annotations and t.annotations.read_only_hint for t in tools.tools
            )
