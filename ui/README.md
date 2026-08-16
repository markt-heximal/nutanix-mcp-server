# Nutanix management UI (Lovable)

Everything needed to build the frontend in Lovable and point it at the
management API running on your AI factory mini.

| File | What it is |
|------|-----------|
| `LOVABLE_BUILD_SPEC.md` | **Start here.** Section 1 is a prompt to paste into a new Lovable project; the rest is the screen-by-screen brief. |
| `API_REFERENCE.md` | Exact endpoints, request/response shapes, error codes, role map. Paste into Lovable **project knowledge**. |
| `tool-catalog.json` | All 71 tools with titles, `min_role`, `destructive`, and JSON-Schema inputs — generated from the server, so forms match reality. |
| `src/lib/types.ts` | TypeScript types for the API. |
| `src/lib/nutanixClient.ts` | Drop-in typed API client (`login`, `callTool`, `waitForTask`, role/config helpers). |

## The shape of it

```
Lovable app (browser) ──HTTPS + JWT──▶ management_api.py (mini) ──▶ Prism Central/Element
```

- **Frontend only** — no Supabase/database in Lovable. All data is `POST /api/tools/{name}`.
- The browser holds only a short-lived JWT; Nutanix credentials never leave the mini.
- Roles gate actions: `viewer` (read), `operator` (safe writes), `admin` (destructive).

## Wiring checklist

1. Deploy the backend: see `../docs/MANAGEMENT_DEPLOY.md`.
2. In Lovable, set env `VITE_API_BASE_URL` to your API origin (e.g. `https://mini.example.com`).
3. On the mini, set `MGMT_CORS_ORIGINS` to your deployed Lovable origin.
4. Create a user (`python ../scripts/mgmt_user.py you admin`) and log in.

## Regenerating the catalogue

If tools are added/changed in the server:

```bash
python - <<'PY'
import json
from nutanix_mcp.tools import get_all_tools
def mr(t):
    a=t['annotations']
    if getattr(a,'readOnlyHint',None) is True: return 'viewer'
    return 'admin' if getattr(a,'destructiveHint',None) is True else 'operator'
json.dump({'tools':[{'name':t['name'],'title':t.get('title'),
  'description':t.get('description'),'min_role':mr(t),
  'destructive':getattr(t['annotations'],'destructiveHint',None) is True,
  'read_only':getattr(t['annotations'],'readOnlyHint',None) is True,
  'inputSchema':t.get('inputSchema')} for t in get_all_tools()]},
  open('ui/tool-catalog.json','w'),indent=2)
PY
```
