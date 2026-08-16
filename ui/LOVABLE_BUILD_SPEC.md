# Lovable build spec — Nutanix management console

This is the brief to build the UI in Lovable. **Section 1 is a prompt you paste
into a new Lovable project.** The rest is reference so follow-up messages stay
consistent. Pair it with `ui/API_REFERENCE.md` (exact endpoints) and
`ui/tool-catalog.json` (all 65 tools + schemas).

The app is a **pure frontend**. It talks to the management API you deploy on the
AI factory mini (`management_api.py`) over HTTPS with a JWT. It has **no database
of its own** and needs no Lovable/Supabase backend — do not enable one.

---

## 1. Paste this into Lovable (initial message)

> Build a **Nutanix infrastructure management console** — a React + TypeScript +
> Tailwind + shadcn/ui single-page app. It is a frontend only: it calls an
> external REST API (my "management API") over HTTPS with a JWT bearer token.
> **Do not add Supabase, a database, or any backend** — all data comes from my API.
>
> **Config:** read the API base URL from `VITE_API_BASE_URL` (env var), with a
> Settings screen to override it at runtime (persist to localStorage). Never
> hardcode the URL.
>
> **Auth:** a login page (username + password) posts to `POST {base}/api/auth/login`
> and receives `{ access_token, role, expires_in }`. Store the token in memory +
> localStorage, attach `Authorization: Bearer <token>` to every request, and show
> a global auth context with the current `username` and `role`. On any `401`,
> clear the token and return to login. Add a logout button.
>
> **Data layer:** all cluster data goes through ONE endpoint —
> `POST {base}/api/tools/{toolName}` with body `{ arguments: {...}, confirm: bool }`,
> returning `{ tool, data }`. Build a typed `callTool(name, arguments, confirm?)`
> helper and use TanStack Query for caching/refetch. On app load, also call
> `GET /api/config` (for `default_pe_host`) and `GET /api/tools` (catalogue with
> `min_role`, `destructive`, `allowed` per tool) and use `allowed` to disable or
> hide actions the current role can't perform.
>
> **Destructive actions** (`destructive: true` in the catalogue — delete VM, power
> off, update VM, restore snapshot): always open a confirm dialog that names the
> exact resource, and send `confirm: true`. A `428` response means confirm was
> required — show the dialog. A `403` means the role is too low — disable the control.
>
> **Layout:** a left sidebar + top bar shell. Sidebar sections: Overview, VMs,
> Hosts, Storage, Data Protection, Networking, Alerts, Tasks, Reports, Settings.
> Show the current cluster/`pe_host` in the top bar with a picker sourced from
> `list_clusters` (and `allowed_pe_hosts` from `/api/config`). Clean, dense,
> enterprise-dashboard aesthetic; dark-mode support; responsive; skeleton loaders;
> empty states; error toasts that surface the API's `detail` message.
>
> **Build the Overview page first** (KPI tiles: cluster count, VM count, hosts,
> capacity used, active alerts by severity, data-resiliency status), then the VMs
> page (table + detail drawer + power/create/clone/snapshot/delete actions). I'll
> ask for the other pages next.

Then iterate page-by-page with the section details below.

---

## 2. Screens

Each screen = read tool(s) for its data + optional action tools. `pe_host`
defaults to `/api/config` → `default_pe_host`.

### Overview
- Tiles from `list_clusters`, `list_vms` (count), `list_hosts` (count),
  `pe_get_cluster_info` / `pe_get_cluster_health` (capacity, resiliency),
  `list_alerts` (counts by `severity`).
- A "resiliency OK / degraded" banner from `pe_get_cluster_health`.

### VMs  *(the core management screen)*
- Table: `list_vms` → name, power state, vCPU, memory, cluster, IP. Search/filter.
- Row → detail drawer: `get_vm` (disks, NICs, categories) + `list_vm_snapshots`.
- Actions (gate by `allowed`):
  - Power On (`power_on_vm`) / Power Off (`power_off_vm`, confirm, `force?` toggle)
  - Create VM (`create_vm`) — form: name, cluster (from `list_clusters`), vCPU,
    memory MB, disk GB.
  - Clone (`clone_vm`), Snapshot (`snapshot_vm`), Edit (`update_vm`, confirm),
    Delete (`delete_vm`, confirm), Restore snapshot (`restore_vm_snapshot`, confirm).
- After any mutation, capture the returned **task UUID** and poll `get_task`;
  show a progress toast and refetch the table on completion.

### Hosts
- `list_hosts` / `get_host`; per-host inventory via `pe_get_host_disks` and
  `pe_get_host_nics` (need `host_uuid`); CVMs via `pe_list_cvms`.

### Storage
- Tabs: Containers (`pe_list_containers` / `list_storage_containers`), Storage
  Pools (`pe_list_storage_pools`), Disks (`pe_list_disks`), Volume Groups
  (`pe_list_volume_groups` → `pe_get_volume_group`).

### Data Protection
- Protection domains (`pe_list_protection_domains` → `pe_get_protection_domain`),
  snapshots (`pe_list_snapshots`), remote sites (`pe_list_remote_sites`),
  replication (`pe_get_replication_status`, `pe_list_pd_replications`),
  **Unprotected VMs** compliance list (`pe_list_unprotected_vms`) — highlight as risk.

### Networking
- Subnets (`list_subnets` / `get_subnet`), Images (`list_images` / `get_image`),
  PE networks (`pe_list_networks`).

### Alerts
- `list_alerts` with severity/resolved filters; row → `get_alert`;
  Acknowledge/Resolve action (`acknowledge_alert`, operator).

### Tasks
- `list_tasks` / `get_task`; auto-refresh running tasks; this is also the poll
  target for mutations elsewhere.

### Reports
- Generate AsBuilt (`generate_asbuilt` → Markdown), then `export_asbuilt_html`
  → render the returned HTML in an iframe / offer download.

### Settings
- API base URL override, current identity + role, token expiry, logout.
- Category management (`list_categories`, `assign_category`, `remove_category`).

---

## 3. Rules the generator must follow

1. **One data path:** every cluster read/write is `POST /api/tools/{name}`. No
   other backend, no direct Nutanix calls from the browser.
2. **Respect `allowed`/`min_role`:** never show an enabled control the role can't use.
3. **Confirm every `destructive` tool** and send `confirm: true`.
4. **Poll tasks** after mutations; don't claim success on the immediate response.
5. **Render defensively** — tool `data` shapes vary; guard for missing fields.
6. **Surface `detail`** from error responses in toasts; map 401→login, 403→disabled.
7. **Secrets:** the app only ever holds the JWT. No Nutanix credentials, no API
   keys in the bundle.

---

## 4. Importing into Lovable

- **Fastest:** create a new Lovable project and paste Section 1 as the first
  message; then send Section 2 screens one at a time. Add
  `ui/API_REFERENCE.md` + `ui/tool-catalog.json` as attachments/knowledge so the
  agent scaffolds forms from the real schemas.
- **Set project knowledge** to the contents of `ui/API_REFERENCE.md` so every
  follow-up message stays aligned to the real endpoints.
- **Env:** set `VITE_API_BASE_URL` to your deployed API origin. Add that same
  origin to `MGMT_CORS_ORIGINS` on the mini so the browser can call it.
- The TypeScript client in `ui/src/lib/` (`nutanixClient.ts`, `types.ts`) is a
  drop-in starting point — tell Lovable to use it as the API layer.
