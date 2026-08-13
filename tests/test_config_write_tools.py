"""Tests for configuration-write tools: subnet create/update, storage container
create/resize.

All v4 mutating operations must pass the ETag from a preceding GET as
if_match — Nutanix rejects mutations without it (HTTP 428).
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from nutanix_mcp.tools.cluster import (
    handle_create_storage_container,
    handle_delete_storage_container,
    handle_resize_storage_container,
)
from nutanix_mcp.tools.networking import (
    handle_create_subnet,
    handle_delete_subnet,
    handle_update_subnet,
)

_GIB = 1024**3

# The SDK models validate that reference fields are real UUIDs.
CLUSTER_UUID = "0006568f-63fb-79aa-274f-3805253a7444"
SUBNET_UUID = "57b75e22-4660-4323-af32-fe0cf9a0ca3c"
CONTAINER_UUID = "64a76b64-eeb8-4bec-8e29-f39bfec00776"


@pytest.fixture
def mock_client():
    client = MagicMock()
    sdk = MagicMock()
    sdk.call = AsyncMock()
    sdk.get_etag = MagicMock(return_value="etag-1")
    client.sdk = sdk
    return client


def _task_response(task_uuid: str) -> MagicMock:
    task_obj = MagicMock()
    task_obj.ext_id = task_uuid
    response = MagicMock()
    response.data = task_obj
    return response


# ─── create_subnet ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_subnet_vlan_only(mock_client):
    """A minimal VLAN subnet sets name, type, network_id, and cluster ref; no ip_config."""
    mock_client.sdk.call.return_value = _task_response("task-1")

    result = await handle_create_subnet(
        mock_client,
        {"name": "prod-vlan", "cluster_uuid": CLUSTER_UUID, "vlan_id": 100},
    )

    assert result["status"] == "subnet_creation_initiated"
    assert result["taskExtId"] == "task-1"

    # Inspect the Subnet model passed to create_subnet.
    create_call = mock_client.sdk.call.call_args
    subnet = create_call.args[1]
    assert subnet.name == "prod-vlan"
    assert subnet.subnet_type == "VLAN"
    assert subnet.network_id == 100
    assert subnet.cluster_reference == CLUSTER_UUID  # plain extId string
    assert subnet.ip_config is None or subnet.ip_config == []


@pytest.mark.asyncio
async def test_create_subnet_with_ipam(mock_client):
    """Providing a CIDR builds an IPv4 ip_config with gateway and pool."""
    mock_client.sdk.call.return_value = _task_response("task-2")

    result = await handle_create_subnet(
        mock_client,
        {
            "name": "managed",
            "cluster_uuid": CLUSTER_UUID,
            "vlan_id": 50,
            "network_cidr": "10.0.1.0/24",
            "gateway_ip": "10.0.1.1",
            "dhcp_pool_start": "10.0.1.100",
            "dhcp_pool_end": "10.0.1.200",
        },
    )

    assert result["status"] == "subnet_creation_initiated"
    subnet = mock_client.sdk.call.call_args.args[1]
    assert len(subnet.ip_config) == 1
    ipv4 = subnet.ip_config[0].ipv4
    assert ipv4.ip_subnet.ip.value == "10.0.1.0"
    assert ipv4.ip_subnet.prefix_length == 24
    assert ipv4.default_gateway_ip.value == "10.0.1.1"
    assert ipv4.pool_list[0].start_ip.value == "10.0.1.100"
    assert ipv4.pool_list[0].end_ip.value == "10.0.1.200"


# ─── update_subnet ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_update_subnet_passes_etag(mock_client):
    """update_subnet fetches current state, applies changes, and updates with if_match."""
    subnet_obj = MagicMock()
    subnet_obj.name = "old"
    subnet_obj.network_id = 10
    get_response = MagicMock()
    get_response.data = subnet_obj

    mock_client.sdk.call.side_effect = [get_response, _task_response("task-3")]

    result = await handle_update_subnet(
        mock_client,
        {"subnet_uuid": SUBNET_UUID, "name": "new", "vlan_id": 20},
    )

    assert result["status"] == "subnet_update_initiated"
    assert subnet_obj.name == "new"
    assert subnet_obj.network_id == 20
    update_call = mock_client.sdk.call.call_args_list[1]
    assert update_call.kwargs["if_match"] == "etag-1"
    assert update_call.args[1] == SUBNET_UUID  # extId positional


# ─── create_storage_container ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_storage_container_minimal(mock_client):
    """A minimal container sets name + cluster and passes the X-Cluster-Id header."""
    mock_client.sdk.call.return_value = _task_response("task-4")

    result = await handle_create_storage_container(
        mock_client,
        {"name": "ct-new", "cluster_uuid": CLUSTER_UUID},
    )

    assert result["status"] == "storage_container_creation_initiated"
    assert result["taskExtId"] == "task-4"

    create_call = mock_client.sdk.call.call_args
    sc = create_call.args[1]
    assert sc.name == "ct-new"
    assert sc.cluster_ext_id == CLUSTER_UUID
    assert create_call.kwargs["X_Cluster_Id"] == CLUSTER_UUID


@pytest.mark.asyncio
async def test_create_storage_container_with_capacity(mock_client):
    """Capacity args are converted from GiB to bytes."""
    mock_client.sdk.call.return_value = _task_response("task-5")

    await handle_create_storage_container(
        mock_client,
        {
            "name": "ct",
            "cluster_uuid": CLUSTER_UUID,
            "replication_factor": 2,
            "advertised_capacity_gb": 100,
            "reserved_capacity_gb": 10,
            "compression_enabled": True,
        },
    )

    sc = mock_client.sdk.call.call_args.args[1]
    assert sc.replication_factor == 2
    assert sc.logical_advertised_capacity_bytes == 100 * _GIB
    assert sc.logical_explicit_reserved_capacity_bytes == 10 * _GIB
    assert sc.is_compression_enabled is True


# ─── resize_storage_container ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_resize_storage_container_passes_etag(mock_client):
    """resize fetches current state, applies capacity change, and updates with if_match."""
    sc_obj = MagicMock()
    get_response = MagicMock()
    get_response.data = sc_obj

    mock_client.sdk.call.side_effect = [get_response, _task_response("task-6")]

    result = await handle_resize_storage_container(
        mock_client,
        {"container_uuid": CONTAINER_UUID, "advertised_capacity_gb": 500},
    )

    assert result["status"] == "storage_container_update_initiated"
    assert sc_obj.logical_advertised_capacity_bytes == 500 * _GIB
    update_call = mock_client.sdk.call.call_args_list[1]
    assert update_call.kwargs["if_match"] == "etag-1"
    assert update_call.args[1] == CONTAINER_UUID


# ─── delete guards + ETag ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_delete_subnet_without_confirm(mock_client):
    """delete_subnet refuses without confirm=True and makes no SDK call."""
    result = await handle_delete_subnet(mock_client, {"subnet_uuid": SUBNET_UUID, "confirm": False})

    assert result["status"] == "error"
    assert "confirm" in result["message"].lower()
    mock_client.sdk.call.assert_not_called()


@pytest.mark.asyncio
async def test_delete_subnet_with_confirm(mock_client):
    """delete_subnet fetches the ETag then deletes with if_match."""
    mock_client.sdk.call.side_effect = [MagicMock(), _task_response("task-7")]

    result = await handle_delete_subnet(mock_client, {"subnet_uuid": SUBNET_UUID, "confirm": True})

    assert result["status"] == "subnet_deletion_initiated"
    assert result["taskExtId"] == "task-7"
    delete_call = mock_client.sdk.call.call_args_list[1]
    assert delete_call.kwargs["if_match"] == "etag-1"
    assert delete_call.args[1] == SUBNET_UUID


@pytest.mark.asyncio
async def test_delete_storage_container_without_confirm(mock_client):
    """delete_storage_container refuses without confirm=True."""
    result = await handle_delete_storage_container(
        mock_client, {"container_uuid": CONTAINER_UUID, "confirm": False}
    )

    assert result["status"] == "error"
    mock_client.sdk.call.assert_not_called()


@pytest.mark.asyncio
async def test_delete_storage_container_with_confirm(mock_client):
    """delete_storage_container fetches the ETag then deletes with if_match."""
    mock_client.sdk.call.side_effect = [MagicMock(), _task_response("task-8")]

    result = await handle_delete_storage_container(
        mock_client, {"container_uuid": CONTAINER_UUID, "confirm": True, "ignore_small_files": True}
    )

    assert result["status"] == "storage_container_deletion_initiated"
    delete_call = mock_client.sdk.call.call_args_list[1]
    assert delete_call.kwargs["if_match"] == "etag-1"
    assert delete_call.kwargs["ignoreSmallFiles"] is True
