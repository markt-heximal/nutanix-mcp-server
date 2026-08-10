"""Authenticated management API over the full Nutanix MCP tool surface.

Purpose
-------
Expose the *entire* Nutanix tool surface (reads **and** writes — including
create/clone/delete VMs) to a browser frontend (e.g. a Lovable app) behind
real user authentication, so an operator can manage the cluster from a UI
without the browser ever holding Nutanix credentials.

How it differs from ``pe_facade.py``
-------------------------------------
``pe_facade.py`` is the *read-only* boundary: it imports only ``pe_list_*``
handlers, so write tools are structurally absent. This module is the opposite
end of the spectrum — it deliberately bridges the whole handler registry — so
it MUST carry a stronger gate than a shared key. It therefore adds:

  * **Username / password login** issuing short-lived **JWT** sessions.
  * **Role-based access control** derived from each tool's own MCP annotations:
        - read-only tools           -> ``viewer``   (and above)
        - non-destructive writes    -> ``operator`` (and above)
        - destructive writes        -> ``admin`` only
  * **Explicit confirmation** for destructive operations: the request must
    carry ``confirm: true`` or the call is refused (428), independent of any
    per-tool ``confirm`` argument.
  * Nutanix credentials stay server-side (loaded via the existing Settings).
  * CORS locked to the configured frontend origin(s).
  * **Fails closed**: refuses to start without a JWT secret and at least one
    configured user.

The bridge stays in lock-step with the MCP server: it dispatches through the
same ``ALL_HANDLERS`` table and advertises the same ``get_all_tools()``
catalogue, so it can never drift out of sync with what the server actually
implements.

Run
---
    # reuses the same NUTANIX_* env / .env as the MCP server, plus:
    export MGMT_JWT_SECRET="$(openssl rand -hex 32)"
    export MGMT_CORS_ORIGINS="https://your-app.lovable.app"     # comma-separated
    export MGMT_USERS_FILE="/etc/nutanix-mgmt/users.json"       # or MGMT_USERS=...
    uvicorn management_api:app --host 127.0.0.1 --port 9780

Put it behind a TLS reverse proxy (Caddy/nginx) or a tailnet; do not bind it
to ``0.0.0.0`` on an untrusted segment.

Endpoints
---------
    GET  /healthz                 liveness, no auth
    POST /api/auth/login          {username, password} -> {access_token, role, ...}
    GET  /api/me                  current identity (auth)
    GET  /api/config              default pe_host + allowlist for the UI (auth)
    GET  /api/tools               tool catalogue with min_role + schemas (auth)
    POST /api/tools/{name}        execute a tool; body {arguments, confirm} (auth + RBAC)
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, Optional

import jwt
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Load the connection env (.env, shared with the MCP server) and the
# management-specific secrets (.management.env) before reading any MGMT_*/
# NUTANIX_* below. Real process env still wins (override=False), so Docker's
# env_file / launchd EnvironmentVariables take precedence over the files.
load_dotenv(".env", override=False)
load_dotenv(".management.env", override=False)

from nutanix_mcp.client import NutanixAPIError, NutanixClient  # noqa: E402
from nutanix_mcp.config import get_settings  # noqa: E402
from nutanix_mcp.server import ALL_HANDLERS  # noqa: E402
from nutanix_mcp.tools import get_all_tools  # noqa: E402

logger = logging.getLogger("nutanix_mgmt")

# ── Roles ─────────────────────────────────────────────────────────────────────
# A total order: a user with a higher-ranked role may do everything a lower one
# can. Tool access is gated by comparing the caller's rank to the tool's rank.
ROLE_RANK: dict[str, int] = {"viewer": 1, "operator": 2, "admin": 3}


def _tool_min_role(tool: dict[str, Any]) -> str:
    """Minimum role required to invoke a tool, from its MCP annotations.

    read-only            -> viewer
    write, non-destructive -> operator
    write, destructive   -> admin
    """
    ann = tool.get("annotations")
    read_only = getattr(ann, "readOnlyHint", None)
    if read_only is True:
        return "viewer"
    if getattr(ann, "destructiveHint", None) is True:
        return "admin"
    return "operator"


# Build the catalogue once at import time so every request is a cheap lookup.
_TOOLS_BY_NAME: dict[str, dict[str, Any]] = {t["name"]: t for t in get_all_tools()}
_TOOL_MIN_ROLE: dict[str, str] = {n: _tool_min_role(t) for n, t in _TOOLS_BY_NAME.items()}
_DESTRUCTIVE: set[str] = {
    n for n, t in _TOOLS_BY_NAME.items()
    if getattr(t.get("annotations"), "destructiveHint", None) is True
}

# ── Auth configuration (fail closed) ──────────────────────────────────────────
_JWT_SECRET = os.environ.get("MGMT_JWT_SECRET", "")
if not _JWT_SECRET:
    raise RuntimeError(
        "MGMT_JWT_SECRET is not set. The management API refuses to start without "
        "a signing secret so it can never issue forgeable sessions."
    )

_JWT_ALG = "HS256"
_TOKEN_TTL = int(os.environ.get("MGMT_TOKEN_TTL_SECONDS", "3600"))
_JWT_ISS = "nutanix-mgmt-api"


def _load_users() -> dict[str, dict[str, str]]:
    """Load the user table from MGMT_USERS_FILE (preferred) or MGMT_USERS.

    Shape: {"alice": {"password_hash": "pbkdf2_sha256$...", "role": "admin"}}
    Generate hashes with ``python scripts/mgmt_user.py alice admin``.
    """
    raw: Optional[str] = None
    path = os.environ.get("MGMT_USERS_FILE")
    if path:
        with open(path, encoding="utf-8") as fh:
            raw = fh.read()
    else:
        raw = os.environ.get("MGMT_USERS")
    if not raw:
        raise RuntimeError(
            "No users configured. Set MGMT_USERS_FILE to a JSON file or MGMT_USERS "
            "to a JSON object mapping username -> {password_hash, role}."
        )
    try:
        users = json.loads(raw)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"MGMT_USERS is not valid JSON: {e}") from e
    if not isinstance(users, dict) or not users:
        raise RuntimeError("MGMT_USERS must be a non-empty JSON object.")
    for name, rec in users.items():
        if not isinstance(rec, dict) or "password_hash" not in rec or "role" not in rec:
            raise RuntimeError(f"User '{name}' must have password_hash and role.")
        if rec["role"] not in ROLE_RANK:
            raise RuntimeError(
                f"User '{name}' has unknown role '{rec['role']}'. "
                f"Valid roles: {', '.join(ROLE_RANK)}."
            )
    return users


_USERS = _load_users()

_CORS_ORIGINS = [
    o.strip() for o in os.environ.get("MGMT_CORS_ORIGINS", "").split(",") if o.strip()
]

settings = get_settings()


# ── Password hashing (stdlib, no extra dependency) ────────────────────────────
def verify_password(password: str, stored: str) -> bool:
    """Verify a password against a ``pbkdf2_sha256$iterations$salt$hash`` string.

    Uses a constant-time compare on the derived key. Unknown/garbled formats
    verify as False rather than raising, so a malformed record can't 500.
    """
    try:
        algo, iters_s, salt_hex, hash_hex = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        iters = int(iters_s)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
    except (ValueError, AttributeError):
        return False
    derived = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iters)
    return hmac.compare_digest(derived, expected)


# ── JWT helpers ───────────────────────────────────────────────────────────────
def _issue_token(username: str, role: str) -> tuple[str, int]:
    now = int(time.time())
    payload = {
        "iss": _JWT_ISS,
        "sub": username,
        "role": role,
        "iat": now,
        "exp": now + _TOKEN_TTL,
    }
    token = jwt.encode(payload, _JWT_SECRET, algorithm=_JWT_ALG)
    return token, _TOKEN_TTL


class Identity(BaseModel):
    username: str
    role: str


def _decode_identity(request: Request) -> Identity:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token.")
    token = auth[len("Bearer "):].strip()
    try:
        payload = jwt.decode(
            token, _JWT_SECRET, algorithms=[_JWT_ALG], issuer=_JWT_ISS
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Session expired. Log in again.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid session token.")
    username = payload.get("sub")
    role = payload.get("role")
    if role not in ROLE_RANK:
        raise HTTPException(status_code=401, detail="Token carries an unknown role.")
    return Identity(username=str(username), role=str(role))


async def require_identity(request: Request) -> Identity:
    """FastAPI dependency: authenticate the caller from the JWT."""
    return _decode_identity(request)


# ── Nutanix client lifecycle ──────────────────────────────────────────────────
_client: NutanixClient | None = None


def _get_client() -> NutanixClient:
    global _client
    if _client is None:
        _client = NutanixClient(settings)
    return _client


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    _get_client()
    try:
        yield
    finally:
        if _client is not None:
            await _client.close()


app = FastAPI(
    title="Nutanix Management API",
    version="1.0.0",
    description="Authenticated full-surface Nutanix management API for a frontend.",
    lifespan=lifespan,
)

if _CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_CORS_ORIGINS,
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type"],
        allow_credentials=False,
    )


# ── Request models ────────────────────────────────────────────────────────────
class LoginRequest(BaseModel):
    username: str
    password: str


class ToolCall(BaseModel):
    arguments: dict[str, Any] = {}
    confirm: bool = False


# ── Routes ────────────────────────────────────────────────────────────────────
@app.get("/healthz")
async def healthz() -> dict[str, str]:
    """Liveness probe (no auth)."""
    return {"status": "ok"}


@app.post("/api/auth/login")
async def login(body: LoginRequest) -> dict[str, Any]:
    """Exchange username/password for a short-lived JWT."""
    rec = _USERS.get(body.username)
    # Always run a verify to keep timing roughly constant for unknown users.
    stored = rec["password_hash"] if rec else "pbkdf2_sha256$1$00$00"
    ok = verify_password(body.password, stored)
    if not rec or not ok:
        logger.warning("Failed login for username=%r", body.username)
        raise HTTPException(status_code=401, detail="Invalid username or password.")
    token, ttl = _issue_token(body.username, rec["role"])
    logger.info("Login ok user=%s role=%s", body.username, rec["role"])
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": ttl,
        "username": body.username,
        "role": rec["role"],
    }


@app.get("/api/me")
async def me(identity: Identity = Depends(require_identity)) -> dict[str, str]:
    """Return the caller's identity and role."""
    return {"username": identity.username, "role": identity.role}


@app.get("/api/config")
async def config(identity: Identity = Depends(require_identity)) -> dict[str, Any]:
    """UI bootstrap: default PE host, allowlist, and role ranking."""
    return {
        "default_pe_host": settings.host,
        "allowed_pe_hosts": settings.allowed_pe_hosts,
        "pe_only": settings.pe_only,
        "roles": ROLE_RANK,
        "your_role": identity.role,
    }


@app.get("/api/tools")
async def list_tools(identity: Identity = Depends(require_identity)) -> dict[str, Any]:
    """Advertise the tool catalogue with the min role and whether the caller
    may run each tool, so the UI can render forms and disable what it can't."""
    caller_rank = ROLE_RANK[identity.role]
    out = []
    for name, tool in _TOOLS_BY_NAME.items():
        min_role = _TOOL_MIN_ROLE[name]
        out.append(
            {
                "name": name,
                "title": tool.get("title"),
                "description": tool.get("description"),
                "inputSchema": tool.get("inputSchema"),
                "min_role": min_role,
                "destructive": name in _DESTRUCTIVE,
                "allowed": caller_rank >= ROLE_RANK[min_role],
            }
        )
    return {"tools": out}


@app.post("/api/tools/{name}")
async def call_tool(
    name: str,
    body: ToolCall,
    identity: Identity = Depends(require_identity),
) -> dict[str, Any]:
    """Execute a tool after enforcing RBAC and destructive-op confirmation."""
    tool = _TOOLS_BY_NAME.get(name)
    handler = ALL_HANDLERS.get(name)
    if tool is None or handler is None:
        raise HTTPException(status_code=404, detail=f"Unknown tool '{name}'.")

    # PE-only deployments block central-plane tools, mirroring the MCP server.
    if settings.pe_only and not name.startswith("pe_"):
        raise HTTPException(
            status_code=409,
            detail=f"Tool '{name}' requires Prism Central; server is in PE-only mode.",
        )

    min_role = _TOOL_MIN_ROLE[name]
    if ROLE_RANK[identity.role] < ROLE_RANK[min_role]:
        raise HTTPException(
            status_code=403,
            detail=f"'{name}' requires role '{min_role}'; you are '{identity.role}'.",
        )

    args = dict(body.arguments or {})

    if name in _DESTRUCTIVE:
        if not body.confirm:
            raise HTTPException(
                status_code=428,
                detail=f"'{name}' is destructive; resend with confirm=true.",
            )
        # Some tools (e.g. delete_vm) carry their own required confirm flag.
        # Honour the top-level confirmation so the UI needs to ask only once.
        schema_required = (tool.get("inputSchema") or {}).get("required", []) or []
        if "confirm" in schema_required:
            args.setdefault("confirm", True)

    # Pin/allowlist the PE host exactly like the read-only façade does.
    if "pe_host" in ((tool.get("inputSchema") or {}).get("properties") or {}):
        host = args.get("pe_host") or settings.host
        if not settings.is_pe_host_allowed(host):
            raise HTTPException(
                status_code=403,
                detail=f"pe_host '{host}' is not in NUTANIX_ALLOWED_PE_HOSTS.",
            )
        args["pe_host"] = host

    logger.info(
        "tool=%s user=%s role=%s destructive=%s args=%s",
        name, identity.username, identity.role, name in _DESTRUCTIVE, sorted(args),
    )

    client = _get_client()
    try:
        result = await handler(client, args)
    except NutanixAPIError as e:
        code = e.status_code or 502
        # Never echo the cluster's own 401/403 back to a browser caller.
        status = 502 if code in (401, 403) else code
        raise HTTPException(status_code=status, detail=f"Nutanix error: {e.message}")
    except Exception as e:  # noqa: BLE001 — surface a clean 502, log the detail
        logger.exception("tool=%s raised", name)
        raise HTTPException(
            status_code=502, detail=f"Tool '{name}' failed: {type(e).__name__}"
        )

    # Coerce SDK model dumps (datetimes etc.) into JSON-safe structured content.
    safe = json.loads(json.dumps(result, default=str))
    return {"tool": name, "data": safe}
