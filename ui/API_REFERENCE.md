# Management API reference (for the frontend)

Base URL: your deployed HTTPS origin (e.g. `https://mini.example.com`).
All app data flows through one generic tool endpoint; auth is a JWT bearer token.

## Auth

### `POST /api/auth/login`
Body: `{ "username": "...", "password": "..." }`
→ `200`:
```json
{ "access_token": "<jwt>", "token_type": "bearer", "expires_in": 3600,
  "username": "alice", "role": "admin" }
```
→ `401` on bad credentials. Store the token; send it on every other call as
`Authorization: Bearer <jwt>`. Tokens expire after `expires_in` seconds — on any
`401` with `"Session expired"`, route the user back to login.

### `GET /api/me` → `{ "username", "role" }`
### `GET /api/config` → `{ "default_pe_host", "allowed_pe_hosts", "pe_only", "roles", "your_role" }`
Use `default_pe_host` to prefill the `pe_host` argument on Prism Element calls.

## Tool catalogue

### `GET /api/tools`
→ `{ "tools": [ { name, title, description, inputSchema, min_role, destructive, allowed } ] }`

- `min_role`: `"viewer" | "operator" | "admin"` required to run it.
- `destructive`: true ⇒ the UI must show a confirm dialog and send `confirm: true`.
- `allowed`: whether the **current** user may run it — disable/hide the control if false.

The catalogue is also committed at `ui/tool-catalog.json` (identical shape minus
`allowed`) so you can scaffold forms without a live backend. TypeScript types are
in `ui/src/lib/types.ts`.

## Executing a tool

### `POST /api/tools/{name}`
Body:
```json
{ "arguments": { ...per the tool's inputSchema... }, "confirm": false }
```
- `arguments` must satisfy the tool's `inputSchema` (required fields enforced by the cluster).
- `confirm` must be `true` for any tool where `destructive === true`, else you get `428`.
  You do **not** need to also put `confirm` inside `arguments` (even for `delete_vm`);
  the server injects it from the top-level flag.

→ `200`: `{ "tool": "<name>", "data": <result> }` — `data` is the raw tool result
(shape varies per tool; render defensively).

Error codes:
| Code | Meaning | UI action |
|------|---------|-----------|
| 401 | not logged in / token expired | redirect to login |
| 403 | your role is too low for this tool | hide/disable the action |
| 404 | unknown tool name | bug — check the name |
| 409 | PE-only mode blocks a Prism Central tool | hide PC features when `pe_only` |
| 428 | destructive op needs `confirm: true` | show confirm dialog, resend |
| 502 | cluster unreachable / upstream error | toast the `detail` message |

The error body is `{ "detail": "<human message>" }` in every case.

## Roles → capability map

| Role | Can call |
|------|----------|
| `viewer` | all read-only tools (list_*, get_*, pe_list_*, pe_get_*, health, alerts, AsBuilt) |
| `operator` | viewer + non-destructive writes: `power_on_vm`, `create_vm`, `clone_vm`, `snapshot_vm`, `acknowledge_alert`, `assign_category`, `remove_category` |
| `admin` | operator + destructive writes: `power_off_vm`, `update_vm`, `delete_vm`, `restore_vm_snapshot` |

## Key tools by screen (with argument shapes)

Prism Central (fleet-wide) tools take no `pe_host`. Prism Element (`pe_*`) tools
take `pe_host` (default from `/api/config`). Mutations return a **task UUID** —
poll `get_task` until complete before declaring success.

**VMs**
- `list_vms` `{ cluster_name?, filter?, limit? }` — table source
- `get_vm` `{ vm_uuid }` — detail drawer (CPU, memory, disks, NICs)
- `power_on_vm` `{ vm_uuid }` (operator)
- `power_off_vm` `{ vm_uuid, force? }` (admin, destructive, confirm)
- `create_vm` `{ name, cluster_uuid, num_vcpus?=2, memory_mb?=4096, disk_size_gb?=40 }` (operator)
- `update_vm` `{ vm_uuid, name?, description?, num_vcpus?, memory_mb? }` (admin, destructive, confirm)
- `clone_vm` `{ vm_uuid, new_name }` (operator)
- `delete_vm` `{ vm_uuid }` + top-level `confirm:true` (admin, destructive)
- `snapshot_vm` `{ vm_uuid, name?, expiration_days? }` (operator)
- `list_vm_snapshots` `{ vm_uuid, limit? }`
- `restore_vm_snapshot` `{ recovery_point_id, vm_uuid }` (admin, destructive, confirm)

**Overview / Clusters / Hosts**
- `list_clusters` `{ filter? }`, `get_cluster` `{ cluster_uuid }`
- `list_hosts` `{ cluster_uuid?, filter?, limit? }`, `get_host` `{ host_uuid }`
- `list_storage_containers` `{ cluster_uuid?, limit? }`
- `pe_get_cluster_info` / `pe_get_cluster_health` / `pe_list_health_checks` `{ pe_host }`

**Storage (Prism Element)**
- `pe_list_containers`, `pe_list_storage_pools`, `pe_list_disks`, `pe_list_volume_groups` `{ pe_host }`
- `pe_get_volume_group` `{ pe_host, uuid }`
- `pe_get_host_disks` / `pe_get_host_nics` `{ pe_host, host_uuid }`

**Data protection (Prism Element)**
- `pe_list_protection_domains`, `pe_list_remote_sites`, `pe_list_unprotected_vms` `{ pe_host }`
- `pe_get_protection_domain` `{ pe_host, name }`, `pe_list_snapshots` `{ pe_host, protection_domain }`
- `pe_get_replication_status` `{ pe_host, protection_domain }`, `pe_list_pd_replications` / `pe_list_dr_snapshots` `{ pe_host }`

**Networking / Images / Categories**
- `list_subnets`, `get_subnet` `{ subnet_uuid }`; `list_images`, `get_image` `{ image_uuid }`
- `list_categories`, `get_category` `{ category_uuid }`, `list_entities_by_category` `{ category_key, category_value }`
- `assign_category` / `remove_category` `{ vm_uuid, category_key, category_value }` (operator)

**Alerts / Tasks**
- `list_alerts` `{ severity?, resolved?, filter?, limit? }`, `get_alert` `{ alert_uuid }`
- `acknowledge_alert` `{ alert_uuid, action? }` (operator)
- `list_tasks` `{ filter?, limit? }`, `get_task` `{ task_uuid }` — poll after mutations

**Reports**
- `generate_asbuilt` `{ pe_host, sections? }` → Markdown
- `export_asbuilt_html` `{ markdown, title? }` → self-contained HTML (render/download)
