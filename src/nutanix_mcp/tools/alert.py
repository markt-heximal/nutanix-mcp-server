"""Centralized alert management tools using Nutanix v4 prism namespace."""

from typing import Any

from nutanix_mcp.client import NutanixClient

# ─── Tool Definitions ─────────────────────────────────────────────────────────

ALERT_TOOLS: list[dict] = [
    {
        "name": "list_alerts",
        "description": (
            "List ALL alerts from Prism Central (auto-paginates internally). "
            "Returns complete results in one call — no manual pagination needed. "
            "Supports filtering by severity and resolved status."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "severity": {
                    "type": "string",
                    "enum": ["CRITICAL", "WARNING", "INFO"],
                    "description": "Filter by severity level.",
                },
                "resolved": {
                    "type": "boolean",
                    "description": "If true, show resolved alerts. If false, show only active. Default: false (active only).",
                },
                "filter": {
                    "type": "string",
                    "description": (
                        "OData filter expression for advanced filtering. "
                        "Examples: \"severity eq 'CRITICAL'\", "
                        "\"creationTime gt '2026-05-01T00:00:00Z'\""
                    ),
                },
                "limit": {
                    "type": "integer",
                    "description": "Optional cap on results. Default: 50.",
                },
            },
        },
    },
    {
        "name": "get_alert",
        "description": (
            "Get full details of a specific alert by UUID. "
            "Returns affected entities, resolution guidance, parameters, "
            "and alert lifecycle information."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "alert_uuid": {
                    "type": "string",
                    "description": "The UUID (extId) of the alert.",
                },
            },
            "required": ["alert_uuid"],
        },
    },
    {
        "name": "acknowledge_alert",
        "description": (
            "Acknowledge or resolve an alert by UUID. "
            "Acknowledging marks the alert as seen; resolving marks it as fixed."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "alert_uuid": {
                    "type": "string",
                    "description": "The UUID (extId) of the alert to acknowledge/resolve.",
                },
                "action": {
                    "type": "string",
                    "enum": ["ACKNOWLEDGE", "RESOLVE"],
                    "description": "Action to take. Default: ACKNOWLEDGE.",
                },
            },
            "required": ["alert_uuid"],
        },
    },
]


# ─── Tool Handlers ────────────────────────────────────────────────────────────


async def handle_list_alerts(client: NutanixClient, arguments: dict[str, Any]) -> dict[str, Any]:
    """List alerts with optional filtering."""
    severity = arguments.get("severity")
    resolved = arguments.get("resolved", False)
    custom_filter = arguments.get("filter")
    limit = arguments.get("limit", 50)

    # Build filter expression
    filter_parts = []
    if severity:
        filter_parts.append(f"severity eq '{severity}'")
    if not resolved:
        filter_parts.append("isResolved eq false")
    else:
        filter_parts.append("isResolved eq true")

    if custom_filter:
        filter_parts.append(custom_filter)

    filter_expr = " and ".join(filter_parts) if filter_parts else None

    result = await client.v4_list(
        namespace="monitoring",
        path="serviceability/alerts",
        filter=filter_expr,
        top=limit,
        orderby="creationTime desc",
    )

    alerts = result.get("data", [])

    formatted = []
    for alert in alerts:
        affected = alert.get("affectedEntities", [])
        entity_summary = [f"{e.get('type', 'unknown')}:{e.get('name', e.get('extId', '?'))}" for e in affected[:3]]

        formatted.append(
            {
                "alert_uuid": alert.get("extId", ""),
                "title": alert.get("title", ""),
                "severity": alert.get("severity", ""),
                "is_resolved": alert.get("isResolved", False),
                "is_acknowledged": alert.get("isAcknowledged", False),
                "creation_time": alert.get("creationTime", ""),
                "last_updated_time": alert.get("lastUpdatedTime", ""),
                "affected_entities": entity_summary,
                "cluster": alert.get("sourceClusterUUID", ""),
            }
        )

    return {
        "total_alerts": len(formatted),
        "filter_applied": filter_expr or "none",
        "alerts": formatted,
    }


async def handle_get_alert(client: NutanixClient, arguments: dict[str, Any]) -> dict[str, Any]:
    """Get full details of a specific alert."""
    alert_uuid = arguments["alert_uuid"]

    result = await client.v4_get(
        namespace="monitoring",
        path=f"serviceability/alerts/{alert_uuid}",
    )

    data = result.get("data", result)

    # Extract affected entities with full details
    affected = data.get("affectedEntities", [])
    entities = [
        {
            "type": e.get("type", ""),
            "name": e.get("name", ""),
            "ext_id": e.get("extId", ""),
        }
        for e in affected
    ]

    return {
        "alert_uuid": data.get("extId", ""),
        "title": data.get("title", ""),
        "severity": data.get("severity", ""),
        "message": data.get("message", ""),
        "is_resolved": data.get("isResolved", False),
        "is_acknowledged": data.get("isAcknowledged", False),
        "creation_time": data.get("creationTime", ""),
        "last_updated_time": data.get("lastUpdatedTime", ""),
        "resolution_time": data.get("resolutionTime", ""),
        "affected_entities": entities,
        "source_cluster_uuid": data.get("sourceClusterUUID", ""),
        "alert_type": data.get("alertType", ""),
        "parameters": data.get("parameters", []),
        "possible_causes": data.get("possibleCauses", []),
        "resolutions": data.get("resolutions", []),
    }


async def handle_acknowledge_alert(client: NutanixClient, arguments: dict[str, Any]) -> dict[str, Any]:
    """Acknowledge or resolve an alert."""
    alert_uuid = arguments["alert_uuid"]
    action = arguments.get("action", "ACKNOWLEDGE")

    # v4 monitoring exposes acknowledge/resolve as $actions endpoints.
    sub_action = "resolve" if action == "RESOLVE" else "acknowledge"

    # Get current alert for ETag (header is authoritative; body metadata is a fallback)
    current, etag = await client.v4_get_with_etag(
        namespace="monitoring",
        path=f"serviceability/alerts/{alert_uuid}",
    )
    if not etag:
        etag = current.get("data", {}).get("$metadata", {}).get("ETag")

    headers = {}
    if etag:
        headers["If-Match"] = etag

    await client.v4_post(
        namespace="monitoring",
        path=f"serviceability/alerts/{alert_uuid}/$actions/{sub_action}",
        headers=headers if headers else None,
    )

    return {
        "status": f"alert_{action.lower()}d",
        "alert_uuid": alert_uuid,
        "action": action,
    }


# ─── Handler Dispatch ─────────────────────────────────────────────────────────

ALERT_HANDLERS: dict[str, Any] = {
    "list_alerts": handle_list_alerts,
    "get_alert": handle_get_alert,
    "acknowledge_alert": handle_acknowledge_alert,
}
