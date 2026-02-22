"""MCP smoke tests — verify the Buckaroo MCP server starts and exposes expected tools."""

import os
import sys
import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# Path to the entry point script, relative to repo root
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_ENTRY_POINT = os.path.join(_REPO_ROOT, "src", "buckaroo_mcp_tool.py")


def _server_params():
    return StdioServerParameters(
        command=sys.executable,
        args=[_ENTRY_POINT],
    )


@pytest.mark.asyncio
async def test_initialize_and_list_tools():
    """Verify the MCP server starts and exposes expected tools."""
    async with stdio_client(_server_params()) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            tool_names = {t.name for t in tools.tools}
            assert "view_data" in tool_names
            assert "buckaroo_diagnostics" in tool_names


@pytest.mark.asyncio
async def test_view_data_with_csv(tmp_path):
    """Verify view_data loads a CSV and returns a summary."""
    csv_file = tmp_path / "test.csv"
    csv_file.write_text("name,age\nAlice,30\nBob,25\n")

    async with stdio_client(_server_params()) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "view_data",
                arguments={"path": str(csv_file)},
            )
            text = str(result.content)
            assert "2" in text  # 2 rows
            assert "name" in text
