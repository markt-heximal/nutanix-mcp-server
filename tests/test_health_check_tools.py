"""Tests for health check tools (Issue #20)."""

from unittest.mock import AsyncMock

import pytest

from nutanix_mcp.tools.prism_element import (
    handle_pe_get_cluster_health,
    handle_pe_list_health_checks,
)


@pytest.fixture
def mock_client():
    client = AsyncMock()
    return client


# Captured verbatim from a live AOS 6.8.1 cluster. The endpoint returns a BARE
# LIST, and each component map is keyed by UPPERCASE component name. The previous
# fixture invented a dict wrapper with lowercase "static_configuration" keys, so
# the suite passed green while every real call raised
# AttributeError: 'list' object has no attribute 'get'.
LIVE_FAULT_TOLERANCE_RESPONSE = [
    {
        "domain_type": "NODE",
        "component_fault_tolerance_status": {
            "STATIC_CONFIGURATION": {
                "component_type": "STATIC_CONFIGURATION",
                "number_of_failures_tolerable": 0,
                "details": {
                    "message": "Not enough nodes (hosts) in the cluster",
                    "attributes": {},
                },
                "under_computation": False,
                "last_updated_time_in_usecs": 1784023938000000,
            },
            "FREE_SPACE": {
                "component_type": "FREE_SPACE",
                "number_of_failures_tolerable": 0,
                "details": {
                    "message": "Cluster does not have enough capacity to tolerate a node failure",
                    "attributes": {},
                },
                "under_computation": False,
                "last_updated_time_in_usecs": 1786893399000000,
            },
        },
        "cluster_under_replicated_data_bytes": 0,
        "cluster_non_fault_tolerant_entries": 0,
    },
    {
        "domain_type": "DISK",
        "component_fault_tolerance_status": {
            "EXTENT_GROUPS": {
                "component_type": "EXTENT_GROUPS",
                "number_of_failures_tolerable": 1,
                # Healthy components report details as null.
                "details": None,
                "under_computation": False,
                "last_updated_time_in_usecs": 1786890305000000,
            },
            "METADATA": {
                "component_type": "METADATA",
                "number_of_failures_tolerable": 2,
                "details": None,
                "under_computation": False,
                "last_updated_time_in_usecs": 1784023960000000,
            },
        },
        "cluster_under_replicated_data_bytes": 0,
        "cluster_non_fault_tolerant_entries": 0,
    },
]


@pytest.mark.asyncio
async def test_get_cluster_health_bare_list(mock_client):
    """The v2 endpoint returns a bare list — this must not raise."""
    mock_client.pe_get.return_value = LIVE_FAULT_TOLERANCE_RESPONSE

    result = await handle_pe_get_cluster_health(mock_client, {"pe_host": "10.0.0.1"})

    assert result["count"] == 2
    assert len(result["faultToleranceStatus"]) == 2

    node = result["faultToleranceStatus"][0]
    assert node["domainType"] == "NODE"
    assert node["minFailuresTolerable"] == 0
    assert node["underReplicatedDataBytes"] == 0
    assert node["nonFaultTolerantEntries"] == 0
    # Components are sorted by type: FREE_SPACE before STATIC_CONFIGURATION.
    assert [c["componentType"] for c in node["components"]] == [
        "FREE_SPACE",
        "STATIC_CONFIGURATION",
    ]
    assert node["components"][1]["message"] == "Not enough nodes (hosts) in the cluster"
    assert node["components"][1]["underComputation"] is False

    disk = result["faultToleranceStatus"][1]
    assert disk["domainType"] == "DISK"
    # Weakest component wins: EXTENT_GROUPS tolerates 1, METADATA tolerates 2.
    assert disk["minFailuresTolerable"] == 1
    # details=None must degrade to a null message, not raise.
    assert all(c["message"] is None for c in disk["components"])

    mock_client.pe_get.assert_called_once_with("10.0.0.1", "cluster/domain_fault_tolerance_status")


@pytest.mark.asyncio
async def test_get_cluster_health_dict_wrapped(mock_client):
    """Some AOS versions wrap the list in a dict — both shapes must work."""
    mock_client.pe_get.return_value = {
        "domain_fault_tolerance_status": LIVE_FAULT_TOLERANCE_RESPONSE
    }

    result = await handle_pe_get_cluster_health(mock_client, {"pe_host": "10.0.0.1"})

    assert result["count"] == 2
    assert result["faultToleranceStatus"][0]["domainType"] == "NODE"
    assert result["faultToleranceStatus"][1]["minFailuresTolerable"] == 1


@pytest.mark.asyncio
async def test_get_cluster_health_empty(mock_client):
    """An empty list is a valid response, not an error."""
    mock_client.pe_get.return_value = []

    result = await handle_pe_get_cluster_health(mock_client, {"pe_host": "10.0.0.1"})

    assert result == {"count": 0, "faultToleranceStatus": []}


@pytest.mark.asyncio
async def test_list_health_checks(mock_client):
    """Test listing health check results."""
    mock_client.pe_list.return_value = {
        "entities": [
            {
                "id": "hc-001",
                "name": "CVM Memory Usage",
                "description": "Checks if CVM memory usage exceeds threshold",
                "affected_entity_types": ["CVM"],
                "check_type": "RESOURCE",
                "severity": "WARNING",
                "last_execution_status": "PASS",
                "last_passed_time_stamp_in_usecs": 1700000000000000,
            },
            {
                "id": "hc-002",
                "name": "Disk Space Usage",
                "description": "Checks cluster disk space utilization",
                "affected_entity_types": ["DISK"],
                "check_type": "CAPACITY",
                "severity": "CRITICAL",
                "last_execution_status": "PASS",
                "last_passed_time_stamp_in_usecs": 1700000000000000,
            },
        ]
    }

    result = await handle_pe_list_health_checks(mock_client, {"pe_host": "10.0.0.1"})

    assert result["count"] == 2
    assert result["healthChecks"][0]["name"] == "CVM Memory Usage"
    assert result["healthChecks"][0]["severity"] == "WARNING"
    assert result["healthChecks"][0]["lastExecutionStatus"] == "PASS"
    assert result["healthChecks"][1]["checkType"] == "CAPACITY"
    mock_client.pe_list.assert_called_once_with("10.0.0.1", "health_checks")
