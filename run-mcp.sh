#!/usr/bin/env bash
# Launch the Nutanix MCP server (stdio) with the repo's .env in scope.
#
# Claude Code / Desktop spawn the MCP server as a child process from whatever
# directory the client happens to run in — not necessarily this repo. The
# server loads NUTANIX_* settings from a .env in the *current* directory, so we
# cd into the script's own directory (the repo root, where .env lives) before
# exec'ing. This keeps the PE password in .env (chmod 600) instead of in the
# Claude Code config.
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"
exec python3 -m nutanix_mcp "$@"
