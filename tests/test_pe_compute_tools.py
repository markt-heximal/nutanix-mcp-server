"""Tests for PE VM detail and task tools.

Fixtures are trimmed copies of live AOS 6.8.1 responses from the lab.
"""

from unittest.mock import AsyncMock

import pytest

from nutanix_mcp.client import ValidationError
from nutanix_mcp.tools import get_all_tools
from nutanix_mcp.tools.pe_compute import (
    handle_pe_get_task,
    handle_pe_get_vm,
    handle_pe_list_tasks,
)


@pytest.fixture
def mock_client():
    return AsyncMock()


VM = {
    "name": "ntnxlab-ubuntu-fl",
    "uuid": "vm-uuid-1",
    "power_state": "on",
    "num_vcpus": 2,
    "num_cores_per_vcpu": 1,
    "memory_mb": 4096,
    "host_uuid": "host-uuid-1",
    "machine_type": "pc",
    "boot": {"uefi_boot": False, "secure_boot": False},
    "ha_priority": 0,
    "allow_live_migrate": True,
    "vm_gpus": [],
    "vm_disk_info": [
        {
            "disk_address": {
                "device_bus": "scsi",
                "device_index": 0,
                "disk_label": "scsi.0",
                "vmdisk_uuid": "vmdisk-1",
            },
            "is_cdrom": False,
            "is_empty": False,
            "storage_container_uuid": "ctr-1",
            "size": 107374182400,
        },
        {
            "disk_address": {"device_bus": "ide", "device_index": 0, "disk_label": "ide.0"},
            "is_cdrom": True,
            "is_empty": True,
        },
    ],
    "vm_nics": [
        {
            "mac_address": "50:6b:8d:dd:99:91",
            "network_uuid": "net-1",
            "nic_uuid": "nic-1",
            "model": "",
            "ip_address": "10.0.1.245",
            "ip_addresses": ["10.0.1.245"],
            "vlan_mode": "Access",
            "is_connected": True,
        }
    ],
}


async def test_get_vm_returns_disks_nics_and_ips(mock_client):
    mock_client.pe_get.return_value = VM
    vm = await handle_pe_get_vm(mock_client, {"pe_host": "10.0.0.1", "vm_uuid": "vm-uuid-1"})

    mock_client.pe_get.assert_called_once_with(
        "10.0.0.1",
        "vms/vm-uuid-1",
        params={"include_vm_disk_config": "true", "include_vm_nic_config": "true"},
    )
    assert vm["name"] == "ntnxlab-ubuntu-fl"
    assert vm["uefiBoot"] is False
    assert vm["ipAddresses"] == ["10.0.1.245"]
    assert vm["nics"] == [{
        "nicUuid": "nic-1",
        "macAddress": "50:6b:8d:dd:99:91",
        "networkUuid": "net-1",
        "ipAddresses": ["10.0.1.245"],
        "isConnected": True,
        "vlanMode": "Access",
        "model": None,
    }]
    disk, cdrom = vm["disks"]
    assert disk == {
        "label": "scsi.0",
        "bus": "scsi",
        "index": 0,
        "isCdrom": False,
        "isEmpty": False,
        "sizeBytes": 107374182400,
        "storageContainerUuid": "ctr-1",
        "vmdiskUuid": "vmdisk-1",
    }
    assert cdrom["isCdrom"] is True and cdrom["sizeBytes"] is None


@pytest.mark.parametrize("bad", ["../cluster", "vm/1", "", "a b", "vm?x=1"])
async def test_ids_are_restricted_to_uuid_characters(mock_client, bad):
    with pytest.raises(ValidationError):
        await handle_pe_get_vm(mock_client, {"pe_host": "10.0.0.1", "vm_uuid": bad})
    with pytest.raises(ValidationError):
        await handle_pe_get_task(mock_client, {"pe_host": "10.0.0.1", "task_uuid": bad})
    mock_client.pe_get.assert_not_called()


def _task(uuid, created, entity_ids, status="Succeeded"):
    return {
        "uuid": uuid,
        "meta_request": {"method_name": "VmPowerOn"},
        "meta_response": {"error_code": 0},
        "create_time_usecs": created,
        "start_time_usecs": created + 10,
        "complete_time_usecs": created + 20,
        "entity_list": [{"entity_id": e, "entity_type": "VM", "entity_name": None} for e in entity_ids],
        "operation_type": "kVmPowerOn",
        "message": "",
        "percentage_complete": 100,
        "progress_status": status,
        "subtask_uuid_list": [],
    }


# The API answers oldest first; the tool must not trust that order.
TASKS = {
    "entities": [
        _task("t-old", 100, ["vm-a"]),
        _task("t-mid", 200, ["vm-b"], status="Failed"),
        _task("t-new", 300, ["vm-a", "host-1"]),
    ]
}


async def test_list_tasks_newest_first_and_trimmed(mock_client):
    mock_client.pe_post.return_value = TASKS
    result = await handle_pe_list_tasks(mock_client, {"pe_host": "10.0.0.1", "count": 2})

    mock_client.pe_post.assert_called_once_with(
        "10.0.0.1", "tasks/list", body={"include_completed": True}
    )
    assert result["totalMatching"] == 3
    assert result["count"] == 2
    assert [t["uuid"] for t in result["tasks"]] == ["t-new", "t-mid"]
    assert result["tasks"][1]["status"] == "Failed"


async def test_list_tasks_filters_by_entity(mock_client):
    mock_client.pe_post.return_value = TASKS
    result = await handle_pe_list_tasks(mock_client, {"pe_host": "10.0.0.1", "entity_uuid": "vm-a"})
    assert [t["uuid"] for t in result["tasks"]] == ["t-new", "t-old"]


async def test_list_tasks_running_only(mock_client):
    mock_client.pe_post.return_value = {"entities": []}
    result = await handle_pe_list_tasks(
        mock_client, {"pe_host": "10.0.0.1", "include_completed": False}
    )
    mock_client.pe_post.assert_called_once_with(
        "10.0.0.1", "tasks/list", body={"include_completed": False}
    )
    assert result == {"totalMatching": 0, "count": 0, "tasks": []}


async def test_get_task_summary(mock_client):
    mock_client.pe_get.return_value = _task("t-1", 100, ["vm-a"])
    task = await handle_pe_get_task(mock_client, {"pe_host": "10.0.0.1", "task_uuid": "t-1"})
    mock_client.pe_get.assert_called_once_with("10.0.0.1", "tasks/t-1")
    assert task["operation"] == "kVmPowerOn"
    assert task["method"] == "VmPowerOn"
    assert task["status"] == "Succeeded"
    assert task["errorCode"] == 0
    assert task["message"] is None
    assert task["entities"] == [{"type": "VM", "uuid": "vm-a", "name": None}]


def test_new_tools_are_read_only_and_served_in_pe_only_mode():
    tools = {t["name"]: t for t in get_all_tools(pe_only=True)}
    for name in ("pe_get_vm", "pe_list_tasks", "pe_get_task"):
        assert name in tools
        assert tools[name]["annotations"].readOnlyHint is True
