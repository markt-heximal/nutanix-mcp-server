"""Tests for storage container and storage pool tools.

These two handlers previously had no test coverage at all, which is why both
called endpoints that return 404 on a real cluster:

  pe_list_containers    called v2.0 "containers"    -> correct is "storage_containers"
  pe_list_storage_pools called v2.0 "storage_pools" -> no v2 resource; it is v1 only

All fixtures below are captured from a live AOS 6.8.1 cluster, so the field
names are the ones the API really emits -- note v1 returns camelCase while v2
returns snake_case.
"""

from unittest.mock import AsyncMock

import pytest

from nutanix_mcp.tools.prism_element import (
    handle_pe_list_containers,
    handle_pe_list_storage_pools,
)


@pytest.fixture
def mock_client():
    return AsyncMock()


# ─── Storage containers (v2.0, snake_case) ───────────────────────────────────

LIVE_CONTAINERS = {
    "entities": [
        {
            "id": "0006568f-63fb-79aa-274f-3805253a7444::189",
            "storage_container_uuid": "64a76b64-eeb8-4bec-8e29-f39bfec00776",
            "cluster_uuid": "0006568f-63fb-79aa-274f-3805253a7444",
            "name": "SelfServiceContainer",
            "max_capacity": 3198160582085,
            "replication_factor": 2,
            "compression_enabled": False,
            "erasure_code": "off",
            "on_disk_dedup": "OFF",
            "marked_for_removal": False,
            # Prism returns usage stats as STRINGS while max_capacity is an int.
            "usage_stats": {"storage.usage_bytes": "163300000000"},
        },
        {
            "id": "0006568f-63fb-79aa-274f-3805253a7444::190",
            "storage_container_uuid": "aa11bb22-cc33-4dd4-9ee5-ff6677889900",
            "cluster_uuid": "0006568f-63fb-79aa-274f-3805253a7444",
            "name": "NutanixManagementShare",
            "max_capacity": 2983400000000,
            "replication_factor": 2,
            "compression_enabled": True,
            "erasure_code": "off",
            "on_disk_dedup": "OFF",
            "marked_for_removal": False,
            "usage_stats": {"storage.usage_bytes": "28500000000"},
        },
    ]
}


@pytest.mark.asyncio
async def test_list_containers_uses_storage_containers_resource(mock_client):
    """Guards the actual bug: the resource is storage_containers, not containers."""
    mock_client.pe_list.return_value = LIVE_CONTAINERS

    result = await handle_pe_list_containers(mock_client, {"pe_host": "10.0.0.1"})

    assert result["count"] == 2
    first = result["containers"][0]
    assert first["name"] == "SelfServiceContainer"
    # storage_container_uuid, NOT container_uuid
    assert first["containerUuid"] == "64a76b64-eeb8-4bec-8e29-f39bfec00776"
    assert first["maxCapacityBytes"] == 3198160582085
    # String stat coerced to int so it matches its sibling capacity field.
    assert first["usedBytes"] == 163300000000
    assert isinstance(first["usedBytes"], int)
    assert first["replicationFactor"] == 2
    # erasure_code is a string ("off"), not a boolean erasure_coded
    assert first["erasureCode"] == "off"
    assert result["containers"][1]["compressionEnabled"] is True

    mock_client.pe_list.assert_called_once_with("10.0.0.1", "storage_containers")


@pytest.mark.asyncio
async def test_list_containers_missing_usage_stats(mock_client):
    """usage_stats absent must not raise."""
    mock_client.pe_list.return_value = {
        "entities": [{"name": "bare", "storage_container_uuid": "u-1"}]
    }

    result = await handle_pe_list_containers(mock_client, {"pe_host": "10.0.0.1"})

    assert result["count"] == 1
    assert result["containers"][0]["usedBytes"] is None


# ─── Storage pools (v1, camelCase) ───────────────────────────────────────────

LIVE_STORAGE_POOLS = {
    "metadata": {"grandTotalEntities": 1, "totalEntities": 1},
    "entities": [
        {
            "id": "0006568f-63fb-79aa-274f-3805253a7444::3",
            "name": "default-storage-pool-62635419953366",
            "storagePoolUuid": "8261fe42-6f8b-40a7-bf52-a0ad73d04180",
            "clusterUuid": "0006568f-63fb-79aa-274f-3805253a7444",
            "capacity": 3198160582085,
            "reservedCapacity": 0,
            "markedForRemoval": False,
            "disks": ["disk-uuid-1", "disk-uuid-2"],
            "diskUuids": ["disk-uuid-1", "disk-uuid-2"],
            "usageStats": {
                "storage.capacity_bytes": "3198160582085",
                "storage.usage_bytes": "321746821120",
            },
        }
    ],
}


@pytest.mark.asyncio
async def test_list_storage_pools_uses_v1(mock_client):
    """Guards the actual bug: storage_pools is a v1-only resource, camelCase."""
    mock_client.pe_v1_get.return_value = LIVE_STORAGE_POOLS

    result = await handle_pe_list_storage_pools(mock_client, {"pe_host": "10.0.0.1"})

    assert result["count"] == 1
    pool = result["storagePools"][0]
    assert pool["name"] == "default-storage-pool-62635419953366"
    # camelCase storagePoolUuid, not snake_case storage_pool_uuid
    assert pool["uuid"] == "8261fe42-6f8b-40a7-bf52-a0ad73d04180"
    assert pool["capacityBytes"] == 3198160582085
    # camelCase usageStats, not usage_stats; string stat coerced to int
    assert pool["usageBytes"] == 321746821120
    assert isinstance(pool["usageBytes"], int)
    assert pool["reservedCapacityBytes"] == 0
    assert pool["numDisks"] == 2
    assert pool["markedForRemoval"] is False

    # Must go through the v1 client, not pe_list/pe_get.
    mock_client.pe_v1_get.assert_called_once_with("10.0.0.1", "storage_pools")
    mock_client.pe_get.assert_not_called()


@pytest.mark.asyncio
async def test_list_storage_pools_falls_back_to_disk_uuids(mock_client):
    """numDisks should still count when only diskUuids is present."""
    mock_client.pe_v1_get.return_value = {
        "entities": [{"name": "p", "storagePoolUuid": "u", "diskUuids": ["a", "b", "c"]}]
    }

    result = await handle_pe_list_storage_pools(mock_client, {"pe_host": "10.0.0.1"})

    assert result["storagePools"][0]["numDisks"] == 3
    assert result["storagePools"][0]["usageBytes"] is None


@pytest.mark.asyncio
async def test_list_storage_pools_empty(mock_client):
    """No entities key is a valid response."""
    mock_client.pe_v1_get.return_value = {"metadata": {}}

    result = await handle_pe_list_storage_pools(mock_client, {"pe_host": "10.0.0.1"})

    assert result == {"count": 0, "storagePools": []}
