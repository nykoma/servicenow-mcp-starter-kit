#!/bin/bash
#
# Stores ServiceNow MCP credentials in the macOS Keychain under a service
# name of your choosing (defaults to "servicenow-mcp-server"). Secrets are
# entered interactively and are NOT echoed, NOT written to disk, and NOT
# placed in your shell history.
#
# Re-run any time to rotate a value; -U updates the existing item in place.
#
set -euo pipefail

SERVICE="${1:-servicenow-mcp-server}"

store() {   # store <account> <prompt> <silent?>
  local account="$1" prompt="$2" silent="${3:-}"
  local value
  if [ "$silent" = "silent" ]; then
    read -r -s -p "$prompt: " value; echo
  else
    read -r -p "$prompt: " value
  fi
  security add-generic-password -U -s "$SERVICE" -a "$account" -w "$value" >/dev/null
  echo "  stored: $account"
}

echo "Configuring Keychain items for $SERVICE"
echo "----------------------------------------"
store instance      "ServiceNow instance host (e.g. yourinstance.service-now.com)"
store client_id     "OAuth client_id"
store client_secret "OAuth client_secret" silent

echo "----------------------------------------"
echo "Configured Keychain service: $SERVICE"
echo "Verify with:  security find-generic-password -s $SERVICE -a instance -w"
echo "Remove all with:    for a in instance client_id client_secret; do security delete-generic-password -s $SERVICE -a \$a 2>/dev/null; done"
