"""Read-only HTTP façade over the Nutanix MCP server's Prism Element tools.

Purpose
-------
Expose ONLY the read-only ``pe_list_*`` Prism Element tools as plain GET
endpoints, so a browser frontend (e.g. a Lovable app) can read cluster state
without ever holding Nutanix credentials or touching a write-capable tool.

Why a façade instead of pointing the frontend at MCP directly
-------------------------------------------------------------
The MCP server carries write tools (power_off_vm, create_vm, delete_vm) and the
raw Prism credentials. A browser should never sit that close to those. This
façade:

  * imports ONLY the pe_list_* handlers — write handlers are never wired up, so
    they are structurally unreachable, not merely filtered;
  * keeps Nutanix credentials server-side (loaded via the existing Settings);
  * gates every call behind an X-API-Key shared secret;
  * pins the target Prism Element host to the configured allowlist;
  * fails closed: refuses to start without an API key.

Run
---
    # reuses the same NUTANIX_* env / .env as the MCP server, plus:
    export FACADE_API_KEY="$(openssl rand -hex 32)"
    export FACADE_CORS_ORIGINS="https://your-app.lovable.app"   # comma-separated
    export NUTANIX_HOST=10.0.1.242          # your PE cluster VIP
    export NUTANIX_VERIFY_SSL=false         # lab only (self-signed PE cert)

    uvicorn pe_facade:app --host 127.0.0.1 --port 9770

Put it behind Tailscale (Funnel/Serve) or a reverse proxy for TLS; do not bind
it to 0.0.0.0 on an untrusted segment.

Endpoints
---------
    GET  /healthz                 liveness, no auth
    GET  /pe/tools                lists the exposed read-only endpoints (auth)
    GET  /pe/{resource}           one per pe_list_* tool, e.g. /pe/vms (auth)

``resource`` is the tool name minus the ``pe_list_`` prefix (pe_list_vms -> vms).
``pe_host`` defaults to NUTANIX_HOST and may be overridden with ?pe_host=,
but only if the value is permitted by NUTANIX_ALLOWED_PE_HOSTS.
"""

from __future__ import annotations

import contextlib
import os
from collections.abc import AsyncIterator
from typing import Any, Callable

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from nutanix_mcp.client import NutanixAPIError, NutanixClient
from nutanix_mcp.config import get_settings
from nutanix_mcp.tools import get_all_tools
from nutanix_mcp.tools.prism_element import PE_HANDLERS

# ── Which tools the façade exposes ────────────────────────────────────────────
# Strictly the read-only pe_list_* surface. To also expose the cluster summary,
# append "pe_get_cluster_info" — it is read-only — to this tuple. Nothing that
# mutates state can ever be added here without also editing the guard below.
EXPOSED_PREFIXES: tuple[str, ...] = ("pe_list_",)

API_KEY_HEADER = "X-API-Key"

settings = get_settings()

if not os.environ.get("FACADE_API_KEY"):
    raise RuntimeError(
        "FACADE_API_KEY is not set. The façade refuses to start without a shared "
        "secret so it can never run open to the network."
    )
_API_KEY = os.environ["FACADE_API_KEY"]

_CORS_ORIGINS = [
    o.strip() for o in os.environ.get("FACADE_CORS_ORIGINS", "").split(",") if o.strip()
]

# Build the read-only tool catalogue from the server's own definitions so the
# façade stays in lock-step with the MCP server rather than hardcoding names.
_PE_TOOLS_BY_NAME: dict[str, dict[str, Any]] = {
    t["name"]: t for t in get_all_tools(pe_only=True)
}
_EXPOSED_TOOLS: dict[str, dict[str, Any]] = {
    name: tool
    for name, tool in _PE_TOOLS_BY_NAME.items()
    if name.startswith(EXPOSED_PREFIXES)
}

# Defense in depth: assert every exposed tool is actually read-only and has a
# handler. If the upstream repo ever marks a pe_list_* tool as mutating, or a
# handler goes missing, the façade fails to import rather than exposing it.
for _name, _tool in _EXPOSED_TOOLS.items():
    ann = _tool.get("annotations")
    read_only = getattr(ann, "readOnlyHint", None)
    if read_only is not True:
        raise RuntimeError(f"Refusing to expose non-read-only tool: {_name}")
    if _name not in PE_HANDLERS:
        raise RuntimeError(f"No handler found for exposed tool: {_name}")

# Single shared client, created on demand and closed on shutdown.
_client: NutanixClient | None = None


def _get_client() -> NutanixClient:
    """Return the shared client, creating it lazily if the lifespan hook
    has not run yet (e.g. under some test harnesses)."""
    global _client
    if _client is None:
        _client = NutanixClient(settings)
    return _client


@contextlib.asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    _get_client()
    try:
        yield
    finally:
        if _client is not None:
            await _client.close()


app = FastAPI(
    title="Nutanix PE Read-Only Façade",
    version="1.0.0",
    description="Read-only Prism Element endpoints for frontend consumption.",
    lifespan=lifespan,
)

if _CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_CORS_ORIGINS,
        allow_methods=["GET"],
        allow_headers=[API_KEY_HEADER],
        allow_credentials=False,
    )


async def require_api_key(request: Request) -> None:
    """Constant-work API-key check on the X-API-Key header."""
    supplied = request.headers.get(API_KEY_HEADER, "")
    # hmac.compare_digest avoids leaking length/timing about the secret.
    import hmac

    if not supplied or not hmac.compare_digest(supplied, _API_KEY):
        raise HTTPException(status_code=401, detail="Invalid or missing API key.")


def _resolve_pe_host(pe_host: str | None) -> str:
    """Pick the target PE host and enforce the allowlist."""
    host = pe_host or settings.host
    if not settings.is_pe_host_allowed(host):
        raise HTTPException(
            status_code=403,
            detail=(
                f"pe_host '{host}' is not permitted. Add it to "
                "NUTANIX_ALLOWED_PE_HOSTS or omit ?pe_host to use NUTANIX_HOST."
            ),
        )
    return host


def _required_extra_args(tool: dict[str, Any]) -> list[str]:
    """Required args for a tool other than pe_host (e.g. protection_domain)."""
    schema = tool.get("inputSchema", {}) or {}
    required = schema.get("required", []) or []
    return [r for r in required if r != "pe_host"]


def _make_route(tool_name: str) -> Callable:
    """Build a GET handler bound to one pe_list_* tool (late-binding-safe)."""
    tool = _EXPOSED_TOOLS[tool_name]
    extra = _required_extra_args(tool)

    async def route(
        request: Request,
        pe_host: str | None = Query(
            default=None,
            description="Prism Element host (defaults to NUTANIX_HOST).",
        ),
        _: None = Depends(require_api_key),
    ) -> JSONResponse:
        client = _get_client()
        host = _resolve_pe_host(pe_host)
        args: dict[str, Any] = {"pe_host": host}

        # Pass through any additional required args from the query string,
        # rejecting anything the tool's own schema does not declare required.
        for key in extra:
            val = request.query_params.get(key)
            if val is None:
                raise HTTPException(
                    status_code=400,
                    detail=f"Missing required query parameter: {key}",
                )
            args[key] = val

        handler = PE_HANDLERS[tool_name]
        try:
            result = await handler(client, args)
        except NutanixAPIError as e:
            code = e.status_code or 502
            # Collapse auth/permission issues to 502 so we never echo the PE's
            # own 401 back to an anonymous-ish browser caller.
            status = 502 if code in (401, 403) else code
            raise HTTPException(status_code=status, detail=f"Nutanix error: {e.message}")
        except Exception as e:  # connection/timeout/etc.
            raise HTTPException(
                status_code=502,
                detail=f"Could not reach Prism Element at {host}: {type(e).__name__}",
            )
        return JSONResponse(content={"pe_host": host, "resource": tool_name, "data": result})

    route.__name__ = f"pe_{tool_name}"
    return route


# Register one GET route per exposed read-only tool.
for _name in sorted(_EXPOSED_TOOLS):
    _resource = _name[len("pe_list_"):] if _name.startswith("pe_list_") else _name
    app.add_api_route(
        f"/pe/{_resource}",
        _make_route(_name),
        methods=["GET"],
        name=f"pe_{_resource}",
        summary=_EXPOSED_TOOLS[_name].get("title") or _name,
    )


@app.get("/pe/tools")
async def list_exposed_tools(_: None = Depends(require_api_key)) -> dict[str, Any]:
    """List the read-only endpoints this façade exposes."""
    out = []
    for name in sorted(_EXPOSED_TOOLS):
        resource = name[len("pe_list_"):] if name.startswith("pe_list_") else name
        out.append(
            {
                "path": f"/pe/{resource}",
                "tool": name,
                "title": _EXPOSED_TOOLS[name].get("title"),
                "extra_required_params": _required_extra_args(_EXPOSED_TOOLS[name]),
            }
        )
    return {"default_pe_host": settings.host, "endpoints": out}


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    """Liveness probe (no auth)."""
    return {"status": "ok"}
