"""Layer 1: MCP protocol tests — verify resource and tool metadata via MCP client."""

import os
import sys
import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_ENTRY_POINT = os.path.join(_REPO_ROOT, "src", "buckaroo_mcp_tool.py")
_PANEL_URI = "ui://buckaroo/view.html"


def _server_params():
    return StdioServerParameters(command=sys.executable, args=[_ENTRY_POINT])


async def test_panel_resource_is_listed():
    """ui://buckaroo/view.html must appear in resources/list."""
    async with stdio_client(_server_params()) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            resources = await session.list_resources()
            uris = [str(r.uri) for r in resources.resources]
            assert _PANEL_URI in uris, f"Panel URI not found. Got: {uris}"


async def test_panel_resource_mime_type():
    """resources/read must return text/html;profile=mcp-app."""
    async with stdio_client(_server_params()) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.read_resource(_PANEL_URI)
            assert result.contents, "Resource returned no contents"
            content = result.contents[0]
            assert content.mimeType == "text/html;profile=mcp-app", (
                f"Wrong mime type: {content.mimeType}"
            )


async def test_panel_resource_html_content():
    """Panel HTML must contain key elements: iframe, postMessage listener, loading div."""
    async with stdio_client(_server_params()) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.read_resource(_PANEL_URI)
            html = result.contents[0].text
            assert "<iframe" in html
            assert "ui/notifications/tool-result" in html
            assert "loading" in html


async def test_view_data_tool_has_panel_meta():
    """view_data tool must declare _meta.ui.resourceUri pointing to panel."""
    async with stdio_client(_server_params()) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            tool = next((t for t in tools.tools if t.name == "view_data"), None)
            assert tool is not None
            meta = tool.meta or {}
            assert meta.get("ui", {}).get("resourceUri") == _PANEL_URI, (
                f"view_data meta.ui.resourceUri wrong: {meta}"
            )


async def test_buckaroo_table_tool_has_panel_meta():
    """buckaroo_table alias must also declare the panel resourceUri."""
    async with stdio_client(_server_params()) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            tool = next((t for t in tools.tools if t.name == "buckaroo_table"), None)
            assert tool is not None
            meta = tool.meta or {}
            assert meta.get("ui", {}).get("resourceUri") == _PANEL_URI, (
                f"buckaroo_table meta.ui.resourceUri wrong: {meta}"
            )


async def test_view_data_returns_tornado_url(tmp_path):
    """Calling view_data must return a response containing a localhost session URL."""
    csv_file = tmp_path / "test.csv"
    csv_file.write_text("name,age\nAlice,30\nBob,25\n")

    async with stdio_client(_server_params()) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "view_data", arguments={"path": str(csv_file)}
            )
            text = str(result.content)
            import re
            urls = re.findall(r"http://localhost:\d+/s/[a-f0-9]+", text)
            assert urls, f"No session URL found in tool response: {text[:500]}"
