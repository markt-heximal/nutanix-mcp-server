# Using the Nutanix MCP server

This fork runs the `jkmills/nutanix-mcp-server` against a **Prism Element-only**
lab (no Prism Central deployed), with a governance-minded read-only HTTP façade
layered on for frontends. This guide covers how to actually use it once it's
installed.

- **What it is:** an MCP server that lets an AI client (Claude Code, Claude
  Desktop) query your Nutanix cluster in natural language.
- **Mode:** `NUTANIX_PE_ONLY=true`. Only the 32 `pe_*` Prism Element tools are
  exposed; the Prism Central tools are hidden until a PC is deployed.
- **Read-only in practice:** every tool in PE-only mode is a `pe_get_*` or
  `pe_list_*` query. Nothing mutates cluster state.

---

## Prerequisites

```bash
cd ~/nutanix-mcp-server
pip install -e . --break-system-packages
```

`.env` in the repo root (chmod 600) supplies the connection:

```
NUTANIX_HOST=10.0.1.242        # PE cluster VIP
NUTANIX_USERNAME=admin
NUTANIX_PASSWORD=•••
NUTANIX_VERIFY_SSL=false        # lab only — self-signed PE cert
NUTANIX_PE_ONLY=true
NUTANIX_ALLOWED_PE_HOSTS=10.0.1.242
```

Smoke test (should log `PE-only mode active`, then wait on stdio — Ctrl-C):

```bash
python3 -m nutanix_mcp
```

---

## Two ways to run it

| Transport | Command | Use for |
| --- | --- | --- |
| **stdio** | `python3 -m nutanix_mcp` | Claude Code / Desktop (spawned on demand) |
| **HTTP (MCP)** | `python3 -m nutanix_mcp --http --host 127.0.0.1 --port 8000` | Networked MCP clients over Tailscale (no built-in auth — keep local) |
| **HTTP (façade)** | `pe_facade.py` via uvicorn/systemd | Browser frontends; read-only `pe_list_*` only, X-API-Key gated |

The MCP server (stdio/HTTP) exposes all 32 tools to an AI client. The façade is a
separate, narrower surface (17 `pe_list_*` endpoints) for dashboards — see the
"Façade" section below.

---

## Wiring into Claude Code (stdio)

Register the server once. Use the wrapper (`run-mcp.sh`) rather than calling
`python3 -m nutanix_mcp` directly, so the server always finds `.env` no matter
which directory `claude` was launched from:

```bash
chmod +x ~/nutanix-mcp-server/run-mcp.sh
claude mcp add nutanix -s user -- ~/nutanix-mcp-server/run-mcp.sh
```

- `-s user` makes it available in every Claude Code session for your account on
  this host. Use `-s local` for just the current project, or `-s project` to
  write a shared `.mcp.json` into a repo.

Verify:

```bash
claude mcp list          # nutanix should appear
claude mcp get nutanix   # shows the command it will run
```

Inside a Claude Code session, `/mcp` lists connected servers and their tools —
you should see 32 `pe_*` tools under `nutanix`.

To remove or re-add:

```bash
claude mcp remove nutanix -s user
```

> **SSH note:** if you register from an SSH session and Claude Code shows an
> interactive trust prompt that won't take keystrokes, the non-interactive
> path is to set `hasTrustDialogAccepted` / `customApiKeyResponses.approved`
> in `~/.claude.json` (the same workaround used for Ruflo on this box).

### Claude Desktop

Add to the Desktop config's `mcpServers` block instead:

```json
{
  "mcpServers": {
    "nutanix": {
      "command": "/home/markt/nutanix-mcp-server/run-mcp.sh"
    }
  }
}
```

---

## What you can ask

Once wired, drive it in plain language. Every `pe_*` tool takes a `pe_host`
argument; the model will use your PE VIP (`10.0.1.242`) — state it once if it
asks. Examples:

- "List all VMs on the cluster and which are powered on."
- "Show me storage pools and container usage."
- "Are there any critical alerts right now?"
- "Which VMs are unprotected — not in any protection domain?"
- "Show cluster health and any failing health checks."
- "List the hosts and their CVMs."
- "What's the licensing status of the cluster?"
- "Show me the protection domains and their replication status."

### The 32 PE tools by area

**Cluster & health** — `pe_get_cluster_info`, `pe_get_cluster_health`,
`pe_list_health_checks`
**Compute** — `pe_list_vms`, `pe_list_hosts`, `pe_list_cvms`, `pe_get_host_disks`,
`pe_get_host_nics`
**Storage** — `pe_list_containers`, `pe_list_storage_pools`, `pe_list_disks`,
`pe_list_volume_groups`, `pe_get_volume_group`
**Networking & images** — `pe_list_networks`, `pe_list_images`
**Data protection / DR** — `pe_list_protection_domains`,
`pe_get_protection_domain`, `pe_list_snapshots`, `pe_list_remote_sites`,
`pe_get_replication_status`, `pe_list_unprotected_vms`, `pe_get_metro_witness`,
`pe_list_dr_snapshots`, `pe_list_pd_replications`
**Alerts** — `pe_list_alerts`
**Cluster config (read)** — `pe_get_auth_config`, `pe_get_smtp_config`,
`pe_get_snmp_config`, `pe_get_syslog_config`, `pe_get_alert_email_config`,
`pe_get_nfs_whitelists`, `pe_get_licensing_info`

`pe_list_snapshots` also needs a `protection_domain`; the others need only
`pe_host`.

---

## The read-only façade (for frontends)

`pe_facade.py` exposes only the 17 `pe_list_*` tools as GET endpoints behind an
`X-API-Key`. Use it when a browser app (e.g. Lovable) needs cluster data — never
point a browser at the MCP server directly (it carries credentials and, once PC
is added, write tools).

Runs as the `nutanix-pe-facade` systemd service (see `deploy/README.md`). Call it:

```bash
KEY=$(grep FACADE_API_KEY ~/nutanix-mcp-server/.facade.env | cut -d= -f2)
curl -s -H "X-API-Key: $KEY" http://localhost:9770/pe/tools   # list endpoints
curl -s -H "X-API-Key: $KEY" http://localhost:9770/pe/vms     # live VM data
```

`{resource}` = tool name minus `pe_list_` (`/pe/vms`, `/pe/hosts`, `/pe/disks`,
…). `pe_host` defaults to `NUTANIX_HOST`; override with `?pe_host=` only if it's
in `NUTANIX_ALLOWED_PE_HOSTS`. `/pe/snapshots` needs `?protection_domain=`.

Expose to a frontend over Tailscale (TLS, no open ports):

```bash
tailscale serve --bg --https=443 http://127.0.0.1:9770
```

---

## When Prism Central arrives

Drop `NUTANIX_PE_ONLY` from `.env` and restart. The full Prism Central tool set
(fleet-wide `list_vms`, `list_clusters`, VM lifecycle, etc.) returns, and the
`pe_*` tools keep working for direct single-cluster access. Under a shared PC
across two sites, `list_clusters` → `list_hosts` resolves CVM IPs to use as
`pe_host` for site-specific queries.

---

## Troubleshooting

| Symptom | Cause / fix |
| --- | --- |
| `No credentials configured` at startup | Server didn't find `.env` — launched from the wrong dir. Use `run-mcp.sh` (it cd's to the repo). |
| `Cannot reach Prism Element … timed out` | Network/host. Test: `curl -k https://10.0.1.242:9440` from this box. |
| `authentication failed (HTTP 401)` | Wrong `NUTANIX_USERNAME`/`NUTANIX_PASSWORD` in `.env`. |
| `InsecureRequestWarning` in logs | Expected with `NUTANIX_VERIFY_SSL=false` against the self-signed PE cert. Not an error. |
| Façade 401 | Missing/wrong `X-API-Key` header. |
| Façade 403 on `?pe_host=` | Host not in `NUTANIX_ALLOWED_PE_HOSTS` (accepts comma or JSON-array form). |
| A PC tool errors "requires Prism Central" | Expected in PE-only mode. Deploy PC and unset `NUTANIX_PE_ONLY`. |
