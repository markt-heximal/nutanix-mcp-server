"""VM management tools using Nutanix v4 vmm namespace."""

from typing import Any, Optional

from nutanix_mcp.client import NutanixClient


def _vm_ip_addresses(vm: Any) -> list[str]:
    """Collect a VM's IPv4 addresses from its NICs (statically assigned + learned)."""
    ips: list[str] = []
    for nic in getattr(vm, "nics", None) or []:
        net = getattr(nic, "network_info", None)
        if not net:
            continue
        # Statically-assigned addresses (ipv4_config)
        cfg = getattr(net, "ipv4_config", None)
        if cfg:
            ip = getattr(cfg, "ip_address", None)
            if ip and getattr(ip, "value", None):
                ips.append(ip.value)
            for sec in getattr(cfg, "secondary_ip_address_list", None) or []:
                if getattr(sec, "value", None):
                    ips.append(sec.value)
        # Learned/discovered addresses (ipv4_info)
        info = getattr(net, "ipv4_info", None)
        if info:
            for learned in getattr(info, "learned_ip_addresses", None) or []:
                if getattr(learned, "value", None):
                    ips.append(learned.value)
    # De-duplicate while preserving order.
    seen: set[str] = set()
    return [ip for ip in ips if not (ip in seen or seen.add(ip))]


def _vm_host(vm: Any) -> Optional[str]:
    """Return the ext_id of the host a VM is running on, if scheduled."""
    host = getattr(vm, "host", None)
    return getattr(host, "ext_id", None) if host else None

# ─── Tool Definitions ─────────────────────────────────────────────────────────

VM_TOOLS: list[dict] = [
    {
        "name": "list_vms",
        "description": (
            "List ALL virtual machines on Nutanix (auto-paginates internally). "
            "Returns complete results in one call — no manual pagination needed. "
            "Use 'cluster_name' to filter VMs to a specific cluster by name. "
            "Use 'filter' to narrow results via OData. Use 'limit' only if you want a subset."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "cluster_name": {
                    "type": "string",
                    "description": "Filter VMs to a specific cluster by name (client-side filtering).",
                },
                "filter": {
                    "type": "string",
                    "description": "OData filter expression. Examples: \"name eq 'my-vm'\", \"powerState eq 'ON'\"",
                },
                "limit": {
                    "type": "integer",
                    "description": "Optional cap on results. Omit to get ALL VMs (default behavior).",
                },
            },
        },
    },
    {
        "name": "get_vm",
        "description": (
            "Get detailed information about a specific VM by its UUID. "
            "Returns full configuration including CPU, memory, disks, and NICs."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "vm_uuid": {
                    "type": "string",
                    "description": "The UUID (extId) of the virtual machine",
                },
            },
            "required": ["vm_uuid"],
        },
    },
    {
        "name": "power_on_vm",
        "description": "Power on a virtual machine.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "vm_uuid": {
                    "type": "string",
                    "description": "The UUID (extId) of the virtual machine",
                },
            },
            "required": ["vm_uuid"],
        },
    },
    {
        "name": "power_off_vm",
        "description": ("Power off a virtual machine. Uses ACPI shutdown by default (guest-initiated)."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "vm_uuid": {
                    "type": "string",
                    "description": "The UUID (extId) of the virtual machine",
                },
                "force": {
                    "type": "boolean",
                    "description": "Force power off (hard shutdown) instead of ACPI guest shutdown",
                    "default": False,
                },
            },
            "required": ["vm_uuid"],
        },
    },
    {
        "name": "create_vm",
        "description": ("Create a new virtual machine. Requires name, cluster UUID, and basic specs."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Name for the new VM",
                },
                "cluster_uuid": {
                    "type": "string",
                    "description": "UUID of the cluster to create the VM on",
                },
                "num_vcpus": {
                    "type": "integer",
                    "description": "Number of vCPUs (default: 2)",
                    "default": 2,
                },
                "memory_mb": {
                    "type": "integer",
                    "description": "Memory in MB (default: 4096)",
                    "default": 4096,
                },
                "disk_size_gb": {
                    "type": "integer",
                    "description": "Boot disk size in GB (default: 40)",
                    "default": 40,
                },
            },
            "required": ["name", "cluster_uuid"],
        },
    },
    {
        "name": "update_vm",
        "description": (
            "Update a virtual machine's configuration (CPU, memory, name, description). "
            "The VM should be powered off for CPU/memory changes. Uses ETag-based "
            "concurrency control. Returns a task UUID for status tracking."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "vm_uuid": {
                    "type": "string",
                    "description": "The UUID (extId) of the virtual machine to update",
                },
                "name": {
                    "type": "string",
                    "description": "New name for the VM (optional)",
                },
                "description": {
                    "type": "string",
                    "description": "New description for the VM (optional)",
                },
                "num_vcpus": {
                    "type": "integer",
                    "description": "New total number of vCPUs (optional, VM must be off)",
                },
                "memory_mb": {
                    "type": "integer",
                    "description": "New memory in MB (optional, VM must be off)",
                },
            },
            "required": ["vm_uuid"],
        },
    },
    {
        "name": "delete_vm",
        "description": (
            "Delete a virtual machine permanently. This action cannot be undone. "
            "Requires explicit confirmation. Returns a task UUID for status tracking."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "vm_uuid": {
                    "type": "string",
                    "description": "The UUID (extId) of the virtual machine to delete",
                },
                "confirm": {
                    "type": "boolean",
                    "description": "Must be true to confirm deletion. Safety guard against accidental deletes.",
                },
            },
            "required": ["vm_uuid", "confirm"],
        },
    },
    {
        "name": "clone_vm",
        "description": (
            "Clone an existing virtual machine. Creates a copy with a new name. "
            "Returns a task UUID for status tracking."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "vm_uuid": {
                    "type": "string",
                    "description": "The UUID (extId) of the source VM to clone",
                },
                "new_name": {
                    "type": "string",
                    "description": "Name for the cloned VM",
                },
            },
            "required": ["vm_uuid", "new_name"],
        },
    },
]


# ─── Tool Handlers ────────────────────────────────────────────────────────────


async def _fetch_vm_etag(sdk: Any, vm_uuid: str) -> tuple[Any, Any]:
    """Fetch current VM state and its ETag (required as If-Match on v4 mutations)."""
    response = await sdk.call(sdk.vm_api.get_vm_by_id, vm_uuid)
    return response, sdk.get_etag(response)


async def handle_list_vms(client: NutanixClient, arguments: dict[str, Any]) -> dict[str, Any]:
    """List VMs using official Nutanix SDK. Handles pagination automatically."""
    filter_expr = arguments.get("filter")
    limit = arguments.get("limit")
    cluster_name = arguments.get("cluster_name")

    sdk = client.sdk
    kwargs: dict[str, Any] = {}
    if filter_expr:
        kwargs["_filter"] = filter_expr

    # Resolve cluster name to UUID for client-side filtering
    cluster_uuid = None
    if cluster_name:
        clusters = await sdk.list_all(sdk.cluster_api.list_clusters)
        for c in clusters:
            if c.name and c.name.lower() == cluster_name.lower():
                cluster_uuid = c.ext_id
                break
        if cluster_uuid is None:
            return {
                "error": f"Cluster '{cluster_name}' not found",
                "availableClusters": [c.name for c in clusters if c.name],
            }

    if limit and not cluster_name:
        # Single page with limit (skip when cluster filtering since we need all VMs).
        # PC v4 caps the VMs page size at 100; clamp so larger UI values don't 400.
        response = await sdk.call(sdk.vm_api.list_vms, _limit=min(limit, 100), **kwargs)
        vms = response.data or []
    else:
        # Auto-paginate all results
        vms = await sdk.list_all(sdk.vm_api.list_vms, **kwargs)

    # Client-side cluster filtering
    if cluster_uuid:
        vms = [vm for vm in vms if vm.cluster and vm.cluster.ext_id == cluster_uuid]
        if limit:
            vms = vms[:limit]

    return {
        "totalReturned": len(vms),
        "cluster": cluster_name if cluster_name else "all",
        "note": "All matching VMs returned. No further pagination needed.",
        "vms": [
            {
                "name": vm.name,
                "extId": vm.ext_id,
                "powerState": vm.power_state,
                "numVcpus": (vm.num_sockets or 0) * (vm.num_cores_per_socket or 0),
                "memorySizeMb": (vm.memory_size_bytes or 0) // (1024 * 1024),
                "cluster": vm.cluster.ext_id if vm.cluster else None,
                "host": _vm_host(vm),
                "ipAddresses": _vm_ip_addresses(vm),
            }
            for vm in vms
        ],
    }


async def handle_get_vm(client: NutanixClient, arguments: dict[str, Any]) -> dict[str, Any]:
    """Get VM details using official Nutanix SDK."""
    vm_uuid = arguments["vm_uuid"]
    sdk = client.sdk
    response = await sdk.call(sdk.vm_api.get_vm_by_id, vm_uuid)
    vm = response.data
    return vm.to_dict() if vm else {}


async def handle_power_on_vm(client: NutanixClient, arguments: dict[str, Any]) -> dict[str, Any]:
    """Power on a VM using official Nutanix SDK."""
    vm_uuid = arguments["vm_uuid"]
    sdk = client.sdk
    _, etag = await _fetch_vm_etag(sdk, vm_uuid)
    response = await sdk.call(sdk.vm_api.power_on_vm, vm_uuid, if_match=etag)
    task_id = response.data.ext_id if response.data else None
    return {"status": "power_on_initiated", "taskExtId": task_id}


async def handle_power_off_vm(client: NutanixClient, arguments: dict[str, Any]) -> dict[str, Any]:
    """Power off a VM using official Nutanix SDK."""
    vm_uuid = arguments["vm_uuid"]
    force = arguments.get("force", False)
    sdk = client.sdk
    _, etag = await _fetch_vm_etag(sdk, vm_uuid)

    if force:
        response = await sdk.call(sdk.vm_api.power_off_vm, vm_uuid, if_match=etag)
        action = "power-off"
    else:
        import ntnx_vmm_py_client.models.vmm.v4.ahv.config.GuestPowerOptions as gpo
        body = gpo.GuestPowerOptions()
        response = await sdk.call(sdk.vm_api.shutdown_guest_vm, vm_uuid, body, if_match=etag)
        action = "guest-shutdown"

    task_id = response.data.ext_id if response.data else None
    return {"status": f"{action}_initiated", "taskExtId": task_id}


async def handle_create_vm(client: NutanixClient, arguments: dict[str, Any]) -> dict[str, Any]:
    """Create a VM using official Nutanix SDK."""
    import ntnx_vmm_py_client.models.vmm.v4.ahv.config.Disk as DiskModule
    import ntnx_vmm_py_client.models.vmm.v4.ahv.config.Vm as VmModule

    name = arguments["name"]
    cluster_uuid = arguments["cluster_uuid"]
    num_vcpus = arguments.get("num_vcpus", 2)
    memory_mb = arguments.get("memory_mb", 4096)
    disk_size_gb = arguments.get("disk_size_gb", 40)

    cluster_ref = VmModule.ClusterReference()
    cluster_ref.ext_id = cluster_uuid

    disk = DiskModule.Disk()
    disk.disk_size_bytes = disk_size_gb * 1024 * 1024 * 1024

    vm = VmModule.Vm()
    vm.name = name
    vm.cluster = cluster_ref
    vm.num_sockets = 1
    vm.num_cores_per_socket = num_vcpus
    vm.memory_size_bytes = memory_mb * 1024 * 1024
    vm.disks = [disk]

    sdk = client.sdk
    response = await sdk.call(sdk.vm_api.create_vm, vm)
    task_id = response.data.ext_id if response.data else None
    return {
        "status": "vm_creation_initiated",
        "taskExtId": task_id,
    }


async def handle_update_vm(client: NutanixClient, arguments: dict[str, Any]) -> dict[str, Any]:
    """Update a VM using official Nutanix SDK with ETag concurrency control."""
    vm_uuid = arguments["vm_uuid"]
    sdk = client.sdk

    # Fetch current VM state and its ETag for If-Match concurrency control
    get_response, etag = await _fetch_vm_etag(sdk, vm_uuid)
    vm = get_response.data

    # Apply requested changes
    if "name" in arguments:
        vm.name = arguments["name"]
    if "description" in arguments:
        vm.description = arguments["description"]
    if "num_vcpus" in arguments:
        vm.num_cores_per_socket = arguments["num_vcpus"]
        vm.num_sockets = 1
    if "memory_mb" in arguments:
        vm.memory_size_bytes = arguments["memory_mb"] * 1024 * 1024

    response = await sdk.call(sdk.vm_api.update_vm_by_id, vm_uuid, vm, if_match=etag)
    task_id = response.data.ext_id if response.data else None
    return {
        "status": "vm_update_initiated",
        "taskExtId": task_id,
    }


async def handle_delete_vm(client: NutanixClient, arguments: dict[str, Any]) -> dict[str, Any]:
    """Delete a VM using official Nutanix SDK."""
    vm_uuid = arguments["vm_uuid"]
    confirm = arguments.get("confirm", False)

    if not confirm:
        return {
            "status": "error",
            "message": "Deletion not confirmed. Set 'confirm: true' to proceed with VM deletion.",
        }

    sdk = client.sdk
    _, etag = await _fetch_vm_etag(sdk, vm_uuid)
    response = await sdk.call(sdk.vm_api.delete_vm_by_id, vm_uuid, if_match=etag)
    task_id = response.data.ext_id if response.data else None
    return {
        "status": "vm_deletion_initiated",
        "taskExtId": task_id,
    }


async def handle_clone_vm(client: NutanixClient, arguments: dict[str, Any]) -> dict[str, Any]:
    """Clone a VM using official Nutanix SDK."""
    import ntnx_vmm_py_client.models.vmm.v4.ahv.config.CloneOverrideParams as CloneModule

    vm_uuid = arguments["vm_uuid"]
    new_name = arguments["new_name"]

    body = CloneModule.CloneOverrideParams()
    body.name = new_name

    sdk = client.sdk
    _, etag = await _fetch_vm_etag(sdk, vm_uuid)
    response = await sdk.call(sdk.vm_api.clone_vm, vm_uuid, body, if_match=etag)
    task_id = response.data.ext_id if response.data else None
    return {
        "status": "vm_clone_initiated",
        "taskExtId": task_id,
    }


# ─── Handler Dispatch ─────────────────────────────────────────────────────────

VM_HANDLERS: dict[str, Any] = {
    "list_vms": handle_list_vms,
    "get_vm": handle_get_vm,
    "power_on_vm": handle_power_on_vm,
    "power_off_vm": handle_power_off_vm,
    "create_vm": handle_create_vm,
    "update_vm": handle_update_vm,
    "delete_vm": handle_delete_vm,
    "clone_vm": handle_clone_vm,
}
