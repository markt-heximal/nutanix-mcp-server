"""Field mappings checked against real Prism Element v2 payloads (AOS 6.8.1).

Each of these handlers once read a key the API never returns, so a field came
back empty on every cluster: VM IPs, snapshot timestamps, auth types. The
fixtures below are trimmed copies of live responses from the lab, so a test
fails if a mapping drifts back to a guessed field name.
"""

from unittest.mock import AsyncMock

import pytest

from nutanix_mcp.tools.prism_element import (
    handle_pe_get_auth_config,
    handle_pe_list_networks,
    handle_pe_list_pd_snapshots,
    handle_pe_list_snapshots,
    handle_pe_list_vms,
)


@pytest.fixture
def mock_client():
    return AsyncMock()


def _vm(name, nics):
    return {
        "name": name,
        "uuid": f"{name}-uuid",
        "power_state": "on",
        "num_vcpus": 1,
        "memory_mb": 1024,
        "host_uuid": "host-uuid-1",
        "vm_nics": nics,
    }


async def test_list_vms_reads_ips_from_nics(mock_client):
    mock_client.pe_get.return_value = {
        "entities": [
            _vm("tsrouter-fl", [{
                "mac_address": "50:6b:8d:b8:10:b4",
                "network_uuid": "net-1",
                "ip_address": "10.0.1.244",
                "ip_addresses": ["10.0.1.244", "10.0.1.248"],
                "is_connected": True,
            }]),
            _vm("two-nics", [
                {"mac_address": "aa", "ip_address": "10.0.0.5", "is_connected": True},
                {"mac_address": "bb", "ip_addresses": ["10.0.0.5", "10.0.0.6"], "is_connected": False},
            ]),
            _vm("no-nics", []),
        ]
    }

    result = await handle_pe_list_vms(mock_client, {"pe_host": "10.0.0.1"})

    router, two, bare = result["vms"]
    assert router["ipAddresses"] == ["10.0.1.244", "10.0.1.248"]
    assert router["nics"] == [{
        "macAddress": "50:6b:8d:b8:10:b4",
        "networkUuid": "net-1",
        "ipAddresses": ["10.0.1.244", "10.0.1.248"],
        "isConnected": True,
    }]
    # ip_address alone is used when ip_addresses is absent; duplicates collapse.
    assert two["ipAddresses"] == ["10.0.0.5", "10.0.0.6"]
    assert two["nics"][0]["ipAddresses"] == ["10.0.0.5"]
    assert bare["ipAddresses"] == [] and bare["nics"] == []


async def test_list_vms_requests_nic_config(mock_client):
    """Without include_vm_nic_config the API omits vm_nics entirely."""
    mock_client.pe_get.return_value = {"entities": []}
    await handle_pe_list_vms(mock_client, {"pe_host": "10.0.0.1", "count": 5})
    mock_client.pe_get.assert_called_once_with(
        "10.0.0.1", "vms", params={"include_vm_nic_config": "true", "count": "5"}
    )


async def test_auth_config_reads_snake_case(mock_client):
    mock_client.pe_get.return_value = {"auth_type_list": ["LOCAL"], "directory_list": []}
    result = await handle_pe_get_auth_config(mock_client, {"pe_host": "10.0.0.1"})
    assert result == {"authTypes": ["LOCAL"], "directories": []}


_SNAPSHOTS = {
    "entities": [{
        "snapshot_id": "35519",
        "state": "AVAILABLE",
        "snapshot_create_time_usecs": 1789956003861954,
        "snapshot_expiry_time_usecs": 1790560803861954,
        "size_in_bytes": 1025464832,
    }]
}


async def test_list_snapshots_timestamps(mock_client):
    mock_client.pe_get.return_value = _SNAPSHOTS
    result = await handle_pe_list_snapshots(
        mock_client, {"pe_host": "10.0.0.1", "protection_domain": "pd-fl-all"}
    )
    assert result["snapshots"] == [{
        "snapshotId": "35519",
        "createdTimestamp": 1789956003861954,
        "expiryTimestamp": 1790560803861954,
        "state": "AVAILABLE",
    }]


async def test_list_pd_snapshots_timestamps(mock_client):
    mock_client.pe_get.return_value = _SNAPSHOTS
    result = await handle_pe_list_pd_snapshots(
        mock_client, {"pe_host": "10.0.0.1", "pd_name": "pd-fl-all"}
    )
    snap = result["snapshots"][0]
    assert snap["createTimeUsecs"] == 1789956003861954
    assert snap["expiryTimeUsecs"] == 1790560803861954
    assert snap["sizeBytes"] == 1025464832


async def test_list_networks_unmanaged(mock_client):
    """An IPAM-less network, as the lab's 'lab' network really answers."""
    mock_client.pe_list.return_value = {
        "entities": [{
            "name": "lab",
            "uuid": "net-1",
            "vlan_id": 0,
            "vswitch_name": "br0",
            "ip_config": {"prefix_length": 0, "ipam_enabled": False, "pool": []},
        }]
    }
    net = (await handle_pe_list_networks(mock_client, {"pe_host": "10.0.0.1"}))["networks"][0]
    assert net["vswitchName"] == "br0"
    assert net["ipamEnabled"] is False
    assert "networkType" not in net
