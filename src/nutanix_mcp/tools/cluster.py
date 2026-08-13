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
    {
        "name": "create_storage_container",
        "description": (
            "Create a storage container on a cluster. Containers thin-provision against "
            "the cluster's storage pool, so capacity settings are optional. Optionally "
            "set replication factor, an advertised (logical) capacity cap, an explicit "
            "reservation, and inline compression. Returns a task UUID."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Storage container name."},
                "cluster_uuid": {
                    "type": "string",
                    "description": "UUID (extId) of the cluster to create the container on.",
                },
                "replication_factor": {
                    "type": "integer",
                    "description": "Replication factor (1, 2, or 3). Must not exceed the cluster's RF. Default: cluster default.",
                },
                "advertised_capacity_gb": {
                    "type": "integer",
                    "description": "Optional advertised (logical) capacity cap, in GiB.",
                },
                "reserved_capacity_gb": {
                    "type": "integer",
                    "description": "Optional explicit reserved (guaranteed) capacity, in GiB.",
                },
                "compression_enabled": {
                    "type": "boolean",
                    "description": "Enable inline compression. Default: cluster default.",
                },
            },
            "required": ["name", "cluster_uuid"],
        },
    },
    {
        "name": "resize_storage_container",
        "description": (
            "Resize or reconfigure a storage container: change its advertised (logical) "
            "capacity cap, explicit reservation, name, or compression setting. Uses "
            "ETag-based concurrency control. Returns a task UUID."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "container_uuid": {
                    "type": "string",
                    "description": "The UUID (extId) of the storage container.",
                },
                "advertised_capacity_gb": {
                    "type": "integer",
                    "description": "New advertised (logical) capacity cap, in GiB.",
                },
                "reserved_capacity_gb": {
                    "type": "integer",
                    "description": "New explicit reserved (guaranteed) capacity, in GiB.",
                },
                "name": {"type": "string", "description": "New container name."},
                "compression_enabled": {
                    "type": "boolean",
                    "description": "Enable or disable inline compression.",
                },
            },
            "required": ["container_uuid"],
        },
    },
    {
        "name": "delete_storage_container",
        "description": (
            "Delete a storage container by UUID. Requires confirm=true to proceed. Uses "
            "ETag-based concurrency control. Returns a task UUID. Fails if the container "
            "still holds vdisks/VMs unless ignore_small_files is set."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "container_uuid": {
                    "type": "string",
                    "description": "The UUID (extId) of the storage container to delete.",
                },
                "confirm": {
                    "type": "boolean",
                    "description": "Must be true to proceed with deletion.",
                },
                "ignore_small_files": {
                    "type": "boolean",
                    "description": "Allow deletion even if the container holds small files. Default: false.",
                },
            },
            "required": ["container_uuid"],
        },
    },
]

# 1 GiB in bytes — capacity args are expressed in GiB for convenience.
_GIB = 1024**3


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


async def handle_create_storage_container(client: NutanixClient, arguments: dict[str, Any]) -> dict[str, Any]:
    """Create a storage container using the official Nutanix SDK."""
    import ntnx_clustermgmt_py_client.models.clustermgmt.v4.config.StorageContainer as SCModule

    cluster_uuid = arguments["cluster_uuid"]
    sc = SCModule.StorageContainer()
    sc.name = arguments["name"]
    sc.cluster_ext_id = cluster_uuid
    if "replication_factor" in arguments:
        sc.replication_factor = arguments["replication_factor"]
    if "advertised_capacity_gb" in arguments:
        sc.logical_advertised_capacity_bytes = int(arguments["advertised_capacity_gb"]) * _GIB
    if "reserved_capacity_gb" in arguments:
        sc.logical_explicit_reserved_capacity_bytes = int(arguments["reserved_capacity_gb"]) * _GIB
    if "compression_enabled" in arguments:
        sc.is_compression_enabled = arguments["compression_enabled"]

    sdk = client.sdk
    # create_storage_container requires the target cluster in an X-Cluster-Id header.
    response = await sdk.call(
        sdk.storage_container_api.create_storage_container, sc, X_Cluster_Id=cluster_uuid
    )
    task_id = response.data.ext_id if response.data else None
    return {"status": "storage_container_creation_initiated", "taskExtId": task_id}


async def handle_resize_storage_container(client: NutanixClient, arguments: dict[str, Any]) -> dict[str, Any]:
    """Resize/reconfigure a storage container with ETag concurrency control."""
    container_uuid = arguments["container_uuid"]
    sdk = client.sdk

    get_response = await sdk.call(sdk.storage_container_api.get_storage_container_by_id, container_uuid)
    etag = sdk.get_etag(get_response)
    sc = get_response.data

    if "name" in arguments:
        sc.name = arguments["name"]
    if "advertised_capacity_gb" in arguments:
        sc.logical_advertised_capacity_bytes = int(arguments["advertised_capacity_gb"]) * _GIB
    if "reserved_capacity_gb" in arguments:
        sc.logical_explicit_reserved_capacity_bytes = int(arguments["reserved_capacity_gb"]) * _GIB
    if "compression_enabled" in arguments:
        sc.is_compression_enabled = arguments["compression_enabled"]

    response = await sdk.call(
        sdk.storage_container_api.update_storage_container_by_id, container_uuid, sc, if_match=etag
    )
    task_id = response.data.ext_id if response.data else None
    return {"status": "storage_container_update_initiated", "taskExtId": task_id}


async def handle_delete_storage_container(client: NutanixClient, arguments: dict[str, Any]) -> dict[str, Any]:
    """Delete a storage container using the official Nutanix SDK (confirm-guarded)."""
    container_uuid = arguments["container_uuid"]
    if not arguments.get("confirm", False):
        return {
            "status": "error",
            "message": "Deletion not confirmed. Set 'confirm: true' to proceed with container deletion.",
        }

    sdk = client.sdk
    get_response = await sdk.call(sdk.storage_container_api.get_storage_container_by_id, container_uuid)
    etag = sdk.get_etag(get_response)

    kwargs: dict[str, Any] = {"if_match": etag}
    if arguments.get("ignore_small_files"):
        kwargs["ignoreSmallFiles"] = True

    response = await sdk.call(
        sdk.storage_container_api.delete_storage_container_by_id, container_uuid, **kwargs
    )
    task_id = response.data.ext_id if response.data else None
    return {"status": "storage_container_deletion_initiated", "taskExtId": task_id}


# ─── Handler Dispatch ─────────────────────────────────────────────────────────

CLUSTER_HANDLERS: dict[str, Any] = {
    "list_clusters": handle_list_clusters,
    "get_cluster": handle_get_cluster,
    "list_hosts": handle_list_hosts,
    "get_host": handle_get_host,
    "list_storage_containers": handle_list_storage_containers,
    "create_storage_container": handle_create_storage_container,
    "resize_storage_container": handle_resize_storage_container,
    "delete_storage_container": handle_delete_storage_container,
}
