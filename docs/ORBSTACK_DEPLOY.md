# Deploying the management API on OrbStack

Your AI factory mini already runs [OrbStack](https://orbstack.dev), so the
backend deploys as a single Docker container — and OrbStack gives it an
**HTTPS URL with a locally-trusted cert automatically**, so there's no Caddy or
manual TLS to set up.

```
Lovable app (browser) ──HTTPS──▶ OrbStack reverse proxy ──▶ nutanix-mgmt-api container ──▶ Prism
   JWT bearer token              https://nutanix-api.orb.local        :9780                 :9440
```

Compose file: `deploy/docker-compose.orbstack.yml` (drops the Caddy proxy the
generic `docker-compose.yml` uses).

## 1. Secrets

```bash
cd ~/nutanix-mcp-server        # your checkout on the mini

cp .env.example .env                            # Nutanix connection
# fill in NUTANIX_HOST / NUTANIX_USERNAME / NUTANIX_PASSWORD / NUTANIX_VERIFY_SSL
# (and NUTANIX_ALLOWED_PE_HOSTS if you want to pin PE targets)

cp deploy/.management.env.example .management.env
sed -i '' "s/replace-with-openssl-rand-hex-32/$(openssl rand -hex 32)/" .management.env
chmod 600 .env .management.env
```

Set `MGMT_CORS_ORIGINS` in `.management.env` to your Lovable app origin
(e.g. `https://your-app.lovable.app`).

Create at least one user (hash only — never plaintext):

```bash
mkdir -p deploy/secrets
python scripts/mgmt_user.py alice admin > deploy/secrets/users.json
# add more users by merging their objects into the same JSON file:
# { "alice": {...}, "bob": {...} }
chmod 600 deploy/secrets/users.json
```

## 2. Choose the domain, then bring it up

```bash
# optional — defaults to nutanix-api.orb.local
export ORB_DOMAIN=nutanix-api.orb.local

docker compose -f deploy/docker-compose.orbstack.yml up -d --build
```

OrbStack now serves the API at `https://${ORB_DOMAIN}` with a trusted cert.
Verify from the Mac:

```bash
curl https://nutanix-api.orb.local/healthz          # {"status":"ok"} — no -k needed
```

Log in and hit a read tool:

```bash
BASE=https://nutanix-api.orb.local
TOKEN=$(curl -s $BASE/api/auth/login -H 'Content-Type: application/json' \
  -d '{"username":"alice","password":"..."}' \
  | python3 -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')
curl -s $BASE/api/tools/list_clusters -X POST -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' -d '{"arguments":{}}'
```

## 3. Point the frontend at it

- In Lovable set `VITE_API_BASE_URL=https://nutanix-api.orb.local`.
- Confirm `MGMT_CORS_ORIGINS` (in `.management.env`) matches the Lovable origin exactly.
- Log in with the user you created.

> **Note on access scope.** `*.orb.local` resolves **only on the Mac running
> OrbStack**. If you open the Lovable app in a browser on that same Mac, the
> trusted-cert HTTPS domain works with zero extra setup. To use the app from a
> phone or another machine, see "Remote access" below.

## Remote access (other devices)

The container also binds `127.0.0.1:9780` on the host, so front it with Tailscale
on the Mac to reach it over your tailnet with TLS:

```bash
tailscale serve --bg --https=443 http://127.0.0.1:9780
tailscale serve status        # shows the https://<host>.<tailnet>.ts.net URL
```

Then use that `*.ts.net` URL as `VITE_API_BASE_URL` and add it to
`MGMT_CORS_ORIGINS`. (Anything reaching the API this way is still gated by
login + JWT + RBAC.)

## Operations

```bash
docker compose -f deploy/docker-compose.orbstack.yml logs -f api
docker compose -f deploy/docker-compose.orbstack.yml up -d --build   # after code changes
docker compose -f deploy/docker-compose.orbstack.yml restart api     # after editing .env / users.json
docker compose -f deploy/docker-compose.orbstack.yml down            # stop
```

Editing `.env` or `.management.env` requires a `restart`; changing
`deploy/secrets/users.json` also requires a `restart` (it's read at startup).
Rotating `MGMT_JWT_SECRET` logs everyone out.
