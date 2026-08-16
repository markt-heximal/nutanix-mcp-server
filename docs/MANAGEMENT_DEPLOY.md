# Deploying the management API on the AI factory mini

The **management API** (`management_api.py`) is the backend for the Lovable UI.
It fronts the full Nutanix tool surface (read **and** write, including
create/clone/delete) behind username/password login, JWT sessions, and
role-based access control. Nutanix credentials stay on the mini; the browser
only ever holds a short-lived JWT.

```
Lovable app (browser)  ──HTTPS──▶  Caddy (TLS)  ──▶  management_api  ──▶  Prism Central / Element
   JWT in Authorization                 :443           :9780 (localhost)      :9440
```

> **Security posture.** This API can trigger destructive operations. Never bind
> it to `0.0.0.0` on an untrusted network, never hand out the `admin` role
> loosely, and keep it behind TLS. Roles: `viewer` (read-only), `operator`
> (non-destructive writes), `admin` (all, incl. delete/power-off/update/restore).

## 0. Prerequisites

- The repo checked out on the mini.
- `.env` filled in with the Nutanix connection (`NUTANIX_HOST`, `NUTANIX_USERNAME`,
  `NUTANIX_PASSWORD`, `NUTANIX_VERIFY_SSL`, and optionally `NUTANIX_ALLOWED_PE_HOSTS`).
- Python 3.10+ **or** Docker Desktop.

## 1. Configure secrets

```bash
cp .env.example .env                       # NUTANIX_* connection settings
cp deploy/.management.env.example .management.env
# stable JWT secret:
sed -i '' "s/replace-with-openssl-rand-hex-32/$(openssl rand -hex 32)/" .management.env  # macOS sed
chmod 600 .env .management.env
# set MGMT_CORS_ORIGINS to your deployed frontend origin (e.g. https://your-app.lovable.app)
```

Create users (hashes only — never plaintext):

```bash
python scripts/mgmt_user.py alice admin     >  users.json        # first user
python scripts/mgmt_user.py bob   viewer    >> /tmp/bob && \
  # then merge bob's object into users.json (it must be one JSON object):
# { "alice": {...}, "bob": {...} }
chmod 600 users.json
```

Point the API at it: set `MGMT_USERS_FILE=/abs/path/users.json` in `.management.env`
(or mount it as shown in compose).

## 2a. Run with Docker (recommended on macOS)

```bash
mkdir -p deploy/secrets && cp users.json deploy/secrets/users.json
# edit deploy/Caddyfile for your hostname (or keep `tls internal` for a lab)
docker compose -f deploy/docker-compose.yml up -d --build
```

- API runs on the internal compose network only; **Caddy** publishes `:443`.
- Verify: `curl -k https://localhost/healthz` → `{"status":"ok"}`.

## 2b. Run natively (launchd, no Docker)

```bash
python3 -m venv .venv && ./.venv/bin/pip install -e '.[api]'
# smoke test in the foreground first:
./.venv/bin/uvicorn management_api:app --host 127.0.0.1 --port 9780
```

Then install the launch agent and a TLS proxy:

```bash
cp deploy/com.heximal.nutanix-mgmt.plist ~/Library/LaunchAgents/
# edit paths inside the plist to match your checkout, then:
launchctl load ~/Library/LaunchAgents/com.heximal.nutanix-mgmt.plist

brew install caddy
caddy reverse-proxy --from :443 --to 127.0.0.1:9780   # or a Caddyfile as a service
```

## 3. Smoke-test the API

```bash
BASE=https://localhost           # or your hostname
curl -sk $BASE/healthz
TOKEN=$(curl -sk $BASE/api/auth/login -H 'Content-Type: application/json' \
  -d '{"username":"alice","password":"..."}' | python3 -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')
curl -sk $BASE/api/me      -H "Authorization: Bearer $TOKEN"
curl -sk $BASE/api/tools   -H "Authorization: Bearer $TOKEN" | head -c 400
# a read:
curl -sk $BASE/api/tools/list_clusters -X POST -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' -d '{"arguments":{}}'
```

## 4. Wire the frontend

Set the deployed origin in `MGMT_CORS_ORIGINS`, then set the same base URL and
your login in the Lovable app's config screen. See `ui/API_REFERENCE.md` for the
exact request/response shapes and `ui/LOVABLE_BUILD_SPEC.md` for the UI brief.

## Operations

```bash
# Docker
docker compose -f deploy/docker-compose.yml logs -f api
docker compose -f deploy/docker-compose.yml restart api     # after editing env/users

# launchd
tail -f /tmp/nutanix-mgmt.err.log
launchctl kickstart -k gui/$(id -u)/com.heximal.nutanix-mgmt
```

Rotating `MGMT_JWT_SECRET` invalidates all active sessions (everyone re-logs in).

## The live deployment on ai-factory-mini

Verified 2026-08-16. This is the actual running setup, as distinct from the
generic instructions above.

| Thing | Value |
|---|---|
| Checkout | `/Users/markt/nutanix-mcp-server` (**not** `/Users/SHARED/…`) |
| Compose file | `deploy/docker-compose.orbstack.yml`, service `api` |
| Container | `nutanix-mgmt-api-1`, listening on `127.0.0.1:9780` |
| Published via | the shared `v0-gateway` Caddy on `/ntx/*` — see [GATEWAY.md](GATEWAY.md) |
| Env | `.env` (`NUTANIX_*`) + `.management.env` (`MGMT_*`), both gitignored |
| Users | `deploy/secrets/users.json`, mounted at `/run/secrets/users.json` |

The launchd unit in `deploy/` is an **alternative** to this, not a description of
it. Do not load both — they would contend for `127.0.0.1:9780`.

### The `.env` sync trap

The mini's `.env` is a **separate copy** and does not sync from anywhere. After
any Prism Central/Element address or credential change, update it or the console
breaks in a way that looks like a frontend bug: the gateway, JWT and CORS all
keep working and `/api/tools` still returns 200, but every
`POST /api/tools/{name}` that touches PC returns 502 with `MaxRetryError` or a
30s timeout.

If that happens, check `NUTANIX_HOST` in the container first:

```bash
docker exec nutanix-mgmt-api-1 env | grep -E '^NUTANIX_(HOST|ALLOWED_PE_HOSTS)='
```

### Rebuilding the image safely

```bash
# 1. Pin a rollback FIRST — a rebuild overwrites :latest.
docker tag nutanix-mgmt-api:latest nutanix-mgmt-api:rollback-$(date +%Y%m%d)

# 2. Move the checkout to the commit you want to ship.
cd /Users/markt/nutanix-mcp-server
git fetch origin && git switch main && git merge --ff-only origin/main

# 3. Build ALONE — never `up --build`, so a failed build cannot take the
#    running service down.
docker compose -f deploy/docker-compose.orbstack.yml build api

# 4. Verify the new image BEFORE deploying it.
docker run --rm --entrypoint sh nutanix-mgmt-api:latest \
  -c 'wc -l < /app/src/nutanix_mcp/tools/prism_element.py'

# 5. Deploy, then verify.
docker compose -f deploy/docker-compose.orbstack.yml up -d --force-recreate api
docker exec nutanix-mgmt-api-1 /app/.venv/bin/python \
  -c 'from nutanix_mcp.tools import get_all_tools; print(len(get_all_tools()))'
```

Rollback: `docker tag nutanix-mgmt-api:rollback-<date> nutanix-mgmt-api:latest`
then re-run step 5.

`.env`, `.management.env` and `deploy/secrets/users.json` are gitignored and
survive a branch switch untouched.

Two gotchas worth knowing:

- Use the container's own interpreter, **`/app/.venv/bin/python`**. The
  container's bare `python3` cannot import `nutanix_mcp`.
- Over **non-interactive** SSH, macOS hands out a minimal `PATH` that omits both
  the OrbStack `docker` CLI and `/usr/local/bin` (the docker credential
  helpers), so builds fail with
  `error getting credentials — exec: "docker-credential-noop": executable file
  not found`. The binary is not missing; it is just not on `PATH`. Fix with
  `export PATH=/usr/local/bin:$HOME/.orbstack/bin:$PATH`, or permanently in
  `~/.zshenv` (done on the mini). Do **not** "fix" `credsStore` in
  `~/.docker/config.json` — that setting is deliberate and correct.
