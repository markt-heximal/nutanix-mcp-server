#!/usr/bin/env bash
# Per-node installer for the Nutanix MCP server.
#
# Run this ON each Claude Code node in the fleet. It is idempotent — safe to
# re-run to update a node to the latest commit.
#
#   Requires on the node: git, python3, and the `claude` CLI.
#   Does NOT create .env — that holds the PE password and is gitignored, so it
#   must be placed separately (e.g. scp'd from a configured "golden" node).
#   The script stops and tells you how if .env is missing.
#
# Usage:
#   ./fleet-install.sh                 # installs to ~/nutanix-mcp-server
#   ./fleet-install.sh /opt/nutanix    # custom location
set -euo pipefail

REPO_URL="https://github.com/markt-heximal/nutanix-mcp-server.git"
REPO_DIR="${1:-$HOME/nutanix-mcp-server}"

echo "== node: $(hostname) =="

# 1. Clone or fast-forward.
if [ -d "$REPO_DIR/.git" ]; then
  echo "-> updating $REPO_DIR"
  git -C "$REPO_DIR" pull --ff-only
else
  echo "-> cloning into $REPO_DIR"
  git clone "$REPO_URL" "$REPO_DIR"
fi
cd "$REPO_DIR"

# 2. Install (editable). Handle PEP 668 externally-managed envs (Ubuntu, Homebrew
#    Python) by retrying with --break-system-packages; fall back for older pip
#    that doesn't know the flag.
echo "-> installing package"
python3 -m pip install -e . --break-system-packages \
  || python3 -m pip install -e . \
  || { echo "!! pip install failed — consider a venv on this node"; exit 1; }

# 3. Make the launch wrapper executable.
chmod +x run-mcp.sh

# 4. Require .env before registering (never fabricate credentials).
if [ ! -f "$REPO_DIR/.env" ]; then
  cat >&2 <<EOF
!! $REPO_DIR/.env not found.
   Copy it from a configured node (all nodes point at the same PE), then re-run:
     scp GOLDEN_NODE:$REPO_DIR/.env "$REPO_DIR/.env" && chmod 600 "$REPO_DIR/.env"
EOF
  exit 1
fi
chmod 600 "$REPO_DIR/.env" || true

# 5. Register with Claude Code at user scope (idempotent: remove then add).
echo "-> registering with Claude Code"
claude mcp remove nutanix -s user >/dev/null 2>&1 || true
claude mcp add nutanix -s user -- "$REPO_DIR/run-mcp.sh"

echo "== done on $(hostname) =="
claude mcp get nutanix || true
