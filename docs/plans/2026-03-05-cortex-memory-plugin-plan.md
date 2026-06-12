# Cortex Memory Plugin Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build the cortex-memory Claude Code plugin with smart-explore, session memory, and context injection — while renaming Skills to Extensions and removing claude-mem.

**Architecture:** Pure Python plugin installed locally per-project via cortexSetup scripts. Plugin provides tree-sitter AST tools (local filesystem), session memory hooks (buffered locally, flushed to Cortex), and context injection (SessionStart). Backend extended with sessions API and extensions rename.

**Tech Stack:** Python 3.12, tree-sitter + tree-sitter-language-pack, httpx, FastAPI, Supabase/PostgreSQL, FastMCP

**Design Doc:** `docs/plans/2026-03-05-cortex-memory-plugin-design.md`

---

## Phase 1: Extensions Rename

Rename "Skills" to "Extensions" across the entire stack. This is a prerequisite for all other work since the plugin will be registered as an extension.

### Task 1: Database Migration — Rename Tables

**Files:**
- Create: `migration/0.1.0/015_rename_skills_to_extensions.sql`

**Step 1: Write migration SQL**

```sql
-- 015_rename_skills_to_extensions.sql
-- Rename skills tables to extensions

-- Rename tables
ALTER TABLE IF EXISTS cortex_skills RENAME TO cortex_extensions;
ALTER TABLE IF EXISTS cortex_skill_versions RENAME TO cortex_extension_versions;
ALTER TABLE IF EXISTS cortex_project_skills RENAME TO cortex_project_extensions;
ALTER TABLE IF EXISTS cortex_system_skills RENAME TO cortex_system_extensions;

-- Add new columns for plugin support
ALTER TABLE cortex_extensions ADD COLUMN IF NOT EXISTS type TEXT NOT NULL DEFAULT 'skill';
ALTER TABLE cortex_extensions ADD COLUMN IF NOT EXISTS plugin_manifest JSONB;

-- Rename indexes
ALTER INDEX IF EXISTS idx_skills_name RENAME TO idx_extensions_name;
ALTER INDEX IF EXISTS idx_skills_created_by RENAME TO idx_extensions_created_by;
ALTER INDEX IF EXISTS idx_skill_versions_skill_id RENAME TO idx_extension_versions_extension_id;
ALTER INDEX IF EXISTS idx_project_skills_project RENAME TO idx_project_extensions_project;
ALTER INDEX IF EXISTS idx_project_skills_skill RENAME TO idx_project_extensions_extension;
ALTER INDEX IF EXISTS idx_system_skills_system RENAME TO idx_system_extensions_system;
ALTER INDEX IF EXISTS idx_system_skills_skill RENAME TO idx_system_extensions_extension;

-- Rename foreign key columns in dependent tables
ALTER TABLE cortex_extension_versions RENAME COLUMN skill_id TO extension_id;
ALTER TABLE cortex_project_extensions RENAME COLUMN skill_id TO extension_id;
ALTER TABLE cortex_system_extensions RENAME COLUMN skill_id TO extension_id;

-- Add index for type filtering
CREATE INDEX IF NOT EXISTS idx_extensions_type ON cortex_extensions(type);
```

**Step 2: Run migration against local Supabase**

Run: `psql $SUPABASE_URL -f migration/0.1.0/015_rename_skills_to_extensions.sql`
Expected: All ALTER statements succeed

**Step 3: Commit**

```bash
git add migration/0.1.0/015_rename_skills_to_extensions.sql
git commit -m "migration: rename skills tables to extensions, add type and plugin_manifest columns"
```

---

### Task 2: Backend Services — Rename skill_service.py

**Files:**
- Rename: `python/src/server/services/skills/` → `python/src/server/services/extensions/`
- Rename: `skill_service.py` → `extension_service.py`
- Rename: `skill_validation_service.py` → `extension_validation_service.py`
- Rename: `skill_sync_service.py` → `extension_sync_service.py`
- Rename: `skill_seeding_service.py` → `extension_seeding_service.py`
- Modify: `python/src/server/services/extensions/__init__.py`

**Step 1: Rename directory and files**

```bash
cd python/src/server/services
git mv skills extensions
cd extensions
git mv skill_service.py extension_service.py
git mv skill_validation_service.py extension_validation_service.py
git mv skill_sync_service.py extension_sync_service.py
git mv skill_seeding_service.py extension_seeding_service.py
```

**Step 2: Update extension_service.py**

Find-and-replace throughout the file:
- `cortex_skills` → `cortex_extensions`
- `cortex_skill_versions` → `cortex_extension_versions`
- `cortex_project_skills` → `cortex_project_extensions`
- `SKILLS_TABLE` → `EXTENSIONS_TABLE`
- `VERSIONS_TABLE` variable value update
- `PROJECT_SKILLS_TABLE` → `PROJECT_EXTENSIONS_TABLE`
- `class SkillService` → `class ExtensionService`
- `skill_id` → `extension_id` (in method parameters and internal usage)
- `skill` → `extension` in method names: `create_skill` → `create_extension`, `list_skills` → `list_extensions`, `list_skills_full` → `list_extensions_full`, `get_skill` → `get_extension`, `find_by_name` → `find_by_name` (keep), `update_skill` → `update_extension`, `delete_skill` → `delete_extension`, `get_versions` → `get_versions` (keep), `get_project_skills` → `get_project_extensions`, `save_project_override` → `save_project_override` (keep)
- Update docstrings and log messages
- Update `_save_version` column reference from `skill_id` to `extension_id`

**Step 3: Update extension_validation_service.py**

Find-and-replace:
- `class SkillValidationService` → `class ExtensionValidationService`
- `MAX_SKILL_SIZE_BYTES` → `MAX_EXTENSION_SIZE_BYTES`
- Update docstrings, log messages, and error messages from "skill" to "extension"
- Keep validation logic identical (SKILL.md format validation still valid for skills type)

**Step 4: Update extension_sync_service.py**

Find-and-replace:
- `cortex_system_skills` → `cortex_system_extensions`
- `SYSTEM_SKILLS_TABLE` → `SYSTEM_EXTENSIONS_TABLE`
- `class SkillSyncService` → `class ExtensionSyncService`
- `skill_id` → `extension_id` in all column references
- Method parameter names: `local_skills` → `local_extensions`, `cortex_skills` → `cortex_extensions`
- Method names: `get_system_skills` → `get_system_extensions`, `get_system_project_skills` → `get_system_project_extensions`
- Update docstrings and log messages

**Step 5: Update extension_seeding_service.py**

Find-and-replace:
- `class SkillSeedingService` → `class ExtensionSeedingService`
- `cortex_skills` → `cortex_extensions`
- `seed_skills` → `seed_extensions`
- `default_skills_dir` → `default_extensions_dir`
- Update the directory path from `integrations/claude-code/skills/` to `integrations/claude-code/extensions/`
- Update docstrings and log messages

**Step 6: Update __init__.py**

```python
from .extension_service import ExtensionService
from .extension_validation_service import ExtensionValidationService
from .extension_sync_service import ExtensionSyncService
from .extension_seeding_service import ExtensionSeedingService
from .system_service import SystemService

__all__ = [
    "ExtensionService",
    "ExtensionValidationService",
    "ExtensionSyncService",
    "ExtensionSeedingService",
    "SystemService",
]
```

**Step 7: Commit**

```bash
git add -A
git commit -m "refactor: rename skill services to extension services"
```

---

### Task 3: Backend API Routes — Rename skills_api.py

**Files:**
- Rename: `python/src/server/api_routes/skills_api.py` → `extensions_api.py`
- Modify: `python/src/server/main.py`

**Step 1: Rename file**

```bash
git mv python/src/server/api_routes/skills_api.py python/src/server/api_routes/extensions_api.py
```

**Step 2: Update extensions_api.py**

Find-and-replace throughout:
- `router = APIRouter(prefix="/api", tags=["skills"])` → `tags=["extensions"]`
- All route paths: `/skills` → `/extensions`, `/projects/{project_id}/skills` → `/projects/{project_id}/extensions`
- Request model names: `CreateSkillRequest` → `CreateExtensionRequest`, `UpdateSkillRequest` → `UpdateExtensionRequest`, `ValidateSkillRequest` → `ValidateExtensionRequest`, `InstallSkillRequest` → `InstallExtensionRequest`, `RemoveSkillRequest` → `RemoveExtensionRequest`, `SaveProjectOverrideRequest` → keep same
- Service imports: `from ..services.extensions import ExtensionService, ExtensionValidationService, SystemService`
- Function names: `list_skills` → `list_extensions`, `get_skill` → `get_extension`, `create_skill` → `create_extension`, `update_skill` → `update_extension`, `delete_skill` → `delete_extension`, `validate_skill` → `validate_extension`, `validate_skill_standalone` → `validate_extension_standalone`, `get_skill_versions` → `get_extension_versions`, `get_project_skills` → `get_project_extensions`, `install_skill` → `install_extension`, `remove_skill` → `remove_extension`
- Parameter names: `skill_id` → `extension_id`
- Error messages and log messages: "skill" → "extension"
- Response field names: `"skill"` → `"extension"`, `"skills"` → `"extensions"`

**Step 3: Update main.py**

Change the import and router inclusion:
- `from .api_routes.extensions_api import router as extensions_router`
- `app.include_router(extensions_router)`
- Update the seeding service import: `from .services.extensions.extension_seeding_service import ExtensionSeedingService`
- Update seeding call: `seeder = ExtensionSeedingService()` and `counts = seeder.seed_extensions()`

**Step 4: Commit**

```bash
git add -A
git commit -m "refactor: rename skills API routes to extensions"
```

---

### Task 4: MCP Tools — Rename skill_tools.py

**Files:**
- Rename: `python/src/mcp_server/features/skills/` → `python/src/mcp_server/features/extensions/`
- Rename: `skill_tools.py` → `extension_tools.py`
- Modify: `python/src/mcp_server/mcp_server.py`

**Step 1: Rename directory and files**

```bash
cd python/src/mcp_server/features
git mv skills extensions
cd extensions
git mv skill_tools.py extension_tools.py
```

**Step 2: Update extension_tools.py**

Find-and-replace:
- `register_skill_tools` → `register_extension_tools`
- `find_skills` → `find_extensions`
- `manage_skills` → `manage_extensions`
- All API URL paths: `/api/skills` → `/api/extensions`, `/api/projects/{pid}/skills` → `/api/projects/{pid}/extensions`
- Parameter names: `skill_id` → `extension_id`, `skill_content` → `extension_content`, `skill_name` → `extension_name`
- Response field names: `"skill"` → `"extension"`, `"skills"` → `"extensions"`
- Docstrings: "skill" → "extension" throughout
- Error messages: "Skill" → "Extension"
- Internal helper function variable names containing "skill"

**Step 3: Update __init__.py**

```python
"""Extensions management tools for Cortex MCP Server."""

from .extension_tools import register_extension_tools

__all__ = ["register_extension_tools"]
```

**Step 4: Update mcp_server.py**

Change the registration block:
- `from src.mcp_server.features.extensions import register_extension_tools`
- `register_extension_tools(mcp)`
- Update log messages: "skill tools" → "extension tools"

**Step 5: Commit**

```bash
git add -A
git commit -m "refactor: rename skill MCP tools to extension tools"
```

---

### Task 5: Frontend — Rename skills feature to extensions

**Files:**
- Rename: `cortex-ui/src/features/projects/skills/` → `extensions/`
- Rename all files within: `SkillsTab.tsx` → `ExtensionsTab.tsx`, `skillService.ts` → `extensionService.ts`, `useSkillQueries.ts` → `useExtensionQueries.ts`, `SkillStatusBadge.tsx` → `ExtensionStatusBadge.tsx`, `SystemSkillList.tsx` → `SystemExtensionList.tsx`
- Modify: `cortex-ui/src/features/projects/views/ProjectsView.tsx`

**Step 1: Rename directory and files**

```bash
cd cortex-ui/src/features/projects
git mv skills extensions
cd extensions
git mv SkillsTab.tsx ExtensionsTab.tsx
git mv services/skillService.ts services/extensionService.ts
git mv hooks/useSkillQueries.ts hooks/useExtensionQueries.ts
git mv components/SkillStatusBadge.tsx components/ExtensionStatusBadge.tsx
git mv components/SystemSkillList.tsx components/SystemExtensionList.tsx
```

**Step 2: Update types/index.ts**

Rename all interfaces:
- `Skill` → `Extension`
- `SystemSkill` → `SystemExtension`
- `SystemWithSkills` → `SystemWithExtensions`
- `ProjectSkillsResponse` → `ProjectExtensionsResponse`
- `SkillsListResponse` → `ExtensionsListResponse`
- Property names: `all_skills` → `all_extensions`, `skills` → `extensions`
- Add `type` field to `Extension` interface: `type: "skill" | "plugin"`
- Add optional `plugin_manifest` field: `plugin_manifest?: PluginManifest | null`

Add new type:
```typescript
interface PluginManifest {
  hooks: string[];
  mcp_server: boolean;
  dependencies: string[];
  skills_included: string[];
  min_python_version: string;
}
```

**Step 3: Update extensionService.ts**

- Export name: `extensionService`
- Method names: `getProjectSkills` → `getProjectExtensions`, `getAllSkills` → `getAllExtensions`, `installSkill` → `installExtension`, `removeSkill` → `removeExtension`
- API paths: `/api/skills` → `/api/extensions`, `/api/projects/{id}/skills` → `/api/projects/{id}/extensions`
- Type imports: use renamed types

**Step 4: Update useExtensionQueries.ts**

- `skillKeys` → `extensionKeys`
- All query key base: `["skills"]` → `["extensions"]`
- Hook names: `useProjectSkills` → `useProjectExtensions`, `useAllSkills` → `useAllExtensions`, `useInstallSkill` → `useInstallExtension`, `useRemoveSkill` → `useRemoveExtension`
- Service import: `extensionService`

**Step 5: Update ExtensionsTab.tsx**

- Component name: `ExtensionsTab`
- Props interface: `ExtensionsTabProps`
- All imports: use renamed hooks, components, types
- Text labels: "Skills" → "Extensions", "Loading skills..." → "Loading extensions..."

**Step 6: Update ExtensionStatusBadge.tsx**

- Component name: `ExtensionStatusBadge`
- Props interface: `ExtensionStatusBadgeProps`

**Step 7: Update SystemExtensionList.tsx**

- Component name: `SystemExtensionList`
- Props interface: `SystemExtensionListProps`
- Variable names: `systemSkills` → `systemExtensions`, `allSkills` → `allExtensions`, `installedSkillIds` → `installedExtensionIds`, `availableSkills` → `availableExtensions`
- Text: "Installed Skills" → "Installed Extensions"

**Step 8: Update SystemCard.tsx**

- Variable: `skillCount` → `extensionCount`
- Text: `skill${...}` → `extension${...}`
- Type import: `SystemWithExtensions`

**Step 9: Update ProjectsView.tsx**

- Import: `ExtensionsTab` from `"../extensions/ExtensionsTab"`
- Tab definition: `{ id: "extensions", label: "Extensions", icon: ... }`
- Conditional render: `activeTab === "extensions" && <ExtensionsTab ...>`
- Update both desktop and mobile tab definitions

**Step 10: Commit**

```bash
git add -A
git commit -m "refactor: rename skills frontend feature to extensions"
```

---

### Task 6: Tests — Rename and Verify

**Files:**
- Rename: `python/tests/server/services/skills/` → `extensions/`
- Rename: all test files within (`test_skill_*.py` → `test_extension_*.py`)
- Rename: `python/tests/server/api_routes/test_skills_api_include_content.py` → `test_extensions_api_include_content.py`
- Rename: `python/tests/mcp_server/features/skills/` → `extensions/`
- Rename: `test_skill_tools.py` → `test_extension_tools.py`

**Step 1: Rename all test directories and files**

```bash
# Service tests
cd python/tests/server/services
git mv skills extensions
cd extensions
git mv test_skill_service.py test_extension_service.py
git mv test_skill_validation_service.py test_extension_validation_service.py
git mv test_skill_sync_service.py test_extension_sync_service.py
git mv test_skill_seeding_service.py test_extension_seeding_service.py

# API tests
cd ../../api_routes
git mv test_skills_api_include_content.py test_extensions_api_include_content.py

# MCP tests
cd ../../../mcp_server/features
git mv skills extensions
cd extensions
git mv test_skill_tools.py test_extension_tools.py
```

**Step 2: Update all test file imports and references**

In each test file:
- Update import paths from `services.skills` to `services.extensions`
- Update class names: `SkillService` → `ExtensionService`, etc.
- Update table name strings: `cortex_skills` → `cortex_extensions`, etc.
- Update API route paths: `/api/skills` → `/api/extensions`
- Update response field names: `"skills"` → `"extensions"`

**Step 3: Run all tests**

Run: `cd python && uv run pytest -v`
Expected: All tests pass

**Step 4: Run frontend type check**

Run: `cd cortex-ui && npx tsc --noEmit`
Expected: No errors

**Step 5: Run frontend linting**

Run: `cd cortex-ui && npm run biome && npm run lint`
Expected: Clean (or only pre-existing issues)

**Step 6: Commit**

```bash
git add -A
git commit -m "refactor: rename skills tests to extensions, verify all pass"
```

---

### Task 7: Integrations Directory — Rename skills to extensions

**Files:**
- Rename: `integrations/claude-code/skills/` → `integrations/claude-code/extensions/`
- Modify: SKILL.md files that reference "skill sync" internally

**Step 1: Rename directory**

```bash
git mv integrations/claude-code/skills integrations/claude-code/extensions
```

**Step 2: Rename cortex-skill-sync to cortex-extension-sync**

```bash
git mv integrations/claude-code/extensions/cortex-skill-sync integrations/claude-code/extensions/cortex-extension-sync
```

**Step 3: Update SKILL.md references**

In `cortex-extension-sync/SKILL.md`:
- Update name in frontmatter: `cortex-extension-sync`
- Update description to reference "extensions"
- Update MCP tool calls from `find_skills`/`manage_skills` to `find_extensions`/`manage_extensions`

In `cortex-bootstrap/SKILL.md`:
- Update references to skill sync to extension sync
- Update MCP tool references

In `cortex-memory/SKILL.md`:
- Update reference to skill sync check

**Step 4: Commit**

```bash
git add -A
git commit -m "refactor: rename integrations skills directory to extensions"
```

---

## Phase 2: Session Memory Backend

New tables, service, API, and MCP tools for session storage.

### Task 8: Database Migration — Sessions Tables

**Files:**
- Create: `migration/0.1.0/016_add_session_tables.sql`

**Step 1: Write migration SQL**

```sql
-- 016_add_session_tables.sql
-- Session memory tables for cortex-memory plugin

-- Session summaries (low volume, has embeddings)
CREATE TABLE IF NOT EXISTS cortex_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES cortex_projects(id) ON DELETE CASCADE,
    machine_id TEXT NOT NULL,
    session_id TEXT NOT NULL UNIQUE,
    started_at TIMESTAMPTZ NOT NULL,
    ended_at TIMESTAMPTZ,
    summary TEXT,
    summary_embedding VECTOR(1536),
    observation_count INT DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Individual observations (high volume, full-text search)
CREATE TABLE IF NOT EXISTS cortex_session_observations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id TEXT NOT NULL REFERENCES cortex_sessions(session_id) ON DELETE CASCADE,
    project_id UUID REFERENCES cortex_projects(id) ON DELETE CASCADE,
    machine_id TEXT NOT NULL,
    type TEXT NOT NULL,
    title TEXT NOT NULL,
    content TEXT,
    files TEXT[],
    search_vector TSVECTOR,
    observed_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for sessions
CREATE INDEX idx_sessions_project_time ON cortex_sessions(project_id, started_at DESC);
CREATE INDEX idx_sessions_machine ON cortex_sessions(machine_id, started_at DESC);
CREATE INDEX idx_sessions_embedding ON cortex_sessions
    USING hnsw(summary_embedding vector_cosine_ops);

-- Indexes for observations
CREATE INDEX idx_observations_session ON cortex_session_observations(session_id);
CREATE INDEX idx_observations_project_time
    ON cortex_session_observations(project_id, observed_at DESC);
CREATE INDEX idx_observations_search
    ON cortex_session_observations USING gin(search_vector);
CREATE INDEX idx_observations_type
    ON cortex_session_observations(project_id, type, observed_at DESC);

-- Auto-populate search_vector on insert/update
CREATE OR REPLACE FUNCTION update_observation_search_vector()
RETURNS TRIGGER AS $$
BEGIN
    NEW.search_vector := to_tsvector('english',
        coalesce(NEW.title, '') || ' ' ||
        coalesce(NEW.content, '') || ' ' ||
        coalesce(array_to_string(NEW.files, ' '), '')
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_observation_search_vector
    BEFORE INSERT OR UPDATE ON cortex_session_observations
    FOR EACH ROW EXECUTE FUNCTION update_observation_search_vector();
```

**Step 2: Run migration**

Run: `psql $SUPABASE_URL -f migration/0.1.0/016_add_session_tables.sql`
Expected: All CREATE statements succeed

**Step 3: Commit**

```bash
git add migration/0.1.0/016_add_session_tables.sql
git commit -m "migration: add session memory tables with full-text search"
```

---

### Task 9: Session Service

**Files:**
- Create: `python/src/server/services/sessions/__init__.py`
- Create: `python/src/server/services/sessions/session_service.py`

**Step 1: Write tests first**

Create: `python/tests/server/services/sessions/test_session_service.py`

```python
"""Tests for SessionService."""
import pytest
from unittest.mock import MagicMock, patch
from src.server.services.sessions.session_service import SessionService


@pytest.fixture
def mock_supabase():
    return MagicMock()


@pytest.fixture
def service(mock_supabase):
    return SessionService(supabase_client=mock_supabase)


def test_create_session_success(service, mock_supabase):
    """Creating a session with observations stores both."""
    mock_supabase.table.return_value.insert.return_value.execute.return_value.data = [
        {"id": "uuid-1", "session_id": "sess-1"}
    ]

    success, result = service.create_session(
        session_id="sess-1",
        machine_id="machine-abc",
        project_id="proj-1",
        started_at="2026-03-05T10:00:00Z",
        ended_at="2026-03-05T11:00:00Z",
        summary="Fixed a bug",
        observations=[
            {
                "type": "bugfix",
                "title": "Fixed null check",
                "content": "Added guard clause",
                "files": ["src/main.py"],
                "timestamp": "2026-03-05T10:30:00Z",
            }
        ],
    )

    assert success is True
    assert "session" in result


def test_create_session_missing_session_id(service):
    """session_id is required."""
    success, result = service.create_session(
        session_id="",
        machine_id="m",
        project_id="p",
        started_at="2026-03-05T10:00:00Z",
    )
    assert success is False
    assert "error" in result


def test_list_sessions_by_project(service, mock_supabase):
    """List sessions filtered by project_id."""
    mock_supabase.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = []

    success, result = service.list_sessions(project_id="proj-1", limit=5)
    assert success is True
    assert "sessions" in result


def test_get_session_with_observations(service, mock_supabase):
    """Get a single session with its observations."""
    mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
        {"id": "uuid-1", "session_id": "sess-1", "summary": "Did stuff"}
    ]

    success, result = service.get_session("sess-1")
    assert success is True
    assert "session" in result


def test_search_sessions(service, mock_supabase):
    """Search sessions by query."""
    mock_supabase.rpc.return_value.execute.return_value.data = []

    success, result = service.search_sessions(query="authentication", project_id="proj-1")
    assert success is True
```

**Step 2: Run tests to verify they fail**

Run: `cd python && uv run pytest tests/server/services/sessions/test_session_service.py -v`
Expected: ImportError (module doesn't exist yet)

**Step 3: Write SessionService**

Create `python/src/server/services/sessions/__init__.py`:
```python
from .session_service import SessionService

__all__ = ["SessionService"]
```

Create `python/src/server/services/sessions/session_service.py` implementing:
- `create_session(session_id, machine_id, project_id, started_at, ended_at?, summary?, observations?)` — inserts session row + batch inserts observations
- `list_sessions(project_id?, machine_id?, limit=10)` — list sessions ordered by started_at DESC
- `get_session(session_id)` — get session + its observations
- `search_sessions(query, project_id?, limit=10)` — full-text search on observations, semantic search on summaries

Follow the existing service pattern:
- Return `tuple[bool, dict[str, Any]]`
- Use `get_supabase_client()` for DB access
- Use `get_logger(__name__)` for logging

**Step 4: Run tests to verify they pass**

Run: `cd python && uv run pytest tests/server/services/sessions/test_session_service.py -v`
Expected: All pass

**Step 5: Commit**

```bash
git add python/src/server/services/sessions/ python/tests/server/services/sessions/
git commit -m "feat: add SessionService for session memory storage"
```

---

### Task 10: Session API Endpoints

**Files:**
- Create: `python/src/server/api_routes/sessions_api.py`
- Modify: `python/src/server/main.py`

**Step 1: Write tests**

Create: `python/tests/server/api_routes/test_sessions_api.py`

Test cases:
- `POST /api/sessions` — create session with observations (batch)
- `GET /api/sessions?project_id=X&limit=5` — list sessions
- `GET /api/sessions?project_id=X&q=search` — search sessions
- `GET /api/sessions/{session_id}` — get session with observations
- `POST /api/sessions` with missing required fields → 422

**Step 2: Run tests to verify they fail**

Run: `cd python && uv run pytest tests/server/api_routes/test_sessions_api.py -v`
Expected: ImportError

**Step 3: Implement sessions_api.py**

Follow the pattern from `extensions_api.py` (formerly `skills_api.py`):
- `router = APIRouter(prefix="/api", tags=["sessions"])`
- Request model: `CreateSessionRequest(BaseModel)` with fields matching the design batch payload
- `POST /sessions` — calls `SessionService.create_session()`
- `GET /sessions` — calls `list_sessions()` or `search_sessions()` based on `q` param
- `GET /sessions/{session_id}` — calls `get_session()`

**Step 4: Register router in main.py**

Add import and `app.include_router(sessions_router)`.

**Step 5: Run tests**

Run: `cd python && uv run pytest tests/server/api_routes/test_sessions_api.py -v`
Expected: All pass

**Step 6: Commit**

```bash
git add python/src/server/api_routes/sessions_api.py python/src/server/main.py python/tests/server/api_routes/test_sessions_api.py
git commit -m "feat: add sessions API endpoints for session memory"
```

---

### Task 11: Session MCP Tools

**Files:**
- Create: `python/src/mcp_server/features/sessions/__init__.py`
- Create: `python/src/mcp_server/features/sessions/session_tools.py`
- Modify: `python/src/mcp_server/mcp_server.py`

**Step 1: Write tests**

Create: `python/tests/mcp_server/features/sessions/test_session_tools.py`

Test the two MCP tools:
- `cortex_search_sessions` — calls backend `GET /api/sessions?q=...`
- `cortex_get_session` — calls backend `GET /api/sessions/{id}`

**Step 2: Implement session_tools.py**

Follow the pattern from `extension_tools.py`:

```python
def register_session_tools(mcp: FastMCP):
    @mcp.tool()
    async def cortex_search_sessions(
        ctx: Context,
        query: str,
        project_id: str | None = None,
        limit: int = 10,
    ) -> str:
        """Search session history across agents and machines."""
        # HTTP call to GET /api/sessions?q=query&project_id=X&limit=N

    @mcp.tool()
    async def cortex_get_session(
        ctx: Context,
        session_id: str,
    ) -> str:
        """Get a specific session with all its observations."""
        # HTTP call to GET /api/sessions/{session_id}
```

**Step 3: Register in mcp_server.py**

Add registration block following the existing pattern.

**Step 4: Run tests**

Run: `cd python && uv run pytest tests/mcp_server/features/sessions/ -v`
Expected: All pass

**Step 5: Commit**

```bash
git add python/src/mcp_server/features/sessions/ python/tests/mcp_server/features/sessions/
git commit -m "feat: add session MCP tools for searching session history"
```

---

## Phase 3: Plugin Core — Smart Explore

Build the tree-sitter based code exploration tools. This is the plugin's local MCP server.

### Task 12: Tree-sitter Parser & Language Queries

**Files:**
- Create: `integrations/claude-code/plugins/cortex-memory/src/__init__.py`
- Create: `integrations/claude-code/plugins/cortex-memory/src/smart_explore/__init__.py`
- Create: `integrations/claude-code/plugins/cortex-memory/src/smart_explore/queries.py`
- Create: `integrations/claude-code/plugins/cortex-memory/src/smart_explore/parser.py`
- Create: `integrations/claude-code/plugins/cortex-memory/requirements.txt`

**Step 1: Create directory structure and requirements.txt**

```bash
mkdir -p integrations/claude-code/plugins/cortex-memory/src/smart_explore
touch integrations/claude-code/plugins/cortex-memory/src/__init__.py
touch integrations/claude-code/plugins/cortex-memory/src/smart_explore/__init__.py
```

`requirements.txt`:
```
tree-sitter>=0.24.0
tree-sitter-language-pack>=0.6.0
httpx>=0.27.0
```

**Step 2: Write queries.py**

Language-specific tree-sitter query patterns for symbol extraction. Each language gets a query string that captures:
- Function/method definitions with `@name` capture
- Class/struct/interface definitions with `@name` capture
- Import statements
- Type definitions, enums, traits

Priority languages: Python, JavaScript, TypeScript/TSX, Go, Rust, Java, Ruby, C, C++

Extension-to-language mapping dict.

**Step 3: Write parser.py**

Core parsing logic:
- `CodeSymbol` dataclass: name, kind, signature, line_start, line_end, parent, exported, docstring, children
- `ParsedFile` dataclass: path, language, symbols, imports, line_count
- `parse_file(path: str, content: str) -> ParsedFile | None` — detect language, load grammar, run query, build symbols
- `extract_signature(lines: list[str], start_line: int) -> str` — get first line(s) of declaration
- `extract_docstring(lines: list[str], symbol_start: int, language: str) -> str | None` — find preceding comments/docstrings
- `detect_exported(symbol, language) -> bool` — language-specific export detection
- `nest_symbols(symbols: list[CodeSymbol]) -> list[CodeSymbol]` — nest methods inside classes by line range

Uses `tree-sitter` Python API directly:
```python
from tree_sitter import Parser, Language
from tree_sitter_language_pack import get_language
```

**Step 4: Write tests**

Create: `integrations/claude-code/plugins/cortex-memory/tests/test_parser.py`

Test with inline code samples:
- Parse a Python file with functions and classes
- Parse a TypeScript file with interfaces and exports
- Verify symbol extraction (names, kinds, line ranges)
- Verify nesting (methods inside classes)
- Verify docstring extraction
- Verify unknown language returns None

**Step 5: Run tests**

Run: `cd integrations/claude-code/plugins/cortex-memory && pip install -r requirements.txt && python -m pytest tests/test_parser.py -v`
Expected: All pass

**Step 6: Commit**

```bash
git add integrations/claude-code/plugins/cortex-memory/
git commit -m "feat: add tree-sitter parser and language queries for smart-explore"
```

---

### Task 13: Search & Ranking

**Files:**
- Create: `integrations/claude-code/plugins/cortex-memory/src/smart_explore/search.py`

**Step 1: Write tests**

Create: `integrations/claude-code/plugins/cortex-memory/tests/test_search.py`

Test cases:
- `walk_directory` discovers code files, skips ignored dirs
- `match_score` returns correct scores for exact/substring/fuzzy matches
- `rank_symbols` scores by name (3x), signature (2x), docstring (1x)
- `search_codebase` end-to-end with a temp directory of test files
- File size limit (>512KB skipped)
- `format_folded_view` produces expected output format
- `format_search_results` produces expected output format

**Step 2: Implement search.py**

Functions:
- `walk_directory(root: str, max_depth=20, file_pattern=None) -> list[str]` — discover code files, skip ignored dirs (`.git`, `node_modules`, `__pycache__`, `dist`, `vendor`, `.venv`, `build`)
- `match_score(text: str, query_parts: list[str]) -> int` — exact (+10), substring (+5), fuzzy (+1)
- `rank_symbols(symbols: list[CodeSymbol], query: str) -> list[tuple[CodeSymbol, int, str]]` — score and rank, return (symbol, score, match_reason)
- `search_codebase(root: str, query: str, max_results=20, file_pattern=None) -> SearchResult` — full pipeline: walk → parse → rank → format
- `format_folded_view(parsed_file: ParsedFile) -> str` — compact structural display
- `format_search_results(result: SearchResult) -> str` — human-readable output with token estimates
- `format_unfold(file_path: str, symbol: CodeSymbol, lines: list[str]) -> str` — full source with location marker

`SearchResult` dataclass: matching_symbols, folded_files, stats, token_estimate

**Step 3: Run tests**

Run: `cd integrations/claude-code/plugins/cortex-memory && python -m pytest tests/test_search.py -v`
Expected: All pass

**Step 4: Commit**

```bash
git add integrations/claude-code/plugins/cortex-memory/
git commit -m "feat: add search and ranking for smart-explore"
```

---

### Task 14: Plugin MCP Server

**Files:**
- Create: `integrations/claude-code/plugins/cortex-memory/src/mcp_server.py`

**Step 1: Write tests**

Create: `integrations/claude-code/plugins/cortex-memory/tests/test_mcp_tools.py`

Test the three MCP tool functions directly (mock the parser/search layer):
- `smart_search` returns ranked results
- `smart_outline` returns folded view for a file
- `smart_unfold` returns full source of a symbol
- `smart_unfold` with nonexistent symbol lists available symbols
- `smart_search` with no results returns helpful message

**Step 2: Implement mcp_server.py**

Uses `mcp.server.fastmcp` with stdio transport:

```python
from mcp.server.fastmcp import FastMCP
import os

mcp = FastMCP("cortex-memory", transport="stdio")

@mcp.tool()
async def smart_search(query: str, path: str | None = None, max_results: int = 20, file_pattern: str | None = None) -> str:
    """Search codebase for symbols using tree-sitter AST parsing."""
    root = path or os.getcwd()
    result = search_codebase(root, query, max_results, file_pattern)
    return format_search_results(result)

@mcp.tool()
async def smart_outline(file_path: str) -> str:
    """Get structural outline of a file — all symbols with signatures, bodies folded."""
    content = read_file(file_path)
    parsed = parse_file(file_path, content)
    return format_folded_view(parsed)

@mcp.tool()
async def smart_unfold(file_path: str, symbol_name: str) -> str:
    """Expand a specific symbol from a file — full source with comments."""
    content = read_file(file_path)
    parsed = parse_file(file_path, content)
    symbol = find_symbol(parsed, symbol_name)
    if not symbol:
        available = [s.name for s in parsed.symbols]
        return f"Symbol '{symbol_name}' not found. Available: {', '.join(available)}"
    return format_unfold(file_path, symbol, content.splitlines())

if __name__ == "__main__":
    mcp.run()
```

**Step 3: Run tests**

Run: `cd integrations/claude-code/plugins/cortex-memory && python -m pytest tests/test_mcp_tools.py -v`
Expected: All pass

**Step 4: Commit**

```bash
git add integrations/claude-code/plugins/cortex-memory/
git commit -m "feat: add plugin MCP server with smart_search, smart_outline, smart_unfold"
```

---

## Phase 4: Plugin — Session Memory & Context

Hook scripts and Cortex integration.

### Task 15: Cortex Client

**Files:**
- Create: `integrations/claude-code/plugins/cortex-memory/src/cortex_client.py`

**Step 1: Implement cortex_client.py**

HTTP client for communicating with Cortex:

```python
class CortexClient:
    def __init__(self, config_path: str | None = None):
        """Load config from cortex-config.json."""
        self.config = self._load_config(config_path)
        self.api_url = self.config.get("cortex_api_url", "")
        self.project_id = self.config.get("project_id", "")
        self.machine_id = self.config.get("machine_id", "")

    def _load_config(self, path: str | None) -> dict:
        """Try local .claude/cortex-config.json, then ~/.claude/cortex-config.json."""

    async def flush_session(self, session_data: dict) -> bool:
        """POST /api/sessions with batch payload."""

    async def get_recent_sessions(self, limit: int = 5) -> list[dict]:
        """GET /api/sessions?project_id=X&limit=N"""

    async def get_active_tasks(self, limit: int = 10) -> list[dict]:
        """GET /api/projects/{id}/tasks?status=doing,review,todo&limit=N"""

    async def get_knowledge_status(self) -> dict:
        """GET /api/knowledge/sources?project_id=X"""

    def is_configured(self) -> bool:
        """Check if cortex-config.json exists and has required fields."""
```

**Step 2: Write tests**

Create: `integrations/claude-code/plugins/cortex-memory/tests/test_cortex_client.py`

Test config loading (local vs global), is_configured check, HTTP call construction (mock httpx).

**Step 3: Run tests and commit**

```bash
git add integrations/claude-code/plugins/cortex-memory/
git commit -m "feat: add Cortex HTTP client for plugin"
```

---

### Task 16: Session Tracker

**Files:**
- Create: `integrations/claude-code/plugins/cortex-memory/src/session_tracker.py`

**Step 1: Implement session_tracker.py**

Manages the local observation buffer and session lifecycle:

```python
class SessionTracker:
    def __init__(self, buffer_path: str = ".claude/cortex-memory-buffer.jsonl"):
        self.buffer_path = buffer_path
        self.session_id: str | None = None
        self.started_at: str | None = None

    def start_session(self) -> str:
        """Generate session_id, record start time, return session_id."""

    def append_observation(self, tool_name: str, files: list[str], summary: str):
        """Append one observation to the JSONL buffer file."""

    def flush(self, cortex_client: CortexClient) -> bool:
        """Read buffer, send batch to Cortex, clear buffer on success."""

    def has_stale_buffer(self) -> bool:
        """Check if buffer file exists with data from a previous session."""

    def flush_stale(self, cortex_client: CortexClient) -> bool:
        """Flush leftover buffer from a crashed session."""
```

**Step 2: Write tests, run, commit**

```bash
git add integrations/claude-code/plugins/cortex-memory/
git commit -m "feat: add session tracker with local buffering"
```

---

### Task 17: Hook Scripts

**Files:**
- Create: `integrations/claude-code/plugins/cortex-memory/scripts/session_start_hook.py`
- Create: `integrations/claude-code/plugins/cortex-memory/scripts/observation_hook.py`
- Create: `integrations/claude-code/plugins/cortex-memory/scripts/session_end_hook.py`

**Step 1: Implement session_start_hook.py**

Runs on SessionStart. Outputs context to stdout (Claude Code captures hook stdout).

```python
#!/usr/bin/env python3
"""SessionStart hook — loads Cortex context, flushes stale buffer."""
import asyncio
import json
import sys

async def main():
    # 1. Check for cortex-config.json
    # 2. If missing → output setup-needed message
    # 3. If present → flush stale buffer, load context from Cortex
    # 4. Output <cortex-context> block to stdout

if __name__ == "__main__":
    asyncio.run(main())
```

Key behaviors:
- 5 second total timeout for all Cortex calls
- Parallel HTTP calls (sessions, tasks, knowledge status)
- If Cortex unreachable → brief warning, continue
- If no config → output setup-needed instruction
- Flush stale buffer from previous crashed session

**Step 2: Implement observation_hook.py**

Runs on PostToolUse. Appends to local buffer. Must be fast (<50ms).

```python
#!/usr/bin/env python3
"""PostToolUse hook — append observation to local buffer."""
import json
import sys
import os
from datetime import datetime, timezone

def main():
    # Read hook input from stdin (Claude Code passes tool info)
    # Append minimal observation to .claude/cortex-memory-buffer.jsonl
    # No HTTP calls — local file append only

if __name__ == "__main__":
    main()
```

**Step 3: Implement session_end_hook.py**

Runs on Stop. Flushes buffer to Cortex.

```python
#!/usr/bin/env python3
"""Stop hook — flush observation buffer to Cortex."""
import asyncio

async def main():
    # 1. Load session tracker
    # 2. Generate session summary from observations
    # 3. Flush to Cortex API (POST /api/sessions)
    # 4. Clear buffer on success

if __name__ == "__main__":
    asyncio.run(main())
```

**Step 4: Commit**

```bash
git add integrations/claude-code/plugins/cortex-memory/scripts/
git commit -m "feat: add hook scripts for session lifecycle"
```

---

## Phase 5: Plugin Packaging & Distribution

### Task 18: Plugin Metadata Files

**Files:**
- Create: `integrations/claude-code/plugins/cortex-memory/.claude-plugin/plugin.json`
- Create: `integrations/claude-code/plugins/cortex-memory/.claude-plugin/CLAUDE.md`
- Create: `integrations/claude-code/plugins/cortex-memory/.mcp.json`
- Create: `integrations/claude-code/plugins/cortex-memory/hooks/hooks.json`

**Step 1: Write plugin.json**

```json
{
  "name": "cortex-memory",
  "version": "1.0.0",
  "description": "Smart code exploration, session memory, and Cortex integration for Claude Code",
  "author": "Cortex"
}
```

**Step 2: Write CLAUDE.md**

Plugin instructions injected into conversations. Include brief description of available tools (smart_search, smart_outline, smart_unfold) and session memory behavior.

**Step 3: Write .mcp.json**

```json
{
  "mcpServers": {
    "cortex-memory": {
      "type": "stdio",
      "command": "python3",
      "args": ["${CLAUDE_PLUGIN_ROOT}/src/mcp_server.py"]
    }
  }
}
```

**Step 4: Write hooks.json**

```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "startup|clear|compact",
        "hooks": [
          {
            "type": "command",
            "command": "python3 \"${CLAUDE_PLUGIN_ROOT}/scripts/session_start_hook.py\"",
            "timeout": 10
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "*",
        "hooks": [
          {
            "type": "command",
            "command": "python3 \"${CLAUDE_PLUGIN_ROOT}/scripts/observation_hook.py\"",
            "timeout": 5
          }
        ]
      }
    ],
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 \"${CLAUDE_PLUGIN_ROOT}/scripts/session_end_hook.py\"",
            "timeout": 30
          }
        ]
      }
    ]
  }
}
```

**Step 5: Commit**

```bash
git add integrations/claude-code/plugins/cortex-memory/
git commit -m "feat: add plugin metadata, MCP config, and hook definitions"
```

---

### Task 19: Plugin Skills

**Files:**
- Create: `integrations/claude-code/plugins/cortex-memory/skills/smart-explore/SKILL.md`
- Create: `integrations/claude-code/plugins/cortex-memory/skills/mem-search/SKILL.md`

**Step 1: Write smart-explore SKILL.md**

Adapted from claude-mem's smart-explore skill but referencing our Python MCP tools. Include the 3-layer workflow (search → outline → unfold), token economics table, and when-to-use-standard-tools guidance.

**Step 2: Write mem-search SKILL.md**

Instructions for searching Cortex session history. Reference the `cortex_search_sessions` and `cortex_get_session` MCP tools from the Cortex MCP server.

**Step 3: Commit**

```bash
git add integrations/claude-code/plugins/cortex-memory/skills/
git commit -m "feat: add smart-explore and mem-search skill definitions"
```

---

### Task 20: Plugin Distribution Endpoints

**Files:**
- Modify: `python/src/mcp_server/mcp_server.py` — add plugin serving endpoints

**Step 1: Add plugin manifest endpoint**

Add to `setup_routes()` in mcp_server.py:

```python
@routes.get("/cortex-setup/plugin-manifest")
async def plugin_manifest(request):
    """Return available plugins with versions."""
    # Read plugin.json from integrations/claude-code/plugins/cortex-memory/
    # Return JSON manifest

@routes.get("/cortex-setup/plugin/{name}.tar.gz")
async def download_plugin(request):
    """Return plugin as compressed archive."""
    # Create tar.gz of the plugin directory
    # Return as streaming response
```

**Step 2: Verify the integrations/ volume mount in docker-compose.yml includes plugins**

Check that `./integrations:/app/integrations` mount covers the plugins directory.

**Step 3: Test endpoints manually**

Run: `curl http://localhost:8051/cortex-setup/plugin-manifest`
Expected: JSON with cortex-memory plugin info

**Step 4: Commit**

```bash
git add python/src/mcp_server/mcp_server.py
git commit -m "feat: add plugin distribution endpoints to MCP server"
```

---

### Task 21: Setup Script Updates

**Files:**
- Modify: `integrations/claude-code/setup/cortexSetup.sh`
- Modify: `integrations/claude-code/setup/cortexSetup.bat`

**Step 1: Add install scope prompt to cortexSetup.sh**

After machine registration, add:
```bash
echo ""
echo "Where should Cortex tools be installed?"
echo ""
echo "  [1] This project only (recommended)"
echo "      Installed to .claude/ in your project root."
echo "      Customize per-project, changes stay isolated."
echo ""
echo "  [2] Global (all projects)"
echo "      Installed to ~/.claude/ in your home directory."
echo "      Same setup shared across all projects."
echo ""
read -p "Choice [1]: " install_scope
install_scope="${install_scope:-1}"

if [ "$install_scope" = "2" ]; then
    INSTALL_DIR="$HOME/.claude"
else
    INSTALL_DIR=".claude"
fi
```

**Step 2: Add claude-mem detection**

```bash
# Check for claude-mem
if [ -d "$HOME/.claude/plugins/cache/thedotmack/claude-mem" ] || [ -d ".claude/plugins/claude-mem" ]; then
    echo ""
    echo "Detected existing plugin: claude-mem"
    echo "The cortex-memory plugin replaces claude-mem with enhanced"
    echo "features and Cortex integration."
    echo ""
    echo "  [1] Remove claude-mem and install cortex-memory (recommended)"
    echo "  [2] Keep both (not recommended - duplicate hooks and tools)"
    echo "  [3] Skip plugin installation"
    echo ""
    read -p "Choice [1]: " claude_mem_choice
    claude_mem_choice="${claude_mem_choice:-1}"

    if [ "$claude_mem_choice" = "1" ]; then
        # Remove claude-mem plugin directory and MCP config
        rm -rf "$HOME/.claude/plugins/cache/thedotmack/claude-mem"
        # Clean MCP config references
    fi
fi
```

**Step 3: Add plugin download and install**

```bash
# Download and install cortex-memory plugin
echo "Installing cortex-memory plugin..."
mkdir -p "$INSTALL_DIR/plugins/cortex-memory"
curl -sL "${MCP_BASE_URL}/cortex-setup/plugin/cortex-memory.tar.gz" | \
    tar xz -C "$INSTALL_DIR/plugins/cortex-memory/"

# Install Python dependencies
if command -v uv &> /dev/null; then
    uv pip install --target "$INSTALL_DIR/plugins/cortex-memory/vendor" \
        -r "$INSTALL_DIR/plugins/cortex-memory/requirements.txt"
else
    pip install --target "$INSTALL_DIR/plugins/cortex-memory/vendor" \
        -r "$INSTALL_DIR/plugins/cortex-memory/requirements.txt"
fi
```

**Step 4: Add cortex-config.json writing**

```bash
# Write cortex-config.json
cat > "$INSTALL_DIR/cortex-config.json" << CONFIGEOF
{
  "cortex_api_url": "$API_BASE_URL",
  "cortex_mcp_url": "$MCP_BASE_URL",
  "project_id": "$project_id",
  "project_title": "$project_title",
  "machine_id": "$machine_fingerprint",
  "install_scope": "$install_scope",
  "installed_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
CONFIGEOF
```

**Step 5: Add gitignore updates**

```bash
# Add to .gitignore if not already present
for entry in ".claude/plugins/" ".claude/skills/" ".claude/cortex-config.json" ".claude/cortex-memory-buffer.jsonl"; do
    grep -qxF "$entry" .gitignore 2>/dev/null || echo "$entry" >> .gitignore
done
```

**Step 6: Apply equivalent changes to cortexSetup.bat**

Mirror all the above steps in Windows batch script syntax.

**Step 7: Commit**

```bash
git add integrations/claude-code/setup/
git commit -m "feat: extend setup scripts with plugin install, scope choice, claude-mem detection"
```

---

## Phase 6: Integration & Cleanup

### Task 22: Remove claude-mem from Cortex Repo

**Files:**
- Check and clean: Any claude-mem references in `.claude/` config files
- Check and clean: Any `<claude-mem-context>` artifacts in CLAUDE.md files

**Step 1: Search for claude-mem references**

```bash
grep -r "claude-mem" --include="*.json" --include="*.md" --include="*.yml" .
```

Remove any configuration entries, plugin references, or context artifacts found.

**Step 2: Verify no claude-mem hooks are active**

Check `~/.claude/plugins/` and project `.claude/` for any remaining claude-mem files.

**Step 3: Commit**

```bash
git add -A
git commit -m "chore: remove claude-mem references from Cortex repo"
```

---

### Task 23: Update Existing Extension Content

**Files:**
- Modify: `integrations/claude-code/extensions/cortex-extension-sync/SKILL.md`
- Modify: `integrations/claude-code/extensions/cortex-bootstrap/SKILL.md`

**Step 1: Update cortex-extension-sync SKILL.md**

- Rename references from "skills" to "extensions"
- Update MCP tool calls: `find_extensions`, `manage_extensions`
- Update description in frontmatter

**Step 2: Update cortex-bootstrap SKILL.md**

- Update references to use "extensions" terminology
- Update the extension sync reference

**Step 3: Commit**

```bash
git add integrations/claude-code/extensions/
git commit -m "docs: update existing extension SKILL.md files with new naming"
```

---

### Task 24: Register Plugin in Extensions Registry

**Step 1: Add cortex-memory plugin to the seeding service**

The `ExtensionSeedingService` reads SKILL.md files from the extensions directory. Update it to also detect and seed plugin entries from the plugins directory.

Modify `extension_seeding_service.py`:
- Add a `seed_plugins()` method that reads `integrations/claude-code/plugins/*/` directories
- For each plugin, read `plugin.json` for metadata and create an extension entry with `type="plugin"` and `plugin_manifest` populated
- Call `seed_plugins()` alongside `seed_extensions()` in the main seed method

**Step 2: Run tests**

Run: `cd python && uv run pytest -v`
Expected: All pass

**Step 3: Commit**

```bash
git add python/src/server/services/extensions/extension_seeding_service.py
git commit -m "feat: seed plugins into extensions registry alongside skills"
```

---

### Task 25: End-to-End Verification

**Step 1: Run full backend test suite**

Run: `cd python && uv run pytest -v`
Expected: All pass

**Step 2: Run frontend type check and lint**

Run: `cd cortex-ui && npx tsc --noEmit && npm run biome && npm run lint`
Expected: Clean

**Step 3: Run Docker build**

Run: `docker compose build`
Expected: All images build successfully

**Step 4: Start stack and test setup flow**

Run: `docker compose up -d`

Test:
1. Verify MCP server health: `curl http://localhost:8051/health`
2. Verify plugin manifest: `curl http://localhost:8051/cortex-setup/plugin-manifest`
3. Verify plugin download: `curl -o /dev/null -w "%{http_code}" http://localhost:8051/cortex-setup/plugin/cortex-memory.tar.gz`
4. Run setup script in a test project directory
5. Verify plugin installed to `.claude/plugins/cortex-memory/`
6. Verify cortex-config.json written
7. Test smart_search on a local codebase

**Step 5: Commit any fixes**

---

### Task 26: Update Documentation

**Files:**
- Modify: `CLAUDE.md` — update MCP tools section from skills to extensions
- Modify: `PRPs/ai_docs/ARCHITECTURE.md` — update references
- Modify: `~/.claude/projects/-home-winadmin-projects-cortex/memory/MEMORY.md` — update active work section

**Step 1: Update CLAUDE.md**

- MCP Tools section: rename skill tools to extension tools
- Development commands: update any skill-related commands
- Common tasks: update "Add or modify MCP tools" section

**Step 2: Update MEMORY.md**

Update the active work section to reflect:
- Skills renamed to Extensions
- cortex-memory plugin built
- Session memory backend added
- claude-mem removed

**Step 3: Commit**

```bash
git add CLAUDE.md PRPs/ai_docs/ARCHITECTURE.md
git commit -m "docs: update documentation for extensions rename and cortex-memory plugin"
```

---

## Task Dependency Graph

```
Phase 1 (Extensions Rename):
  T1 (DB migration) → T2 (services) → T3 (API) → T4 (MCP) → T5 (frontend) → T6 (tests) → T7 (integrations dir)

Phase 2 (Session Backend):      [can start after T1]
  T8 (DB migration) → T9 (service) → T10 (API) → T11 (MCP tools)

Phase 3 (Smart Explore):        [can start immediately, no dependencies]
  T12 (parser) → T13 (search) → T14 (MCP server)

Phase 4 (Plugin Hooks):         [depends on Phase 2 + Phase 3]
  T15 (cortex client) → T16 (session tracker) → T17 (hooks)

Phase 5 (Packaging):            [depends on Phase 4]
  T18 (metadata) → T19 (skills) → T20 (distribution) → T21 (setup scripts)

Phase 6 (Cleanup):              [depends on all]
  T22 (remove claude-mem) → T23 (update extensions) → T24 (registry) → T25 (e2e) → T26 (docs)
```

**Parallelization opportunities:**
- Phase 1 and Phase 3 can run in parallel (rename vs plugin core)
- Phase 2 can start after T1 completes (needs renamed tables)
- Within Phase 1, T2-T4 (backend) and T5 (frontend) can run in parallel after T1
