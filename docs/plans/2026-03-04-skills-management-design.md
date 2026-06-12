# Skills Management System — Design Document

**Date:** 2026-03-04
**Status:** Approved

## Overview

A system for managing Claude Code skills across machines and projects through Cortex. Skills originate locally from users, sync up to a central Cortex registry, and can be distributed to other systems via a pull model. The Cortex UI gains a "Skills" tab in the project view showing registered systems and their skill states, with the ability to queue installs remotely.

## Goals

1. **Centralize skill distribution** — Cortex becomes the canonical registry for skills across all connected systems
2. **Detect drift** — On startup, compare local skills against Cortex and surface conflicts with clear resolution options
3. **Enable remote management** — From the Cortex UI, queue skill installs/removals that systems pick up on next sync
4. **Build the library organically** — Users create skills locally; uploading to Cortex grows the shared library
5. **Validate quality** — Skills pass a cleanup/validation process before being distributed

## Key Design Decisions

- **Pull model** — Systems check for pending actions on sync rather than Cortex pushing to clients
- **Machine fingerprint** — Systems identified by SHA256(hostname | username | OS) rather than MAC address; more portable
- **Claude Code SKILL.md format** — All skills are standard SKILL.md files with YAML frontmatter
- **Lazy sync trigger** — Every Cortex skill checks sync freshness in Phase 0; if stale (>24h), runs sync first
- **Skills originate locally** — Users create skills in their projects; Cortex is the registry they sync up to, not just down from
- **Full DB registry (Approach A)** — Skill content + metadata stored in database for maximum flexibility

## Architecture

### Approach Chosen: Full DB Registry

Skills content and metadata live in the database. This supports:
- Distributing skills to systems that don't have the Cortex repo cloned
- Version history with rollback capability
- Project-specific overrides without forking the canonical skill
- Future custom skills upload via Cortex UI

Alternatives considered:
- **File-based registry** — Skills only in git, DB tracks assignments. Simpler but can't serve skills without repo access.
- **Hybrid DB + git** — Metadata in DB, content seeded from git. Two-source-of-truth risk.

---

## Database Schema

### `cortex_skills` — Central skill registry

```sql
CREATE TABLE cortex_skills (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL UNIQUE,           -- Kebab-case from SKILL.md frontmatter (e.g. "cortex-memory")
  display_name TEXT NOT NULL,          -- Human-friendly (e.g. "Cortex Memory")
  description TEXT DEFAULT '',         -- From frontmatter description field
  content TEXT NOT NULL,               -- Full SKILL.md content
  content_hash TEXT NOT NULL,          -- SHA256 of content for drift detection
  version INTEGER DEFAULT 1,
  is_required BOOLEAN DEFAULT false,   -- Required skills auto-install on system registration
  is_validated BOOLEAN DEFAULT false,  -- Passed cleanup/validation process
  tags TEXT[] DEFAULT '{}',
  created_by_system_id UUID REFERENCES cortex_systems(id),
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

### `cortex_skill_versions` — Version history

```sql
CREATE TABLE cortex_skill_versions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  skill_id UUID NOT NULL REFERENCES cortex_skills(id) ON DELETE CASCADE,
  version INTEGER NOT NULL,
  content TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  change_summary TEXT,
  created_by_system_id UUID REFERENCES cortex_systems(id),
  created_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(skill_id, version)
);
```

### `cortex_project_skills` — Project-specific overrides

```sql
CREATE TABLE cortex_project_skills (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID NOT NULL REFERENCES cortex_projects(id) ON DELETE CASCADE,
  skill_id UUID NOT NULL REFERENCES cortex_skills(id) ON DELETE CASCADE,
  content_override TEXT,               -- NULL = use canonical; non-null = project variant
  content_hash TEXT,                   -- Hash of override content
  override_version INTEGER DEFAULT 1,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(project_id, skill_id)
);
```

### `cortex_systems` — Registered machines

```sql
CREATE TABLE cortex_systems (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  fingerprint TEXT NOT NULL UNIQUE,    -- SHA256(hostname | username | os)
  name TEXT NOT NULL,                  -- User-provided friendly name
  hostname TEXT,                       -- Raw hostname for display
  os TEXT,                             -- OS identifier
  last_seen_at TIMESTAMPTZ DEFAULT NOW(),
  created_at TIMESTAMPTZ DEFAULT NOW()
);
```

### `cortex_system_skills` — What's installed where

```sql
CREATE TABLE cortex_system_skills (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  system_id UUID NOT NULL REFERENCES cortex_systems(id) ON DELETE CASCADE,
  skill_id UUID NOT NULL REFERENCES cortex_skills(id) ON DELETE CASCADE,
  project_id UUID NOT NULL REFERENCES cortex_projects(id) ON DELETE CASCADE,
  status TEXT NOT NULL DEFAULT 'pending_install',  -- pending_install | installed | pending_remove | removed
  installed_content_hash TEXT,          -- Hash of what's actually on disk
  installed_version INTEGER,
  has_local_changes BOOLEAN DEFAULT false,
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(system_id, skill_id, project_id)
);
```

### Schema design notes

- `content_hash` on every content-bearing table enables drift detection by comparing local file hash vs DB hash
- `cortex_skill_versions` preserves full history so updates never destroy previous content
- `cortex_project_skills.content_override` allows project-specific variants without forking the canonical skill
- `has_local_changes` flags when sync detects a local modification that doesn't match Cortex
- `is_validated` tracks whether a skill has passed the cleanup process
- `created_by_system_id` provides attribution for who contributed the skill

---

## Sync Flow (Startup)

### Trigger: Lazy sync in Phase 0

Every Cortex skill's Phase 0 (health check) includes a sync freshness check:

```
Read .claude/cortex-state.json
If last_skill_sync is missing or older than 24 hours:
  → Run skill sync flow before continuing
  → Update last_skill_sync timestamp
Else:
  → Continue with the skill normally
```

### Sync flow steps

```
Step 1: Compute fingerprint
  SHA256(hostname | username | os)

Step 2: Scan local skills
  Glob: .claude/skills/**/*.md + integrations/claude-code/skills/**/SKILL.md
  For each: parse frontmatter name, compute content SHA256
  Build local_skills list: [{name, content_hash}]

Step 3: Call manage_skills(action="sync")
  Send: fingerprint, system_name (if first time), project_id, local_skills
  Receive: sync report

Step 4: Handle pending installs
  For each pending_install: write SKILL.md to local skills directory
  Report: "Installed 2 new skills: code-reviewer, test-runner"

Step 5: Handle pending removals
  For each pending_remove: delete local SKILL.md
  Report: "Removed 1 skill: deprecated-tool"

Step 6: Handle local changes (interactive — ask user)
  For each changed skill:
    1. Update Source       → Push local content as new version of canonical skill
    2. Save Project Version → Store as project-specific override (canonical unchanged)
    3. Create New Skill    → Upload as new skill with new name (runs validation first)
    4. Discard Changes     → Overwrite local with Cortex canonical version

Step 7: Handle unknown local skills (interactive — ask user)
  For each skill not in Cortex:
    1. Upload to Cortex → Validate + upload
    2. Skip             → Leave as local-only, not tracked

Step 8: Update state file
  Write last_skill_sync timestamp to .claude/cortex-state.json

Step 9: Summary
  "Skill sync complete: 4 in sync, 1 updated, 2 installed, 1 uploaded"
```

### First-time system registration

Happens in Step 3. If the MCP server doesn't recognize the fingerprint, the sync response includes `"is_new": true`. The sync skill prompts the user for a system name, then re-calls with `system_name` set.

---

## Skill Cleanup / Validation Process

When a user uploads a new skill to Cortex or updates the source, it runs through validation before being marked `is_validated=true`.

### Validation checks

| Check | What it verifies | Severity |
|-------|-----------------|----------|
| Frontmatter present | YAML frontmatter with `name` and `description` fields | Error |
| Name format | Kebab-case, alphanumeric + hyphens only | Error |
| Name uniqueness | No existing skill with same name (unless updating) | Error |
| Description quality | Non-empty, >= 20 chars, includes trigger phrases | Warning |
| Content structure | Has at least one `## ` heading | Warning |
| Tool references valid | MCP tool names match known registered tools | Warning |
| No hardcoded paths | No absolute paths like `/home/user/...` | Warning |
| No secrets | No patterns matching API keys, tokens, passwords | Error |
| Size limit | Content under 50KB | Error |

### Severity levels

- **Error** — blocks the upload; must be fixed
- **Warning** — reported to user but allows upload; user can fix or proceed

### Validation response format

```json
{
  "valid": true,
  "errors": [],
  "warnings": [
    {
      "check": "description_quality",
      "message": "Description is short (23 chars). Consider adding trigger phrases."
    }
  ],
  "parsed": {
    "name": "my-custom-skill",
    "description": "Does something useful",
    "heading_count": 4,
    "estimated_phases": 3
  }
}
```

### MCP tool reference checking

If a referenced MCP tool is not recognized, the validation flags it as a warning: "Tool `X` is not yet cataloged in Cortex." Full MCP tool cataloging is deferred to a future phase.

---

## MCP Tools

Two new consolidated tools following the existing `find_*` / `manage_*` pattern.

### `find_skills`

```
find_skills(
    skill_id?: string,           -- Get specific skill by ID
    query?: string,              -- Search by name/description
    project_id?: string,         -- Skills assigned to a project
    system_id?: string,          -- Skills installed on a system
    status?: string,             -- Filter by install status
    include_content?: bool,      -- Include full SKILL.md content (default false for lists)
)
```

### `manage_skills`

```
manage_skills(
    action: string,              -- "sync" | "upload" | "install" | "remove" | "validate"

    -- For sync:
    local_skills?: list[{name, content_hash, content?}],
    system_fingerprint?: string,
    system_name?: string,
    project_id?: string,

    -- For upload/validate:
    skill_content?: string,
    skill_name?: string,

    -- For install/remove:
    skill_id?: string,
    system_id?: string,
    project_id?: string,
)
```

### Action summary

| Action | Caller | Purpose |
|--------|--------|---------|
| `sync` | Auto-sync skill at startup | Register system, compare hashes, return pending actions + drift report |
| `upload` | User via conflict resolution | Run validation, create/update skill in DB, save version history |
| `validate` | Pre-upload check | Run cleanup validation, return report without saving |
| `install` | Cortex UI or sync skill | Set `pending_install` or write file and mark `installed` |
| `remove` | Cortex UI or user | Set `pending_remove` or delete file and mark `removed` |

### Sync response example

```json
{
  "success": true,
  "system": {"id": "uuid", "name": "Jason's MacBook", "is_new": false},
  "in_sync": ["cortex-memory", "cortex-link-project"],
  "local_changes": [
    {"name": "my-custom-tool", "local_hash": "abc...", "cortex_hash": "def..."}
  ],
  "pending_install": [
    {"skill_id": "uuid", "name": "code-reviewer", "content": "...full SKILL.md..."}
  ],
  "pending_remove": [],
  "unknown_local": [
    {"name": "experimental-skill", "content_hash": "ghi..."}
  ]
}
```

---

## Backend API Endpoints

### Skills CRUD

```
GET    /api/skills                          -- List all skills in registry
GET    /api/skills/{skill_id}               -- Get skill with full content
POST   /api/skills                          -- Create skill
PUT    /api/skills/{skill_id}               -- Update skill (bumps version)
DELETE /api/skills/{skill_id}               -- Remove from registry
POST   /api/skills/{skill_id}/validate      -- Run validation without saving
GET    /api/skills/{skill_id}/versions      -- Version history
```

### Systems

```
GET    /api/systems                          -- List all registered systems
GET    /api/systems/{system_id}              -- System details
PUT    /api/systems/{system_id}              -- Update system name
DELETE /api/systems/{system_id}              -- Unregister system
```

### Project-scoped (for Skills tab)

```
GET    /api/projects/{project_id}/skills                    -- Skills + install state per system
GET    /api/projects/{project_id}/systems                   -- Systems registered to project
POST   /api/projects/{project_id}/skills/{skill_id}/install -- Queue install on selected systems
POST   /api/projects/{project_id}/skills/{skill_id}/remove  -- Queue removal on selected systems
PUT    /api/projects/{project_id}/skills/{skill_id}         -- Save project-specific override
```

Install/remove endpoints accept target system IDs:
```json
{"system_ids": ["uuid-1", "uuid-2"]}
```

### Service layer

```
python/src/server/services/skills/
├── __init__.py
├── skill_service.py              -- CRUD + version management + content hashing
├── skill_validation_service.py   -- Cleanup checks
├── system_service.py             -- Fingerprint matching + registration
└── skill_sync_service.py         -- Hash comparison + pending action resolution
```

### API route file

```
python/src/server/api_routes/skills_api.py
```

---

## Frontend — Skills Tab

### File structure

```
cortex-ui/src/features/projects/skills/
├── SkillsTab.tsx                     -- Entry point
├── components/
│   ├── SystemCard.tsx                -- Registered system card
│   ├── SystemSkillList.tsx           -- Skills on a system with status badges
│   ├── SkillStatusBadge.tsx          -- installed | pending_install | pending_remove | local_changes
│   ├── AvailableSkillsModal.tsx      -- Skill picker for installation
│   └── SkillDetailPanel.tsx          -- Right-side inspector
├── hooks/
│   └── useSkillQueries.ts           -- Query key factory + hooks + mutations
├── services/
│   └── skillService.ts              -- API client
└── types/
    └── index.ts                     -- Skill, System, SystemSkill types
```

### Layout

Two-level drill-down: systems list on left, detail panel on right.

```
┌──────────────────────┬──────────────────────────────────────┐
│  SYSTEMS             │  DETAIL PANEL                        │
│                      │                                      │
│  ┌────────────────┐  │  System: Jason's MacBook             │
│  │ Jason's MacBook │◄─│  Last seen: 2 min ago               │
│  │ 4 skills       │  │  Fingerprint: a3f2...               │
│  │ ● online       │  │                                      │
│  └────────────────┘  │  INSTALLED SKILLS                    │
│                      │  ┌──────────────────────────────┐    │
│  ┌────────────────┐  │  │ cortex-memory      installed  │   │
│  │ CI Server      │  │  │ cortex-link-project installed  │   │
│  │ 2 skills       │  │  │ code-reviewer   pending_install│   │
│  │ ○ offline      │  │  │ my-custom-tool  local_changes  │   │
│  └────────────────┘  │  └──────────────────────────────┘    │
│                      │                                      │
│  [+ Install Skills]  │  AVAILABLE (not installed)           │
│                      │  ┌──────────────────────────────┐    │
│                      │  │ test-runner         [Install]  │   │
│                      │  │ db-migration-helper  [Install]  │  │
│                      │  └──────────────────────────────┘    │
└──────────────────────┴──────────────────────────────────────┘
```

### Integration into ProjectsView.tsx

Add to PillNavigation items (between Knowledge and Tasks):
```typescript
{ id: "skills", label: "Skills", icon: <Puzzle className="w-4 h-4" /> }
```

Add conditional rendering:
```typescript
{activeTab === "skills" && <SkillsTab projectId={selectedProject.id} />}
```

Update both layout modes (horizontal and sidebar) in ProjectsView.tsx.

### Key interactions

- Selecting a system shows its installed + available skills
- "Install" button queues `pending_install` in DB
- Status badges: green (installed), yellow (pending_install), red (pending_remove), orange (local_changes)
- Online indicator: `last_seen_at` within last 5 minutes

---

## Auto-Sync Skill

### Location

`integrations/claude-code/skills/cortex-skill-sync/SKILL.md`

### Invocation

- **Manual:** `/cortex-skill-sync`
- **Automatic:** Triggered by sync freshness check in other Cortex skills' Phase 0

### Updates to existing skills

All existing Cortex skills (cortex-memory, cortex-link-project) get an additional check in Phase 0:

```
Read .claude/cortex-state.json
If last_skill_sync is missing or older than 24h:
  → Run /cortex-skill-sync before continuing
```

---

## Complete Component Inventory

### Database (5 new tables)

| Table | Purpose |
|-------|---------|
| `cortex_skills` | Canonical skill registry |
| `cortex_skill_versions` | Version history per skill |
| `cortex_project_skills` | Project-specific overrides |
| `cortex_systems` | Registered machines |
| `cortex_system_skills` | Install state junction |

### Backend (5 new files)

| File | Purpose |
|------|---------|
| `skills_api.py` | REST endpoints |
| `skill_service.py` | CRUD + versioning |
| `skill_validation_service.py` | Cleanup checks |
| `system_service.py` | Fingerprint + registration |
| `skill_sync_service.py` | Hash comparison + sync logic |

### MCP (2 new tools)

| Tool | Purpose |
|------|---------|
| `find_skills` | Query skills by project/system/status |
| `manage_skills` | sync, upload, validate, install, remove |

### Frontend (8 new files)

| File | Purpose |
|------|---------|
| `SkillsTab.tsx` | Tab entry point |
| `SystemCard.tsx` | System display |
| `SystemSkillList.tsx` | Skill list per system |
| `SkillStatusBadge.tsx` | Status indicator |
| `AvailableSkillsModal.tsx` | Install picker |
| `SkillDetailPanel.tsx` | Right-side inspector |
| `useSkillQueries.ts` | TanStack Query hooks |
| `skillService.ts` | API client |

### Skills (1 new, 2 updated)

| Skill | Change |
|-------|--------|
| `cortex-skill-sync` | NEW — full sync flow |
| `cortex-memory` | Add sync freshness check to Phase 0 |
| `cortex-link-project` | Add sync freshness check to Phase 0 |

---

## Future Phases (Out of Scope)

- **MCP tool cataloging** — Catalog known MCP tools so validation can check tool references authoritatively
- **Skill sets / groups** — Batch deploy multiple skills together
- **Custom skills upload via Cortex UI** — API already supports it; UI form deferred
- **Diff viewer** — Show local vs Cortex content diff for `local_changes` status in Skills tab
- **Skill marketplace** — Browse and install community-contributed skills
