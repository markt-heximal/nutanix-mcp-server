#!/usr/bin/env bash
# One-shot bring-up for the Nutanix management API on the AI factory mini (macOS
# + OrbStack). Run it ON THE MINI, from the repo root:
#
#     ./deploy/orbstack-up.sh
#
# It is idempotent: it creates missing secrets, builds one admin user, then
# brings up the container behind OrbStack's trusted-HTTPS domain. Re-run it any
# time to rebuild/restart. Uses BSD sed (macOS default) on purpose.
set -euo pipefail
cd "$(cd "$(dirname "$0")/.." && pwd)"   # repo root

ORB_DOMAIN="${ORB_DOMAIN:-nutanix-api.orb.local}"
PREVIEW_ORIGIN_DEFAULT="https://id-preview--de69a308-005e-4ff6-b3c9-f7bf609f8c28.lovable.app"

need() { command -v "$1" >/dev/null 2>&1 || { echo "error: '$1' not found in PATH" >&2; exit 1; }; }
need docker; need openssl; need python3

# 1. Nutanix connection (.env) — must be filled in by hand (has your password).
if [ ! -f .env ]; then
  cp .env.example .env
  echo ""
  echo ">> Created .env. Edit it with your NUTANIX_HOST / NUTANIX_USERNAME /"
  echo "   NUTANIX_PASSWORD (and NUTANIX_VERIFY_SSL=false for a self-signed PE),"
  echo "   then re-run this script."
  exit 1
fi

# 2. Management secrets (.management.env) — JWT secret + CORS origin.
if [ ! -f .management.env ]; then
  cp deploy/.management.env.example .management.env
  sed -i '' "s#replace-with-openssl-rand-hex-32#$(openssl rand -hex 32)#" .management.env
  printf ">> Frontend origin for CORS [%s]: " "$PREVIEW_ORIGIN_DEFAULT"
  read -r ORIGIN || true
  ORIGIN="${ORIGIN:-$PREVIEW_ORIGIN_DEFAULT}"
  sed -i '' "s#^MGMT_CORS_ORIGINS=.*#MGMT_CORS_ORIGINS=$ORIGIN#" .management.env
  chmod 600 .management.env
  echo ">> Wrote .management.env (JWT secret generated, CORS=$ORIGIN)."
fi

# 3. First admin user (deploy/secrets/users.json). mgmt_user.py prompts for the
#    password on the tty; clean JSON goes to the file.
mkdir -p deploy/secrets
if [ ! -s deploy/secrets/users.json ]; then
  printf ">> Admin username to create: "
  read -r ADMIN
  [ -n "$ADMIN" ] || { echo "error: empty username" >&2; exit 1; }
  python3 scripts/mgmt_user.py "$ADMIN" admin > deploy/secrets/users.json
  chmod 600 deploy/secrets/users.json
  echo ">> Created admin user '$ADMIN' in deploy/secrets/users.json."
fi

# 4. Build + start behind OrbStack's HTTPS domain.
echo ">> Building and starting the container (ORB_DOMAIN=$ORB_DOMAIN)..."
ORB_DOMAIN="$ORB_DOMAIN" docker compose -f deploy/docker-compose.orbstack.yml up -d --build

# 5. Smoke test the health endpoint via the OrbStack domain.
echo ">> Waiting for the API to come up..."
for i in 1 2 3 4 5 6 7 8 9 10; do
  if curl -fsS "https://$ORB_DOMAIN/healthz" >/dev/null 2>&1; then
    echo ""
    echo "✅ Up: https://$ORB_DOMAIN/healthz responded."
    echo "   Point the Lovable app's VITE_API_BASE_URL at: https://$ORB_DOMAIN"
    echo "   Log in with the admin user you just created."
    exit 0
  fi
  sleep 2
done

echo ""
echo "⚠️  API did not answer /healthz yet. Check logs:"
echo "   docker compose -f deploy/docker-compose.orbstack.yml logs -f api"
exit 1
