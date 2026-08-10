# Nutanix MCP Server

> [!WARNING]
> **Use at your own risk.** MCP servers grant AI models the ability to execute actions against your infrastructure. AI-driven management of production environments carries inherent risk — models can misinterpret intent, hallucinate parameters, or trigger destructive operations. This software is provided "as is" without warranty of any kind. The authors accept no liability for data loss, downtime, or any damages arising from use of this tool. Always review AI-proposed actions before execution and maintain proper backups.

An MCP (Model Context Protocol) server that exposes Nutanix Prism Central and Prism Element APIs as tools for AI assistants like GitHub Copilot, Claude, and others.

## Features

- **65 tools** — Full coverage of Prism Central v4 and Prism Element v2 APIs
- **Prism Central (v4 API)** — VM lifecycle, snapshots, clusters, hosts, networking, categories, alerts, tasks
- **Prism Element (v2 API)** — Direct cluster access for storage, disks, data protection, system config, health checks
- **Tool annotations** — Every tool carries MCP `readOnlyHint`/`destructiveHint`/`idempotentHint` metadata, so clients can require approval for destructive operations (`delete_vm`, `power_off_vm`, …) and fast-track read-only ones
- **Structured output** — Results are returned as MCP `structuredContent` with a JSON text fallback; failures return proper `isError` results with actionable messages
- **ETag concurrency control** — All v4 mutations send `If-Match` automatically, as required by Nutanix v4 APIs
- **AsBuilt Reports** — Generate comprehensive HTML reports with interactive TOC, Mermaid topology diagrams, and print-to-PDF support
- **API version routing** — Prefers v4, falls back to v3/v2 when needed
- **Async** — Non-blocking HTTP client using httpx; official Nutanix SDK calls run off the event loop

## Available Tools (65)

### VM Management — Prism Central v4
| Tool | Description |
|------|-------------|
| `list_vms` | List all VMs with OData filtering (auto-paginates) |
| `get_vm` | Get full VM config — CPU, memory, disks, NICs |
| `power_on_vm` | Power on a VM |
| `power_off_vm` | Power off a VM (ACPI guest shutdown or force) |
| `create_vm` | Create a new VM with name, cluster, CPU, memory, disk |
| `update_vm` | Update VM config — CPU, memory, name, description |
| `delete_vm` | Permanently delete a VM (requires confirmation) |
| `clone_vm` | Clone a VM with a new name |

### VM Snapshots — Prism Central v4
| Tool | Description |
|------|-------------|
| `snapshot_vm` | Create an on-demand recovery point of a VM |
| `list_vm_snapshots` | List all recovery points for a VM |
| `restore_vm_snapshot` | Restore a VM to a previous recovery point |

### Cluster & Host Management — Prism Central v4
| Tool | Description |
|------|-------------|
| `list_clusters` | List all registered Nutanix clusters |
| `get_cluster` | Get cluster config, network, storage, and health details |
| `list_hosts` | List all hypervisor hosts across clusters |
| `get_host` | Get host hardware specs, hypervisor info, and resource usage |
| `list_storage_containers` | List storage containers across clusters |

### Networking & Images — Prism Central v4
| Tool | Description |
|------|-------------|
| `list_subnets` | List subnets/VLANs with CIDR, VLAN ID, and cluster |
| `get_subnet` | Get subnet details including IP pools and DHCP config |
| `list_images` | List disk images (ISOs, QCOW2) in the image library |
| `get_image` | Get image details — size, type, source, cluster placement |
| `list_categories` | List all category keys and values |
| `get_category` | Get all values for a specific category key |

### Categories & Tagging — Prism Central v4
| Tool | Description |
|------|-------------|
| `assign_category` | Tag a VM with a category key:value pair |
| `remove_category` | Remove a category assignment from a VM |
| `list_entities_by_category` | Find all VMs tagged with a specific category |

### Alerts & Tasks — Prism Central v4
| Tool | Description |
|------|-------------|
| `list_alerts` | List all alerts from Prism Central |
| `get_alert` | Get full alert details — entities, resolution guidance |
| `acknowledge_alert` | Acknowledge or resolve an alert |
| `list_tasks` | List recent async tasks with status |
| `get_task` | Get task completion status and error details |

### Prism Element — Cluster & Hosts (v2 direct access)
| Tool | Description |
|------|-------------|
| `pe_get_cluster_info` | Cluster AOS version, capacity, and health |
| `pe_list_hosts` | Hosts with hardware specs and CVM info |
| `pe_get_host_disks` | Per-host physical disk inventory (model, serial, firmware, tier) |
| `pe_get_host_nics` | Per-host NIC details — speed, link state, MAC, LLDP |
| `pe_list_cvms` | Controller VMs — IP, memory, power state |
| `pe_get_cluster_health` | Data resiliency and fault tolerance status |
| `pe_list_health_checks` | NCC-style health check results |
| `pe_list_alerts` | Active/resolved alerts on a PE cluster |

### Prism Element — Storage
| Tool | Description |
|------|-------------|
| `pe_list_containers` | Storage containers with replication factor and policies |
| `pe_list_storage_pools` | Storage pools and disk composition |
| `pe_list_disks` | Physical disk inventory — type, status, capacity |
| `pe_list_volume_groups` | Volume groups — iSCSI IQN, attached VMs, CHAP |
| `pe_get_volume_group` | Detailed volume group config |

### Prism Element — VMs, Networks & Images
| Tool | Description |
|------|-------------|
| `pe_list_vms` | VMs on a specific cluster |
| `pe_list_networks` | VLANs — managed/unmanaged, IP pool config |
| `pe_list_images` | Disk images and ISOs on a cluster |

### Prism Element — Data Protection
| Tool | Description |
|------|-------------|
| `pe_list_protection_domains` | Protection domains — schedules, replication state |
| `pe_get_protection_domain` | Detailed PD config — consistency groups, VMs, schedules |
| `pe_list_snapshots` | Snapshots for a protection domain |
| `pe_list_remote_sites` | DR partner clusters — addresses, capabilities |
| `pe_get_replication_status` | Active replication progress, lag, and bandwidth |
| `pe_list_dr_snapshots` | DR snapshots across remote sites |
| `pe_list_pd_replications` | All active PD replications cluster-wide |
| `pe_list_unprotected_vms` | VMs not in any protection domain (compliance gaps) |

### Prism Element — System Configuration
| Tool | Description |
|------|-------------|
| `pe_get_auth_config` | Auth types, directory services (LDAP/AD) |
| `pe_get_smtp_config` | SMTP relay server configuration |
| `pe_get_snmp_config` | SNMP traps, users, and community strings |
| `pe_get_syslog_config` | Remote syslog targets and severity levels |
| `pe_get_alert_email_config` | Alert email recipients and notification rules |
| `pe_get_nfs_whitelists` | Global NFS export ACLs |
| `pe_get_licensing_info` | License type (Starter/Pro/Ultimate) and features |
| `pe_get_metro_witness` | Metro Availability witness server config |

### AsBuilt Reports
| Tool | Description |
|------|-------------|
| `generate_asbuilt` | Generate a comprehensive infrastructure report from a PE cluster — overview, system config, hosts, storage, VMs, networks, data protection, alerts, health checks, and Mermaid topology diagram |
| `export_asbuilt_html` | Convert AsBuilt Markdown to self-contained HTML with interactive TOC sidebar and print-optimized CSS for PDF export |
| `get_project_architecture` | Get the Nutanix MCP Server project architecture documentation |

AsBuilt reports include 9 sections: overview, system, hosts (with per-host disk inventory), VMs, networks, storage, data protection (with remote sites and unprotected VM detection), alerts, and health checks. Hypervisor names are mapped automatically (kKvm → AHV). The HTML export features an interactive table of contents with scroll-spy that is hidden when printing to PDF.

### MCP Resources (URI-based browsing)

The server exposes resources via `nutanix://` URIs, allowing LLMs to browse
entities without explicit tool calls:

| URI Pattern | Description |
|-------------|-------------|
| `nutanix://vms` | Browse all VMs |
| `nutanix://vms/{uuid}` | Get a specific VM |
| `nutanix://clusters` | Browse all clusters |
| `nutanix://clusters/{uuid}` | Get a specific cluster |
| `nutanix://hosts/{uuid}` | Get a specific host |
| `nutanix://subnets/{uuid}` | Get a specific subnet |
| `nutanix://images/{uuid}` | Get a specific image |

### MCP Prompts

| Prompt | Description |
|--------|-------------|
| `set_credentials` | Interactive credential configuration (for clients without env var support) |
| `nutanix_overview` | Guided environment overview — clusters, hosts, storage, alerts |

## Web UI & HTTP backends

Two optional HTTP layers let a browser frontend (e.g. a Lovable app) use this
server without holding Nutanix credentials or speaking MCP:

| Layer | File | Surface | Auth | Use it for |
|-------|------|---------|------|-----------|
| Read-only façade | `pe_facade.py` | `pe_list_*` GETs only | shared `X-API-Key` | monitoring dashboards |
| Management API | `management_api.py` | **full** tool surface (read + write) | username/password → **JWT**, RBAC (viewer/operator/admin) | a management console that can create/power/delete VMs |

The management API bridges the same handler registry the MCP server uses, so it
never drifts out of sync. Destructive tools require an explicit `confirm`, and
role is derived from each tool's MCP annotations.

- Build the UI in Lovable: **`ui/`** (`LOVABLE_BUILD_SPEC.md`, `API_REFERENCE.md`,
  `tool-catalog.json`, a TypeScript client in `ui/src/lib/`).
- Deploy the backend on a mini/host: **`docs/MANAGEMENT_DEPLOY.md`** (Docker or
  native macOS/launchd, TLS via Caddy).

```bash
pip install -e '.[api]'
export MGMT_JWT_SECRET="$(openssl rand -hex 32)"
export MGMT_CORS_ORIGINS="https://your-app.lovable.app"
export MGMT_USERS_FILE=./users.json     # python scripts/mgmt_user.py alice admin
uvicorn management_api:app --host 127.0.0.1 --port 9780
```

## Setup

### Prerequisites
- Python 3.10+
- Network access to your Prism Central instance (port 9440)
- Nutanix credentials with API access

### Install

```bash
cd mcp/nutanix-mcp-server
pip install -e .
```

Or with dev dependencies:
```bash
pip install -e ".[dev]"
```

### Configure

Copy `.env.example` to `.env` and fill in your credentials:

```bash
cp .env.example .env
```

```env
NUTANIX_HOST=your-prism-central.example.com
NUTANIX_PORT=9440
NUTANIX_USERNAME=your-username
NUTANIX_PASSWORD=your-password
NUTANIX_VERIFY_SSL=true
NUTANIX_TIMEOUT=30

# Optional: restrict which Prism Element hosts may receive credentials
# NUTANIX_ALLOWED_PE_HOSTS=10.0.0.1,10.0.0.2

# Optional: stderr diagnostic verbosity (DEBUG, INFO, WARNING, ERROR)
# NUTANIX_LOG_LEVEL=INFO
```

### Run

```bash
nutanix-mcp
```

Or directly:
```bash
python -m nutanix_mcp
```

## MCP Client Configuration

This server uses **stdio transport** — it communicates via stdin/stdout. Each client
configures a command to launch the server process.

> **Tip:** Store credentials in environment variables or a `.env` file, never in config files committed to source control.

---

### Claude Code (CLI)

Add the server to your project with the `claude mcp add` command:

```bash
claude mcp add nutanix -- python -m nutanix_mcp
```

Or manually create/edit `.mcp.json` in your project root:

```json
{
  "mcpServers": {
    "nutanix": {
      "type": "stdio",
      "command": "python",
      "args": ["-m", "nutanix_mcp"],
      "cwd": "/path/to/mcp/nutanix-mcp-server",
      "env": {
        "NUTANIX_HOST": "your-prism-central.example.com",
        "NUTANIX_USERNAME": "your-username",
        "NUTANIX_PASSWORD": "your-password",
        "NUTANIX_VERIFY_SSL": "true"
      }
    }
  }
}
```

For user-wide availability (all projects), add to `~/.claude.json` instead.

---

### Claude Desktop

Edit the config file at:
- **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`
- **Linux:** `~/.config/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "nutanix": {
      "type": "stdio",
      "command": "python",
      "args": ["-m", "nutanix_mcp"],
      "cwd": "/path/to/mcp/nutanix-mcp-server",
      "env": {
        "NUTANIX_HOST": "your-prism-central.example.com",
        "NUTANIX_USERNAME": "your-username",
        "NUTANIX_PASSWORD": "your-password",
        "NUTANIX_VERIFY_SSL": "true"
      }
    }
  }
}
```

Restart Claude Desktop fully after editing.

---

### GitHub Copilot (VS Code)

Add to `.vscode/mcp.json` in your workspace:

```json
{
  "servers": {
    "nutanix": {
      "type": "stdio",
      "command": "python",
      "args": ["-m", "nutanix_mcp"],
      "cwd": "${workspaceFolder}/mcp/nutanix-mcp-server",
      "env": {
        "NUTANIX_HOST": "your-prism-central.example.com",
        "NUTANIX_USERNAME": "your-username",
        "NUTANIX_PASSWORD": "your-password",
        "NUTANIX_VERIFY_SSL": "true"
      }
    }
  }
}
```

---

### OpenCode (sst/opencode)

Add to `opencode.json` (or `opencode.jsonc`) in your project root:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "nutanix": {
      "type": "local",
      "command": ["python", "-m", "nutanix_mcp"],
      "environment": {
        "NUTANIX_HOST": "your-prism-central.example.com",
        "NUTANIX_USERNAME": "your-username",
        "NUTANIX_PASSWORD": "your-password",
        "NUTANIX_VERIFY_SSL": "true"
      },
      "enabled": true
    }
  }
}
```

Note: OpenCode uses `"command"` as an array and `"environment"` instead of `"env"`.

---

### Docker MCP Gateway

The [Docker MCP Gateway](https://docs.docker.com/ai/mcp-catalog-and-toolkit/mcp-gateway/)
can proxy this server inside a container. Two approaches:

#### Option A: Run directly via Docker

Build a container image and reference it in your MCP client config:

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY mcp/nutanix-mcp-server/ .
RUN pip install --no-cache-dir -e .
CMD ["python", "-m", "nutanix_mcp"]
```

Then in any MCP client config:

```json
{
  "mcpServers": {
    "nutanix": {
      "type": "stdio",
      "command": "docker",
      "args": [
        "run", "-i", "--rm",
        "-e", "NUTANIX_HOST=your-prism-central.example.com",
        "-e", "NUTANIX_USERNAME=your-username",
        "-e", "NUTANIX_PASSWORD=your-password",
        "-e", "NUTANIX_VERIFY_SSL=true",
        "nutanix-mcp-server"
      ]
    }
  }
}
```

#### Option B: Register with Docker MCP Gateway

If you have Docker Desktop with the MCP Toolkit:

```bash
docker mcp gateway run
```

Configure the gateway profile to include the nutanix server. The gateway then
exposes all registered MCP servers as a single unified endpoint.

In your AI client, point to the gateway:

```json
{
  "mcpServers": {
    "MCP_DOCKER": {
      "command": "docker",
      "args": ["mcp", "gateway", "run"]
    }
  }
}
```

The gateway handles routing, lifecycle management, and credential isolation.

## API Version Strategy

| Version | Endpoint Pattern | Use Case |
|---------|-----------------|----------|
| v4 (preferred) | `/api/{namespace}/v4.0/{path}` | VMs, clusters, hosts, networking |
| v3 (fallback) | `/api/nutanix/v3/{resource}/list` | Resources not yet in v4 |
| v2 (PE direct) | `https://{pe_ip}:9440/api/nutanix/v2.0/{resource}` | Per-cluster storage, disks, alerts |

## Discovering Prism Element Hosts

Use `list_clusters` to find cluster UUIDs, then `list_hosts` to find CVM IPs.
Those CVM IPs can be used as `pe_host` in the Prism Element tools.

## Development

```bash
# Lint
ruff check src/

# Type check
mypy src/

# Test
pytest
```

## References

- [Nutanix v4 API Documentation](https://developers.nutanix.com)
- [Nutanix Developer Portal](https://www.nutanix.dev)
- [Prism Central v3 API](https://www.nutanix.dev/api_reference/apis/prism_v3.html)
- [Prism Element v2 API](https://www.nutanix.dev/api_reference/apis/prism_v2.html)
- [MCP Protocol Specification](https://modelcontextprotocol.io)
