"""Tests for host detail tools (Issue #18)."""

from unittest.mock import AsyncMock

import pytest

from nutanix_mcp.tools.prism_element import (
    handle_pe_get_host_disks,
    handle_pe_get_host_nics,
    handle_pe_list_cvms,
)


@pytest.fixture
def mock_client():
    client = AsyncMock()
    return client


@pytest.mark.asyncio
async def test_get_host_disks(mock_client):
    """Test retrieving disk inventory for a host."""
    mock_client.pe_get.return_value = {
        "entities": [
            {
                "id": "disk-1",
                "disk_uuid": "d-uuid-1",
                "disk_hardware_config": {
                    "serial_number": "SN123456",
                    "model": "Samsung PM1733",
                    "current_firmware_version": "1.2.3",
                    "vendor": "Samsung",
                },
                "storage_tier_name": "SSD-SATA",
                "disk_status": "NORMAL",
                "disk_size": 1920383410176,
                "online": True,
                "mount_path": "/home/nutanix/data/stargate-storage/disks/disk-1",
                "location": 1,
            },
            {
                "id": "disk-2",
                "disk_uuid": "d-uuid-2",
                "disk_hardware_config": {
                    "serial_number": "SN789012",
                    "model": "Seagate Exos",
                    "current_firmware_version": "2.0.1",
                    "vendor": "Seagate",
                },
                "storage_tier_name": "DAS-SATA",
                "disk_status": "NORMAL",
                "disk_size": 8001563222016,
                "online": True,
                "mount_path": "/home/nutanix/data/stargate-storage/disks/disk-2",
                "location": 2,
            },
        ]
    }

    result = await handle_pe_get_host_disks(mock_client, {"pe_host": "10.0.0.1", "host_uuid": "host-uuid-1"})

    assert result["hostUuid"] == "host-uuid-1"
    assert result["count"] == 2
    assert result["disks"][0]["serialNumber"] == "SN123456"
    assert result["disks"][0]["model"] == "Samsung PM1733"
    assert result["disks"][0]["storageTierName"] == "SSD-SATA"
    assert result["disks"][1]["vendor"] == "Seagate"
    # hosts/{uuid}/host_disks does not exist on AOS 6.8.1; the disks collection
    # filtered by host_ids is the route that works.
    mock_client.pe_get.assert_called_once_with("10.0.0.1", "disks/", params={"host_ids": "host-uuid-1"})


@pytest.mark.asyncio
async def test_get_host_nics(mock_client):
    """Test retrieving NIC details for a host.

    Shape captured from AOS 6.8.1: a bare JSON list, not an {"entities": [...]}
    envelope, with ipv4_addresses / status / switch_management_ip rather than
    the singular ip_address / interface_status / switch_management_address the
    original fixture invented. Unmanaged switches leave most fields null.
    """
    mock_client.pe_get.return_value = [
        {
            "id": "0006568f-63fb-79aa-274f-3805253a7444::2:eth0",
            "uuid": "7d3df984-22c8-46da-8067-75d0e21a4d34",
            "name": "eth0",
            "mac_address": "38:05:25:3a:74:46",
            "ipv4_addresses": [],
            "ipv6_addresses": [],
            "status": None,
            "dhcp_enabled": None,
            "link_speed_in_kbps": None,
            "mtu_in_bytes": 1500,
            "switch_port_id": None,
            "switch_vlan_id": None,
            "switch_management_ip": None,
        },
        {
            "id": "0006568f-63fb-79aa-274f-3805253a7444::2:eth1",
            "uuid": "9c4d1f22-0e51-4a7b-9d3e-1f2a3b4c5d6e",
            "name": "eth1",
            "mac_address": "38:05:25:3a:74:47",
            "ipv4_addresses": ["10.0.1.243"],
            "ipv6_addresses": [],
            "status": "UP",
            "dhcp_enabled": False,
            "link_speed_in_kbps": 10000000,
            "mtu_in_bytes": 9000,
            "switch_port_id": "Ethernet1/2",
            "switch_vlan_id": 200,
            "switch_management_ip": "10.0.1.254",
        },
    ]

    result = await handle_pe_get_host_nics(mock_client, {"pe_host": "10.0.0.1", "host_uuid": "host-uuid-1"})

    assert result["hostUuid"] == "host-uuid-1"
    assert result["count"] == 2
    assert result["nics"][0]["name"] == "eth0"
    assert result["nics"][0]["macAddress"] == "38:05:25:3a:74:46"
    assert result["nics"][0]["ipv4Addresses"] == []
    assert result["nics"][0]["linkSpeedMbps"] is None
    assert result["nics"][0]["mtu"] == 1500
    assert result["nics"][1]["ipv4Addresses"] == ["10.0.1.243"]
    assert result["nics"][1]["linkSpeedMbps"] == 10000
    assert result["nics"][1]["interfaceStatus"] == "UP"
    assert result["nics"][1]["switchManagementAddress"] == "10.0.1.254"
    assert result["nics"][1]["switchPortId"] == "Ethernet1/2"
    mock_client.pe_get.assert_called_once_with("10.0.0.1", "hosts/host-uuid-1/host_nics")


@pytest.mark.asyncio
async def test_list_cvms(mock_client):
    """Test listing Controller VMs."""
    mock_client.pe_list.return_value = {
        "entities": [
            {
                "name": "NTNX-node1-CVM",
                "uuid": "cvm-uuid-1",
                "power_state": "on",
                "memory_mb": 32768,
                "num_vcpus": 12,
                "host_uuid": "host-uuid-1",
                "ip_addresses": ["10.0.0.11"],
            },
            {
                "name": "NTNX-node2-CVM",
                "uuid": "cvm-uuid-2",
                "power_state": "on",
                "memory_mb": 32768,
                "num_vcpus": 12,
                "host_uuid": "host-uuid-2",
                "ip_addresses": ["10.0.0.12"],
            },
        ]
    }

    result = await handle_pe_list_cvms(mock_client, {"pe_host": "10.0.0.1"})

    assert result["count"] == 2
    assert result["cvms"][0]["name"] == "NTNX-node1-CVM"
    assert result["cvms"][0]["memoryMb"] == 32768
    assert result["cvms"][0]["ipAddresses"] == ["10.0.0.11"]
    mock_client.pe_list.assert_called_once_with("10.0.0.1", "vms", filter_criteria="is_cvm==true")
