#!/usr/bin/env bash
# Launch the Nutanix MCP server (stdio) with the repo's .env in scope.
#
# Claude Code / Desktop spawn the MCP server as a child process from whatever
# directory the client happens to run in — not necessarily this repo. The
# server loads NUTANIX_* settings from a .env in the *current* directory, so we
# cd into the script's own directory (the repo root, where .env lives) before
# exec'ing. This keeps the PE password in .env (chmod 600) instead of in the
# Claude Code config.
#
# Portable across Linux and macOS: avoids `readlink -f` (GNU-only) in favor of
# cd+pwd, which resolves the script's directory on both platforms.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"
exec python3 -m nutanix_mcp "$@"
