#!/usr/bin/env bash
# Prints the HTTP headers for the official GitHub MCP server as JSON on stdout:
#   {"Authorization": "Bearer <token>"}
# Used as Claude Code `headersHelper` and Codex `http_headers_helper`.
# The token comes from the GitHub CLI's own login (`gh auth token`), so no token
# is written to any config file. Prefer a fine-grained PAT? Put it in a per-machine,
# non-synced file and print that instead.
# Do not run this by hand in a shared terminal or log: it prints a credential.
set -euo pipefail
export PATH="$PATH:/usr/local/bin:/opt/homebrew/bin:/usr/bin"
tok=$(gh auth token 2>/dev/null) || { echo '{}' ; exit 0; }
[ -n "$tok" ] || { echo '{}'; exit 0; }
printf '{"Authorization": "Bearer %s"}\n' "$tok"
