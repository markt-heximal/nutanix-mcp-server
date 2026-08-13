"""Networking tools using Nutanix v4 networking namespace."""

from typing import Any

from nutanix_mcp.client import NutanixClient

# ─── Tool Definitions ─────────────────────────────────────────────────────────

NETWORKING_TOOLS: list[dict] = [
    {
        "name": "list_subnets",
        "description": (
            "List ALL subnets/VLANs in Prism Central (auto-paginates internally). "
            "Returns complete results in one call — no manual pagination needed."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "filter": {
                    "type": "string",
                    "description": (
                        'OData filter expression. Examples: "name eq \'production-vlan\'", "vlanId eq 100"'
                    ),
                },
                "limit": {
                    "type": "integer",
                    "description": "Optional cap on results. Omit to get ALL subnets (default behavior).",
                },
            },
        },
    },
    {
        "name": "get_subnet",
        "description": (
            "Get detailed subnet configuration including IP pools, DHCP config, and virtual switch assignment."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "subnet_uuid": {
                    "type": "string",
                    "description": "The UUID (extId) of the subnet",
                },
            },
            "required": ["subnet_uuid"],
        },
    },
    {
        "name": "create_subnet",
        "description": (
            "Create a VLAN-backed subnet on a cluster. Provide the VLAN id and target "
            "cluster UUID. Optionally enable IPAM (a managed subnet) by supplying a "
            "network CIDR, default gateway, and a DHCP pool range. Returns a task UUID."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Subnet name."},
                "cluster_uuid": {
                    "type": "string",
                    "description": "UUID (extId) of the cluster to create the subnet on.",
                },
                "vlan_id": {
                    "type": "integer",
                    "description": "VLAN ID (use 0 for the untagged/native VLAN).",
                },
                "subnet_type": {
                    "type": "string",
                    "enum": ["VLAN", "OVERLAY"],
                    "description": "Subnet type. Default: VLAN.",
                },
                "description": {"type": "string", "description": "Optional description."},
                "network_cidr": {
                    "type": "string",
                    "description": "Optional. Enables IPAM. Network in CIDR form, e.g. '10.0.1.0/24'.",
                },
                "gateway_ip": {
                    "type": "string",
                    "description": "Optional default gateway IP (requires network_cidr).",
                },
                "dhcp_pool_start": {
                    "type": "string",
                    "description": "Optional DHCP/managed pool start IP (requires network_cidr).",
                },
                "dhcp_pool_end": {
                    "type": "string",
                    "description": "Optional DHCP/managed pool end IP (requires network_cidr).",
                },
            },
            "required": ["name", "cluster_uuid", "vlan_id"],
        },
    },
    {
        "name": "update_subnet",
        "description": (
            "Update an existing subnet's configuration (name, description, VLAN id, or "
            "IPAM settings). Uses ETag-based concurrency control. Returns a task UUID."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "subnet_uuid": {
                    "type": "string",
                    "description": "The UUID (extId) of the subnet to update.",
                },
                "name": {"type": "string", "description": "New subnet name."},
                "description": {"type": "string", "description": "New description."},
                "vlan_id": {"type": "integer", "description": "New VLAN ID."},
                "network_cidr": {
                    "type": "string",
                    "description": "Set/replace the IPAM network CIDR, e.g. '10.0.1.0/24'.",
                },
                "gateway_ip": {
                    "type": "string",
                    "description": "Set the default gateway IP (requires network_cidr).",
                },
                "dhcp_pool_start": {
                    "type": "string",
                    "description": "Managed pool start IP (requires network_cidr).",
                },
                "dhcp_pool_end": {
                    "type": "string",
                    "description": "Managed pool end IP (requires network_cidr).",
                },
            },
            "required": ["subnet_uuid"],
        },
    },
    {
        "name": "list_images",
        "description": (
            "List ALL disk images (ISOs, QCOW2) in the image library (auto-paginates internally). "
            "Returns complete results in one call — no manual pagination needed."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "filter": {
                    "type": "string",
                    "description": (
                        "OData filter expression. Examples: \"name eq 'ubuntu-22.04'\", \"type eq 'DISK_IMAGE'\""
                    ),
                },
                "limit": {
                    "type": "integer",
                    "description": "Optional cap on results. Omit to get ALL images (default behavior).",
                },
            },
        },
    },
    {
        "name": "get_image",
        "description": (
            "Get detailed information about a specific disk image by UUID. "
            "Returns size, type, source, and cluster placement."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "image_uuid": {
                    "type": "string",
                    "description": "The UUID (extId) of the image",
                },
            },
            "required": ["image_uuid"],
        },
    },
    {
        "name": "list_categories",
        "description": (
            "List ALL category keys and values (auto-paginates internally). "
            "Returns complete results in one call — no manual pagination needed."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "filter": {
                    "type": "string",
                    "description": "OData filter expression. Example: \"key eq 'Environment'\"",
                },
                "limit": {
                    "type": "integer",
                    "description": "Optional cap on results. Omit to get ALL categories (default behavior).",
                },
            },
        },
    },
    {
        "name": "get_category",
        "description": (
            "Get all values for a specific category key. "
            "Example: category 'Environment' may have values 'Production', 'Dev', 'Test'."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "category_uuid": {
                    "type": "string",
                    "description": "The UUID (extId) of the category",
                },
            },
            "required": ["category_uuid"],
        },
    },
]


# ─── Tool Handlers ────────────────────────────────────────────────────────────


async def handle_list_subnets(client: NutanixClient, arguments: dict[str, Any]) -> dict[str, Any]:
    """List subnets using official Nutanix SDK."""
    filter_expr = arguments.get("filter")
    limit = arguments.get("limit")
    sdk = client.sdk

    kwargs: dict[str, Any] = {}
    if filter_expr:
        kwargs["_filter"] = filter_expr

    if limit:
        response = await sdk.call(sdk.subnet_api.list_subnets, _limit=limit, **kwargs)
        subnets = response.data or []
    else:
        subnets = await sdk.list_all(sdk.subnet_api.list_subnets, **kwargs)

    return {
        "totalReturned": len(subnets),
        "note": "All matching subnets returned. No further pagination needed.",
        "subnets": [
            {
                "name": s.name,
                "extId": s.ext_id,
                "subnetType": s.subnet_type,
                "vlanId": s.network_id,
                "cidr": _extract_cidr_from_model(s),
                "cluster": s.cluster_reference if hasattr(s, "cluster_reference") else None,
            }
            for s in subnets
        ],
    }


def _extract_cidr_from_model(subnet: Any) -> str | None:
    """Extract CIDR from subnet model IP config."""
    ip_config = getattr(subnet, "ip_config", None)
    if not ip_config:
        return None
    # ip_config can be a list of configs
    if isinstance(ip_config, list):
        ip_config = ip_config[0] if ip_config else None
    if not ip_config:
        return None
    ipv4 = getattr(ip_config, "ipv4", None)
    if not ipv4:
        return None
    ip_subnet = getattr(ipv4, "ip_subnet", None)
    if not ip_subnet:
        return None
    ip_obj = getattr(ip_subnet, "ip", None)
    prefix = getattr(ip_subnet, "prefix_length", None)
    if ip_obj and prefix:
        ip_val = getattr(ip_obj, "value", None)
        if ip_val:
            return f"{ip_val}/{prefix}"
    return None


def _extract_cidr(subnet: dict) -> str | None:
    """Extract CIDR from subnet IP config (legacy dict fallback)."""
    ip_config = subnet.get("ipConfig")
    if not ip_config:
        return None
    if isinstance(ip_config, list):
        ip_config = ip_config[0] if ip_config else None
    if not ip_config or not isinstance(ip_config, dict):
        return None
    ipv4 = ip_config.get("ipv4", {})
    if not ipv4:
        return None
    ip_subnet = ipv4.get("ipSubnet", {})
    if not ip_subnet:
        return None
    ip = ip_subnet.get("ip", {}).get("value")
    prefix = ip_subnet.get("prefixLength")
    if ip and prefix:
        return f"{ip}/{prefix}"
    return None


async def handle_get_subnet(client: NutanixClient, arguments: dict[str, Any]) -> dict[str, Any]:
    """Get subnet details using official Nutanix SDK."""
    subnet_uuid = arguments["subnet_uuid"]
    sdk = client.sdk
    response = await sdk.call(sdk.subnet_api.get_subnet_by_id, subnet_uuid)
    subnet = response.data
    return subnet.to_dict() if subnet else {}


def _build_subnet_ip_config(arguments: dict[str, Any]) -> Any:
    """Build an IPConfig entry from IPAM arguments, or None when no CIDR is given."""
    network_cidr = arguments.get("network_cidr")
    if not network_cidr:
        return None

    import ntnx_networking_py_client.models.common.v1.config.IPv4Address as AddrModule
    import ntnx_networking_py_client.models.networking.v4.config.IPConfig as IPConfigModule
    import ntnx_networking_py_client.models.networking.v4.config.IPv4Config as IPv4ConfigModule
    import ntnx_networking_py_client.models.networking.v4.config.IPv4Pool as PoolModule
    import ntnx_networking_py_client.models.networking.v4.config.IPv4Subnet as SubnetIpModule

    ip, _, prefix_str = network_cidr.partition("/")
    prefix = int(prefix_str) if prefix_str else 24

    ipv4_config = IPv4ConfigModule.IPv4Config()
    ipv4_config.ip_subnet = SubnetIpModule.IPv4Subnet(
        ip=AddrModule.IPv4Address(value=ip, prefix_length=prefix),
        prefix_length=prefix,
    )

    gateway_ip = arguments.get("gateway_ip")
    if gateway_ip:
        ipv4_config.default_gateway_ip = AddrModule.IPv4Address(value=gateway_ip, prefix_length=prefix)

    pool_start = arguments.get("dhcp_pool_start")
    pool_end = arguments.get("dhcp_pool_end")
    if pool_start and pool_end:
        ipv4_config.pool_list = [
            PoolModule.IPv4Pool(
                start_ip=AddrModule.IPv4Address(value=pool_start, prefix_length=prefix),
                end_ip=AddrModule.IPv4Address(value=pool_end, prefix_length=prefix),
            )
        ]

    ip_config = IPConfigModule.IPConfig()
    ip_config.ipv4 = ipv4_config
    return ip_config


async def handle_create_subnet(client: NutanixClient, arguments: dict[str, Any]) -> dict[str, Any]:
    """Create a subnet using the official Nutanix SDK."""
    import ntnx_networking_py_client.models.networking.v4.config.Subnet as SubnetModule

    subnet = SubnetModule.Subnet()
    subnet.name = arguments["name"]
    subnet.subnet_type = arguments.get("subnet_type", "VLAN")
    subnet.network_id = arguments["vlan_id"]
    # cluster_reference is a plain cluster extId string on the Subnet model.
    subnet.cluster_reference = arguments["cluster_uuid"]
    if arguments.get("description"):
        subnet.description = arguments["description"]

    ip_config = _build_subnet_ip_config(arguments)
    if ip_config:
        subnet.ip_config = [ip_config]

    sdk = client.sdk
    response = await sdk.call(sdk.subnet_api.create_subnet, subnet)
    task_id = response.data.ext_id if response.data else None
    return {"status": "subnet_creation_initiated", "taskExtId": task_id}


async def handle_update_subnet(client: NutanixClient, arguments: dict[str, Any]) -> dict[str, Any]:
    """Update a subnet using the official Nutanix SDK with ETag concurrency control."""
    subnet_uuid = arguments["subnet_uuid"]
    sdk = client.sdk

    get_response = await sdk.call(sdk.subnet_api.get_subnet_by_id, subnet_uuid)
    etag = sdk.get_etag(get_response)
    subnet = get_response.data

    if "name" in arguments:
        subnet.name = arguments["name"]
    if "description" in arguments:
        subnet.description = arguments["description"]
    if "vlan_id" in arguments:
        subnet.network_id = arguments["vlan_id"]

    ip_config = _build_subnet_ip_config(arguments)
    if ip_config:
        subnet.ip_config = [ip_config]

    response = await sdk.call(sdk.subnet_api.update_subnet_by_id, subnet_uuid, subnet, if_match=etag)
    task_id = response.data.ext_id if response.data else None
    return {"status": "subnet_update_initiated", "taskExtId": task_id}


async def handle_list_images(client: NutanixClient, arguments: dict[str, Any]) -> dict[str, Any]:
    """List images using official Nutanix SDK."""
    filter_expr = arguments.get("filter")
    limit = arguments.get("limit")
    sdk = client.sdk

    kwargs: dict[str, Any] = {}
    if filter_expr:
        kwargs["_filter"] = filter_expr

    if limit:
        response = await sdk.call(sdk.image_api.list_images, _limit=limit, **kwargs)
        images = response.data or []
    else:
        images = await sdk.list_all(sdk.image_api.list_images, **kwargs)

    return {
        "totalReturned": len(images),
        "note": "All matching images returned. No further pagination needed.",
        "images": [
            {
                "name": img.name,
                "extId": img.ext_id,
                "type": img.type,
                "sizeBytes": img.size_bytes,
                "sourceUri": img.source.url if hasattr(img, "source") and img.source else None,
                "description": img.description,
            }
            for img in images
        ],
    }


async def handle_get_image(client: NutanixClient, arguments: dict[str, Any]) -> dict[str, Any]:
    """Get image details using official Nutanix SDK."""
    image_uuid = arguments["image_uuid"]
    sdk = client.sdk
    response = await sdk.call(sdk.image_api.get_image_by_id, image_uuid)
    image = response.data
    return image.to_dict() if image else {}


async def handle_list_categories(client: NutanixClient, arguments: dict[str, Any]) -> dict[str, Any]:
    """List categories using official Nutanix SDK."""
    filter_expr = arguments.get("filter")
    limit = arguments.get("limit")
    sdk = client.sdk

    kwargs: dict[str, Any] = {}
    if filter_expr:
        kwargs["_filter"] = filter_expr

    if limit:
        response = await sdk.call(sdk.category_api.list_categories, _limit=limit, **kwargs)
        categories = response.data or []
    else:
        categories = await sdk.list_all(sdk.category_api.list_categories, **kwargs)

    return {
        "totalReturned": len(categories),
        "note": "All matching categories returned. No further pagination needed.",
        "categories": [
            {
                "key": cat.key,
                "extId": cat.ext_id,
                "value": cat.value,
                "description": cat.description,
                "type": cat.type,
            }
            for cat in categories
        ],
    }


async def handle_get_category(client: NutanixClient, arguments: dict[str, Any]) -> dict[str, Any]:
    """Get category details using official Nutanix SDK."""
    category_uuid = arguments["category_uuid"]
    sdk = client.sdk
    response = await sdk.call(sdk.category_api.get_category_by_id, category_uuid)
    category = response.data
    return category.to_dict() if category else {}


# ─── Handler Dispatch ─────────────────────────────────────────────────────────

NETWORKING_HANDLERS: dict[str, Any] = {
    "list_subnets": handle_list_subnets,
    "get_subnet": handle_get_subnet,
    "create_subnet": handle_create_subnet,
    "update_subnet": handle_update_subnet,
    "list_images": handle_list_images,
    "get_image": handle_get_image,
    "list_categories": handle_list_categories,
    "get_category": handle_get_category,
}
