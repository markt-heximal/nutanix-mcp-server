"""Tests for centralized alert management tools."""

from unittest.mock import AsyncMock

import pytest

from nutanix_mcp.tools.alert import (
    handle_acknowledge_alert,
    handle_get_alert,
    handle_list_alerts,
)


@pytest.fixture
def mock_client():
    client = AsyncMock()
    return client


@pytest.mark.asyncio
async def test_list_alerts_default(mock_client):
    """Test listing active alerts (default filter)."""
    mock_client.v4_list.return_value = {
        "data": [
            {
                "extId": "alert-1",
                "title": "Disk failure detected",
                "severity": "CRITICAL",
                "isResolved": False,
                "isAcknowledged": False,
                "creationTime": "2026-05-07T10:00:00Z",
                "lastUpdatedTime": "2026-05-07T10:05:00Z",
                "affectedEntities": [{"type": "host", "name": "host-01", "extId": "host-uuid-1"}],
                "sourceClusterUUID": "cluster-uuid-1",
            },
        ]
    }

    result = await handle_list_alerts(mock_client, {})

    assert result["total_alerts"] == 1
    assert result["alerts"][0]["title"] == "Disk failure detected"
    assert result["alerts"][0]["severity"] == "CRITICAL"
    assert "isResolved eq false" in result["filter_applied"]


@pytest.mark.asyncio
async def test_list_alerts_with_severity_filter(mock_client):
    """Test listing alerts filtered by severity."""
    mock_client.v4_list.return_value = {"data": []}

    await handle_list_alerts(
        mock_client,
        {
            "severity": "WARNING",
            "limit": 10,
        },
    )

    call_args = mock_client.v4_list.call_args
    filter_used = call_args.kwargs["filter"]
    assert "severity eq 'WARNING'" in filter_used
    assert "isResolved eq false" in filter_used
    assert call_args.kwargs["top"] == 10


@pytest.mark.asyncio
async def test_get_alert(mock_client):
    """Test getting alert details."""
    mock_client.v4_get.return_value = {
        "data": {
            "extId": "alert-uuid-123",
            "title": "Storage capacity warning",
            "severity": "WARNING",
            "message": "Container is 85% full",
            "isResolved": False,
            "isAcknowledged": False,
            "creationTime": "2026-05-07T10:00:00Z",
            "lastUpdatedTime": "2026-05-07T10:00:00Z",
            "resolutionTime": "",
            "affectedEntities": [
                {"type": "storage_container", "name": "default", "extId": "sc-1"},
            ],
            "sourceClusterUUID": "cluster-1",
            "alertType": "STORAGE",
            "parameters": [{"key": "usage_pct", "value": "85"}],
            "possibleCauses": ["High VM disk usage"],
            "resolutions": ["Expand storage or delete unused VMs"],
        }
    }

    result = await handle_get_alert(mock_client, {"alert_uuid": "alert-uuid-123"})

    assert result["alert_uuid"] == "alert-uuid-123"
    assert result["message"] == "Container is 85% full"
    assert result["affected_entities"][0]["type"] == "storage_container"
    assert result["possible_causes"] == ["High VM disk usage"]
    assert result["resolutions"] == ["Expand storage or delete unused VMs"]


@pytest.mark.asyncio
async def test_acknowledge_alert(mock_client):
    """Test acknowledging an alert (ETag from response header)."""
    mock_client.v4_get_with_etag.return_value = (
        {"data": {"extId": "alert-uuid-123"}},
        "etag-value-1",
    )
    mock_client.v4_post.return_value = {"data": {"extId": "alert-uuid-123"}}

    result = await handle_acknowledge_alert(
        mock_client,
        {
            "alert_uuid": "alert-uuid-123",
            "action": "ACKNOWLEDGE",
        },
    )

    assert result["status"] == "alert_acknowledged"
    assert result["alert_uuid"] == "alert-uuid-123"

    # Verify POST hit the acknowledge $action endpoint with the ETag
    post_call = mock_client.v4_post.call_args
    assert post_call.kwargs["namespace"] == "monitoring"
    assert post_call.kwargs["path"] == "serviceability/alerts/alert-uuid-123/$actions/acknowledge"
    assert post_call.kwargs["headers"]["If-Match"] == "etag-value-1"


@pytest.mark.asyncio
async def test_resolve_alert(mock_client):
    """Test resolving an alert (ETag falls back to body $metadata when header absent)."""
    mock_client.v4_get_with_etag.return_value = (
        {
            "data": {
                "extId": "alert-uuid-456",
                "$metadata": {"ETag": "etag-2"},
            }
        },
        None,
    )
    mock_client.v4_post.return_value = {"data": {"extId": "alert-uuid-456"}}

    result = await handle_acknowledge_alert(
        mock_client,
        {
            "alert_uuid": "alert-uuid-456",
            "action": "RESOLVE",
        },
    )

    assert result["status"] == "alert_resolved"
    post_call = mock_client.v4_post.call_args
    assert post_call.kwargs["path"] == "serviceability/alerts/alert-uuid-456/$actions/resolve"
    assert post_call.kwargs["headers"]["If-Match"] == "etag-2"
