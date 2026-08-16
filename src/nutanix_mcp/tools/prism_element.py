"""Prism Element tools using Nutanix v2.0 API (direct cluster access).

These tools connect directly to individual Prism Element CVMs,
which are discovered via Prism Central's cluster list.
"""

from typing import Any

from nutanix_mcp.client import NutanixClient

# ─── Tool Definitions ─────────────────────────────────────────────────────────

PE_TOOLS: list[dict] = [
    {
        "name": "pe_get_cluster_info",
        "description": (
            "Get cluster info directly from a Prism Element node. "
            "Returns AOS version, cluster name, storage capacity, and health."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "pe_host": {
                    "type": "string",
                    "description": "Prism Element CVM IP address or hostname",
                },
            },
            "required": ["pe_host"],
        },
    },
    {
        "name": "pe_list_vms",
        "description": (
            "List VMs on a specific Prism Element cluster. "
            "Returns VM names, UUIDs, power states, and resource allocation."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "pe_host": {
                    "type": "string",
                    "description": "Prism Element CVM IP address or hostname",
                },
                "count": {
                    "type": "integer",
                    "description": "Maximum number of VMs to return",
                },
            },
            "required": ["pe_host"],
        },
    },
    {
        "name": "pe_list_hosts",
        "description": (
            "List hypervisor hosts on a Prism Element cluster. Returns host names, IPs, hardware specs, and CVM info."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "pe_host": {
                    "type": "string",
                    "description": "Prism Element CVM IP address or hostname",
                },
            },
            "required": ["pe_host"],
        },
    },
    {
        "name": "pe_list_containers",
        "description": (
            "List storage containers on a Prism Element cluster. "
            "Returns names, capacity, usage, replication factor, and policies."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "pe_host": {
                    "type": "string",
                    "description": "Prism Element CVM IP address or hostname",
                },
            },
            "required": ["pe_host"],
        },
    },
    {
        "name": "pe_list_storage_pools",
        "description": (
            "List storage pools on a Prism Element cluster. Returns pool names, capacity, and disk composition."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "pe_host": {
                    "type": "string",
                    "description": "Prism Element CVM IP address or hostname",
                },
            },
            "required": ["pe_host"],
        },
    },
    {
        "name": "pe_list_disks",
        "description": (
            "List physical disks on a Prism Element cluster. "
            "Returns disk type (SSD/HDD), status, capacity, and location."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "pe_host": {
                    "type": "string",
                    "description": "Prism Element CVM IP address or hostname",
                },
            },
            "required": ["pe_host"],
        },
    },
    {
        "name": "pe_list_alerts",
        "description": (
            "List alerts on a Prism Element cluster. Returns alert titles, severity, timestamps, and affected entities."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "pe_host": {
                    "type": "string",
                    "description": "Prism Element CVM IP address or hostname",
                },
                "resolved": {
                    "type": "boolean",
                    "description": "Include resolved alerts (default: false, only active)",
                    "default": False,
                },
                "count": {
                    "type": "integer",
                    "description": "Maximum number of alerts to return (default: 50)",
                    "default": 50,
                },
            },
            "required": ["pe_host"],
        },
    },
    {
        "name": "pe_list_protection_domains",
        "description": (
            "List protection domains on a Prism Element cluster. "
            "Returns PD names, protected entities, schedules, and replication state."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "pe_host": {
                    "type": "string",
                    "description": "Prism Element CVM IP address or hostname",
                },
            },
            "required": ["pe_host"],
        },
    },
    {
        "name": "pe_list_snapshots",
        "description": ("List snapshots for a protection domain on a Prism Element cluster."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "pe_host": {
                    "type": "string",
                    "description": "Prism Element CVM IP address or hostname",
                },
                "protection_domain": {
                    "type": "string",
                    "description": "Name of the protection domain",
                },
            },
            "required": ["pe_host", "protection_domain"],
        },
    },
    # ─── System Configuration Tools (Issue #16) ───────────────────────────
    {
        "name": "pe_get_auth_config",
        "description": (
            "Get authentication configuration from a Prism Element cluster. "
            "Returns auth types, directory services (LDAP/AD), and local account settings."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "pe_host": {
                    "type": "string",
                    "description": "Prism Element CVM IP address or hostname",
                },
            },
            "required": ["pe_host"],
        },
    },
    {
        "name": "pe_get_smtp_config",
        "description": (
            "Get SMTP server configuration from a Prism Element cluster. "
            "Returns relay server, port, sender address, and security settings."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "pe_host": {
                    "type": "string",
                    "description": "Prism Element CVM IP address or hostname",
                },
            },
            "required": ["pe_host"],
        },
    },
    {
        "name": "pe_get_snmp_config",
        "description": (
            "Get SNMP configuration from a Prism Element cluster. "
            "Returns SNMP traps, transports, users, and community strings."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "pe_host": {
                    "type": "string",
                    "description": "Prism Element CVM IP address or hostname",
                },
            },
            "required": ["pe_host"],
        },
    },
    {
        "name": "pe_get_syslog_config",
        "description": (
            "Get remote syslog server configuration from a Prism Element cluster. "
            "Returns syslog targets, protocols, ports, and severity levels."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "pe_host": {
                    "type": "string",
                    "description": "Prism Element CVM IP address or hostname",
                },
            },
            "required": ["pe_host"],
        },
    },
    {
        "name": "pe_get_alert_email_config",
        "description": (
            "Get alert email notification configuration from a Prism Element cluster. "
            "Returns email recipients and alert notification rules."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "pe_host": {
                    "type": "string",
                    "description": "Prism Element CVM IP address or hostname",
                },
            },
            "required": ["pe_host"],
        },
    },
    {
        "name": "pe_get_nfs_whitelists",
        "description": (
            "Get global NFS whitelist configuration from a Prism Element cluster. "
            "Returns filesystem whitelists (NFS export ACLs) for cluster-wide access control."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "pe_host": {
                    "type": "string",
                    "description": "Prism Element CVM IP address or hostname",
                },
            },
            "required": ["pe_host"],
        },
    },
    {
        "name": "pe_get_licensing_info",
        "description": (
            "Get licensing information from a Prism Element cluster. "
            "Returns license type (Starter/Pro/Ultimate), expiry, and enabled cluster features."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "pe_host": {
                    "type": "string",
                    "description": "Prism Element CVM IP address or hostname",
                },
            },
            "required": ["pe_host"],
        },
    },
    # ─── Data Protection Tools (Issue #17) ────────────────────────────────
    {
        "name": "pe_get_protection_domain",
        "description": (
            "Get detailed configuration of a specific protection domain. "
            "Returns consistency groups, VM list, schedules, and replication config."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "pe_host": {
                    "type": "string",
                    "description": "Prism Element CVM IP address or hostname",
                },
                "name": {
                    "type": "string",
                    "description": "Name of the protection domain",
                },
            },
            "required": ["pe_host", "name"],
        },
    },
    {
        "name": "pe_list_remote_sites",
        "description": (
            "List remote sites (DR partner clusters) on a Prism Element cluster. "
            "Returns remote site names, addresses, replication bandwidth, and capabilities."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "pe_host": {
                    "type": "string",
                    "description": "Prism Element CVM IP address or hostname",
                },
            },
            "required": ["pe_host"],
        },
    },
    {
        "name": "pe_get_replication_status",
        "description": (
            "Get active replication status for a protection domain. "
            "Returns current replications, lag, and bandwidth usage."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "pe_host": {
                    "type": "string",
                    "description": "Prism Element CVM IP address or hostname",
                },
                "protection_domain": {
                    "type": "string",
                    "description": "Name of the protection domain",
                },
            },
            "required": ["pe_host", "protection_domain"],
        },
    },
    {
        "name": "pe_list_unprotected_vms",
        "description": (
            "List VMs not in any protection domain on a Prism Element cluster. "
            "Identifies compliance gaps where VMs lack DR protection."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "pe_host": {
                    "type": "string",
                    "description": "Prism Element CVM IP address or hostname",
                },
            },
            "required": ["pe_host"],
        },
    },
    # ─── Host Detail Tools (Issue #18) ────────────────────────────────────
    {
        "name": "pe_get_host_disks",
        "description": (
            "Get physical disk inventory for a specific host. "
            "Returns disk model, serial number, firmware, tier (SSD/HDD), status, and capacity."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "pe_host": {
                    "type": "string",
                    "description": "Prism Element CVM IP address or hostname",
                },
                "host_uuid": {
                    "type": "string",
                    "description": "UUID of the host to get disk inventory for",
                },
            },
            "required": ["pe_host", "host_uuid"],
        },
    },
    {
        "name": "pe_get_host_nics",
        "description": (
            "Get network interface details for a specific host. "
            "Returns NIC name, speed, link state, MAC address, and switch info via LLDP."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "pe_host": {
                    "type": "string",
                    "description": "Prism Element CVM IP address or hostname",
                },
                "host_uuid": {
                    "type": "string",
                    "description": "UUID of the host to get NIC details for",
                },
            },
            "required": ["pe_host", "host_uuid"],
        },
    },
    {
        "name": "pe_list_cvms",
        "description": (
            "List Controller VMs (CVMs) on a Prism Element cluster. "
            "Returns CVM IP, memory allocation, power state, and associated host."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "pe_host": {
                    "type": "string",
                    "description": "Prism Element CVM IP address or hostname",
                },
            },
            "required": ["pe_host"],
        },
    },
    # ─── Volume Group Tools (Issue #19) ───────────────────────────────────
    {
        "name": "pe_list_volume_groups",
        "description": (
            "List volume groups on a Prism Element cluster. "
            "Returns VG name, size, iSCSI target IQN, attached VMs, and CHAP config."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "pe_host": {
                    "type": "string",
                    "description": "Prism Element CVM IP address or hostname",
                },
            },
            "required": ["pe_host"],
        },
    },
    {
        "name": "pe_get_volume_group",
        "description": (
            "Get detailed volume group configuration. "
            "Returns disk list, client attachments, iSCSI details, and usage."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "pe_host": {
                    "type": "string",
                    "description": "Prism Element CVM IP address or hostname",
                },
                "uuid": {
                    "type": "string",
                    "description": "UUID of the volume group",
                },
            },
            "required": ["pe_host", "uuid"],
        },
    },
    # ─── Health Check Tools (Issue #20) ───────────────────────────────────
    {
        "name": "pe_get_cluster_health",
        "description": (
            "Get cluster data resiliency and fault tolerance status. "
            "Returns per-domain (NODE, RACKABLE_UNIT, RACK, DISK) fault tolerance: how many "
            "failures each component can tolerate, and an explanatory message when it cannot."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "pe_host": {
                    "type": "string",
                    "description": "Prism Element CVM IP address or hostname",
                },
            },
            "required": ["pe_host"],
        },
    },
    {
        "name": "pe_list_health_checks",
        "description": (
            "List NCC-style health check results on a Prism Element cluster. "
            "Returns check names, statuses, and any warnings or failures."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "pe_host": {
                    "type": "string",
                    "description": "Prism Element CVM IP address or hostname",
                },
            },
            "required": ["pe_host"],
        },
    },
    # ─── Additional Tools (AsBuiltReport parity) ─────────────────────────
    {
        "name": "pe_list_images",
        "description": (
            "List images (ISOs, disk images) on a Prism Element cluster. "
            "Returns image name, type, state, size, and source URI."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "pe_host": {
                    "type": "string",
                    "description": "Prism Element CVM IP address or hostname",
                },
            },
            "required": ["pe_host"],
        },
    },
    {
        "name": "pe_list_networks",
        "description": (
            "List networks (VLANs) on a Prism Element cluster. "
            "Returns network name, VLAN ID, managed/unmanaged state, and IP pool configuration."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "pe_host": {
                    "type": "string",
                    "description": "Prism Element CVM IP address or hostname",
                },
            },
            "required": ["pe_host"],
        },
    },
    {
        "name": "pe_get_metro_witness",
        "description": (
            "Get Metro Availability witness server configuration. "
            "Returns witness address, status, and cluster association."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "pe_host": {
                    "type": "string",
                    "description": "Prism Element CVM IP address or hostname",
                },
            },
            "required": ["pe_host"],
        },
    },
    {
        "name": "pe_list_dr_snapshots",
        "description": (
            "List disaster recovery snapshots across remote sites. "
            "Returns snapshot IDs, PD names, remote site, and retention info."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "pe_host": {
                    "type": "string",
                    "description": "Prism Element CVM IP address or hostname",
                },
            },
            "required": ["pe_host"],
        },
    },
    {
        "name": "pe_list_pd_replications",
        "description": (
            "List all active protection domain replications across the cluster. "
            "Returns replication status, progress, bandwidth, and remote site for all PDs."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "pe_host": {
                    "type": "string",
                    "description": "Prism Element CVM IP address or hostname",
                },
            },
            "required": ["pe_host"],
        },
    },
]


# ─── Tool Handlers ────────────────────────────────────────────────────────────


async def handle_pe_get_cluster_info(client: NutanixClient, arguments: dict[str, Any]) -> dict[str, Any]:
    """Get cluster info from Prism Element v2 API."""
    pe_host = arguments["pe_host"]
    result = await client.pe_get(pe_host, "cluster")

    return {
        "name": result.get("name"),
        "clusterUuid": result.get("cluster_uuid"),
        "version": result.get("version"),
        "numNodes": result.get("num_nodes"),
        "storageType": result.get("storage_type"),
        "hypervisorTypes": result.get("hypervisor_types"),
        "clusterExternalIp": result.get("cluster_external_ipaddress"),
    }


async def handle_pe_list_vms(client: NutanixClient, arguments: dict[str, Any]) -> dict[str, Any]:
    """List VMs from Prism Element v2 API."""
    pe_host = arguments["pe_host"]
    count = arguments.get("count")

    result = await client.pe_list(pe_host, "vms", count=count)
    entities = result.get("entities", [])

    return {
        "count": len(entities),
        "vms": [
            {
                "name": vm.get("name"),
                "uuid": vm.get("uuid"),
                "powerState": vm.get("power_state"),
                "numVcpus": vm.get("num_vcpus"),
                "memoryMb": vm.get("memory_mb"),
                "hostUuid": vm.get("host_uuid"),
                "ipAddresses": vm.get("ip_addresses", []),
            }
            for vm in entities
        ],
    }


async def handle_pe_list_hosts(client: NutanixClient, arguments: dict[str, Any]) -> dict[str, Any]:
    """List hosts from Prism Element v2 API."""
    pe_host = arguments["pe_host"]
    result = await client.pe_list(pe_host, "hosts")
    entities = result.get("entities", [])

    return {
        "count": len(entities),
        "hosts": [
            {
                "name": h.get("name"),
                "uuid": h.get("uuid"),
                "hypervisorAddress": h.get("hypervisor_address"),
                "cvmAddress": h.get("controller_vm_backplane_ip"),
                "cpuModel": h.get("cpu_model"),
                "numCpuSockets": h.get("num_cpu_sockets"),
                "numCpuCores": h.get("num_cpu_cores"),
                "memoryCapacityGb": (h.get("memory_capacity_in_bytes", 0)) // (1024**3),
                "hypervisorType": h.get("hypervisor_type"),
            }
            for h in entities
        ],
    }


async def handle_pe_list_containers(client: NutanixClient, arguments: dict[str, Any]) -> dict[str, Any]:
    """List storage containers from Prism Element v2 API."""
    pe_host = arguments["pe_host"]
    result = await client.pe_list(pe_host, "containers")
    entities = result.get("entities", [])

    return {
        "count": len(entities),
        "containers": [
            {
                "name": c.get("name"),
                "containerUuid": c.get("container_uuid"),
                "storagePoolUuid": c.get("storage_pool_uuid"),
                "maxCapacityBytes": c.get("max_capacity"),
                "replicationFactor": c.get("replication_factor"),
                "compressionEnabled": c.get("compression_enabled"),
                "erasureCoded": c.get("erasure_coded"),
            }
            for c in entities
        ],
    }


async def handle_pe_list_storage_pools(client: NutanixClient, arguments: dict[str, Any]) -> dict[str, Any]:
    """List storage pools from Prism Element v2 API."""
    pe_host = arguments["pe_host"]
    result = await client.pe_list(pe_host, "storage_pools")
    entities = result.get("entities", [])

    return {
        "count": len(entities),
        "storagePools": [
            {
                "name": sp.get("name"),
                "uuid": sp.get("storage_pool_uuid"),
                "capacityBytes": sp.get("capacity"),
                "usageBytes": sp.get("usage_stats", {}).get("storage.usage_bytes"),
                "numDisks": len(sp.get("disks", [])),
            }
            for sp in entities
        ],
    }


async def handle_pe_list_disks(client: NutanixClient, arguments: dict[str, Any]) -> dict[str, Any]:
    """List physical disks from Prism Element v2 API."""
    pe_host = arguments["pe_host"]
    result = await client.pe_list(pe_host, "disks")
    entities = result.get("entities", [])

    return {
        "count": len(entities),
        "disks": [
            {
                "id": d.get("id"),
                "uuid": d.get("disk_uuid"),
                "serialNumber": d.get("disk_hardware_config", {}).get("serial_number"),
                "storageTierName": d.get("storage_tier_name"),
                "diskStatus": d.get("disk_status"),
                "hostName": d.get("host_name"),
                "capacityBytes": d.get("disk_size"),
                "onlineStatus": d.get("online"),
            }
            for d in entities
        ],
    }


async def handle_pe_list_alerts(client: NutanixClient, arguments: dict[str, Any]) -> dict[str, Any]:
    """List alerts from Prism Element v2 API."""
    pe_host = arguments["pe_host"]
    resolved = arguments.get("resolved", False)
    count = arguments.get("count", 50)

    params: dict[str, str] = {"count": str(count)}
    if not resolved:
        params["resolved"] = "false"

    result = await client.pe_get(pe_host, "alerts", params=params)
    entities = result.get("entities", [])

    return {
        "count": len(entities),
        "alerts": [
            {
                "id": a.get("id"),
                "alertTitle": a.get("alert_title"),
                "severity": a.get("severity"),
                "message": a.get("message"),
                "resolved": a.get("resolved"),
                "createdTimeStamp": a.get("created_time_stamp_in_usecs"),
                "affectedEntities": a.get("affected_entities", []),
            }
            for a in entities
        ],
    }


async def handle_pe_list_protection_domains(client: NutanixClient, arguments: dict[str, Any]) -> dict[str, Any]:
    """List protection domains from Prism Element v2 API."""
    pe_host = arguments["pe_host"]
    result = await client.pe_list(pe_host, "protection_domains")
    entities = result.get("entities", [])

    return {
        "count": len(entities),
        "protectionDomains": [
            {
                "name": pd.get("name"),
                "active": pd.get("active"),
                "cronSchedules": pd.get("cron_schedules", []),
                "replicationLinks": pd.get("replication_links", []),
                "vmCount": len(pd.get("vms", [])),
            }
            for pd in entities
        ],
    }


async def handle_pe_list_snapshots(client: NutanixClient, arguments: dict[str, Any]) -> dict[str, Any]:
    """List snapshots for a protection domain from Prism Element v2 API."""
    pe_host = arguments["pe_host"]
    pd_name = arguments["protection_domain"]

    result = await client.pe_get(pe_host, f"protection_domains/{pd_name}/dr_snapshots")
    entities = result.get("entities", [])

    return {
        "count": len(entities),
        "snapshots": [
            {
                "snapshotId": s.get("snapshot_id"),
                "snapshotName": s.get("snapshot_name"),
                "createdTimestamp": s.get("created_time_stamp_in_usecs"),
                "expiryTimestamp": s.get("expiry_time_stamp_in_usecs"),
                "state": s.get("state"),
            }
            for s in entities
        ],
    }


# ─── System Configuration Handlers (Issue #16) ───────────────────────────────


async def handle_pe_get_auth_config(client: NutanixClient, arguments: dict[str, Any]) -> dict[str, Any]:
    """Get authentication configuration from Prism Element v2 API."""
    pe_host = arguments["pe_host"]
    result = await client.pe_get(pe_host, "authconfig")

    directory_list = result.get("directoryList", [])
    return {
        "authTypes": result.get("authTypeList", []),
        "directories": [
            {
                "name": d.get("name"),
                "directoryType": d.get("directory_type"),
                "domain": d.get("domain"),
                "directoryUrl": d.get("directory_url"),
                "connectionType": d.get("connection_type"),
                "groupSearchType": d.get("group_search_type"),
            }
            for d in directory_list
        ],
        "clientAuth": result.get("clientAuth"),
    }


async def handle_pe_get_smtp_config(client: NutanixClient, arguments: dict[str, Any]) -> dict[str, Any]:
    """Get SMTP server configuration from Prism Element v2 API."""
    pe_host = arguments["pe_host"]
    result = await client.pe_get(pe_host, "cluster/smtp")

    return {
        "address": result.get("address"),
        "port": result.get("port"),
        "username": result.get("username"),
        "secureMode": result.get("secure_mode"),
        "fromEmailAddress": result.get("from_email_address"),
        "emailStatus": result.get("email_status"),
    }


async def handle_pe_get_snmp_config(client: NutanixClient, arguments: dict[str, Any]) -> dict[str, Any]:
    """Get SNMP configuration from Prism Element v2 API."""
    pe_host = arguments["pe_host"]
    result = await client.pe_get(pe_host, "snmp")

    return {
        "enabled": result.get("enabled"),
        "traps": [
            {
                "address": t.get("address"),
                "port": t.get("port"),
                "communityString": t.get("community_string"),
                "version": t.get("version"),
                "inform": t.get("inform"),
            }
            for t in result.get("trap_list", [])
        ],
        "users": [
            {
                "username": u.get("username"),
                "authType": u.get("auth_type"),
                "privType": u.get("priv_type"),
            }
            for u in result.get("user_list", [])
        ],
        "transports": [
            {
                "port": tr.get("port"),
                "protocol": tr.get("protocol"),
            }
            for tr in result.get("transport_list", [])
        ],
    }


async def handle_pe_get_syslog_config(client: NutanixClient, arguments: dict[str, Any]) -> dict[str, Any]:
    """Get remote syslog server configuration from Prism Element v2 API."""
    pe_host = arguments["pe_host"]
    result = await client.pe_get(pe_host, "remote_syslog_servers")
    entities = result.get("entities", [])

    return {
        "count": len(entities),
        "servers": [
            {
                "serverName": s.get("server_name"),
                "ipAddress": s.get("ip_address"),
                "port": s.get("port"),
                "networkProtocol": s.get("network_protocol"),
                "modules": s.get("module_list", []),
            }
            for s in entities
        ],
    }


async def handle_pe_get_alert_email_config(client: NutanixClient, arguments: dict[str, Any]) -> dict[str, Any]:
    """Get alert email notification configuration from Prism Element v2 API."""
    pe_host = arguments["pe_host"]
    result = await client.pe_get(pe_host, "alerts/configuration")

    return {
        "emailContactList": result.get("email_contact_list", []),
        "enable": result.get("enable"),
        "enableDefaultNutanixEmail": result.get("enable_default_nutanix_email"),
        "enableEmailDigest": result.get("enable_email_digest"),
    }


async def handle_pe_get_nfs_whitelists(client: NutanixClient, arguments: dict[str, Any]) -> dict[str, Any]:
    """Get NFS whitelist configuration from Prism Element v2 API."""
    pe_host = arguments["pe_host"]
    result = await client.pe_get(pe_host, "cluster/nfs_whitelist")

    # Endpoint returns a list directly or wrapped
    nfs_whitelist = result if isinstance(result, list) else result.get("nfs_whitelist_address", result.get("whitelist", []))
    return {
        "count": len(nfs_whitelist) if isinstance(nfs_whitelist, list) else 0,
        "whitelists": nfs_whitelist,
    }


async def handle_pe_get_licensing_info(client: NutanixClient, arguments: dict[str, Any]) -> dict[str, Any]:
    """Get licensing information from Prism Element v1 API."""
    pe_host = arguments["pe_host"]
    result = await client.pe_v1_get(pe_host, "license")

    return {
        "category": result.get("category"),
        "licenseType": result.get("license_type"),
        "expiryDate": result.get("expiry_date"),
        "clusterUuid": result.get("cluster_uuid"),
        "enabledFeatures": result.get("enabled_feature_list", []),
    }


# ─── Data Protection Handlers (Issue #17) ────────────────────────────────────


async def handle_pe_get_protection_domain(client: NutanixClient, arguments: dict[str, Any]) -> dict[str, Any]:
    """Get detailed protection domain config from Prism Element v2 API."""
    pe_host = arguments["pe_host"]
    pd_name = arguments["name"]

    result = await client.pe_get(pe_host, f"protection_domains/{pd_name}")

    return {
        "name": result.get("name"),
        "active": result.get("active"),
        "cronSchedules": result.get("cron_schedules", []),
        "replicationLinks": result.get("replication_links", []),
        "vms": [
            {
                "vmName": vm.get("vm_name"),
                "vmId": vm.get("vm_id"),
                "consistencyGroup": vm.get("consistency_group_name"),
            }
            for vm in result.get("vms", [])
        ],
        "nfsFiles": result.get("nfs_files", []),
        "volumeGroups": result.get("volume_groups", []),
        "markedForRemoval": result.get("marked_for_removal"),
    }


async def handle_pe_list_remote_sites(client: NutanixClient, arguments: dict[str, Any]) -> dict[str, Any]:
    """List remote sites (DR partners) from Prism Element v2 API."""
    pe_host = arguments["pe_host"]
    result = await client.pe_list(pe_host, "remote_sites")
    entities = result.get("entities", [])

    return {
        "count": len(entities),
        "remoteSites": [
            {
                "name": rs.get("name"),
                "uuid": rs.get("uuid"),
                "remoteIpPorts": rs.get("remote_ip_ports", {}),
                "capabilities": rs.get("capabilities", []),
                "compressionEnabled": rs.get("compression_enabled"),
                "bandwidthPolicyEnabled": rs.get("bandwidth_policy_enabled"),
                "maxBandwidthMbps": rs.get("max_bandwidth_kbps", 0) // 1024 if rs.get("max_bandwidth_kbps") else None,
                "proxyEnabled": rs.get("proxy_enabled"),
                "sshEnabled": rs.get("ssh_enabled"),
                "vstoreMapping": rs.get("vstore_name_map", {}),
            }
            for rs in entities
        ],
    }


async def handle_pe_get_replication_status(client: NutanixClient, arguments: dict[str, Any]) -> dict[str, Any]:
    """Get replication status for a protection domain from Prism Element v2 API."""
    pe_host = arguments["pe_host"]
    pd_name = arguments["protection_domain"]

    result = await client.pe_get(pe_host, f"protection_domains/{pd_name}/replications")
    entities = result.get("entities", [])

    return {
        "count": len(entities),
        "replications": [
            {
                "id": r.get("id"),
                "protectionDomainName": r.get("protection_domain_name"),
                "remoteSiteName": r.get("remote_site_name"),
                "snapshotId": r.get("snapshot_id"),
                "status": r.get("replication_status"),
                "completedPercentage": r.get("completed_percentage"),
                "completedBytes": r.get("completed_bytes"),
                "totalBytes": r.get("total_bytes"),
            }
            for r in entities
        ],
    }


async def handle_pe_list_unprotected_vms(client: NutanixClient, arguments: dict[str, Any]) -> dict[str, Any]:
    """List VMs not in any protection domain from Prism Element v2 API."""
    pe_host = arguments["pe_host"]

    # Use the native v2 endpoint for unprotected VMs
    result = await client.pe_list(pe_host, "protection_domains/unprotected_vms")
    entities = result.get("entities", [])

    return {
        "unprotectedCount": len(entities),
        "unprotectedVms": [
            {
                "name": vm.get("vm_name") or vm.get("name"),
                "uuid": vm.get("vm_id") or vm.get("uuid"),
                "powerState": vm.get("power_state"),
                "hostUuid": vm.get("host_uuid"),
            }
            for vm in entities
        ],
    }


# ─── Host Detail Handlers (Issue #18) ────────────────────────────────────────


async def handle_pe_get_host_disks(client: NutanixClient, arguments: dict[str, Any]) -> dict[str, Any]:
    """Get physical disk inventory for a specific host from Prism Element v2 API."""
    pe_host = arguments["pe_host"]
    host_uuid = arguments["host_uuid"]

    result = await client.pe_get(pe_host, f"hosts/{host_uuid}/host_disks")
    entities = result.get("entities", [])

    return {
        "hostUuid": host_uuid,
        "count": len(entities),
        "disks": [
            {
                "id": d.get("id"),
                "uuid": d.get("disk_uuid"),
                "serialNumber": d.get("disk_hardware_config", {}).get("serial_number"),
                "model": d.get("disk_hardware_config", {}).get("model"),
                "firmware": d.get("disk_hardware_config", {}).get("current_firmware_version"),
                "vendor": d.get("disk_hardware_config", {}).get("vendor"),
                "storageTierName": d.get("storage_tier_name"),
                "diskStatus": d.get("disk_status"),
                "capacityBytes": d.get("disk_size"),
                "onlineStatus": d.get("online"),
                "mountPath": d.get("mount_path"),
                "location": d.get("location"),
            }
            for d in entities
        ],
    }


async def handle_pe_get_host_nics(client: NutanixClient, arguments: dict[str, Any]) -> dict[str, Any]:
    """Get network interface details for a specific host from Prism Element v2 API."""
    pe_host = arguments["pe_host"]
    host_uuid = arguments["host_uuid"]

    result = await client.pe_get(pe_host, f"hosts/{host_uuid}/host_nics")
    entities = result.get("entities", [])

    return {
        "hostUuid": host_uuid,
        "count": len(entities),
        "nics": [
            {
                "name": n.get("name"),
                "uuid": n.get("uuid"),
                "macAddress": n.get("mac_address"),
                "ipAddress": n.get("ip_address"),
                "linkSpeedMbps": n.get("link_speed_in_kbps", 0) // 1000 if n.get("link_speed_in_kbps") else None,
                "mtu": n.get("mtu_in_bytes"),
                "interfaceStatus": n.get("interface_status"),
                "dhcpEnabled": n.get("dhcp_enabled"),
                "switchManagementAddress": n.get("switch_management_address"),
                "switchPortId": n.get("switch_port_id"),
                "switchVlanId": n.get("switch_vlan_id"),
            }
            for n in entities
        ],
    }


async def handle_pe_list_cvms(client: NutanixClient, arguments: dict[str, Any]) -> dict[str, Any]:
    """List Controller VMs (CVMs) from Prism Element v2 API."""
    pe_host = arguments["pe_host"]

    result = await client.pe_list(pe_host, "vms", filter_criteria="is_cvm==true")
    entities = result.get("entities", [])

    return {
        "count": len(entities),
        "cvms": [
            {
                "name": vm.get("name"),
                "uuid": vm.get("uuid"),
                "powerState": vm.get("power_state"),
                "memoryMb": vm.get("memory_mb"),
                "numVcpus": vm.get("num_vcpus"),
                "hostUuid": vm.get("host_uuid"),
                "ipAddresses": vm.get("ip_addresses", []),
            }
            for vm in entities
        ],
    }


# ─── Volume Group Handlers (Issue #19) ───────────────────────────────────────


async def handle_pe_list_volume_groups(client: NutanixClient, arguments: dict[str, Any]) -> dict[str, Any]:
    """List volume groups from Prism Element v2 API."""
    pe_host = arguments["pe_host"]
    result = await client.pe_list(pe_host, "volume_groups")
    entities = result.get("entities", [])

    return {
        "count": len(entities),
        "volumeGroups": [
            {
                "name": vg.get("name"),
                "uuid": vg.get("uuid"),
                "diskList": [
                    {
                        "index": d.get("index"),
                        "sizeMb": d.get("vmdisk_size_mb"),
                        "storageContainerUuid": d.get("storage_container_uuid"),
                    }
                    for d in vg.get("disk_list", [])
                ],
                "iscsiTarget": vg.get("iscsi_target"),
                "attachedVmUuids": vg.get("attachment_list", []),
                "flashModeEnabled": vg.get("flash_mode_enabled"),
            }
            for vg in entities
        ],
    }


async def handle_pe_get_volume_group(client: NutanixClient, arguments: dict[str, Any]) -> dict[str, Any]:
    """Get detailed volume group config from Prism Element v2 API."""
    pe_host = arguments["pe_host"]
    vg_uuid = arguments["uuid"]

    result = await client.pe_get(pe_host, f"volume_groups/{vg_uuid}")

    return {
        "name": result.get("name"),
        "uuid": result.get("uuid"),
        "description": result.get("description"),
        "diskList": [
            {
                "index": d.get("index"),
                "sizeMb": d.get("vmdisk_size_mb"),
                "storageContainerUuid": d.get("storage_container_uuid"),
                "vmdiskUuid": d.get("vmdisk_uuid"),
            }
            for d in result.get("disk_list", [])
        ],
        "iscsiTarget": result.get("iscsi_target"),
        "attachmentList": result.get("attachment_list", []),
        "flashModeEnabled": result.get("flash_mode_enabled"),
        "createdTimestamp": result.get("created_time_stamp_in_usecs"),
    }


# ─── Health Check Handlers (Issue #20) ───────────────────────────────────────


async def handle_pe_get_cluster_health(client: NutanixClient, arguments: dict[str, Any]) -> dict[str, Any]:
    """Get cluster health and domain fault tolerance status from Prism Element v2 API."""
    pe_host = arguments["pe_host"]
    result = await client.pe_get(pe_host, "cluster/domain_fault_tolerance_status")

    # The endpoint returns a bare list of per-domain entries; some AOS versions
    # wrap it in a dict. Accept both rather than assuming a mapping.
    if isinstance(result, dict):
        domain_statuses = result.get("domain_fault_tolerance_status", result)
    else:
        domain_statuses = result

    if not isinstance(domain_statuses, list):
        return {"faultToleranceStatus": domain_statuses}

    domains = []
    for status in domain_statuses:
        components = []
        for name, component in (status.get("component_fault_tolerance_status") or {}).items():
            if not isinstance(component, dict):
                continue
            # "details" is null for healthy components.
            details = component.get("details") or {}
            components.append(
                {
                    "componentType": component.get("component_type") or name,
                    "failuresTolerable": component.get("number_of_failures_tolerable"),
                    "message": details.get("message"),
                    "underComputation": component.get("under_computation"),
                    "lastUpdatedTimestamp": component.get("last_updated_time_in_usecs"),
                }
            )
        components.sort(key=lambda c: c["componentType"] or "")

        tolerable = [
            c["failuresTolerable"] for c in components if isinstance(c["failuresTolerable"], int)
        ]
        domains.append(
            {
                "domainType": status.get("domain_type") or status.get("type"),
                # A domain is only as resilient as its weakest component.
                "minFailuresTolerable": min(tolerable) if tolerable else None,
                "underReplicatedDataBytes": status.get("cluster_under_replicated_data_bytes"),
                "nonFaultTolerantEntries": status.get("cluster_non_fault_tolerant_entries"),
                "components": components,
            }
        )

    return {"count": len(domains), "faultToleranceStatus": domains}


async def handle_pe_list_health_checks(client: NutanixClient, arguments: dict[str, Any]) -> dict[str, Any]:
    """List health check results from Prism Element v2 API."""
    pe_host = arguments["pe_host"]
    result = await client.pe_list(pe_host, "health_checks")
    entities = result.get("entities", result.get("health_check_list", []))

    if isinstance(entities, list):
        return {
            "count": len(entities),
            "healthChecks": [
                {
                    "id": hc.get("id"),
                    "name": hc.get("name"),
                    "description": hc.get("description"),
                    "affectedEntityTypes": hc.get("affected_entity_types", []),
                    "checkType": hc.get("check_type"),
                    "severity": hc.get("severity"),
                    "lastExecutionStatus": hc.get("last_execution_status"),
                    "lastPassedTimestamp": hc.get("last_passed_time_stamp_in_usecs"),
                }
                for hc in entities
            ],
        }
    return {"healthChecks": entities}


# ─── Additional Handlers (AsBuiltReport parity) ──────────────────────────────


async def handle_pe_list_images(client: NutanixClient, arguments: dict[str, Any]) -> dict[str, Any]:
    """List images (ISOs, disk images) from Prism Element v2 API."""
    pe_host = arguments["pe_host"]
    result = await client.pe_list(pe_host, "images")
    entities = result.get("entities", [])

    return {
        "count": len(entities),
        "images": [
            {
                "name": img.get("name"),
                "uuid": img.get("uuid"),
                "imageType": img.get("image_type"),
                "imageState": img.get("image_state"),
                "sizeMb": round(img.get("vm_disk_size", 0) / (1024 * 1024), 1) if img.get("vm_disk_size") else None,
                "sourceUri": img.get("source_uri"),
                "storageContainerName": img.get("storage_container_name"),
                "createdTimestamp": img.get("created_time_in_usecs"),
                "updatedTimestamp": img.get("updated_time_in_usecs"),
            }
            for img in entities
        ],
    }


async def handle_pe_list_networks(client: NutanixClient, arguments: dict[str, Any]) -> dict[str, Any]:
    """List networks (VLANs) from Prism Element v2 API."""
    pe_host = arguments["pe_host"]
    result = await client.pe_list(pe_host, "networks")
    entities = result.get("entities", [])

    return {
        "count": len(entities),
        "networks": [
            {
                "name": net.get("name"),
                "uuid": net.get("uuid"),
                "vlanId": net.get("vlan_id"),
                "networkType": net.get("network_type"),
                "ipConfig": {
                    "networkAddress": net.get("ip_config", {}).get("network_address") if net.get("ip_config") else None,
                    "prefixLength": net.get("ip_config", {}).get("prefix_length") if net.get("ip_config") else None,
                    "defaultGateway": net.get("ip_config", {}).get("default_gateway") if net.get("ip_config") else None,
                    "dhcpServerAddress": net.get("ip_config", {}).get("dhcp_server_address") if net.get("ip_config") else None,
                    "poolList": net.get("ip_config", {}).get("pool", []) if net.get("ip_config") else [],
                } if net.get("ip_config") else None,
            }
            for net in entities
        ],
    }


async def handle_pe_get_metro_witness(client: NutanixClient, arguments: dict[str, Any]) -> dict[str, Any]:
    """Get Metro Availability witness server configuration from Prism Element v2 API."""
    pe_host = arguments["pe_host"]
    result = await client.pe_get(pe_host, "cluster/metro_witness")

    # May return a witness object or empty dict if not configured
    if not result or (isinstance(result, dict) and not result.get("witness_address")):
        return {"configured": False, "witness": None}

    return {
        "configured": True,
        "witness": {
            "witnessAddress": result.get("witness_address"),
            "clusterUuid": result.get("cluster_uuid"),
            "witnessState": result.get("witness_state"),
            "hasWitness": result.get("has_witness"),
        },
    }


async def handle_pe_list_dr_snapshots(client: NutanixClient, arguments: dict[str, Any]) -> dict[str, Any]:
    """List DR snapshots across remote sites from Prism Element v2 API."""
    pe_host = arguments["pe_host"]
    result = await client.pe_list(pe_host, "remote_sites/dr_snapshots")
    entities = result.get("entities", [])

    return {
        "count": len(entities),
        "drSnapshots": [
            {
                "snapshotId": snap.get("snapshot_id"),
                "protectionDomainName": snap.get("protection_domain_name"),
                "remoteSiteName": snap.get("remote_site_name"),
                "consistencyGroupName": snap.get("consistency_group_name"),
                "createdTimestamp": snap.get("created_time_in_usecs"),
                "expirationTimestamp": snap.get("expiration_time_in_usecs"),
                "sizeBytes": snap.get("size_in_bytes"),
            }
            for snap in entities
        ],
    }


async def handle_pe_list_pd_replications(client: NutanixClient, arguments: dict[str, Any]) -> dict[str, Any]:
    """List all active protection domain replications from Prism Element v2 API."""
    pe_host = arguments["pe_host"]
    result = await client.pe_list(pe_host, "protection_domains/replications")
    entities = result.get("entities", [])

    return {
        "count": len(entities),
        "replications": [
            {
                "id": r.get("id"),
                "protectionDomainName": r.get("protection_domain_name"),
                "remoteSiteName": r.get("remote_site_name"),
                "snapshotId": r.get("snapshot_id"),
                "status": r.get("replication_status"),
                "completedPercentage": r.get("completed_percentage"),
                "completedBytes": r.get("completed_bytes"),
                "totalBytes": r.get("total_bytes"),
                "replicatingVms": r.get("replicating_vms", []),
            }
            for r in entities
        ],
    }


# ─── Handler Dispatch ─────────────────────────────────────────────────────────

PE_HANDLERS: dict[str, Any] = {
    "pe_get_cluster_info": handle_pe_get_cluster_info,
    "pe_list_vms": handle_pe_list_vms,
    "pe_list_hosts": handle_pe_list_hosts,
    "pe_list_containers": handle_pe_list_containers,
    "pe_list_storage_pools": handle_pe_list_storage_pools,
    "pe_list_disks": handle_pe_list_disks,
    "pe_list_alerts": handle_pe_list_alerts,
    "pe_list_protection_domains": handle_pe_list_protection_domains,
    "pe_list_snapshots": handle_pe_list_snapshots,
    # Issue #16: System Configuration
    "pe_get_auth_config": handle_pe_get_auth_config,
    "pe_get_smtp_config": handle_pe_get_smtp_config,
    "pe_get_snmp_config": handle_pe_get_snmp_config,
    "pe_get_syslog_config": handle_pe_get_syslog_config,
    "pe_get_alert_email_config": handle_pe_get_alert_email_config,
    "pe_get_nfs_whitelists": handle_pe_get_nfs_whitelists,
    "pe_get_licensing_info": handle_pe_get_licensing_info,
    # Issue #17: Data Protection
    "pe_get_protection_domain": handle_pe_get_protection_domain,
    "pe_list_remote_sites": handle_pe_list_remote_sites,
    "pe_get_replication_status": handle_pe_get_replication_status,
    "pe_list_unprotected_vms": handle_pe_list_unprotected_vms,
    # Issue #18: Host Details
    "pe_get_host_disks": handle_pe_get_host_disks,
    "pe_get_host_nics": handle_pe_get_host_nics,
    "pe_list_cvms": handle_pe_list_cvms,
    # Issue #19: Volume Groups
    "pe_list_volume_groups": handle_pe_list_volume_groups,
    "pe_get_volume_group": handle_pe_get_volume_group,
    # Issue #20: Health Checks
    "pe_get_cluster_health": handle_pe_get_cluster_health,
    "pe_list_health_checks": handle_pe_list_health_checks,
    # AsBuiltReport parity
    "pe_list_images": handle_pe_list_images,
    "pe_list_networks": handle_pe_list_networks,
    "pe_get_metro_witness": handle_pe_get_metro_witness,
    "pe_list_dr_snapshots": handle_pe_list_dr_snapshots,
    "pe_list_pd_replications": handle_pe_list_pd_replications,
}
