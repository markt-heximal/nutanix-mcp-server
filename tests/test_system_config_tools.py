"""Tests for system configuration tools (Issue #16)."""

from unittest.mock import AsyncMock

import pytest

from nutanix_mcp.tools.prism_element import (
    handle_pe_get_alert_email_config,
    handle_pe_get_auth_config,
    handle_pe_get_licensing_info,
    handle_pe_get_nfs_whitelists,
    handle_pe_get_smtp_config,
    handle_pe_get_snmp_config,
    handle_pe_get_syslog_config,
)


@pytest.fixture
def mock_client():
    client = AsyncMock()
    return client


@pytest.mark.asyncio
async def test_get_auth_config(mock_client):
    """Test retrieving authentication configuration."""
    mock_client.pe_get.return_value = {
        "authTypeList": ["LOCAL", "LDAP"],
        "directoryList": [
            {
                "name": "corp-ad",
                "directory_type": "ACTIVE_DIRECTORY",
                "domain": "corp.example.com",
                "directory_url": "ldaps://ad.corp.example.com:636",
                "connection_type": "LDAP",
                "group_search_type": "RECURSIVE",
            }
        ],
        "clientAuth": "NONE",
    }

    result = await handle_pe_get_auth_config(mock_client, {"pe_host": "10.0.0.1"})

    assert result["authTypes"] == ["LOCAL", "LDAP"]
    assert len(result["directories"]) == 1
    assert result["directories"][0]["name"] == "corp-ad"
    assert result["directories"][0]["directoryType"] == "ACTIVE_DIRECTORY"
    assert result["directories"][0]["domain"] == "corp.example.com"
    mock_client.pe_get.assert_called_once_with("10.0.0.1", "authconfig")


@pytest.mark.asyncio
async def test_get_smtp_config(mock_client):
    """Test retrieving SMTP configuration."""
    mock_client.pe_get.return_value = {
        "address": "smtp.corp.example.com",
        "port": 587,
        "username": "alerts@corp.example.com",
        "secure_mode": "STARTTLS",
        "from_email_address": "nutanix@corp.example.com",
        "email_status": "VERIFIED",
    }

    result = await handle_pe_get_smtp_config(mock_client, {"pe_host": "10.0.0.1"})

    assert result["address"] == "smtp.corp.example.com"
    assert result["port"] == 587
    assert result["secureMode"] == "STARTTLS"
    assert result["fromEmailAddress"] == "nutanix@corp.example.com"
    mock_client.pe_get.assert_called_once_with("10.0.0.1", "cluster/smtp")


@pytest.mark.asyncio
async def test_get_snmp_config(mock_client):
    """Test retrieving SNMP configuration."""
    mock_client.pe_get.return_value = {
        "enabled": True,
        "trap_list": [
            {
                "address": "10.1.1.100",
                "port": 162,
                "community_string": "public",
                "version": "V2C",
                "inform": False,
            }
        ],
        "user_list": [
            {
                "username": "snmpuser",
                "auth_type": "SHA",
                "priv_type": "AES",
            }
        ],
        "transport_list": [
            {
                "port": 161,
                "protocol": "UDP",
            }
        ],
    }

    result = await handle_pe_get_snmp_config(mock_client, {"pe_host": "10.0.0.1"})

    assert result["enabled"] is True
    assert len(result["traps"]) == 1
    assert result["traps"][0]["address"] == "10.1.1.100"
    assert result["traps"][0]["version"] == "V2C"
    assert len(result["users"]) == 1
    assert result["users"][0]["username"] == "snmpuser"
    assert len(result["transports"]) == 1
    mock_client.pe_get.assert_called_once_with("10.0.0.1", "snmp")


@pytest.mark.asyncio
async def test_get_syslog_config_none_configured(mock_client):
    """A cluster with no syslog servers.

    Response body captured verbatim from AOS 6.8.1. There is no v1 or v2 route
    for this entity — every documented remote_syslog_servers / rsyslog_configs
    path returns 404 — so the handler goes through the v3 groups API.
    """
    mock_client.pe_v3_groups.return_value = {
        "entity_type": "remote_syslog_server",
        "filtered_group_count": 0,
        "filtered_entity_count": 0,
        "group_results": [],
        "total_entity_count": 0,
        "total_group_count": 0,
    }

    result = await handle_pe_get_syslog_config(mock_client, {"pe_host": "10.0.0.1"})

    assert result == {"count": 0, "servers": []}
    mock_client.pe_v3_groups.assert_called_once_with("10.0.0.1", "remote_syslog_server")


@pytest.mark.asyncio
async def test_get_syslog_config_populated(mock_client):
    """A cluster with a syslog server configured.

    The envelope is the standard v3 groups column format. This lab cluster has
    no syslog server, so the populated case is covered against that documented
    shape rather than a captured payload — attribute names are passed through
    verbatim precisely because they cannot be verified here.
    """
    mock_client.pe_v3_groups.return_value = {
        "entity_type": "remote_syslog_server",
        "group_results": [
            {
                "entity_results": [
                    {
                        "entity_id": "syslog-1",
                        "data": [
                            {"name": "server_name", "values": [{"values": ["syslog-prod"]}]},
                            {"name": "ip_address", "values": [{"values": ["10.2.0.50"]}]},
                            {"name": "port", "values": [{"values": ["514"]}]},
                            {"name": "network_protocol", "values": [{"values": ["UDP"]}]},
                            {"name": "module_list", "values": [{"values": ["ACROPOLIS", "GENESIS"]}]},
                        ],
                    }
                ]
            }
        ],
    }

    result = await handle_pe_get_syslog_config(mock_client, {"pe_host": "10.0.0.1"})

    assert result["count"] == 1
    server = result["servers"][0]
    assert server["entityId"] == "syslog-1"
    assert server["server_name"] == "syslog-prod"
    assert server["ip_address"] == "10.2.0.50"
    assert server["network_protocol"] == "UDP"
    # Multi-valued attributes stay as lists; single values are unwrapped.
    assert server["module_list"] == ["ACROPOLIS", "GENESIS"]


@pytest.mark.asyncio
async def test_get_alert_email_config(mock_client):
    """Test retrieving alert email configuration."""
    mock_client.pe_get.return_value = {
        "email_contact_list": ["ops@corp.example.com", "admin@corp.example.com"],
        "enable": True,
        "enable_default_nutanix_email": False,
        "enable_email_digest": True,
    }

    result = await handle_pe_get_alert_email_config(mock_client, {"pe_host": "10.0.0.1"})

    assert result["emailContactList"] == ["ops@corp.example.com", "admin@corp.example.com"]
    assert result["enable"] is True
    assert result["enableDefaultNutanixEmail"] is False
    assert result["enableEmailDigest"] is True
    mock_client.pe_get.assert_called_once_with("10.0.0.1", "alerts/configuration")


@pytest.mark.asyncio
async def test_get_nfs_whitelists(mock_client):
    """Test retrieving NFS whitelist configuration."""
    mock_client.pe_get.return_value = ["10.0.0.0/24", "192.168.1.0/24", "10.1.0.100"]

    result = await handle_pe_get_nfs_whitelists(mock_client, {"pe_host": "10.0.0.1"})

    assert result["count"] == 3
    assert "10.0.0.0/24" in result["whitelists"]
    assert "192.168.1.0/24" in result["whitelists"]
    mock_client.pe_get.assert_called_once_with("10.0.0.1", "cluster/nfs_whitelist")


def _allowance(display_name, enabled):
    """Build one allowanceMap entry in the shape v1/license actually returns."""
    return {
        "allowancesType": "BOOLEAN",
        "boolValue": {
            "allowanceType": "BOOLEAN",
            "boolValue": enabled,
            "intValue": None,
            "violationAction": "Warn",
        },
        "displayName": display_name,
        "clusterUuids": None,
    }


@pytest.mark.asyncio
async def test_get_licensing_info(mock_client):
    """v1/license nests everything under licenseDTO.

    The previous fixture asserted a flat schema with license_type /
    expiry_date / enabled_feature_list -- none of which the API returns. It
    passed while every real call produced all-None. Shape below is captured
    from a live AOS 6.8.1 cluster.
    """
    mock_client.pe_v1_get.return_value = {
        "actionMetadata": {},
        "complianceDetails": {},
        "licenseInfoDTO": {},
        "licenseDTO": {
            "category": "Community",
            "subCategory": "",
            "licenseClass": "appliance",
            "clusterExpiryUsecs": 0,
            "allowanceMap": {
                "SNMP": _allowance("SNMP", True),
                "OFFLINE_COMPRESSION": _allowance("Post-process Compression", True),
                "METRO_AVAILABILITY": _allowance("Metro Availability", False),
            },
        },
    }

    result = await handle_pe_get_licensing_info(mock_client, {"pe_host": "10.0.0.1"})

    assert result["category"] == "Community"
    assert result["licenseClass"] == "appliance"
    assert result["clusterExpiryUsecs"] == 0
    # Enabled features come from allowanceMap, keyed on the nested boolValue.
    assert result["enabledFeatures"] == ["Post-process Compression", "SNMP"]
    assert "Metro Availability" not in result["enabledFeatures"]
    mock_client.pe_v1_get.assert_called_once_with("10.0.0.1", "license")


@pytest.mark.asyncio
async def test_get_licensing_info_missing_dto(mock_client):
    """A payload without licenseDTO must degrade, not raise."""
    mock_client.pe_v1_get.return_value = {"complianceDetails": {}}

    result = await handle_pe_get_licensing_info(mock_client, {"pe_host": "10.0.0.1"})

    assert result["category"] is None
    assert result["enabledFeatures"] == []
