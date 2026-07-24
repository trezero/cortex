#!/usr/bin/env bash
# Install Cortex's deterministic Codex skill client for the current repository.

set -euo pipefail

CORTEX_API_URL="{{CORTEX_API_URL}}"
CORTEX_MCP_URL="{{CORTEX_MCP_URL}}"
PROJECT_ID="${CORTEX_PROJECT_ID:-}"
PROJECT_ROOT="$PWD"
INSTALL_HOOK=1

usage() {
  cat <<'EOF'
Usage: cortexCodexSetup.sh --project-id ID [options]

Options:
  --api-url URL       Cortex API URL
  --mcp-url URL       Cortex MCP base URL
  --project-root DIR  Repository to associate with the Cortex project
  --no-hook           Do not add the deterministic SessionStart status hook
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --project-id) PROJECT_ID="$2"; shift 2 ;;
    --api-url) CORTEX_API_URL="${2%/}"; shift 2 ;;
    --mcp-url) CORTEX_MCP_URL="${2%/}"; shift 2 ;;
    --project-root) PROJECT_ROOT="$(cd "$2" && pwd)"; shift 2 ;;
    --no-hook) INSTALL_HOOK=0; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

if [ -z "$PROJECT_ID" ]; then
  echo "--project-id or CORTEX_PROJECT_ID is required" >&2
  exit 2
fi
for command in curl python3; do
  command -v "$command" >/dev/null || {
    echo "$command is required" >&2
    exit 2
  }
done

# Noninteractive WSL shells can see a Windows Codex wrapper before they see the
# Linux Node runtime managed by NVM.
if ! command -v node >/dev/null 2>&1 && [ -s "$HOME/.nvm/nvm.sh" ]; then
  # shellcheck disable=SC1091
  . "$HOME/.nvm/nvm.sh"
  nvm use default >/dev/null 2>&1 || nvm use node >/dev/null 2>&1 || true
fi

curl -fsS "$CORTEX_API_URL/api/projects/$PROJECT_ID" >/dev/null

install -d "$HOME/.local/bin" "$PROJECT_ROOT/.cortex" "$HOME/.config/cortex"
curl -fsS "$CORTEX_MCP_URL/cortex-setup/codex-client.py" \
  -o "$HOME/.local/bin/cortex-codex"
chmod 0755 "$HOME/.local/bin/cortex-codex"

python3 - "$PROJECT_ROOT/.cortex/codex.json" "$CORTEX_API_URL" "$CORTEX_MCP_URL" "$PROJECT_ID" "$PROJECT_ROOT" <<'PY'
import json
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
path.write_text(
    json.dumps(
        {
            "schema_version": 1,
            "agent": "codex",
            "api_url": sys.argv[2],
            "mcp_url": sys.argv[3],
            "project_id": sys.argv[4],
            "project_root": sys.argv[5],
        },
        indent=2,
        sort_keys=True,
    )
    + "\n",
    encoding="utf-8",
)
PY

if command -v codex >/dev/null 2>&1 && codex --version >/dev/null 2>&1; then
  codex mcp remove cortex >/dev/null 2>&1 || true
  codex mcp add cortex --url "$CORTEX_MCP_URL/mcp" >/dev/null
else
  echo "Warning: Codex CLI is unavailable; skipped MCP registration." >&2
fi

if [ "$INSTALL_HOOK" -eq 1 ]; then
  python3 - "$HOME/.codex/hooks.json" <<'PY'
import json
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
try:
    data = json.loads(path.read_text(encoding="utf-8"))
except FileNotFoundError:
    data = {}
hooks = data.setdefault("hooks", {}).setdefault("SessionStart", [])
command = '"$HOME/.local/bin/cortex-codex" --project-root "$PWD" status --quiet'
entry = {
    "matcher": "startup|resume|clear",
    "hooks": [
        {
            "type": "command",
            "command": command,
            "timeout": 20,
            "statusMessage": "Checking Cortex Codex skills",
        }
    ],
}
if not any(
    hook.get("command") == command
    for group in hooks
    for hook in group.get("hooks", [])
):
    hooks.append(entry)
path.parent.mkdir(parents=True, exist_ok=True)
temporary = path.with_name(f".{path.name}.tmp")
temporary.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
temporary.replace(path)
PY
fi

echo "Cortex Codex configured for $PROJECT_ROOT"
echo "Run: cortex-codex --project-root \"$PROJECT_ROOT\" sync"
