"""MCP Server implementation for Nutanix Prism Central & Element."""

import asyncio
import contextlib
import json
import logging
import sys
from collections.abc import AsyncIterator
from typing import Any

from mcp.server import Server
from mcp.server.lowlevel.helper_types import ReadResourceContents
from mcp.server.stdio import stdio_server
from mcp.types import (
    CallToolResult,
    GetPromptResult,
    Prompt,
    Resource,
    ResourceTemplate,
    TextContent,
    Tool,
)

from nutanix_mcp import __version__
from nutanix_mcp.client import NutanixAPIError, NutanixClient
from nutanix_mcp.config import Settings, get_settings
from nutanix_mcp.prompts import PROMPT_HANDLERS, PROMPTS
from nutanix_mcp.resources import (
    RESOURCE_TEMPLATES,
    STATIC_RESOURCES,
    resolve_resource,
)
from nutanix_mcp.tools import get_all_tools
from nutanix_mcp.tools.alert import ALERT_HANDLERS
from nutanix_mcp.tools.asbuilt import ASBUILT_HANDLERS
from nutanix_mcp.tools.category import CATEGORY_HANDLERS
from nutanix_mcp.tools.cluster import CLUSTER_HANDLERS
from nutanix_mcp.tools.networking import NETWORKING_HANDLERS
from nutanix_mcp.tools.prism_element import PE_HANDLERS
from nutanix_mcp.tools.snapshot import SNAPSHOT_HANDLERS
from nutanix_mcp.tools.task import TASK_HANDLERS
from nutanix_mcp.tools.vm import VM_HANDLERS

logger = logging.getLogger("nutanix_mcp")

# Merge all handler dispatch tables
ALL_HANDLERS: dict[str, Any] = {
    **VM_HANDLERS,
    **CLUSTER_HANDLERS,
    **PE_HANDLERS,
    **NETWORKING_HANDLERS,
    **TASK_HANDLERS,
    **ALERT_HANDLERS,
    **CATEGORY_HANDLERS,
    **SNAPSHOT_HANDLERS,
    **ASBUILT_HANDLERS,
}

SERVER_INSTRUCTIONS = """\
This server manages Nutanix infrastructure through two API surfaces:

- Prism Central tools (list_vms, get_cluster, list_alerts, ...) operate
  fleet-wide through the central management plane.
- Prism Element tools (pe_*) query a single cluster directly and take a
  `pe_host` argument. Discover valid hosts with list_clusters, or pass a
  cluster name/UUID to generate_asbuilt which resolves it automatically.

Mutating operations (create/update/delete/power/clone) return a task UUID
immediately; poll get_task to confirm completion before reporting success.
delete_vm additionally requires confirm=true. Before risky changes,
snapshot_vm provides a recovery point as a safety net.
"""


def _error_result(message: str) -> CallToolResult:
    """Build a tool error result the client can detect via isError."""
    return CallToolResult(
        content=[TextContent(type="text", text=message)],
        isError=True,
    )


def _describe_exception(e: Exception, settings: Settings) -> str:
    """Translate SDK/transport exceptions into actionable error messages.

    The Nutanix SDK raises per-namespace ApiException classes (duck-typed
    via .status/.reason) and urllib3 connection errors whose raw text is
    noisy; give the model something it can act on instead.
    """
    status = getattr(e, "status", None)
    reason = getattr(e, "reason", None)
    if status is not None:
        if status in (401, 403):
            return f"Nutanix API error: authentication failed (HTTP {status}). Check NUTANIX_USERNAME/NUTANIX_PASSWORD."
        if status == 404:
            return "Nutanix API error: resource not found (HTTP 404). Verify the UUID/extId."
        if status == 412 or status == 409:
            return f"Nutanix API error: concurrent modification conflict (HTTP {status}). Re-fetch the entity and retry."
        return f"Nutanix API error (HTTP {status}): {reason or e}"
    name = type(e).__name__
    if "MaxRetryError" in name or "ConnectionError" in name or "NewConnectionError" in name:
        return (
            f"Cannot reach Prism Central at {settings.host}:{settings.port}. "
            "Check NUTANIX_HOST, network connectivity, and that port 9440 is open."
        )
    return f"Unexpected error ({name}): {e}"


def _jsonable(value: Any) -> Any:
    """Coerce handler output into JSON-serializable structured content.

    SDK model dumps can contain datetimes and other rich types that
    json.dumps rejects; stringify anything non-standard.
    """
    return json.loads(json.dumps(value, default=str))


def create_server(settings: Settings) -> tuple[Server, NutanixClient]:
    """Create and configure the MCP server."""
    server = Server(
        "nutanix-mcp",
        version=__version__,
        instructions=SERVER_INSTRUCTIONS,
    )
    client = NutanixClient(settings)
    all_tools = get_all_tools(settings.pe_only)

    # ─── Tools ────────────────────────────────────────────────────────────

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        """Return the list of available tools."""
        return [
            Tool(
                name=tool["name"],
                title=tool["title"],
                description=tool["description"],
                inputSchema=tool["inputSchema"],
                annotations=tool["annotations"],
            )
            for tool in all_tools
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any] | CallToolResult:
        """Execute a tool and return structured content (or an error result)."""
        if settings.pe_only and not name.startswith("pe_"):
            return _error_result(
                f"Tool '{name}' requires Prism Central, but this server is "
                "running in PE-only mode (NUTANIX_PE_ONLY=true). Only Prism "
                "Element tools (pe_*) are available until a Prism Central is "
                "deployed and NUTANIX_PE_ONLY is unset."
            )

        handler = ALL_HANDLERS.get(name)
        if not handler:
            return _error_result(f"Unknown tool '{name}'")

        try:
            result = await handler(client, arguments or {})
            return _jsonable(result)
        except NutanixAPIError as e:
            error_text = f"Nutanix API error: {e.message}"
            if e.status_code:
                error_text += f" (HTTP {e.status_code})"
            logger.warning("Tool %s failed: %s", name, error_text)
            return _error_result(error_text)
        except Exception as e:
            logger.exception("Tool %s raised unexpected error", name)
            return _error_result(_describe_exception(e, settings))

    # ─── Resources ────────────────────────────────────────────────────────

    @server.list_resources()
    async def list_resources() -> list[Resource]:
        """Return browseable static resources.

        The nutanix:// resources are backed by Prism Central, so they are
        hidden in PE-only mode to avoid advertising unusable entry points.
        """
        if settings.pe_only:
            return []
        return STATIC_RESOURCES

    @server.list_resource_templates()
    async def list_resource_templates() -> list[ResourceTemplate]:
        """Return URI templates for parameterized resource access."""
        if settings.pe_only:
            return []
        return RESOURCE_TEMPLATES

    @server.read_resource()
    async def read_resource(uri: str) -> list[ReadResourceContents]:
        """Resolve a nutanix:// URI to resource contents."""
        if settings.pe_only:
            return [
                ReadResourceContents(
                    content=json.dumps(
                        {
                            "error": "nutanix:// resources are backed by Prism "
                            "Central and are unavailable in PE-only mode "
                            "(NUTANIX_PE_ONLY=true). Use pe_* tools instead."
                        }
                    ),
                    mime_type="application/json",
                )
            ]
        try:
            return await resolve_resource(client, str(uri))
        except NutanixAPIError as e:
            error_text = f"Error: {e.message}"
            if e.status_code:
                error_text += f" (HTTP {e.status_code})"
            logger.warning("Resource read %s failed: %s", uri, error_text)
            return [
                ReadResourceContents(
                    content=json.dumps({"error": error_text}),
                    mime_type="application/json",
                )
            ]

    # ─── Prompts ──────────────────────────────────────────────────────────

    @server.list_prompts()
    async def list_prompts() -> list[Prompt]:
        """Return available prompts."""
        return PROMPTS

    @server.get_prompt()
    async def get_prompt(name: str, arguments: dict[str, str] | None) -> GetPromptResult:
        """Handle a prompt request."""
        handler = PROMPT_HANDLERS.get(name)
        if not handler:
            raise ValueError(f"Unknown prompt: {name}")
        return handler(arguments or {})

    return server, client


def _configure_logging(settings: Settings) -> None:
    """Send logs to stderr (stdout is reserved for the stdio transport)."""
    logging.basicConfig(
        stream=sys.stderr,
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )


async def run_stdio() -> None:
    """Run the MCP server over stdio transport."""
    settings = get_settings()
    _configure_logging(settings)

    if not settings.has_credentials:
        logger.error("No credentials configured. Set NUTANIX_USERNAME and NUTANIX_PASSWORD.")
        sys.exit(1)

    logger.info("Starting Nutanix MCP server (stdio) for %s:%s", settings.host, settings.port)
    if settings.pe_only:
        logger.info("PE-only mode active: Prism Central tools are hidden; only pe_* tools are exposed.")

    server, client = create_server(settings)

    try:
        async with stdio_server() as (read_stream, write_stream):
            await server.run(
                read_stream,
                write_stream,
                server.create_initialization_options(),
            )
    finally:
        await client.close()


def run_http(host: str = "0.0.0.0", port: int = 8000) -> None:
    """Run the MCP server over streamable HTTP transport."""
    import uvicorn
    from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
    from starlette.applications import Starlette
    from starlette.routing import Mount

    settings = get_settings()
    _configure_logging(settings)

    if not settings.has_credentials:
        logger.error("No credentials configured. Set NUTANIX_USERNAME and NUTANIX_PASSWORD.")
        sys.exit(1)

    server, client = create_server(settings)
    session_manager = StreamableHTTPSessionManager(app=server, json_response=True)

    @contextlib.asynccontextmanager
    async def lifespan(app: Starlette) -> AsyncIterator[None]:
        async with session_manager.run():
            yield
        await client.close()

    app = Starlette(
        lifespan=lifespan,
        routes=[Mount("/mcp", app=session_manager.handle_request)],
    )

    logger.info("Starting Nutanix MCP server (HTTP) at http://%s:%s/mcp", host, port)
    uvicorn.run(app, host=host, port=port)


def main() -> None:
    """Entry point for the MCP server. Supports --http flag for HTTP transport."""
    try:
        if "--http" in sys.argv:
            host = "0.0.0.0"
            port = 8000
            for i, arg in enumerate(sys.argv):
                if arg == "--host" and i + 1 < len(sys.argv):
                    host = sys.argv[i + 1]
                elif arg == "--port" and i + 1 < len(sys.argv):
                    port = int(sys.argv[i + 1])
            run_http(host=host, port=port)
        else:
            asyncio.run(run_stdio())
    except KeyboardInterrupt:
        print("\nShutting down...", file=sys.stderr)
    except Exception as e:
        print(f"Fatal error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
