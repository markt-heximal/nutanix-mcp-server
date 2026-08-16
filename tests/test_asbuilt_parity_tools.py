"""Tests for AsBuiltReport parity tools (images, networks, metro witness, DR snapshots, PD replications)."""

from unittest.mock import AsyncMock

import pytest

from nutanix_mcp.client import NutanixAPIError
from nutanix_mcp.tools.prism_element import (
    handle_pe_get_metro_witness,
    handle_pe_list_dr_snapshots,
    handle_pe_list_images,
    handle_pe_list_networks,
    handle_pe_list_pd_replications,
)


@pytest.fixture
def mock_client():
    client = AsyncMock()
    return client


@pytest.mark.asyncio
async def test_list_images(mock_client):
    """Test listing images from PE cluster."""
    mock_client.pe_list.return_value = {
        "entities": [
            {
                "name": "ubuntu-22.04.iso",
                "uuid": "img-uuid-1",
                "image_type": "ISO_IMAGE",
                "image_state": "ACTIVE",
                "vm_disk_size": 3758096384,
                "source_uri": "http://releases.ubuntu.com/22.04/ubuntu-22.04-live-server-amd64.iso",
                "storage_container_name": "images-ctr",
                "created_time_in_usecs": 1700000000000000,
                "updated_time_in_usecs": 1700000000000000,
            },
            {
                "name": "win2022-base",
                "uuid": "img-uuid-2",
                "image_type": "DISK_IMAGE",
                "image_state": "ACTIVE",
                "vm_disk_size": 10737418240,
                "source_uri": None,
                "storage_container_name": "images-ctr",
                "created_time_in_usecs": 1699000000000000,
                "updated_time_in_usecs": 1699000000000000,
            },
        ]
    }

    result = await handle_pe_list_images(mock_client, {"pe_host": "10.0.0.1"})

    assert result["count"] == 2
    assert result["images"][0]["name"] == "ubuntu-22.04.iso"
    assert result["images"][0]["imageType"] == "ISO_IMAGE"
    assert result["images"][0]["sizeMb"] == pytest.approx(3584.0, rel=0.01)
    assert result["images"][1]["imageType"] == "DISK_IMAGE"
    mock_client.pe_list.assert_called_once_with("10.0.0.1", "images")


@pytest.mark.asyncio
async def test_list_networks(mock_client):
    """Test listing networks from PE cluster."""
    mock_client.pe_list.return_value = {
        "entities": [
            {
                "name": "vlan-100-prod",
                "uuid": "net-uuid-1",
                "vlan_id": 100,
                "network_type": "MANAGED",
                "ip_config": {
                    "network_address": "10.0.100.0",
                    "prefix_length": 24,
                    "default_gateway": "10.0.100.1",
                    "dhcp_server_address": "10.0.100.2",
                    "pool": [{"range": "10.0.100.100 10.0.100.200"}],
                },
            },
            {
                "name": "vlan-200-dev",
                "uuid": "net-uuid-2",
                "vlan_id": 200,
                "network_type": "UNMANAGED",
                "ip_config": None,
            },
        ]
    }

    result = await handle_pe_list_networks(mock_client, {"pe_host": "10.0.0.1"})

    assert result["count"] == 2
    assert result["networks"][0]["name"] == "vlan-100-prod"
    assert result["networks"][0]["vlanId"] == 100
    assert result["networks"][0]["ipConfig"]["defaultGateway"] == "10.0.100.1"
    assert result["networks"][1]["ipConfig"] is None
    mock_client.pe_list.assert_called_once_with("10.0.0.1", "networks")


@pytest.mark.asyncio
async def test_get_metro_witness_configured(mock_client):
    """Test getting metro witness when configured."""
    mock_client.pe_get.return_value = {
        "witness_address": "10.0.0.200",
        "cluster_uuid": "cluster-uuid-1",
        "witness_state": "HEALTHY",
        "has_witness": True,
    }

    result = await handle_pe_get_metro_witness(mock_client, {"pe_host": "10.0.0.1"})

    assert result["configured"] is True
    assert result["witness"]["witnessAddress"] == "10.0.0.200"
    assert result["witness"]["witnessState"] == "HEALTHY"
    mock_client.pe_get.assert_called_once_with("10.0.0.1", "cluster/metro_witness")


@pytest.mark.asyncio
async def test_get_metro_witness_not_configured(mock_client):
    """Test getting metro witness when not configured."""
    mock_client.pe_get.return_value = {}

    result = await handle_pe_get_metro_witness(mock_client, {"pe_host": "10.0.0.1"})

    assert result["configured"] is False
    assert result["witness"] is None


@pytest.mark.asyncio
async def test_get_metro_witness_precondition_failed(mock_client):
    """A cluster without metro availability answers HTTP 412, not an empty body.

    Observed on AOS 6.8.1. That is the API saying "not configured", so it must
    surface as a clean answer rather than a raised error.
    """
    mock_client.pe_get.side_effect = NutanixAPIError("API request failed (HTTP 412)", status_code=412)

    result = await handle_pe_get_metro_witness(mock_client, {"pe_host": "10.0.0.1"})

    assert result["configured"] is False
    assert result["witness"] is None


@pytest.mark.asyncio
async def test_get_metro_witness_other_errors_propagate(mock_client):
    """Only 412 means "not configured" — real failures must still raise."""
    mock_client.pe_get.side_effect = NutanixAPIError("boom", status_code=500)

    with pytest.raises(NutanixAPIError):
        await handle_pe_get_metro_witness(mock_client, {"pe_host": "10.0.0.1"})


@pytest.mark.asyncio
async def test_list_dr_snapshots(mock_client):
    """Test listing DR snapshots across remote sites."""
    mock_client.pe_list.return_value = {
        "entities": [
            {
                "snapshot_id": "snap-dr-1",
                "protection_domain_name": "pd-prod",
                "remote_site_name": "dr-site-east",
                "consistency_group_name": "cg-web",
                "created_time_in_usecs": 1700000000000000,
                "expiration_time_in_usecs": 1700086400000000,
                "size_in_bytes": 5368709120,
            }
        ]
    }

    result = await handle_pe_list_dr_snapshots(mock_client, {"pe_host": "10.0.0.1"})

    assert result["count"] == 1
    assert result["drSnapshots"][0]["snapshotId"] == "snap-dr-1"
    assert result["drSnapshots"][0]["protectionDomainName"] == "pd-prod"
    assert result["drSnapshots"][0]["remoteSiteName"] == "dr-site-east"
    mock_client.pe_list.assert_called_once_with("10.0.0.1", "remote_sites/dr_snapshots")


@pytest.mark.asyncio
async def test_list_pd_replications(mock_client):
    """Test listing all active protection domain replications."""
    mock_client.pe_list.return_value = {
        "entities": [
            {
                "id": "repl-global-1",
                "protection_domain_name": "pd-prod",
                "remote_site_name": "dr-site-east",
                "snapshot_id": "snap-100",
                "replication_status": "COMPLETED",
                "completed_percentage": 100,
                "completed_bytes": 10737418240,
                "total_bytes": 10737418240,
                "replicating_vms": ["vm-1", "vm-2"],
            }
        ]
    }

    result = await handle_pe_list_pd_replications(mock_client, {"pe_host": "10.0.0.1"})

    assert result["count"] == 1
    assert result["replications"][0]["protectionDomainName"] == "pd-prod"
    assert result["replications"][0]["status"] == "COMPLETED"
    assert result["replications"][0]["completedPercentage"] == 100
    assert result["replications"][0]["replicatingVms"] == ["vm-1", "vm-2"]
    mock_client.pe_list.assert_called_once_with("10.0.0.1", "protection_domains/replications")
