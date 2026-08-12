"""Cluster management tools using Nutanix v4 clustermgmt namespace."""

from typing import Any

from nutanix_mcp.client import NutanixClient

# ─── Tool Definitions ─────────────────────────────────────────────────────────

CLUSTER_TOOLS: list[dict] = [
    {
        "name": "list_clusters",
        "description": (
            "List ALL Nutanix clusters registered with Prism Central (auto-paginates internally). "
            "Returns complete results in one call — no manual pagination needed."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "filter": {
                    "type": "string",
                    "description": "OData filter expression. Example: \"name eq 'prod-cluster'\"",
                },
            },
        },
    },
    {
        "name": "get_cluster",
        "description": (
            "Get detailed information about a specific cluster by UUID. "
            "Returns configuration, network, storage, and health details."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "cluster_uuid": {
                    "type": "string",
                    "description": "The UUID (extId) of the cluster",
                },
            },
            "required": ["cluster_uuid"],
        },
    },
    {
        "name": "list_hosts",
        "description": (
            "List ALL hypervisor hosts (auto-paginates internally). "
            "Returns complete results in one call — no manual pagination needed. "
            "Optionally filter by cluster UUID."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "cluster_uuid": {
                    "type": "string",
                    "description": "Filter hosts to a specific cluster UUID",
                },
                "filter": {
                    "type": "string",
                    "description": "OData filter expression",
                },
                "limit": {
                    "type": "integer",
                    "description": "Optional cap on results. Omit to get ALL hosts (default behavior).",
                },
            },
        },
    },
    {
        "name": "get_host",
        "description": (
            "Get detailed information about a specific host by UUID. "
            "Returns hardware specs, hypervisor info, and resource usage."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "host_uuid": {
                    "type": "string",
                    "description": "The UUID (extId) of the host",
                },
            },
            "required": ["host_uuid"],
        },
    },
    {
        "name": "list_storage_containers",
        "description": (
            "List ALL storage containers (auto-paginates internally). "
            "Returns complete results in one call — no manual pagination needed."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "cluster_uuid": {
                    "type": "string",
                    "description": "Filter to a specific cluster UUID",
                },
                "limit": {
                    "type": "integer",
                    "description": "Optional cap on results. Omit to get ALL containers (default behavior).",
                },
            },
        },
    },
]


# ─── Tool Handlers ────────────────────────────────────────────────────────────


async def handle_list_clusters(client: NutanixClient, arguments: dict[str, Any]) -> dict[str, Any]:
    """List clusters using official Nutanix SDK."""
    filter_expr = arguments.get("filter")
    sdk = client.sdk

    kwargs: dict[str, Any] = {}
    if filter_expr:
        kwargs["_filter"] = filter_expr

    clusters = await sdk.list_all(sdk.cluster_api.list_clusters, **kwargs)

    return {
        "totalReturned": len(clusters),
        "note": "All matching clusters returned. No further pagination needed.",
        "clusters": [
            {
                "name": c.name,
                "extId": c.ext_id,
                "clusterFunction": c.config.cluster_function if c.config else None,
                "hypervisorTypes": c.config.hypervisor_types if c.config else None,
                "operationMode": c.config.operation_mode if c.config else None,
                "redundancyFactor": c.config.redundancy_factor if c.config else None,
            }
            for c in clusters
        ],
    }


async def handle_get_cluster(client: NutanixClient, arguments: dict[str, Any]) -> dict[str, Any]:
    """Get cluster details using official Nutanix SDK."""
    cluster_uuid = arguments["cluster_uuid"]
    sdk = client.sdk
    response = await sdk.call(sdk.cluster_api.get_cluster_by_id, cluster_uuid)
    cluster = response.data
    return cluster.to_dict() if cluster else {}


async def handle_list_hosts(client: NutanixClient, arguments: dict[str, Any]) -> dict[str, Any]:
    """List hosts using official Nutanix SDK."""
    cluster_uuid = arguments.get("cluster_uuid")
    filter_expr = arguments.get("filter")
    limit = arguments.get("limit")
    sdk = client.sdk

    kwargs: dict[str, Any] = {}
    if filter_expr:
        kwargs["_filter"] = filter_expr

    if cluster_uuid:
        # Use cluster-scoped list
        if limit:
            response = await sdk.call(
                sdk.cluster_api.list_hosts_by_cluster_id, cluster_uuid, _limit=limit, **kwargs
            )
            hosts = response.data or []
        else:
            hosts = await sdk.list_all(sdk.cluster_api.list_hosts_by_cluster_id, cluster_uuid, **kwargs)
    else:
        # Use global hosts list
        if limit:
            response = await sdk.call(sdk.cluster_api.list_hosts, _limit=limit, **kwargs)
            hosts = response.data or []
        else:
            hosts = await sdk.list_all(sdk.cluster_api.list_hosts, **kwargs)

    def _extract_host(h: Any) -> dict:
        hypervisor = h.hypervisor
        ip_address = None
        if hypervisor and hypervisor.external_address:
            addr = hypervisor.external_address
            if hasattr(addr, "ipv4") and addr.ipv4:
                ip_address = addr.ipv4.value
        cluster_ref = h.cluster
        return {
            "name": h.host_name,
            "extId": h.ext_id,
            "hypervisorType": hypervisor.type if hypervisor else None,
            "ipAddress": ip_address,
            "cpuModel": h.cpu_model,
            "numCpuSockets": h.number_of_cpu_sockets,
            "numCpuCores": h.number_of_cpu_cores,
            "memorySizeBytes": h.memory_size_bytes,
            "cluster": cluster_ref.uuid if cluster_ref else None,
            "clusterName": cluster_ref.name if cluster_ref else None,
        }

    return {
        "totalReturned": len(hosts),
        "note": "All matching hosts returned. No further pagination needed.",
        "hosts": [_extract_host(h) for h in hosts],
    }


async def handle_get_host(client: NutanixClient, arguments: dict[str, Any]) -> dict[str, Any]:
    """Get host details. Uses httpx fallback since SDK requires clusterExtId."""
    host_uuid = arguments["host_uuid"]
    # SDK's get_host_by_id requires clusterExtId — use httpx for direct access
    result = await client.v4_get(
        namespace="clustermgmt",
        path=f"config/hosts/{host_uuid}",
    )
    return result.get("data", result)


async def handle_list_storage_containers(client: NutanixClient, arguments: dict[str, Any]) -> dict[str, Any]:
    """List storage containers using official Nutanix SDK."""
    cluster_uuid = arguments.get("cluster_uuid")
    limit = arguments.get("limit")
    sdk = client.sdk

    kwargs: dict[str, Any] = {}
    if cluster_uuid:
        kwargs["_filter"] = f"clusterExtId eq '{cluster_uuid}'"

    if limit:
        response = await sdk.call(sdk.storage_container_api.list_storage_containers, _limit=limit, **kwargs)
        containers = response.data or []
    else:
        containers = await sdk.list_all(sdk.storage_container_api.list_storage_containers, **kwargs)

    return {
        "totalReturned": len(containers),
        "note": "All matching storage containers returned. No further pagination needed.",
        "storageContainers": [
            {
                "name": sc.name,
                "extId": sc.container_ext_id if hasattr(sc, "container_ext_id") else sc.ext_id,
                "maxCapacityBytes": sc.max_capacity_bytes if hasattr(sc, "max_capacity_bytes") else None,
                "replicationFactor": sc.replication_factor if hasattr(sc, "replication_factor") else None,
                "compressionEnabled": sc.is_compression_enabled if hasattr(sc, "is_compression_enabled") else None,
                "encrypted": sc.is_encrypted if hasattr(sc, "is_encrypted") else None,
                "clusterExtId": sc.cluster_ext_id if hasattr(sc, "cluster_ext_id") else None,
                "clusterName": sc.cluster_name if hasattr(sc, "cluster_name") else None,
            }
            for sc in containers
        ],
    }


# ─── Handler Dispatch ─────────────────────────────────────────────────────────

CLUSTER_HANDLERS: dict[str, Any] = {
    "list_clusters": handle_list_clusters,
    "get_cluster": handle_get_cluster,
    "list_hosts": handle_list_hosts,
    "get_host": handle_get_host,
    "list_storage_containers": handle_list_storage_containers,
}
