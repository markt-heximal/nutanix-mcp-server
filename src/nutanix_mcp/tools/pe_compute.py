"""Prism Element VM detail and task tools (v2.0 API, read-only).

These restore, on PE-only deployments, read surfaces that were only reachable
through Prism Central: one VM's full configuration (disks, NICs, IPs) and the
cluster's task history. Every field below was checked against live AOS 6.8.1
responses; the v2 API's key names are not the ones its docs suggest.
"""

import re
from typing import Any

from nutanix_mcp.client import NutanixClient, ValidationError
from nutanix_mcp.tools.prism_element import vm_ip_addresses

_PE_HOST = {
    "type": "string",
    "description": "Prism Element CVM IP address or hostname",
}

_ID = re.compile(r"^[A-Za-z0-9-]+$")


def _path_id(arguments: dict[str, Any], key: str) -> str:
    """A caller-supplied ID that is interpolated into a URL path.

    Restricted to UUID characters so a value like '../cluster' cannot steer
    the request to a different endpoint.
    """
    value = str(arguments.get(key) or "")
    if not _ID.match(value):
        raise ValidationError(f"Invalid {key}: expected a UUID", status_code=None)
    return value


PE_COMPUTE_TOOLS: list[dict] = [
    {
        "name": "pe_get_vm",
        "description": (
            "Get one VM's full configuration on a Prism Element cluster: power "
            "state, vCPUs, memory, host, boot mode, every disk (bus, size, "
            "container, CD-ROM or not) and every NIC with its MAC and IP "
            "addresses. Find the VM's UUID with pe_list_vms."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "pe_host": _PE_HOST,
                "vm_uuid": {"type": "string", "description": "UUID of the VM"},
            },
            "required": ["pe_host", "vm_uuid"],
        },
    },
    {
        "name": "pe_list_tasks",
        "description": (
            "List recent tasks on a Prism Element cluster, newest first: what "
            "ran, on which entities, whether it succeeded, and when. Optionally "
            "narrow to the tasks that touched one entity (a VM, host, image...)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "pe_host": _PE_HOST,
                "count": {
                    "type": "integer",
                    "description": "Maximum number of tasks to return (default 20)",
                },
                "entity_uuid": {
                    "type": "string",
                    "description": "Only tasks that touched this entity UUID",
                },
                "include_completed": {
                    "type": "boolean",
                    "description": "Include finished tasks (default true); false shows only running ones",
                },
            },
            "required": ["pe_host"],
        },
    },
    {
        "name": "pe_get_task",
        "description": (
            "Get one task on a Prism Element cluster by UUID: its operation, "
            "status, percent complete, affected entities and timings. Use it to "
            "follow a task another tool started."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "pe_host": _PE_HOST,
                "task_uuid": {"type": "string", "description": "UUID of the task"},
            },
            "required": ["pe_host", "task_uuid"],
        },
    },
]


def _disk_summary(disk: dict[str, Any]) -> dict[str, Any]:
    addr = disk.get("disk_address") or {}
    return {
        "label": addr.get("disk_label"),
        "bus": addr.get("device_bus"),
        "index": addr.get("device_index"),
        "isCdrom": disk.get("is_cdrom"),
        "isEmpty": disk.get("is_empty"),
        "sizeBytes": disk.get("size"),
        "storageContainerUuid": disk.get("storage_container_uuid"),
        "vmdiskUuid": addr.get("vmdisk_uuid"),
    }


def _nic_detail(nic: dict[str, Any]) -> dict[str, Any]:
    return {
        "nicUuid": nic.get("nic_uuid"),
        "macAddress": nic.get("mac_address"),
        "networkUuid": nic.get("network_uuid"),
        "ipAddresses": nic.get("ip_addresses") or ([nic["ip_address"]] if nic.get("ip_address") else []),
        "isConnected": nic.get("is_connected"),
        "vlanMode": nic.get("vlan_mode"),
        "model": nic.get("model") or None,
    }


def _task_summary(task: dict[str, Any]) -> dict[str, Any]:
    return {
        "uuid": task.get("uuid"),
        "operation": task.get("operation_type"),
        "method": (task.get("meta_request") or {}).get("method_name"),
        "status": task.get("progress_status"),
        "percentComplete": task.get("percentage_complete"),
        "message": task.get("message") or None,
        "errorCode": (task.get("meta_response") or {}).get("error_code"),
        "entities": [
            {"type": e.get("entity_type"), "uuid": e.get("entity_id"), "name": e.get("entity_name")}
            for e in task.get("entity_list") or []
        ],
        "createTimeUsecs": task.get("create_time_usecs"),
        "startTimeUsecs": task.get("start_time_usecs"),
        "completeTimeUsecs": task.get("complete_time_usecs"),
        "subtaskUuids": task.get("subtask_uuid_list") or [],
    }


async def handle_pe_get_vm(client: NutanixClient, arguments: dict[str, Any]) -> dict[str, Any]:
    """One VM with disk and NIC configuration (both are omitted unless asked for)."""
    pe_host = arguments["pe_host"]
    vm = await client.pe_get(
        pe_host,
        f"vms/{_path_id(arguments, 'vm_uuid')}",
        params={"include_vm_disk_config": "true", "include_vm_nic_config": "true"},
    )
    boot = vm.get("boot") or {}
    return {
        "name": vm.get("name"),
        "uuid": vm.get("uuid"),
        "powerState": vm.get("power_state"),
        "numVcpus": vm.get("num_vcpus"),
        "numCoresPerVcpu": vm.get("num_cores_per_vcpu"),
        "memoryMb": vm.get("memory_mb"),
        "hostUuid": vm.get("host_uuid"),
        "machineType": vm.get("machine_type"),
        "uefiBoot": boot.get("uefi_boot"),
        "secureBoot": boot.get("secure_boot"),
        "haPriority": vm.get("ha_priority"),
        "allowLiveMigrate": vm.get("allow_live_migrate"),
        "ipAddresses": vm_ip_addresses(vm),
        "nics": [_nic_detail(n) for n in vm.get("vm_nics") or []],
        "disks": [_disk_summary(d) for d in vm.get("vm_disk_info") or []],
        "gpus": vm.get("vm_gpus") or [],
    }


async def handle_pe_list_tasks(client: NutanixClient, arguments: dict[str, Any]) -> dict[str, Any]:
    """Recent tasks, newest first.

    v2 tasks/list is a POST query that returns tasks OLDEST first, and its
    `count` keeps the oldest — count=5 answers with the five oldest tasks. So
    the whole retained list is fetched (Prism keeps only recent history; ~100
    tasks on the lab clusters) and sorted and trimmed here. The server-side
    entity_list filter is not used either: it returned one task for a VM that
    appears in many, so entity filtering is done here too.
    """
    pe_host = arguments["pe_host"]
    count = arguments.get("count") or 20
    entity_uuid = arguments.get("entity_uuid")
    include_completed = arguments.get("include_completed", True)

    result = await client.pe_post(pe_host, "tasks/list", body={"include_completed": include_completed})
    tasks = result.get("entities") or []
    if entity_uuid:
        tasks = [
            t for t in tasks
            if any(e.get("entity_id") == entity_uuid for e in t.get("entity_list") or [])
        ]
    tasks.sort(key=lambda t: t.get("create_time_usecs") or 0, reverse=True)
    return {
        "totalMatching": len(tasks),
        "count": min(count, len(tasks)),
        "tasks": [_task_summary(t) for t in tasks[:count]],
    }


async def handle_pe_get_task(client: NutanixClient, arguments: dict[str, Any]) -> dict[str, Any]:
    """One task by UUID."""
    task = await client.pe_get(arguments["pe_host"], f"tasks/{_path_id(arguments, 'task_uuid')}")
    return _task_summary(task)


PE_COMPUTE_HANDLERS: dict[str, Any] = {
    "pe_get_vm": handle_pe_get_vm,
    "pe_list_tasks": handle_pe_list_tasks,
    "pe_get_task": handle_pe_get_task,
}
