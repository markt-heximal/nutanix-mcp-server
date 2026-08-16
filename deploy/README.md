# Deploy — systemd services

Reboot-proof deployment for the read-only façade (and, optionally, the MCP
server in HTTP mode). Verified on Spark-47d8 (Ubuntu, aarch64) against live
Prism Element at 10.0.1.242.

The **stdio** MCP server needs no service — Claude Code / Ruflo spawn it on
demand over the pipe (`claude mcp add nutanix -- python3 -m nutanix_mcp`). Only
long-running network services belong here.

## Prerequisites

```bash
cd ~/nutanix-mcp-server
pip install -e . --break-system-packages   # fastapi is a declared dependency
```

`.env` in the repo root supplies `NUTANIX_*` (including `NUTANIX_PE_ONLY=true`).
The façade also needs a **stable** API key in `.facade.env` — an ephemeral key
would change on every restart and break the frontend.

## 1. Stable façade key

```bash
cp deploy/.facade.env.example .facade.env
# put a real key in it:
sed -i "s/replace-with-openssl-rand-hex-32/$(openssl rand -hex 32)/" .facade.env
# set FACADE_CORS_ORIGINS to the real frontend origin, then lock it down:
chmod 600 .facade.env
```

`.facade.env` is gitignored (`.env` suffix) — the secret never leaves the host.

## 2. Façade service

```bash
sudo cp deploy/nutanix-pe-facade.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now nutanix-pe-facade.service
systemctl status nutanix-pe-facade.service --no-pager
```

Verify it serves live data:

```bash
KEY=$(grep FACADE_API_KEY .facade.env | cut -d= -f2)
curl -s -H "X-API-Key: $KEY" http://localhost:9770/pe/vms | head -c 200; echo
```

## 3. (Optional) MCP server over HTTP

Only if you need networked MCP clients. The HTTP transport has **no built-in
auth**, so keep it on 127.0.0.1 and reach it over Tailscale only.

```bash
sudo cp deploy/nutanix-mcp-http.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now nutanix-mcp-http.service
```

## 4. Expose the façade (Tailscale Serve)

Both units bind 127.0.0.1 by design. Front the façade with TLS over the tailnet
rather than opening a port:

```bash
tailscale serve --bg --https=443 http://127.0.0.1:9770
tailscale serve status
```

Point the frontend at the resulting HTTPS URL; send the stable key as
`X-API-Key`.

## Per-node notes

The units hardcode `User=markt` and `/home/markt/nutanix-mcp-server`. On the SFO
node, adjust those paths/user if different, and point `NUTANIX_HOST` in `.env`
at that site's PE VIP. Under a shared Prism Central (two-site plan), you can run
one façade per site for locality — each reads only its local PE.

## Operations

```bash
sudo systemctl restart nutanix-pe-facade      # after editing .env or .facade.env
journalctl -u nutanix-pe-facade -n 50 --no-pager
sudo systemctl disable --now nutanix-pe-facade # stop + remove from boot
```
