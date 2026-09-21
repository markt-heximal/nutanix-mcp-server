"""Tests for MCP server plumbing: structured output, error results, resources."""

import json
import os
from unittest.mock import AsyncMock, patch

import pytest
from mcp.server.lowlevel.helper_types import ReadResourceContents
from mcp.types import CallToolResult

from nutanix_mcp.client import NutanixAPIError
from nutanix_mcp.config import Settings
from nutanix_mcp.server import _error_result, _jsonable, create_server


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch):
    """Keep these tests off the operator's real configuration.

    Settings reads a .env from the current directory and NUTANIX_* from the
    environment. A PE-only deployment sets NUTANIX_PE_ONLY=true, which makes
    the server refuse every non-pe_ tool, so the list_vms tests below failed
    on any checkout configured for one.
    """
    for key in [k for k in os.environ if k.startswith("NUTANIX_")]:
        monkeypatch.delenv(key, raising=False)


@pytest.fixture
def settings():
    # _env_file=None completes the isolation started by the fixture above.
    return Settings(_env_file=None, host="pc.example.com", username="admin", password="secret")


def test_jsonable_handles_datetimes():
    from datetime import datetime, timezone

    value = {"createdTime": datetime(2026, 1, 1, tzinfo=timezone.utc), "count": 3}
    result = _jsonable(value)
    json.dumps(result)  # must not raise
    assert result["count"] == 3
    assert "2026" in result["createdTime"]


def test_error_result_sets_is_error():
    result = _error_result("boom")
    assert isinstance(result, CallToolResult)
    assert result.isError is True
    assert "boom" in result.content[0].text


def test_create_server_exposes_metadata(settings):
    server, client = create_server(settings)
    assert server.name == "nutanix-mcp"
    assert server.version
    assert "Prism" in (server.instructions or "")


@pytest.mark.asyncio
async def test_resolve_resource_returns_read_resource_contents(settings):
    """resolve_resource must return ReadResourceContents (the mcp SDK contract)."""
    from nutanix_mcp.resources import resolve_resource

    _, client = create_server(settings)
    contents = await resolve_resource(client, "nutanix://asbuilt/project")
    assert isinstance(contents[0], ReadResourceContents)
    assert contents[0].mime_type == "text/markdown"
    assert "Architecture" in contents[0].content


@pytest.mark.asyncio
async def test_unknown_resource_type_reports_error(settings):
    from nutanix_mcp.resources import resolve_resource

    _, client = create_server(settings)
    contents = await resolve_resource(client, "nutanix://bogus")
    payload = json.loads(contents[0].content)
    assert "Unknown resource type" in payload["error"]


@pytest.mark.asyncio
async def test_call_tool_wraps_api_errors(settings):
    """NutanixAPIError from a handler becomes an isError result, not a crash."""
    server, client = create_server(settings)

    failing = AsyncMock(side_effect=NutanixAPIError("Authentication failed", status_code=401))
    with patch.dict("nutanix_mcp.server.ALL_HANDLERS", {"list_vms": failing}):
        # Reach the registered call_tool handler through the request handler table
        import mcp.types as types

        handler = server.request_handlers[types.CallToolRequest]
        request = types.CallToolRequest(
            method="tools/call",
            params=types.CallToolRequestParams(name="list_vms", arguments={}),
        )
        result = await handler(request)

    assert result.root.isError is True
    assert "Authentication failed" in result.root.content[0].text
    assert "HTTP 401" in result.root.content[0].text


@pytest.mark.asyncio
async def test_call_tool_returns_structured_content(settings):
    server, client = create_server(settings)

    ok = AsyncMock(return_value={"totalReturned": 1, "vms": [{"name": "web-01"}]})
    with patch.dict("nutanix_mcp.server.ALL_HANDLERS", {"list_vms": ok}):
        import mcp.types as types

        handler = server.request_handlers[types.CallToolRequest]
        request = types.CallToolRequest(
            method="tools/call",
            params=types.CallToolRequestParams(name="list_vms", arguments={}),
        )
        result = await handler(request)

    assert result.root.isError is False
    assert result.root.structuredContent == {"totalReturned": 1, "vms": [{"name": "web-01"}]}
    # Text fallback carries the same JSON for clients without structured support
    assert "web-01" in result.root.content[0].text
