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

## Quick start (one command)

On the mini, from the repo root:

```bash
./deploy/orbstack-up.sh
```

It creates any missing secrets (JWT secret, CORS origin, first admin user),
builds the image, starts it behind OrbStack's HTTPS domain, and smoke-tests
`/healthz`. The first run stops after creating `.env` so you can fill in your
Nutanix credentials — edit it, then run the script again. The manual steps
below are the same thing, broken out.

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

This deployment is scoped to **same-Mac access**: `*.orb.local` resolves only on
the Mac running OrbStack, so you use the Lovable app in a browser **on this Mac**.

- In Lovable set `VITE_API_BASE_URL=https://nutanix-api.orb.local`.
- Set `MGMT_CORS_ORIGINS` (in `.management.env`) to your Lovable app origin exactly
  — e.g. `https://your-app.lovable.app` (the app's published/preview origin, **not**
  the `orb.local` address). That's the page origin the browser sends; `orb.local`
  is only where the API lives.
- Log in with the user you created.

> **Why it just works.** The Lovable page is served from a *public* origin but
> calls the API on a *private* address (`orb.local`). Chrome guards that with a
> Private Network Access preflight; the management API answers it
> (`Access-Control-Allow-Private-Network: true`), and OrbStack's cert is already
> trusted on this Mac — so there are no CORS, mixed-content, or cert warnings.
>
> Using the app from a **different device** (phone, another laptop) is out of
> scope for this setup, since `orb.local` won't resolve there.

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
