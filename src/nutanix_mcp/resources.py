"""MCP Resource Templates for browseable URI-based access to Nutanix entities."""

import json
from typing import Any

from mcp.server.lowlevel.helper_types import ReadResourceContents
from mcp.types import Resource, ResourceTemplate

from nutanix_mcp.client import NutanixClient

# ─── Resource Template Definitions ────────────────────────────────────────────

RESOURCE_TEMPLATES: list[ResourceTemplate] = [
    ResourceTemplate(
        uriTemplate="nutanix://vms/{vm_uuid}",
        name="Virtual Machine",
        description="Access a Nutanix VM by UUID. Returns full configuration.",
        mimeType="application/json",
    ),
    ResourceTemplate(
        uriTemplate="nutanix://clusters/{cluster_uuid}",
        name="Cluster",
        description="Access a Nutanix cluster by UUID. Returns cluster details.",
        mimeType="application/json",
    ),
    ResourceTemplate(
        uriTemplate="nutanix://hosts/{host_uuid}",
        name="Host",
        description="Access a hypervisor host by UUID. Returns hardware and config.",
        mimeType="application/json",
    ),
    ResourceTemplate(
        uriTemplate="nutanix://subnets/{subnet_uuid}",
        name="Subnet",
        description="Access a subnet by UUID. Returns VLAN, CIDR, and DHCP config.",
        mimeType="application/json",
    ),
    ResourceTemplate(
        uriTemplate="nutanix://images/{image_uuid}",
        name="Image",
        description="Access a disk image by UUID. Returns image metadata.",
        mimeType="application/json",
    ),
]

# ─── Static Resource Listings ─────────────────────────────────────────────────

STATIC_RESOURCES: list[Resource] = [
    Resource(
        uri="nutanix://asbuilt/project",
        name="Project Architecture",
        description="Nutanix MCP Server architecture documentation — components, API layers, tool inventory, and deployment topology",
        mimeType="text/markdown",
    ),
    Resource(
        uri="nutanix://vms",
        name="All Virtual Machines",
        description="List all VMs registered with Prism Central",
        mimeType="application/json",
    ),
    Resource(
        uri="nutanix://clusters",
        name="All Clusters",
        description="List all clusters registered with Prism Central",
        mimeType="application/json",
    ),
    Resource(
        uri="nutanix://hosts",
        name="All Hosts",
        description="List all hypervisor hosts",
        mimeType="application/json",
    ),
    Resource(
        uri="nutanix://subnets",
        name="All Subnets",
        description="List all subnets/networks",
        mimeType="application/json",
    ),
    Resource(
        uri="nutanix://images",
        name="All Images",
        description="List all disk images (ISO, QCOW2)",
        mimeType="application/json",
    ),
]


# ─── Resource Handlers ────────────────────────────────────────────────────────


async def resolve_resource(client: NutanixClient, uri: str) -> list[ReadResourceContents]:
    """Resolve a nutanix:// URI to resource contents."""
    parts = uri.replace("nutanix://", "").strip("/").split("/")
    resource_type = parts[0] if parts else ""
    resource_id = parts[1] if len(parts) > 1 else None

    # Static text resources
    if resource_type == "asbuilt" and resource_id == "project":
        return [
            ReadResourceContents(
                content=_project_architecture_doc(),
                mime_type="text/markdown",
            )
        ]

    sdk = client.sdk
    data: Any

    if resource_type == "vms":
        if resource_id:
            response = await sdk.call(sdk.vm_api.get_vm_by_id, resource_id)
            data = response.data.to_dict() if response.data else {}
        else:
            vms = await sdk.list_all(sdk.vm_api.list_vms)
            data = [vm.to_dict() for vm in vms]
    elif resource_type == "clusters":
        if resource_id:
            response = await sdk.call(sdk.cluster_api.get_cluster_by_id, resource_id)
            data = response.data.to_dict() if response.data else {}
        else:
            clusters = await sdk.list_all(sdk.cluster_api.list_clusters)
            data = [c.to_dict() for c in clusters]
    elif resource_type == "hosts":
        if resource_id:
            # SDK requires clusterExtId for get_host_by_id; use httpx fallback
            result = await client.v4_get(namespace="clustermgmt", path=f"config/hosts/{resource_id}")
            data = result.get("data", result)
        else:
            hosts = await sdk.list_all(sdk.cluster_api.list_hosts)
            data = [h.to_dict() for h in hosts]
    elif resource_type == "subnets":
        if resource_id:
            response = await sdk.call(sdk.subnet_api.get_subnet_by_id, resource_id)
            data = response.data.to_dict() if response.data else {}
        else:
            subnets = await sdk.list_all(sdk.subnet_api.list_subnets)
            data = [s.to_dict() for s in subnets]
    elif resource_type == "images":
        if resource_id:
            response = await sdk.call(sdk.image_api.get_image_by_id, resource_id)
            data = response.data.to_dict() if response.data else {}
        else:
            images = await sdk.list_all(sdk.image_api.list_images)
            data = [img.to_dict() for img in images]
    else:
        data = {"error": f"Unknown resource type: {resource_type}"}

    return [
        ReadResourceContents(
            content=json.dumps(data, indent=2, default=str),
            mime_type="application/json",
        )
    ]


def _project_architecture_doc() -> str:
    """Return the project architecture documentation as Markdown."""
    from nutanix_mcp.tools import get_all_tools

    tools = get_all_tools()
    tool_list = "\n".join(f"| `{t['name']}` | {t['description'][:80]} |" for t in tools)

    return f"""\
# Nutanix MCP Server — Architecture

## Overview

The Nutanix MCP Server exposes Nutanix Prism Central (v4 API) and Prism Element
(v2 API) as MCP tools for AI assistants. It runs as a stdio-based MCP server
inside a Docker container, managed by the Docker MCP Toolkit.

## Component Architecture

```mermaid
graph TD
    AI["AI Assistant<br/>(Claude, GPT, etc.)"]
    MCP["MCP Protocol<br/>(stdio / HTTP)"]
    SERVER["nutanix_mcp.server<br/>MCP Server"]
    TOOLS["Tool Registry<br/>{len(tools)} tools"]
    SDK["NutanixSDKClient<br/>v4 SDK wrapper"]
    HTTPX["NutanixClient<br/>httpx async HTTP"]
    PC["Prism Central<br/>v4 API"]
    PE["Prism Element<br/>v2 API"]

    AI -->|JSON-RPC| MCP
    MCP --> SERVER
    SERVER --> TOOLS
    TOOLS --> SDK
    TOOLS --> HTTPX
    SDK -->|v4.0/v4.1| PC
    HTTPX -->|v2.0| PE
```

## API Layers

| Layer | Protocol | Auth | Use Case |
|-------|----------|------|----------|
| **Prism Central v4** | SDK (ntnx-*-py-client 4.1.x) | Basic Auth | VMs, clusters, hosts, subnets, images, tasks, categories, alerts, snapshots |
| **Prism Central v3** | httpx POST | Basic Auth | Fallback for resources not in v4 |
| **Prism Element v2** | httpx GET | Basic Auth | Direct cluster access: containers, disks, PDs, health, config |
| **Prism Element v1** | httpx GET | Basic Auth | Auth config, licensing |

## Tool Inventory ({len(tools)} tools)

| Tool | Description |
|------|-------------|
{tool_list}

## Key Design Decisions

- **SDK version pinning**: SDKs pinned to `>=4.0.0,<4.2` because SDK 4.2+ uses
  API paths (`/v4.2/`) not supported by current Prism Central versions
- **Client-side VM filtering**: OData filter on cluster UUID returns HTTP 500 on
  v4.1 VM API, so `list_vms` resolves cluster name → UUID then filters client-side
- **Async wrapping**: SDK calls are synchronous; wrapped in `asyncio.to_thread()`
  to avoid blocking the MCP event loop
- **PE host allowlist**: when `NUTANIX_ALLOWED_PE_HOSTS` is set, credentials are
  only sent to hosts in it or in `NUTANIX_PE_CREDENTIALS`, preventing SSRF. When
  it is empty, any PE host is accepted and network controls are the only guard

## Deployment

```
Docker MCP Toolkit
  └── ghcr.io/jkmills/nutanix-mcp-server:latest
       ├── Python 3.14 + uv
       ├── nutanix-mcp (stdio entrypoint)
       └── Environment: NUTANIX_HOST, NUTANIX_USERNAME, NUTANIX_PASSWORD, etc.

Catalog: ghcr.io/jkmills/nutanix-mcp-catalog:latest
```

## File Structure

```
src/nutanix_mcp/
├── __init__.py          # Package entry point
├── __main__.py          # CLI runner
├── server.py            # MCP Server setup, handler dispatch
├── client.py            # Async HTTP client (PC v4/v3, PE v2/v1)
├── sdk_client.py        # Nutanix v4 SDK wrapper (lazy init, pagination)
├── config.py            # Settings (Pydantic, env vars)
├── resources.py         # MCP resource templates
├── prompts.py           # MCP prompt templates
└── tools/
    ├── __init__.py      # Tool registry (get_all_tools)
    ├── vm.py            # VM lifecycle (8 tools)
    ├── cluster.py       # Clusters & hosts (5 tools)
    ├── networking.py    # Subnets, images, categories (6 tools)
    ├── prism_element.py # PE direct access (32 tools)
    ├── task.py          # Task tracking (2 tools)
    ├── alert.py         # Alert management (3 tools)
    ├── category.py      # Category tagging (3 tools)
    ├── snapshot.py      # VM snapshots (3 tools)
    └── asbuilt.py       # AsBuilt reports (2 tools)
```
"""
