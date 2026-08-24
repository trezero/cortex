#!/usr/bin/env bash
# Provision or revoke a per-machine Cortex Cloudflare Access service token.
# Secrets are read from and written to the approved Atlas 1Password vault only.

set -euo pipefail

CORTEX_URL_DEFAULT="https://cortex.persalto.io"
APP_ID_DEFAULT="${CORTEX_ACCESS_APP_ID:-1082b663-fc56-4a98-8334-aa648815450a}"
POLICY_NAME="approved-machines"
CF_API="https://api.cloudflare.com/client/v4"
OP_WRAPPER_DEFAULT="${OP_WRAPPER:-/home/winadmin/projects/persalto-operating-space/scripts/op_service_account.sh}"

MACHINE=""
CORTEX_URL="$CORTEX_URL_DEFAULT"
APP_ID="$APP_ID_DEFAULT"
OP_WRAPPER="$OP_WRAPPER_DEFAULT"
REVOKE=0

die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --machine) MACHINE="$2"; shift 2 ;;
    --url) CORTEX_URL="$2"; shift 2 ;;
    --app-id) APP_ID="$2"; shift 2 ;;
    --op-wrapper) OP_WRAPPER="$2"; shift 2 ;;
    --revoke) REVOKE=1; shift ;;
    -h|--help) sed -n '2,34p' "$0"; exit 0 ;;
    --ssh|--print-only|--env-file)
      die "$1 is retired: credentials must remain in 1Password and must never be printed or copied into files"
      ;;
    *) die "unknown argument: $1" ;;
  esac
done

command -v curl >/dev/null || die "curl not found"
command -v jq >/dev/null || die "jq not found"
[[ "$MACHINE" =~ ^[a-zA-Z0-9][a-zA-Z0-9._-]*$ ]] || die "--machine must be a short filesystem-safe identifier"
[[ "$CORTEX_URL" == https://* ]] || die "--url must use HTTPS"
[[ -x "$OP_WRAPPER" ]] || die "approved 1Password wrapper is not executable: $OP_WRAPPER"
"$OP_WRAPPER" --preflight >/dev/null

CF_API_TOKEN="$("$OP_WRAPPER" read 'op://Atlas/Cloudflare - trezero/api_token')"
CF_ACCOUNT_ID="$("$OP_WRAPPER" read 'op://Atlas/Cloudflare - trezero/account_id')"
[[ -n "$CF_API_TOKEN" && -n "$CF_ACCOUNT_ID" ]] || die "Cloudflare fields are missing from the approved Atlas item"

TOKEN_NAME="cortex-${MACHINE}"
ITEM_NAME="Cortex Cloudflare Access - ${MACHINE}"
auth=(-H "Authorization: Bearer $CF_API_TOKEN")

find_token_id() {
  curl -fsS "${auth[@]}" "$CF_API/accounts/$CF_ACCOUNT_ID/access/service_tokens" \
    | jq -r --arg name "$TOKEN_NAME" '.result[] | select(.name == $name) | .id' \
    | head -n1
}

POLICY_ID="$(
  curl -fsS "${auth[@]}" "$CF_API/accounts/$CF_ACCOUNT_ID/access/apps/$APP_ID/policies" \
    | jq -r --arg name "$POLICY_NAME" '.result[] | select(.name == $name) | .id' \
    | head -n1
)"
[[ -n "$POLICY_ID" ]] || die "policy '$POLICY_NAME' not found on app $APP_ID"

policy_remove_token() {
  local token_id="$1"
  local current remaining payload success
  current="$(curl -fsS "${auth[@]}" "$CF_API/accounts/$CF_ACCOUNT_ID/access/apps/$APP_ID/policies/$POLICY_ID")"
  remaining="$(
    jq -c --arg token_id "$token_id" \
      '[.result.include[]? | select((.service_token.token_id // "") != $token_id)]' \
      <<<"$current"
  )"
  [[ "$(jq 'length' <<<"$remaining")" -gt 0 ]] \
    || die "refusing to remove the last approved machine from '$POLICY_NAME'"
  payload="$(jq -cn --arg name "$POLICY_NAME" --argjson include "$remaining" \
    '{name:$name,decision:"non_identity",include:$include}')"
  success="$(
    curl -fsS -X PUT "${auth[@]}" -H 'Content-Type: application/json' \
      "$CF_API/accounts/$CF_ACCOUNT_ID/access/apps/$APP_ID/policies/$POLICY_ID" \
      --data "$payload" | jq -r '.success'
  )"
  [[ "$success" == "true" ]] || die "failed to remove service token from '$POLICY_NAME'"
}

if [[ "$REVOKE" -eq 1 ]]; then
  token_id="$(find_token_id)"
  [[ -n "$token_id" ]] || die "no service token named '$TOKEN_NAME' found"
  policy_remove_token "$token_id"
  success="$(
    curl -fsS -X DELETE "${auth[@]}" \
      "$CF_API/accounts/$CF_ACCOUNT_ID/access/service_tokens/$token_id" | jq -r '.success'
  )"
  [[ "$success" == "true" ]] || die "policy was updated but Cloudflare token deletion failed"
  "$OP_WRAPPER" item delete "$ITEM_NAME" --vault Atlas --archive >/dev/null 2>&1 || true
  printf "Revoked '%s'; its 1Password item was archived.\n" "$TOKEN_NAME"
  exit 0
fi

[[ -z "$(find_token_id)" ]] \
  || die "service token '$TOKEN_NAME' already exists; revoke it before re-issuing"

response="$(
  curl -fsS -X POST "${auth[@]}" -H 'Content-Type: application/json' \
    "$CF_API/accounts/$CF_ACCOUNT_ID/access/service_tokens" \
    --data "$(jq -cn --arg name "$TOKEN_NAME" '{name:$name}')"
)"
token_id="$(jq -r '.result.id // empty' <<<"$response")"
client_id="$(jq -r '.result.client_id // empty' <<<"$response")"
client_secret="$(jq -r '.result.client_secret // empty' <<<"$response")"
[[ -n "$token_id" && -n "$client_id" && ${#client_secret} -ge 20 ]] \
  || die "Cloudflare did not return a complete service token"

rollback_needed=1
rollback() {
  if [[ "$rollback_needed" -eq 1 ]]; then
    curl -fsS -X DELETE "${auth[@]}" \
      "$CF_API/accounts/$CF_ACCOUNT_ID/access/service_tokens/$token_id" >/dev/null 2>&1 || true
    "$OP_WRAPPER" item delete "$ITEM_NAME" --vault Atlas --archive >/dev/null 2>&1 || true
  fi
}
trap rollback EXIT

template="$("$OP_WRAPPER" item template get Login)"
item_result="$(
  printf '%s\n%s\n' "$template" "$response" \
    | jq -s --arg title "$ITEM_NAME" --arg url "$CORTEX_URL" '
        .[0] as $item | .[1].result as $token
        | $item
        | .title = $title
        | .urls = [{label:"website",href:$url,primary:true}]
        | (.fields[] | select(.id == "username") | .value) = $token.client_id
        | (.fields[] | select(.id == "password") | .value) = $token.client_secret
      ' \
    | "$OP_WRAPPER" item create --vault Atlas -
)"
item_id="$(jq -r '.id // empty' <<<"$item_result")"
[[ -n "$item_id" ]] || die "1Password item creation failed"
unset client_id client_secret response template item_result

current="$(curl -fsS "${auth[@]}" "$CF_API/accounts/$CF_ACCOUNT_ID/access/apps/$APP_ID/policies/$POLICY_ID")"
include="$(
  jq -c --arg token_id "$token_id" '
    ([.result.include[]?] + [{"service_token":{"token_id":$token_id}}])
    | unique_by(.service_token.token_id // tostring)
  ' <<<"$current"
)"
payload="$(jq -cn --arg name "$POLICY_NAME" --argjson include "$include" \
  '{name:$name,decision:"non_identity",include:$include}')"
success="$(
  curl -fsS -X PUT "${auth[@]}" -H 'Content-Type: application/json' \
    "$CF_API/accounts/$CF_ACCOUNT_ID/access/apps/$APP_ID/policies/$POLICY_ID" \
    --data "$payload" | jq -r '.success'
)"
[[ "$success" == "true" ]] || die "failed to add the token to '$POLICY_NAME'"

rollback_needed=0
trap - EXIT
printf "Provisioned '%s' and stored it in Atlas vault item '%s' (item id %s).\n" \
  "$TOKEN_NAME" "$ITEM_NAME" "$item_id"
printf "Clients must resolve that item plus 'Cortex MCP Service Token' at runtime; no credential file was created.\n"
