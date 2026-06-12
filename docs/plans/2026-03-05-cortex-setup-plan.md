# Cortex Setup — Guided Machine Onboarding Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the manual MCP tool bootstrap with a downloadable interactive setup script (`cortexSetup.sh` / `cortexSetup.bat`) served by the Cortex MCP server, plus a `/cortex-setup` Claude Code slash command that completes machine registration and skill installation.

**Architecture:** The MCP server exposes three new HTTP endpoints that dynamically serve setup scripts with the server URL baked in. Scripts run interactively in the terminal, collect system name and project, call `claude mcp add`, download the slash command, and write `cortex-state.json`. The user then opens Claude Code and runs `/cortex-setup` to register the system and install skills. The MCP page gains a "Connect a New Machine" download section at the top.

**Tech Stack:** Python 3.12, FastAPI/FastMCP `custom_route`, bash, Windows batch + PowerShell, React 18, TypeScript, Tailwind, TanStack Query v5

---

## Task 1: Add `?q=` search param to `GET /api/projects`

The setup script needs server-side project search — fetching all 100+ projects client-side is not viable.

**Files:**
- Modify: `python/src/server/api_routes/projects_api.py` (around line 85)
- Test: `python/tests/server/api_routes/test_projects_search.py` (new)

**Step 1: Write the failing test**

Create `python/tests/server/api_routes/test_projects_search.py`:

```python
"""Tests for GET /api/projects?q= search parameter."""
from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient
from src.server.main import app

client = TestClient(app)


def test_list_projects_without_q_returns_all(mock_projects):
    with patch("src.server.api_routes.projects_api.ProjectService") as MockService, \
         patch("src.server.api_routes.projects_api.SourceLinkingService"):
        mock_svc = MockService.return_value
        mock_svc.list_projects.return_value = (True, {"projects": mock_projects})
        response = client.get("/api/projects?include_content=false")
        assert response.status_code == 200
        assert len(response.json()["projects"]) == 3


def test_list_projects_q_filters_by_title(mock_projects):
    with patch("src.server.api_routes.projects_api.ProjectService") as MockService, \
         patch("src.server.api_routes.projects_api.SourceLinkingService"):
        mock_svc = MockService.return_value
        mock_svc.list_projects.return_value = (True, {"projects": mock_projects})
        response = client.get("/api/projects?include_content=false&q=recipe")
        assert response.status_code == 200
        projects = response.json()["projects"]
        assert all("recipe" in p["title"].lower() for p in projects)


def test_list_projects_q_case_insensitive(mock_projects):
    with patch("src.server.api_routes.projects_api.ProjectService") as MockService, \
         patch("src.server.api_routes.projects_api.SourceLinkingService"):
        mock_svc = MockService.return_value
        mock_svc.list_projects.return_value = (True, {"projects": mock_projects})
        response = client.get("/api/projects?include_content=false&q=RECIPE")
        assert response.status_code == 200
        projects = response.json()["projects"]
        assert len(projects) > 0


@pytest.fixture
def mock_projects():
    return [
        {"id": "1", "title": "RecipeRaiders", "description": ""},
        {"id": "2", "title": "RecipeManager", "description": ""},
        {"id": "3", "title": "WeatherApp", "description": ""},
    ]
```

**Step 2: Run to verify it fails**

```bash
cd /home/winadmin/projects/Trinity/cortex/python && uv run pytest tests/server/api_routes/test_projects_search.py -v
```

Expected: FAIL (fixture and filtering not yet implemented)

**Step 3: Add `q` parameter to `list_projects` endpoint**

In `python/src/server/api_routes/projects_api.py`, update the `list_projects` signature:

```python
@router.get("/projects")
async def list_projects(
    response: Response,
    include_content: bool = True,
    q: str | None = Query(None, description="Filter projects by title (case-insensitive)"),
    if_none_match: str | None = Header(None)
):
```

Ensure `Query` is imported: add to the existing fastapi import line if not present:
```python
from fastapi import APIRouter, Header, HTTPException, Query, Response
```

After `formatted_projects` is built, add filtering before ETag logic:

```python
# Apply title search filter if provided
if q:
    q_lower = q.lower()
    formatted_projects = [
        p for p in formatted_projects
        if q_lower in (p.get("title") or "").lower()
    ]
```

**Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/server/api_routes/test_projects_search.py -v
```

Expected: 3 PASSED

**Step 5: Commit**

```bash
git add python/src/server/api_routes/projects_api.py python/tests/server/api_routes/test_projects_search.py
git commit -m "feat: add ?q= search filter to GET /api/projects"
```

---

## Task 2: MCP server — three setup file endpoints

The MCP server serves the setup scripts and command file dynamically. The server URL is injected at request time so every download is self-configured.

**Files:**
- Modify: `python/src/mcp_server/mcp_server.py` (after the `/health` registration at the end)
- Test: `python/tests/mcp_server/test_setup_endpoints.py` (new)

**Step 1: Write the failing test**

Create `python/tests/mcp_server/test_setup_endpoints.py`:

```python
"""Tests for the cortex-setup download endpoints."""
import pytest
from unittest.mock import patch
from starlette.testclient import TestClient


@pytest.fixture
def mcp_test_client():
    """TestClient using the FastMCP app directly."""
    with patch.dict("os.environ", {"CORTEX_MCP_PORT": "8051"}):
        from src.mcp_server.mcp_server import mcp
        return TestClient(mcp.streamable_http_app())


def test_cortex_setup_sh_returns_200(mcp_test_client):
    response = mcp_test_client.get("/cortex-setup.sh")
    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]


def test_cortex_setup_sh_contains_server_url(mcp_test_client):
    response = mcp_test_client.get("/cortex-setup.sh")
    assert "CORTEX_SERVER=" in response.text


def test_cortex_setup_bat_returns_200(mcp_test_client):
    response = mcp_test_client.get("/cortex-setup.bat")
    assert response.status_code == 200


def test_cortex_setup_md_returns_200(mcp_test_client):
    response = mcp_test_client.get("/cortex-setup.md")
    assert response.status_code == 200
    assert "cortex-setup" in response.text


def test_cortex_setup_sh_content_type_is_plain_text(mcp_test_client):
    response = mcp_test_client.get("/cortex-setup.sh")
    assert response.headers["content-type"].startswith("text/plain")
```

**Step 2: Run to verify it fails**

```bash
cd /home/winadmin/projects/Trinity/cortex/python && uv run pytest tests/mcp_server/test_setup_endpoints.py -v
```

Expected: FAIL (endpoints don't exist yet)

**Step 3: Add the three endpoint handlers in `mcp_server.py`**

Add these imports at the top of `mcp_server.py` (after existing imports):

```python
from starlette.responses import PlainTextResponse
```

Add the three endpoint functions after the existing `/health` registration block (around line 653):

```python
# ── Setup file endpoints ────────────────────────────────────────────────────

async def http_cortex_setup_sh(request: Request):
    """Serve cortexSetup.sh with the Cortex server URL baked in."""
    server_url = str(request.base_url).rstrip("/")
    script = _render_setup_sh(server_url)
    return PlainTextResponse(
        script,
        headers={"Content-Disposition": 'attachment; filename="cortexSetup.sh"'},
    )


async def http_cortex_setup_bat(request: Request):
    """Serve cortexSetup.bat with the Cortex server URL baked in."""
    server_url = str(request.base_url).rstrip("/")
    script = _render_setup_bat(server_url)
    return PlainTextResponse(
        script,
        headers={"Content-Disposition": 'attachment; filename="cortexSetup.bat"'},
    )


async def http_cortex_setup_md(request: Request):
    """Serve the /cortex-setup Claude Code slash command."""
    content = _render_setup_md()
    return PlainTextResponse(content)


def _render_setup_sh(server_url: str) -> str:
    """Generate cortexSetup.sh with server_url injected."""
    # Read the template from the bundled integrations directory
    template_path = Path(__file__).resolve()
    for parent in template_path.parents:
        candidate = parent / "integrations" / "claude-code" / "setup" / "cortexSetup.sh"
        if candidate.exists():
            content = candidate.read_text()
            return content.replace("{{CORTEX_SERVER_URL}}", server_url)
    raise FileNotFoundError("cortexSetup.sh template not found")


def _render_setup_bat(server_url: str) -> str:
    """Generate cortexSetup.bat with server_url injected."""
    template_path = Path(__file__).resolve()
    for parent in template_path.parents:
        candidate = parent / "integrations" / "claude-code" / "setup" / "cortexSetup.bat"
        if candidate.exists():
            content = candidate.read_text()
            return content.replace("{{CORTEX_SERVER_URL}}", server_url)
    raise FileNotFoundError("cortexSetup.bat template not found")


def _render_setup_md() -> str:
    """Return the /cortex-setup Claude Code slash command content."""
    template_path = Path(__file__).resolve()
    for parent in template_path.parents:
        candidate = parent / "integrations" / "claude-code" / "commands" / "cortex-setup.md"
        if candidate.exists():
            return candidate.read_text()
    raise FileNotFoundError("cortex-setup.md not found")


# Register setup endpoints
try:
    mcp.custom_route("/cortex-setup.sh", methods=["GET"])(http_cortex_setup_sh)
    mcp.custom_route("/cortex-setup.bat", methods=["GET"])(http_cortex_setup_bat)
    mcp.custom_route("/cortex-setup.md", methods=["GET"])(http_cortex_setup_md)
    logger.info("✓ Setup file endpoints registered")
except Exception as e:
    logger.error(f"✗ Failed to register setup endpoints: {e}")
```

**Step 4: Run tests (they'll still fail until template files exist — that's expected)**

Note: Tests will pass once Tasks 3, 4, 5 create the template files. Proceed to Task 3.

**Step 5: Commit the endpoint stubs**

```bash
git add python/src/mcp_server/mcp_server.py python/tests/mcp_server/test_setup_endpoints.py
git commit -m "feat: add /cortex-setup.sh, .bat, .md endpoints to MCP server"
```

---

## Task 3: Write `cortex-setup.md` — the Claude Code slash command

**Files:**
- Create: `integrations/claude-code/commands/cortex-setup.md`

**Step 1: Create the directory and file**

```bash
mkdir -p /home/winadmin/projects/Trinity/cortex/integrations/claude-code/commands
```

Write `integrations/claude-code/commands/cortex-setup.md`:

```markdown
# Cortex Setup — Register This Machine

Connect this machine to Cortex: register it as a system, download all project skills, and install them to `~/.claude/skills/`.

## Phase 0: Health Check

Call `health_check()` via the Cortex MCP tool.

If the server is unreachable, print:
```
Cortex server is not reachable. Ensure the MCP is connected.
```
Stop.

## Phase 1: Load Existing State

Read `.claude/cortex-state.json` if it exists. Extract:
- `system_fingerprint` → `<fingerprint>` (may be absent)
- `system_name` → `<system_name>` (may be absent)
- `cortex_project_id` → `<project_id>` (may be absent)

## Phase 2: Compute Fingerprint (if missing)

If `<fingerprint>` was not in the state file:

Detect OS:
```bash
uname -s
```

If output is `Darwin`:
```bash
echo -n "$(hostname)|$(whoami)|$(uname -s)" | shasum -a 256 | cut -d' ' -f1
```

Otherwise:
```bash
echo -n "$(hostname)|$(whoami)|$(uname -s)" | sha256sum | cut -d' ' -f1
```

Store result as `<fingerprint>`.

## Phase 3: Confirm System Name (if missing)

If `<system_name>` was not in the state file:

```bash
hostname
```

Ask the user:
> I'll register this machine as **`<hostname>`**. Press Enter to confirm or type a different name:

Store confirmed name as `<system_name>`.

## Phase 4: Bootstrap

Call:
```
manage_skills(
    action="bootstrap",
    system_fingerprint="<fingerprint>",
    system_name="<system_name>",
    project_id="<project_id>"   ← omit if no project_id
)
```

If the call fails, report the error and stop.

Extract `<system_id>` from `response.system.id` if present, otherwise `"unknown"`.

## Phase 5: Install Skills

For each skill in `response.skills`:

1. Create directory `~/.claude/skills/<name>/`
2. Write skill content to `~/.claude/skills/<name>/SKILL.md` using the Write tool (not bash heredoc)

## Phase 6: Update State

Read `.claude/cortex-state.json` or start with `{}`.

Merge — do not overwrite existing fields like `cortex_project_id`:
- `system_fingerprint`: `<fingerprint>`
- `system_name`: `<system_name>`
- `system_id`: `<system_id>`
- `last_bootstrap`: current ISO 8601 timestamp

Write merged object back to `.claude/cortex-state.json`.

## Phase 7: Report

```
## Cortex Setup Complete

System: <system_name> (<system_id>)
Skills installed: <N> → ~/.claude/skills/
  - <list each skill name>
Project: <project name if registered, else "No project linked">

Restart Claude Code for the new skills to take effect.
```

If `response.system.is_new` is `true`, also print:
```
This system has been registered with Cortex for the first time.
```
```

**Step 2: Verify the file exists**

```bash
cat integrations/claude-code/commands/cortex-setup.md | head -5
```

Expected: Shows `# Cortex Setup — Register This Machine`

**Step 3: Commit**

```bash
git add integrations/claude-code/commands/cortex-setup.md
git commit -m "feat: add /cortex-setup Claude Code slash command"
```

---

## Task 4: Write `cortexSetup.sh` — macOS/Linux setup script

**Files:**
- Create: `integrations/claude-code/setup/cortexSetup.sh`

**Step 1: Create the directory and file**

```bash
mkdir -p /home/winadmin/projects/Trinity/cortex/integrations/claude-code/setup
```

Write `integrations/claude-code/setup/cortexSetup.sh`:

```bash
#!/usr/bin/env bash
# Cortex Setup Script — Connect this machine to Cortex
# Server URL is baked in at download time.

set -e

CORTEX_SERVER="{{CORTEX_SERVER_URL}}"
API_BASE="$CORTEX_SERVER"

# ── Helpers ─────────────────────────────────────────────────────────────────

print_header() {
  echo ""
  echo "╔══════════════════════════════════════╗"
  echo "║         Cortex Setup                 ║"
  printf "║  Server: %-28s  ║\n" "$CORTEX_SERVER"
  echo "╚══════════════════════════════════════╝"
  echo ""
}

check_dependency() {
  if ! command -v "$1" &>/dev/null; then
    echo "Error: '$1' is required but not installed." >&2
    exit 1
  fi
}

ask() {
  local prompt="$1"
  local default="$2"
  local answer
  printf "%s [%s]: " "$prompt" "$default"
  read -r answer
  echo "${answer:-$default}"
}

# ── Dependency checks ────────────────────────────────────────────────────────

check_dependency curl
check_dependency python3
check_dependency claude

# ── Start ────────────────────────────────────────────────────────────────────

print_header

# ── Step 1/4: System name ────────────────────────────────────────────────────

echo "[1/4] System name"
DETECTED_HOSTNAME=$(hostname)
SYSTEM_NAME=$(ask "      Name for this machine" "$DETECTED_HOSTNAME")
echo ""

# ── Step 2/4: Project ────────────────────────────────────────────────────────

echo "[2/4] Project"

# Try to match current directory name to an Cortex project
DIR_NAME=$(basename "$(pwd)")
MATCHED_PROJECT=""
MATCHED_PROJECT_ID=""

SEARCH_RESULT=$(curl -sf "$API_BASE/api/projects?include_content=false&q=$(python3 -c "import urllib.parse,sys; print(urllib.parse.quote(sys.argv[1]))" "$DIR_NAME")" 2>/dev/null || echo '{"projects":[]}')
MATCH_COUNT=$(python3 -c "import json,sys; d=json.loads(sys.argv[1]); print(len(d.get('projects',[])))" "$SEARCH_RESULT")

if [ "$MATCH_COUNT" -eq 1 ]; then
  MATCHED_PROJECT=$(python3 -c "import json,sys; d=json.loads(sys.argv[1]); print(d['projects'][0]['title'])" "$SEARCH_RESULT")
  MATCHED_PROJECT_ID=$(python3 -c "import json,sys; d=json.loads(sys.argv[1]); print(d['projects'][0]['id'])" "$SEARCH_RESULT")
  printf "      Matched in Cortex: %s\n" "$MATCHED_PROJECT"
  CONFIRM=$(ask "      Press Enter to accept or type to search" "")
  if [ -z "$CONFIRM" ]; then
    PROJECT_ID="$MATCHED_PROJECT_ID"
    PROJECT_TITLE="$MATCHED_PROJECT"
  else
    SEARCH_TERM="$CONFIRM"
    MATCHED_PROJECT=""
  fi
fi

# Search loop
if [ -z "$PROJECT_ID" ]; then
  SEARCH_TERM="${SEARCH_TERM:-}"
  while true; do
    if [ -z "$SEARCH_TERM" ]; then
      printf "      Search (or Enter to list all): "
      read -r SEARCH_TERM
    fi

    ENCODED=$(python3 -c "import urllib.parse,sys; print(urllib.parse.quote(sys.argv[1]))" "$SEARCH_TERM")
    RESULTS=$(curl -sf "$API_BASE/api/projects?include_content=false&q=$ENCODED" 2>/dev/null || echo '{"projects":[]}')
    COUNT=$(python3 -c "import json,sys; print(len(json.loads(sys.argv[1]).get('projects',[])))" "$RESULTS")

    echo ""
    if [ "$COUNT" -eq 0 ]; then
      echo "      No results found."
    else
      python3 - "$RESULTS" <<'PYEOF'
import json, sys
data = json.loads(sys.argv[1])
projects = data.get("projects", [])[:10]
for i, p in enumerate(projects, 1):
    print(f"        {i}. {p['title']}")
PYEOF
    fi

    echo "        C. Create new project in Cortex"
    echo ""
    printf "      Enter number, new search term, or C to create: "
    read -r SELECTION

    if [ "$SELECTION" = "C" ] || [ "$SELECTION" = "c" ]; then
      # Create new project
      DEFAULT_NAME="$DIR_NAME"
      NEW_NAME=$(ask "      New project name" "$DEFAULT_NAME")
      printf "      Description (optional): "
      read -r NEW_DESC
      echo "      Creating project..."
      CREATE_RESULT=$(curl -sf -X POST "$API_BASE/api/projects" \
        -H "Content-Type: application/json" \
        -d "{\"title\":\"$NEW_NAME\",\"description\":\"$NEW_DESC\"}" 2>/dev/null)
      PROJECT_ID=$(python3 -c "import json,sys; d=json.loads(sys.argv[1]); print(d.get('id',''))" "$CREATE_RESULT")
      PROJECT_TITLE="$NEW_NAME"
      if [ -z "$PROJECT_ID" ]; then
        echo "      Error creating project. Continuing without project link."
      else
        echo "      ✓ Created \"$NEW_NAME\""
      fi
      break
    elif echo "$SELECTION" | grep -qE '^[0-9]+$'; then
      IDX=$((SELECTION - 1))
      PROJECT_ID=$(python3 -c "import json,sys; ps=json.loads(sys.argv[1]).get('projects',[]); print(ps[$IDX]['id'] if $IDX < len(ps) else '')" "$RESULTS")
      PROJECT_TITLE=$(python3 -c "import json,sys; ps=json.loads(sys.argv[1]).get('projects',[]); print(ps[$IDX]['title'] if $IDX < len(ps) else '')" "$RESULTS")
      if [ -z "$PROJECT_ID" ]; then
        echo "      Invalid selection."
      else
        break
      fi
    else
      SEARCH_TERM="$SELECTION"
    fi
  done
fi

echo ""

# ── Step 3/4: Add MCP ────────────────────────────────────────────────────────

echo "[3/4] Setting up Claude Code MCP..."
MCP_URL="$CORTEX_SERVER/mcp"
if claude mcp add --transport http cortex "$MCP_URL" 2>/dev/null; then
  echo "      ✓ Added cortex MCP server ($MCP_URL)"
else
  echo "      ✓ Cortex MCP already configured (or updated)"
fi
echo ""

# ── Step 4/4: Install /cortex-setup command ──────────────────────────────────

echo "[4/4] Installing /cortex-setup command..."
mkdir -p "$HOME/.claude/commands"
curl -sf "$CORTEX_SERVER/cortex-setup.md" -o "$HOME/.claude/commands/cortex-setup.md"
echo "      ✓ Installed to ~/.claude/commands/cortex-setup.md"
echo ""

# ── Write initial state ──────────────────────────────────────────────────────

mkdir -p ".claude"
STATE_FILE=".claude/cortex-state.json"

# Merge with existing state if present
if [ -f "$STATE_FILE" ]; then
  EXISTING=$(cat "$STATE_FILE")
else
  EXISTING="{}"
fi

python3 - "$EXISTING" "$SYSTEM_NAME" "$PROJECT_ID" <<'PYEOF'
import json, sys
state = json.loads(sys.argv[1])
state["system_name"] = sys.argv[2]
if sys.argv[3]:
    state["cortex_project_id"] = sys.argv[3]
with open(".claude/cortex-state.json", "w") as f:
    json.dump(state, f, indent=2)
PYEOF

# ── Done ─────────────────────────────────────────────────────────────────────

echo "══════════════════════════════════════"
echo "✓ Setup complete!"
echo ""
echo "  Open Claude Code in this directory and run:"
echo ""
echo "    /cortex-setup"
echo ""
echo "  This will register your system and install all project skills."
echo "══════════════════════════════════════"
echo ""
```

**Step 2: Make it executable**

```bash
chmod +x integrations/claude-code/setup/cortexSetup.sh
```

**Step 3: Manual smoke test (dry run)**

```bash
# Verify the template placeholder is present
grep "{{CORTEX_SERVER_URL}}" integrations/claude-code/setup/cortexSetup.sh
```

Expected: line shown with the placeholder

**Step 4: Commit**

```bash
git add integrations/claude-code/setup/cortexSetup.sh
git commit -m "feat: add cortexSetup.sh interactive machine setup script"
```

---

## Task 5: Write `cortexSetup.bat` — Windows setup script

**Files:**
- Create: `integrations/claude-code/setup/cortexSetup.bat`

**Step 1: Write the file**

Write `integrations/claude-code/setup/cortexSetup.bat`:

```batch
@echo off
setlocal EnableDelayedExpansion

set "CORTEX_SERVER={{CORTEX_SERVER_URL}}"

echo.
echo  =============================================
echo    Cortex Setup
echo    Server: %CORTEX_SERVER%
echo  =============================================
echo.

:: Check dependencies
where curl >nul 2>&1 || (echo Error: curl is required. Install from https://curl.se & exit /b 1)
where claude >nul 2>&1 || (echo Error: claude CLI not found. Install Claude Code first. & exit /b 1)
where powershell >nul 2>&1 || (echo Error: PowerShell is required. & exit /b 1)

:: ── Step 1/4: System name ──────────────────────────────────────────────────
echo [1/4] System name
for /f "delims=" %%H in ('hostname') do set "DETECTED=%~%%H"
set /p "SYSTEM_NAME=      Name for this machine [%COMPUTERNAME%]: "
if "%SYSTEM_NAME%"=="" set "SYSTEM_NAME=%COMPUTERNAME%"
echo.

:: ── Step 2/4: Project ─────────────────────────────────────────────────────
echo [2/4] Project

for %%F in (.) do set "DIR_NAME=%%~nxF"
set "PROJECT_ID="
set "PROJECT_TITLE="

:search_loop
set /p "SEARCH_TERM=      Search projects (or Enter to list all): "

set "ENCODED_TERM="
for /f "delims=" %%E in ('powershell -Command "[uri]::EscapeDataString('%SEARCH_TERM%')"') do set "ENCODED_TERM=%%E"

set "RESULTS_FILE=%TEMP%\cortex_projects.json"
curl -sf "%CORTEX_SERVER%/api/projects?include_content=false&q=!ENCODED_TERM!" -o "%RESULTS_FILE%" 2>nul

powershell -Command ^
  "$data = Get-Content '%RESULTS_FILE%' | ConvertFrom-Json; " ^
  "$projects = $data.projects | Select-Object -First 10; " ^
  "$i = 1; foreach ($p in $projects) { Write-Host ('        ' + $i + '. ' + $p.title); $i++ }"

echo         C. Create new project in Cortex
echo.
set /p "SELECTION=      Enter number, new search, or C to create: "

if /i "%SELECTION%"=="C" goto :create_project

:: Check if numeric
echo %SELECTION%| findstr /r "^[0-9][0-9]*$" >nul
if %errorlevel%==0 (
  for /f "delims=" %%R in ('powershell -Command ^
    "$data = Get-Content '%RESULTS_FILE%' | ConvertFrom-Json; " ^
    "$projects = $data.projects; " ^
    "$idx = %SELECTION% - 1; " ^
    "if ($idx -lt $projects.Count) { $projects[$idx].id + '|' + $projects[$idx].title }"') do (
    for /f "tokens=1,2 delims=|" %%A in ("%%R") do (
      set "PROJECT_ID=%%A"
      set "PROJECT_TITLE=%%B"
    )
  )
  if defined PROJECT_ID goto :project_done
  echo       Invalid selection.
)

set "SEARCH_TERM=%SELECTION%"
goto :search_loop

:create_project
set /p "NEW_NAME=      New project name [%DIR_NAME%]: "
if "%NEW_NAME%"=="" set "NEW_NAME=%DIR_NAME%"
set /p "NEW_DESC=      Description (optional): "
echo       Creating project...
set "CREATE_FILE=%TEMP%\cortex_create.json"
powershell -Command ^
  "$body = @{ title = '%NEW_NAME%'; description = '%NEW_DESC%' } | ConvertTo-Json; " ^
  "Invoke-RestMethod -Uri '%CORTEX_SERVER%/api/projects' -Method POST -Body $body -ContentType 'application/json' | ConvertTo-Json" ^
  > "%CREATE_FILE%" 2>nul
for /f "delims=" %%I in ('powershell -Command ^
  "$d = Get-Content '%CREATE_FILE%' | ConvertFrom-Json; $d.id"') do set "PROJECT_ID=%%I"
set "PROJECT_TITLE=%NEW_NAME%"
echo       Created "%NEW_NAME%"

:project_done
echo.

:: ── Step 3/4: Add MCP ─────────────────────────────────────────────────────
echo [3/4] Setting up Claude Code MCP...
claude mcp add --transport http cortex "%CORTEX_SERVER%/mcp" 2>nul || echo       (Already configured)
echo       Added cortex MCP server
echo.

:: ── Step 4/4: Install /cortex-setup ───────────────────────────────────────
echo [4/4] Installing /cortex-setup command...
if not exist "%USERPROFILE%\.claude\commands" mkdir "%USERPROFILE%\.claude\commands"
curl -sf "%CORTEX_SERVER%/cortex-setup.md" -o "%USERPROFILE%\.claude\commands\cortex-setup.md"
echo       Installed to %%USERPROFILE%%\.claude\commands\cortex-setup.md
echo.

:: ── Write initial state ───────────────────────────────────────────────────
if not exist ".claude" mkdir ".claude"
powershell -Command ^
  "$state = if (Test-Path '.claude\cortex-state.json') { Get-Content '.claude\cortex-state.json' | ConvertFrom-Json } else { @{} }; " ^
  "$state | Add-Member -Force NotePropertyName 'system_name' -NotePropertyValue '%SYSTEM_NAME%'; " ^
  "if ('%PROJECT_ID%') { $state | Add-Member -Force NotePropertyName 'cortex_project_id' -NotePropertyValue '%PROJECT_ID%' }; " ^
  "$state | ConvertTo-Json | Set-Content '.claude\cortex-state.json'"

:: ── Done ─────────────────────────────────────────────────────────────────
echo =============================================
echo  Setup complete!
echo.
echo  Open Claude Code and run:
echo.
echo    /cortex-setup
echo.
echo  This will register your system and install all project skills.
echo =============================================
echo.
```

**Step 2: Verify placeholder**

```bash
grep "{{CORTEX_SERVER_URL}}" integrations/claude-code/setup/cortexSetup.bat
```

Expected: line shown with placeholder

**Step 3: Run the MCP endpoint tests now (all template files exist)**

```bash
cd /home/winadmin/projects/Trinity/cortex/python && uv run pytest tests/mcp_server/test_setup_endpoints.py -v
```

Expected: 5 PASSED

**Step 4: Commit**

```bash
git add integrations/claude-code/setup/cortexSetup.bat
git commit -m "feat: add cortexSetup.bat Windows setup script"
```

---

## Task 6: Frontend — `CortexSetupDownload` component

A clean download section for the MCP page. No logic — just two download links and a next-step callout.

**Files:**
- Create: `cortex-ui/src/features/mcp/components/CortexSetupDownload.tsx`
- Modify: `cortex-ui/src/features/mcp/components/index.ts`

**Step 1: Write the component**

Create `cortex-ui/src/features/mcp/components/CortexSetupDownload.tsx`:

```tsx
import { Download } from "lucide-react";

export function CortexSetupDownload() {
  return (
    <div className="rounded-xl border border-cyan-500/20 bg-cyan-500/5 p-6">
      <div className="flex items-start gap-4">
        <div className="flex-shrink-0 w-10 h-10 rounded-lg bg-cyan-500/10 flex items-center justify-center">
          <Download className="w-5 h-5 text-cyan-400" />
        </div>
        <div className="flex-1 min-w-0">
          <h2 className="text-lg font-semibold text-white mb-1">Connect a New Machine</h2>
          <p className="text-sm text-zinc-400 mb-4">
            Download the setup script and run it in your project directory. It adds Cortex to Claude
            Code and installs the{" "}
            <code className="text-cyan-300 bg-white/5 px-1 rounded">/cortex-setup</code> command in
            one step.
          </p>
          <div className="flex flex-wrap gap-3 mb-4">
            <a
              href="/cortex-setup.sh"
              download="cortexSetup.sh"
              className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-cyan-500/10 border border-cyan-500/30 text-cyan-300 text-sm font-medium hover:bg-cyan-500/20 transition-colors"
            >
              <Download className="w-4 h-4" />
              cortexSetup.sh
              <span className="text-xs text-zinc-500">Mac / Linux</span>
            </a>
            <a
              href="/cortex-setup.bat"
              download="cortexSetup.bat"
              className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-white/5 border border-white/10 text-zinc-300 text-sm font-medium hover:bg-white/10 transition-colors"
            >
              <Download className="w-4 h-4" />
              cortexSetup.bat
              <span className="text-xs text-zinc-500">Windows</span>
            </a>
          </div>
          <p className="text-xs text-zinc-500">
            Then open Claude Code in your project and run{" "}
            <code className="text-cyan-400">/cortex-setup</code> to register your system and install
            skills.
          </p>
        </div>
      </div>
    </div>
  );
}
```

**Step 2: Export from index**

In `cortex-ui/src/features/mcp/components/index.ts`, add:

```typescript
export { CortexSetupDownload } from "./CortexSetupDownload";
```

**Step 3: TypeScript check**

```bash
cd /home/winadmin/projects/Trinity/cortex/cortex-ui && npx tsc --noEmit 2>&1 | grep "src/features/mcp"
```

Expected: no output (no errors)

**Step 4: Biome check**

```bash
npm run biome:fix -- --write src/features/mcp/components/CortexSetupDownload.tsx
```

**Step 5: Commit**

```bash
cd /home/winadmin/projects/Trinity/cortex && git add cortex-ui/src/features/mcp/components/CortexSetupDownload.tsx cortex-ui/src/features/mcp/components/index.ts
git commit -m "feat: add CortexSetupDownload component for MCP page"
```

---

## Task 7: Integrate `CortexSetupDownload` into `McpView`

**Files:**
- Modify: `cortex-ui/src/features/mcp/views/McpView.tsx`

**Step 1: Add the import**

In `McpView.tsx`, add `CortexSetupDownload` to the existing component imports:

```typescript
import { McpClientList, McpConfigSection, McpStatusBar, CortexSetupDownload } from "../components";
```

**Step 2: Add to JSX — first item in the `motion.div` list, before Status Bar**

Inside the return's `<motion.div>`, add before the existing Status Bar block:

```tsx
{/* Connect a New Machine */}
<motion.div variants={itemVariants}>
  <CortexSetupDownload />
</motion.div>
```

**Step 3: TypeScript check**

```bash
cd /home/winadmin/projects/Trinity/cortex/cortex-ui && npx tsc --noEmit 2>&1 | grep "src/features/mcp"
```

Expected: no output

**Step 4: Biome check**

```bash
npm run biome:fix -- --write src/features/mcp/views/McpView.tsx
```

**Step 5: Run full backend test suite to verify nothing broken**

```bash
cd /home/winadmin/projects/Trinity/cortex/python && uv run pytest -q 2>&1 | tail -5
```

Expected: all pass

**Step 6: Commit**

```bash
cd /home/winadmin/projects/Trinity/cortex && git add cortex-ui/src/features/mcp/views/McpView.tsx
git commit -m "feat: add Connect a New Machine section to MCP page"
```

---

## Download URL Routing Note

The download buttons use `/cortex-setup.sh` and `/cortex-setup.bat` as relative paths. In development (Vite proxy), these need to be proxied to the MCP server (port 8051), not the API server (port 8181).

**Check `vite.config.ts` proxy rules** — if there is no catch-all proxy to MCP for these paths, add:

```typescript
"/cortex-setup": {
  target: "http://localhost:8051",
  changeOrigin: true,
}
```

in `cortex-ui/vite.config.ts`. This should be verified during manual testing after Task 7.
