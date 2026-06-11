#!/usr/bin/env bash
#
# provision-machine.sh — grant a remote machine secure, headless access to Archon
# at https://archon.persalto.io via a per-machine Cloudflare Access service token.
#
# What it does (all headless, no browser):
#   1. Mints a new Cloudflare Access service token named "archon-<machine>".
#   2. Adds that token to the "approved-machines" service-auth policy on the Archon
#      Access application (so only explicitly-listed machines are accepted).
#   3. Pushes the credential file + a ready-to-use MCP config to the remote machine
#      over SSH (credential stored chmod 600; never echoed to the terminal).
#
# Access is gated entirely at the Cloudflare edge: a machine without a valid, listed
# token gets HTTP 403 on every path. Revoke a machine with: delete its service token
# (see --revoke), which is enforced at the edge immediately.
#
# Requirements on THIS machine: curl, jq, ssh, and a Cloudflare API token with
# Access: Service Tokens (Edit) + Access: Apps and Policies (Edit).
#
# Usage:
#   ./provision-machine.sh --machine <name> --ssh <user@host> [options]
#   ./provision-machine.sh --revoke  --machine <name>
#
# Options:
#   --machine <name>     Short identifier for the machine (used in the token name and
#                        credential file). e.g. "lab-jetson-01".
#   --ssh <user@host>    SSH target to push the credential to (omit with --print-only).
#   --url <url>          Archon base URL (default: https://archon.persalto.io).
#   --print-only         Mint the token + update the policy, but print the credential
#                        instead of pushing over SSH (you place it manually).
#   --revoke             Delete the named machine's service token (revokes access).
#   --env-file <path>    File holding CF_API_TOKEN + CF_ACCOUNT_ID
#                        (default: $CF_ENV_FILE or the path below).
#   --app-id <id>        Access application id (default: $ARCHON_ACCESS_APP_ID or built-in).
#
set -euo pipefail

# ---- Defaults (non-secret identifiers; override via flags/env) ---------------
ARCHON_URL_DEFAULT="https://archon.persalto.io"
APP_ID_DEFAULT="${ARCHON_ACCESS_APP_ID:-1082b663-fc56-4a98-8334-aa648815450a}"
POLICY_NAME="approved-machines"
CF_ENV_FILE_DEFAULT="${CF_ENV_FILE:-/mnt/e/Projects/persalto-operating-space/cloudflare.persalto.env.local}"
CF_API="https://api.cloudflare.com/client/v4"

MACHINE=""; SSH_TARGET=""; ARCHON_URL="$ARCHON_URL_DEFAULT"; APP_ID="$APP_ID_DEFAULT"
CF_ENV_FILE="$CF_ENV_FILE_DEFAULT"; PRINT_ONLY=0; REVOKE=0

die() { echo "ERROR: $*" >&2; exit 1; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --machine)   MACHINE="$2"; shift 2;;
    --ssh)       SSH_TARGET="$2"; shift 2;;
    --url)       ARCHON_URL="$2"; shift 2;;
    --app-id)    APP_ID="$2"; shift 2;;
    --env-file)  CF_ENV_FILE="$2"; shift 2;;
    --print-only) PRINT_ONLY=1; shift;;
    --revoke)    REVOKE=1; shift;;
    -h|--help)   sed -n '2,40p' "$0"; exit 0;;
    *) die "unknown argument: $1";;
  esac
done

command -v curl >/dev/null || die "curl not found"
command -v jq   >/dev/null || die "jq not found"
[[ -n "$MACHINE" ]] || die "--machine is required"
[[ -f "$CF_ENV_FILE" ]] || die "Cloudflare env file not found: $CF_ENV_FILE (set --env-file or CF_ENV_FILE)"

# shellcheck disable=SC1090
set -a; source "$CF_ENV_FILE"; set +a
[[ -n "${CF_API_TOKEN:-}" && -n "${CF_ACCOUNT_ID:-}" ]] || die "CF_API_TOKEN / CF_ACCOUNT_ID missing in $CF_ENV_FILE"

TOKEN_NAME="archon-${MACHINE}"
auth=(-H "Authorization: Bearer $CF_API_TOKEN")

# Find an existing service token by name (returns its id, or empty).
find_token_id() {
  curl -s "${auth[@]}" "$CF_API/accounts/$CF_ACCOUNT_ID/access/service_tokens" \
    | jq -r --arg n "$TOKEN_NAME" '.result[] | select(.name==$n) | .id' | head -n1
}

# ---- Resolve the policy id by name ------------------------------------------
POLICY_ID="$(curl -s "${auth[@]}" "$CF_API/accounts/$CF_ACCOUNT_ID/access/apps/$APP_ID/policies" \
  | jq -r --arg n "$POLICY_NAME" '.result[] | select(.name==$n) | .id' | head -n1)"
[[ -n "$POLICY_ID" ]] || die "policy '$POLICY_NAME' not found on app $APP_ID"

# Remove a token id from the policy include list (preserving the rest). PUTs the policy.
# Cloudflare requires a non-empty include, so it refuses to remove the last token this way.
policy_remove_token() {
  local tid="$1"
  local remaining
  remaining="$(curl -s "${auth[@]}" "$CF_API/accounts/$CF_ACCOUNT_ID/access/apps/$APP_ID/policies/$POLICY_ID" \
    | jq -c --arg tid "$tid" '[.result.include[]? | select((.service_token.token_id // "") != $tid)]')"
  if [[ "$(echo "$remaining" | jq 'length')" -eq 0 ]]; then
    die "refusing to remove the last token from policy '$POLICY_NAME' (Access requires >=1). Provision a replacement machine first, or delete the Archon Access app entirely."
  fi
  local ok
  ok=$(curl -s -X PUT "${auth[@]}" -H "Content-Type: application/json" \
    "$CF_API/accounts/$CF_ACCOUNT_ID/access/apps/$APP_ID/policies/$POLICY_ID" \
    --data "{\"name\":\"$POLICY_NAME\",\"decision\":\"non_identity\",\"include\":$remaining}" | jq -r '.success')
  [[ "$ok" == "true" ]] || die "failed to update policy while removing token $tid"
}

# ---- Revoke path -------------------------------------------------------------
if [[ "$REVOKE" -eq 1 ]]; then
  TID="$(find_token_id)"
  [[ -n "$TID" ]] || die "no service token named '$TOKEN_NAME' found — nothing to revoke"
  # Must remove the policy reference before Cloudflare will allow deleting the token.
  policy_remove_token "$TID"
  ok=$(curl -s -X DELETE "${auth[@]}" "$CF_API/accounts/$CF_ACCOUNT_ID/access/service_tokens/$TID" | jq -r '.success')
  [[ "$ok" == "true" ]] || die "removed from policy but failed to delete service token $TID"
  echo "Revoked service token '$TOKEN_NAME' ($TID): removed from policy '$POLICY_NAME' and deleted. Access from that machine is blocked at the edge."
  exit 0
fi

# ---- Reuse or mint the service token ----------------------------------------
EXISTING="$(find_token_id)"
if [[ -n "$EXISTING" ]]; then
  die "a service token named '$TOKEN_NAME' already exists ($EXISTING). Revoke it first (--revoke) to re-issue, since the secret is only shown once at creation."
fi

RESP="$(curl -s -X POST "${auth[@]}" -H "Content-Type: application/json" \
  "$CF_API/accounts/$CF_ACCOUNT_ID/access/service_tokens" \
  --data "{\"name\":\"$TOKEN_NAME\"}")"
CID="$(echo "$RESP"   | jq -r '.result.client_id')"
CSECRET="$(echo "$RESP" | jq -r '.result.client_secret')"
TID="$(echo "$RESP"   | jq -r '.result.id')"
[[ -n "$CID" && "$CID" != "null" && ${#CSECRET} -ge 20 ]] \
  || die "token creation failed: $(echo "$RESP" | jq -c '{success,errors}')"
echo "Minted service token '$TOKEN_NAME' (id=$TID, client_id=${CID:0:10}…)"

# ---- Append the token to the policy include list (preserve existing) --------
INCLUDE="$(curl -s "${auth[@]}" "$CF_API/accounts/$CF_ACCOUNT_ID/access/apps/$APP_ID/policies/$POLICY_ID" \
  | jq -c --arg tid "$TID" '
      ([.result.include[]?] + [{"service_token":{"token_id":$tid}}])
      | unique_by(.service_token.token_id // tostring)')"
ok=$(curl -s -X PUT "${auth[@]}" -H "Content-Type: application/json" \
  "$CF_API/accounts/$CF_ACCOUNT_ID/access/apps/$APP_ID/policies/$POLICY_ID" \
  --data "{\"name\":\"$POLICY_NAME\",\"decision\":\"non_identity\",\"include\":$INCLUDE}" | jq -r '.success')
[[ "$ok" == "true" ]] || die "failed to add token to policy $POLICY_ID"
echo "Added token to policy '$POLICY_NAME'."

# ---- Build the credential payload -------------------------------------------
CRED_CONTENT="$(cat <<EOF
# Archon Cloudflare Access credentials for machine: $MACHINE
# Generated by provision-machine.sh. Keep secret (chmod 600). Do not commit.
CF_ACCESS_CLIENT_ID=$CID
CF_ACCESS_CLIENT_SECRET=$CSECRET
ARCHON_URL=$ARCHON_URL
EOF
)"

MCP_JSON="$(cat <<EOF
{
  "mcpServers": {
    "archon": {
      "type": "http",
      "url": "$ARCHON_URL/mcp",
      "headers": {
        "CF-Access-Client-Id": "$CID",
        "CF-Access-Client-Secret": "$CSECRET"
      }
    }
  }
}
EOF
)"

# ---- Deliver -----------------------------------------------------------------
if [[ "$PRINT_ONLY" -eq 1 || -z "$SSH_TARGET" ]]; then
  echo
  echo "=== credential file (place at ~/.config/archon/cf-access.env, chmod 600) ==="
  echo "$CRED_CONTENT"
  echo
  echo "=== MCP config snippet (.mcp.json) ==="
  echo "$MCP_JSON"
  echo
  echo "Quick test from the target machine:"
  echo "  source ~/.config/archon/cf-access.env"
  echo "  curl -s -H \"CF-Access-Client-Id: \$CF_ACCESS_CLIENT_ID\" -H \"CF-Access-Client-Secret: \$CF_ACCESS_CLIENT_SECRET\" \$ARCHON_URL/api/health"
  exit 0
fi

command -v ssh >/dev/null || die "ssh not found (use --print-only to place the credential manually)"
echo "Pushing credential + MCP config to $SSH_TARGET …"
# umask 077 ensures the files are created chmod 600; secret travels over the SSH channel only.
ssh "$SSH_TARGET" "umask 077; mkdir -p ~/.config/archon" \
  || die "ssh to $SSH_TARGET failed"
printf '%s\n' "$CRED_CONTENT" | ssh "$SSH_TARGET" "umask 077; cat > ~/.config/archon/cf-access.env"
printf '%s\n' "$MCP_JSON"     | ssh "$SSH_TARGET" "umask 077; cat > ~/.config/archon/archon.mcp.json"
echo "Delivered:"
echo "  ~/.config/archon/cf-access.env       (credential, chmod 600)"
echo "  ~/.config/archon/archon.mcp.json     (MCP server config for Claude Code / Cursor)"
echo
echo "On $SSH_TARGET, wire the MCP server into your client, e.g. for Claude Code in a project:"
echo "  cp ~/.config/archon/archon.mcp.json <project>/.mcp.json"
echo "Verify connectivity:"
echo "  ssh $SSH_TARGET 'source ~/.config/archon/cf-access.env && curl -s -o /dev/null -w \"%{http_code}\\n\" \\"
echo "    -H \"CF-Access-Client-Id: \$CF_ACCESS_CLIENT_ID\" -H \"CF-Access-Client-Secret: \$CF_ACCESS_CLIENT_SECRET\" \$ARCHON_URL/api/health'  # expect 200"
