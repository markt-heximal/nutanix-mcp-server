"""Tool registry and definitions.

Tool modules define bare tool dicts (name/description/inputSchema).
This registry enriches them with MCP metadata — a human-readable
``title`` and ``annotations`` (read-only / destructive / idempotent
hints) — so clients can present and gate tools appropriately.
"""

from typing import Any

from mcp.types import ToolAnnotations

from nutanix_mcp.tools.alert import ALERT_TOOLS
from nutanix_mcp.tools.asbuilt import ASBUILT_TOOLS
from nutanix_mcp.tools.category import CATEGORY_TOOLS
from nutanix_mcp.tools.cluster import CLUSTER_TOOLS
from nutanix_mcp.tools.networking import NETWORKING_TOOLS
from nutanix_mcp.tools.prism_element import PE_TOOLS
from nutanix_mcp.tools.snapshot import SNAPSHOT_TOOLS
from nutanix_mcp.tools.task import TASK_TOOLS
from nutanix_mcp.tools.vm import VM_TOOLS

# Hints for tools that mutate state. Everything not listed here is read-only.
# destructiveHint: the call can delete/overwrite data or interrupt workloads.
# idempotentHint: repeating the call with the same arguments has no extra effect.
_WRITE_TOOL_HINTS: dict[str, dict[str, bool]] = {
    "create_vm": {"destructiveHint": False, "idempotentHint": False},
    "update_vm": {"destructiveHint": True, "idempotentHint": True},
    "delete_vm": {"destructiveHint": True, "idempotentHint": True},
    "clone_vm": {"destructiveHint": False, "idempotentHint": False},
    "power_on_vm": {"destructiveHint": False, "idempotentHint": True},
    "power_off_vm": {"destructiveHint": True, "idempotentHint": True},
    "snapshot_vm": {"destructiveHint": False, "idempotentHint": False},
    "restore_vm_snapshot": {"destructiveHint": True, "idempotentHint": True},
    "acknowledge_alert": {"destructiveHint": False, "idempotentHint": True},
    "assign_category": {"destructiveHint": False, "idempotentHint": True},
    "remove_category": {"destructiveHint": False, "idempotentHint": True},
    "create_subnet": {"destructiveHint": False, "idempotentHint": False},
    "update_subnet": {"destructiveHint": True, "idempotentHint": True},
    "delete_subnet": {"destructiveHint": True, "idempotentHint": True},
    "create_storage_container": {"destructiveHint": False, "idempotentHint": False},
    "resize_storage_container": {"destructiveHint": True, "idempotentHint": True},
    "delete_storage_container": {"destructiveHint": True, "idempotentHint": True},
}

# Acronyms and product terms that plain title-casing would mangle.
_TITLE_WORDS: dict[str, str] = {
    "vm": "VM",
    "vms": "VMs",
    "cvms": "CVMs",
    "nics": "NICs",
    "pe": "PE",
    "dr": "DR",
    "pd": "PD",
    "smtp": "SMTP",
    "snmp": "SNMP",
    "nfs": "NFS",
    "html": "HTML",
    "asbuilt": "AsBuilt",
}


def _derive_title(name: str) -> str:
    """Build a human-readable title from a snake_case tool name."""
    words = name.split("_")
    prefix = ""
    if words and words[0] == "pe":
        prefix = "PE: "
        words = words[1:]
    titled = " ".join(_TITLE_WORDS.get(w, w.capitalize()) for w in words)
    return f"{prefix}{titled}"


def _annotations_for(name: str) -> ToolAnnotations:
    """Derive MCP tool annotations from the tool's behavior."""
    hints = _WRITE_TOOL_HINTS.get(name)
    if hints is None:
        return ToolAnnotations(
            title=_derive_title(name),
            readOnlyHint=True,
            openWorldHint=False,
        )
    return ToolAnnotations(
        title=_derive_title(name),
        readOnlyHint=False,
        destructiveHint=hints["destructiveHint"],
        idempotentHint=hints["idempotentHint"],
        openWorldHint=False,
    )


def get_all_tools(pe_only: bool = False) -> list[dict[str, Any]]:
    """Return all registered tool definitions, enriched with MCP metadata.

    When ``pe_only`` is True, only Prism Element (``pe_*``) tools are returned.
    This keeps the advertised tool surface honest on deployments that have no
    Prism Central: the model never sees central-plane tools it cannot use.
    """
    tools = (
        VM_TOOLS + CLUSTER_TOOLS + PE_TOOLS + NETWORKING_TOOLS + TASK_TOOLS
        + ALERT_TOOLS + CATEGORY_TOOLS + SNAPSHOT_TOOLS + ASBUILT_TOOLS
    )
    if pe_only:
        tools = [t for t in tools if t["name"].startswith("pe_")]
    seen: set[str] = set()
    enriched: list[dict[str, Any]] = []
    for tool in tools:
        name = tool["name"]
        if name in seen:
            raise ValueError(f"Duplicate tool name registered: {name}")
        seen.add(name)
        enriched.append(
            {
                **tool,
                "title": tool.get("title") or _derive_title(name),
                "annotations": _annotations_for(name),
            }
        )
    return enriched
