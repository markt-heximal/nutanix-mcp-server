"""Tests for Prism Element write tools: cluster services (SMTP/DNS/NTP) and
data protection (protection domains).

These hit PE v2 endpoints via the pe_put / pe_post / pe_delete client helpers.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from nutanix_mcp.tools.prism_element import (
    handle_pe_add_dns_servers,
    handle_pe_add_ntp_servers,
    handle_pe_create_pd_snapshot,
    handle_pe_create_protection_domain,
    handle_pe_delete_protection_domain,
    handle_pe_protect_vms,
    handle_pe_remove_dns_servers,
    handle_pe_set_smtp_config,
)

PE = "10.0.1.242"


@pytest.fixture
def mock_client():
    client = MagicMock()
    client.pe_put = AsyncMock(return_value={"status": "ok"})
    client.pe_post = AsyncMock(return_value={"status": "ok"})
    client.pe_delete = AsyncMock(return_value={"status": "ok"})
    return client


# ─── Cluster services ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_set_smtp_config(mock_client):
    result = await handle_pe_set_smtp_config(
        mock_client,
        {
            "pe_host": PE,
            "address": "smtp.example.com",
            "port": 587,
            "from_email_address": "cluster@example.com",
            "secure_mode": "STARTTLS",
            "username": "u",
            "password": "p",
        },
    )
    assert result["status"] == "smtp_config_updated"
    call = mock_client.pe_put.call_args
    assert call.args[0] == PE
    assert call.args[1] == "cluster/smtp"
    body = call.kwargs["body"]
    assert body["address"] == "smtp.example.com"
    assert body["port"] == 587
    assert body["secure_mode"] == "STARTTLS"
    assert body["from_email_address"] == "cluster@example.com"


@pytest.mark.asyncio
async def test_set_smtp_config_defaults_secure_mode(mock_client):
    await handle_pe_set_smtp_config(
        mock_client, {"pe_host": PE, "address": "smtp.local", "port": 25}
    )
    body = mock_client.pe_put.call_args.kwargs["body"]
    assert body["secure_mode"] == "NONE"
    assert "username" not in body  # omitted when not provided


@pytest.mark.asyncio
async def test_add_dns_servers(mock_client):
    result = await handle_pe_add_dns_servers(
        mock_client, {"pe_host": PE, "servers": ["8.8.8.8", "1.1.1.1"]}
    )
    assert result["status"] == "dns_servers_added"
    call = mock_client.pe_post.call_args
    assert call.args[1] == "cluster/name_servers/add_list"
    assert call.kwargs["body"] == ["8.8.8.8", "1.1.1.1"]


@pytest.mark.asyncio
async def test_remove_dns_servers(mock_client):
    result = await handle_pe_remove_dns_servers(
        mock_client, {"pe_host": PE, "servers": ["8.8.8.8"]}
    )
    assert result["status"] == "dns_servers_removed"
    call = mock_client.pe_post.call_args
    assert call.args[1] == "cluster/name_servers/remove_list"
    assert call.kwargs["body"] == ["8.8.8.8"]


@pytest.mark.asyncio
async def test_add_ntp_servers(mock_client):
    await handle_pe_add_ntp_servers(mock_client, {"pe_host": PE, "servers": ["pool.ntp.org"]})
    call = mock_client.pe_post.call_args
    assert call.args[1] == "cluster/ntp_servers/add_list"
    assert call.kwargs["body"] == ["pool.ntp.org"]


# ─── Data protection ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_protection_domain(mock_client):
    result = await handle_pe_create_protection_domain(
        mock_client, {"pe_host": PE, "name": "pd-prod"}
    )
    assert result["status"] == "protection_domain_created"
    call = mock_client.pe_post.call_args
    assert call.args[1] == "protection_domains"
    assert call.kwargs["body"] == {"value": "pd-prod"}


@pytest.mark.asyncio
async def test_protect_vms(mock_client):
    result = await handle_pe_protect_vms(
        mock_client, {"pe_host": PE, "pd_name": "pd-prod", "vm_names": ["vm1", "vm2"]}
    )
    assert result["status"] == "vms_protected"
    call = mock_client.pe_post.call_args
    assert call.args[1] == "protection_domains/pd-prod/protect_vms"
    assert call.kwargs["body"] == {"names": ["vm1", "vm2"]}


@pytest.mark.asyncio
async def test_create_pd_snapshot_with_retention(mock_client):
    await handle_pe_create_pd_snapshot(
        mock_client, {"pe_host": PE, "pd_name": "pd-prod", "retention_seconds": 3600}
    )
    call = mock_client.pe_post.call_args
    assert call.args[1] == "protection_domains/pd-prod/oob_schedules"
    assert call.kwargs["body"] == {"snapshot_retention_time_secs": 3600}


@pytest.mark.asyncio
async def test_delete_protection_domain_requires_confirm(mock_client):
    result = await handle_pe_delete_protection_domain(
        mock_client, {"pe_host": PE, "pd_name": "pd-prod", "confirm": False}
    )
    assert result["status"] == "error"
    mock_client.pe_delete.assert_not_called()


@pytest.mark.asyncio
async def test_delete_protection_domain_with_confirm(mock_client):
    result = await handle_pe_delete_protection_domain(
        mock_client, {"pe_host": PE, "pd_name": "pd-prod", "confirm": True}
    )
    assert result["status"] == "protection_domain_deleted"
    call = mock_client.pe_delete.call_args
    assert call.args[1] == "protection_domains/pd-prod"
