# PE-only mode + read-only façade

Two additions for running `nutanix-mcp-server` against a lab that has **Prism
Element only** (no Prism Central yet), and for safely exposing read-only cluster
data to a web frontend.

Both were built and verified against a fresh clone of `jkmills/nutanix-mcp-server`.

---

## 1. PE-only guard — `pe_only_guard.patch`

**Problem it solves.** The server registers Prism Central tools (`list_vms`,
`list_clusters`, …) and Prism Element tools (`pe_*`) together. With no Prism
Central deployed, the PC tools don't fail at startup — they fail one call at a
time, at *call* time, which reads to the model as confusing intermittent errors.

**What the patch does.** Adds a `NUTANIX_PE_ONLY` setting. When `true`:

- `get_all_tools()` returns only the `pe_*` tools (65 → 32 here), so the model
  never sees a central-plane tool it can't use.
- `call_tool` blocks any non-`pe_` tool with a clear "PE-only mode" message.
- `nutanix://` resources (PC-backed) are hidden and reads return a clear error.
- Startup logs that PE-only mode is active.

Touches `config.py`, `server.py`, `tools/__init__.py` — 3 files, ~51 lines. No
behavior change when `NUTANIX_PE_ONLY` is unset.

**Apply:**

```bash
cd /path/to/nutanix-mcp-server
git apply pe_only_guard.patch      # or: git apply --check first
```

**Enable** (in `.env` or environment):

```
NUTANIX_HOST=10.0.1.242      # your PE cluster VIP
NUTANIX_USERNAME=...
NUTANIX_PASSWORD=...
NUTANIX_VERIFY_SSL=false     # lab only — self-signed PE cert
NUTANIX_PE_ONLY=true
```

Then the `pe_*` tools take a `pe_host` argument — pass your PE VIP (`10.0.1.242`).
When Prism Central lands and you bring Charlotte + SFO under it, just drop
`NUTANIX_PE_ONLY` and the full v4 tool surface returns.

---

## 2. Read-only façade — `pe_facade.py`

A thin FastAPI layer that exposes **only** the read-only `pe_list_*` tools as GET
endpoints, so a Lovable (or any browser) frontend can read cluster state without
holding Nutanix credentials or touching a write tool.

**Why not point the frontend at MCP directly.** MCP carries write tools
(`power_off_vm`, `create_vm`, `delete_vm`) and the raw Prism credentials. The
façade imports *only* the `pe_list_*` handlers — write tools are not merely
hidden, they're absent from the process. It also:

- gates every call behind an `X-API-Key` shared secret (same pattern as netmgr);
- keeps Nutanix creds server-side;
- pins the target PE host to `NUTANIX_ALLOWED_PE_HOSTS` when set;
- **fails closed** — refuses to start without `FACADE_API_KEY`.

**Run:**

```bash
pip install fastapi "uvicorn[standard]"
export FACADE_API_KEY="$(openssl rand -hex 32)"
export FACADE_CORS_ORIGINS="https://your-app.lovable.app"   # comma-separated
# reuses the same NUTANIX_* env as the MCP server
uvicorn pe_facade:app --host 127.0.0.1 --port 9770
```

Put it behind Tailscale Serve/Funnel for TLS rather than binding `0.0.0.0`.

**Endpoints:**

| Path | Auth | Notes |
| --- | --- | --- |
| `GET /healthz` | no | liveness |
| `GET /pe/tools` | yes | lists exposed endpoints + any extra required params |
| `GET /pe/{resource}` | yes | one per `pe_list_*` tool, e.g. `/pe/vms`, `/pe/hosts`, `/pe/disks` |

`{resource}` = tool name minus `pe_list_` (`pe_list_vms` → `/pe/vms`). `pe_host`
defaults to `NUTANIX_HOST`; override with `?pe_host=` only if allowlisted. Tools
needing more (e.g. `/pe/snapshots` needs `?protection_domain=`) enforce it from
the tool's own schema and return 400 if missing.

To also expose the cluster summary, add `pe_get_cluster_info` (read-only) to
`EXPOSED_PREFIXES` in `pe_facade.py`. Nothing that mutates state can be added
there — the file asserts every exposed tool is `readOnlyHint=True` at import.

---

## `NUTANIX_ALLOWED_PE_HOSTS` format (fixed in this patch)

Upstream, this field only accepted JSON-array form — a bare comma-separated
string errored at startup, because pydantic-settings JSON-decodes list fields
before the validator runs. The patch annotates the field with
`pydantic_settings.NoDecode` and teaches the validator to accept **both**, so
either of these works:

```
NUTANIX_ALLOWED_PE_HOSTS=10.0.1.242,10.0.2.242      # comma-separated
NUTANIX_ALLOWED_PE_HOSTS=["10.0.1.242","10.0.2.242"] # JSON array
```

This bumps the `pydantic-settings` floor to `>=2.2.0` (when `NoDecode` was
added); your resolved version is well past that.

---

## Verified

- Patch applies cleanly to a fresh clone; package imports; PE-only filtering
  65 → 32 tools, all `pe_*`.
- `NUTANIX_ALLOWED_PE_HOSTS` accepts both comma-separated and JSON-array forms.
- Façade: auth 401 without key, 17 `pe_list_*` endpoints registered, schema-required
  params enforced (400), disallowed `pe_host` rejected (403), unreachable PE
  handled as 502 with no credential leak, write routes return 404 (structurally absent).
