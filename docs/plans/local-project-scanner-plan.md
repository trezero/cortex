# Local Project Scanner — Feature Plan (v1: CLI-First)

## Overview

The **Local Project Scanner** enables a user to point Cortex at a directory on their local filesystem (e.g. `~/projects/`), automatically discover all Git/GitHub repositories within it, and **bulk-run the equivalent of `/cortex-setup`** for every discovered project. This eliminates the need to open each project individually and run setup manually.

**v1 Scope**: Claude Code CLI flow via MCP tools. Web UI deferred to [local-project-scanner-web-plan.md](./local-project-scanner-web-plan.md).

**Expected Usage**: Most users will run this once per system to onboard all their existing projects into Cortex.

---

## Problem Statement

Users with many local projects (10, 50, 100+) currently must:
1. Open Claude Code in each project directory
2. Run `/cortex-setup` manually in each one
3. Wait for each setup to complete before moving to the next

For a user with 50 projects, this could take hours of manual work. The Local Project Scanner automates this by scanning a directory tree, detecting repositories, and running the equivalent of `/cortex-setup` for all of them in a single batch operation.

---

## What the Scanner Replicates

The scanner produces the same end state as if the user ran `/cortex-setup` in each discovered project. Per project, this means:

### Per-Project Operations (from cortex-setup)

| Operation | How Scanner Implements It |
|-----------|--------------------------|
| Create Cortex project in DB | `ProjectService.create_project(title, github_repo, tags, metadata)` — includes dependencies in metadata, infra markers in tags |
| Register system for project | `POST /api/projects/{project_id}/sync` with system fingerprint |
| Write `.claude/cortex-config.json` | Backend writes to mounted volume at project path |
| Write `.claude/cortex-state.json` | Backend writes to mounted volume at project path |
| Write `.claude/settings.local.json` | Backend writes PostToolUse hook config |
| Install extensions to `.claude/skills/` | Extract cached tarball into project's `.claude/skills/` |
| Update `.gitignore` | Backend appends Cortex entries if not present |
| Ingest local README to knowledge base | Store full README as document with embeddings — immediate searchable knowledge |
| Crawl GitHub README as knowledge source | `POST /api/knowledge-items/crawl` with `project_id` (supplements local copy) |
| Generate AI description | Claude Code generates from README content (see AI Description section) |

### Per-Project Extension Installation

Extensions are installed **per-project** (into each project's `.claude/skills/`), not globally. This is intentional — extensions frequently need project-specific customizations, and global installs create conflicts when different projects need different extension versions.

| Operation | How Scanner Implements It |
|-----------|--------------------------|
| Download extensions tarball | Fetch from `{cortex_mcp_url}/cortex-setup/extensions.tar.gz` |
| Extract to `.claude/skills/` | Write to project's `.claude/skills/` via mounted volume |

The tarball is downloaded **once** and cached in the scanner's working directory, then extracted into each project. This avoids redundant network requests.

### One-Time Prerequisites

These must already be done before the scanner can run:
- System registration (fingerprint, system name, hostname)
- Global MCP endpoint configuration (`claude mcp add cortex`)
- Global hook registration (SessionStart, Stop hooks in `~/.claude/settings.json`)
- Cortex-memory plugin installation (global — shared across projects)

**Prerequisite check**: Before scanning, the scanner verifies the system is already registered by checking for a valid system fingerprint. If not found, it directs the user to run `/cortex-setup` in any single project first.

---

## Architecture

### System Flow (v1: CLI via MCP Tools)

```
┌──────────────┐    MCP tool call     ┌──────────────────┐
│  Claude Code │ ──────────────────→  │  Cortex MCP      │
│  (any dir)   │                      │  (Docker)        │
└──────┬───────┘                      └────────┬─────────┘
       │                                       │
       │  scan_local_projects()                │ HTTP call
       │                                       ▼
       │                              ┌──────────────────┐
       │                              │  Scanner API     │
       │                              │  (cortex-server) │
       │                              └────────┬─────────┘
       │                                       │
       │  Returns scan results                 │ Scans mounted volume
       │  with README content                  │ /projects/ → host ~/projects/
       │◄──────────────────────────────────────┘
       │
       │  Claude Code generates descriptions
       │  from README content (optional)
       │
       │  apply_scan_template()        ┌──────────────────┐
       │ ─────────────────────────────→│  Scanner API     │
       │                               └────────┬─────────┘
       │                                        │
       │  Poll progress                         ▼
       │◄──────────────────    ┌────────────────────────────┐
       │                       │  For each selected project: │
       │                       │  1. Create Cortex project   │
       │                       │  2. Register system         │
       │                       │  3. Write config files      │
       │                       │  4. Update .gitignore       │
       │                       │  5. Start README crawl      │
       │                       └────────────────────────────┘
```

### Filesystem Access: Docker Volume Mount

The scanner backend reads AND writes to project directories via a Docker bind mount. The user configures this once in their `.env` file.

**Docker Compose addition:**
```yaml
cortex-server:
  volumes:
    - ./python/src:/app/src
    # ... existing mounts ...
    - ${PROJECTS_DIRECTORY:-~/projects}:/projects:rw   # Scanner mount
  environment:
    - SCANNER_PROJECTS_ROOT=/projects   # Container-side path
```

**`.env` addition:**
```bash
# Local Project Scanner — path to your projects directory on the host
PROJECTS_DIRECTORY=~/projects
```

The backend always operates on `/projects/` inside the container, which maps to the user's actual projects directory on the host.

### Where Does the User Run Claude Code?

The user runs Claude Code from **any project that already has Cortex MCP configured**, or from **any directory** if Cortex MCP is configured globally. The scanner MCP tools are API calls to the Cortex backend — Claude Code's working directory is irrelevant for scanning.

The user does NOT need to:
- Be in the projects directory (Claude Code would try to index everything)
- Create a dedicated repo for scanning
- Have any special local setup beyond Cortex MCP access

---

## Smart Depth: Project Group Detection

### The Problem

Users often organize related projects under a parent directory:
```
~/projects/
├── standalone-app/              # Direct git repo (depth 1)
├── another-project/             # Direct git repo (depth 1)
├── RecipeRaiders_Complete/      # NOT a git repo — project group
│   ├── RecipeRaiders/           # Git repo (depth 2)
│   ├── reciperaiders-dashboard/ # Git repo (depth 2)
│   ├── reciperaiders-repdash/   # Git repo (depth 2)
│   ├── reciperaiders-spa/       # Git repo (depth 2)
│   └── SEOMarketingAutomation/  # Git repo (depth 2)
└── node_modules/                # NOT a git repo, no git children — skip
```

### Smart Recurse Algorithm

Rather than arbitrary configurable depth, the scanner uses a **smart two-pass approach**:

1. **Pass 1**: Scan immediate children of the target directory
   - If child has `.git/` → add as detected project
   - If child does NOT have `.git/` → mark as potential project group

2. **Pass 2**: For each potential project group, scan ITS immediate children
   - If any child has `.git/` → the parent is a **project group**
   - Add all git repos found as detected projects, tagged with `group_name`
   - If no children have `.git/` → skip the directory entirely

3. **Never recurse deeper than 2 levels** (hardcoded safety limit)

### Project Group → Parent Project Hierarchy

When a project group is detected:
- **Template option** `create_group_parents: bool = True`
- If enabled: Create a parent Cortex project for the group (e.g. "RecipeRaiders_Complete") with no `github_repo`, and create child projects with `parent_project_id` set
- If disabled: Create all repos as top-level projects, tagged with group name

This integrates with the existing `parent_project_id` single-level hierarchy in the project model.

### Skip List

The scanner automatically skips directories matching common non-project patterns:
```python
SKIP_DIRS = {
    "node_modules", ".git", "__pycache__", ".venv", "venv",
    ".cache", ".npm", ".nvm", "dist", "build", ".tox",
    "vendor", "target", ".gradle", "Pods",
}
```

---

## AI Description Generation

### Flow (v1: Claude Code as the AI)

Since this is CLI-first, Claude Code itself generates descriptions. No additional AI provider configuration needed.

1. **During scan**: The scanner reads `README.md` content (first 5000 chars) for each detected project and includes it in the scan results
2. **After scan results return**: Claude Code receives the scan results including README content
3. **Before apply**: Claude Code generates a concise 1-2 sentence project description for each project based on the README
4. **During apply**: Descriptions are passed in the apply request and stored on the created projects

### MCP Tool Design for Description Generation

The `scan_local_projects` tool returns README content so Claude Code can generate descriptions:

```python
# scan_local_projects returns:
{
    "projects": [
        {
            "directory_name": "RecipeRaiders",
            "github_url": "https://github.com/user/RecipeRaiders",
            "readme_content": "# RecipeRaiders\nA recipe sharing platform...",
            # ... other metadata
        }
    ]
}
```

The `apply_scan_template` tool accepts descriptions:

```python
# apply_scan_template receives:
{
    "scan_id": "uuid",
    "template": {...},
    "descriptions": {
        "RecipeRaiders": "A recipe sharing platform with social features and meal planning",
        "reciperaiders-dashboard": "Admin dashboard for RecipeRaiders content moderation"
    }
}
```

### Verification Before Apply

Before starting the apply phase, Claude Code should confirm with the user:
- Show the list of projects with generated descriptions
- Allow the user to edit/approve descriptions
- Only proceed when the user confirms

---

## Dependency & Infrastructure Capture

### Why Capture This During Scan

The scanner has **one-time filesystem access** to every project via the Docker volume mount. A future conversational AI interface in Cortex will need cross-project context: "which projects use React?", "how do my RecipeRaiders projects relate?", "which projects have Docker deployments?". Capturing dependency and infrastructure data now — while we have filesystem access — avoids expensive re-scanning later.

### Dependency Extraction

During scan, the git detector reads dependency names (not versions) from manifest files:

| File | Ecosystem | What to Extract |
|------|-----------|-----------------|
| `package.json` | npm | `dependencies` + `devDependencies` keys |
| `pyproject.toml` | pip | `[project.dependencies]` package names |
| `requirements.txt` | pip | Package names (strip version specifiers) |
| `Cargo.toml` | cargo | `[dependencies]` keys |
| `go.mod` | go | `require` block module paths |
| `pom.xml` | maven | `<artifactId>` values from `<dependencies>` |
| `build.gradle` | gradle | `implementation`/`api` dependency strings |

**Storage format** (JSONB on `cortex_scan_projects`):
```json
{
    "npm": ["react", "next", "tailwindcss", "@tanstack/react-query"],
    "pip": ["fastapi", "pydantic", "supabase"]
}
```

Only top-level dependency names are captured — no versions, no transitive dependencies. This keeps the scan fast while providing enough signal for cross-project analysis.

### Infrastructure Markers

The scanner checks for the **existence** of infrastructure-revealing files and directories (no content reading — just `os.path.exists()`):

```python
INFRA_MARKERS = {
    "docker-compose.yml": "docker",
    "docker-compose.yaml": "docker",
    "Dockerfile": "docker",
    ".github/workflows": "github-actions",
    ".gitlab-ci.yml": "gitlab-ci",
    "firebase.json": "firebase",
    ".firebaserc": "firebase",
    "vercel.json": "vercel",
    "netlify.toml": "netlify",
    "serverless.yml": "serverless",
    "terraform": "terraform",
    "k8s": "kubernetes",
    "Makefile": "make",
    ".env.example": "env-config",
    "supabase": "supabase",
    "prisma": "prisma",
    ".github/dependabot.yml": "dependabot",
}
```

**Storage**: `infra_markers TEXT[]` on `cortex_scan_projects`. Persisted to project `tags` alongside language tags during apply.

### Persisting to Projects After Apply

When a project is created during apply, the scanner persists captured data to the Cortex project record:
- `dependencies` → stored in the project's `metadata` JSONB field under key `"dependencies"`
- `infra_markers` → merged into the project's `tags` array alongside language tags
- `group_name` → stored in `metadata` under key `"project_group"` (preserves the relationship even for non-hierarchical setups)

This ensures the data survives scan expiration and is queryable through the standard project API.

### Local README as Knowledge Document

In addition to the GitHub README crawl (which may fail for private repos), the scanner **directly stores the local README** content as a document in the Cortex knowledge base during apply:

1. Read full `README.md` from the mounted volume (already captured during scan)
2. Create a document via `DocumentService` with:
   - `source`: project directory name
   - `content`: full README text
   - `metadata`: `{"origin": "scanner", "file": "README.md"}`
3. Generate embeddings for the document
4. Link to the project via `source_linking`

This provides immediate searchable knowledge for every project — no crawl delay, works for private repos, and ensures the conversational AI has context for every scanned project from the moment the scan completes.

---

## Duplicate Prevention

### During Scan: Existing Project Detection

Match **only on normalized `github_url`**:
1. Fetch all existing Cortex projects with non-null `github_repo`
2. Normalize URLs: strip `.git` suffix, normalize to `https://github.com/{owner}/{repo}` format
3. Compare against each detected project's normalized URL
4. Mark matches as `already_in_cortex: true` with `existing_project_id`

**For repos with no remote**: Never mark as "already in Cortex" — let the user decide.

### During Apply: Pre-Creation Check

Before creating each project, check again:
1. Query Cortex for any project with matching normalized `github_url`
2. If found → skip with status `"duplicate_skipped"` in results
3. This prevents duplicates from concurrent apply operations or double-click scenarios

### URL Normalization

```python
def normalize_github_url(url: str | None) -> str | None:
    """Normalize GitHub URL to canonical form: https://github.com/{owner}/{repo}"""
    if not url:
        return None
    # Handle SSH: git@github.com:owner/repo.git → https://github.com/owner/repo
    # Handle HTTPS: https://github.com/owner/repo.git → https://github.com/owner/repo
    # Strip trailing .git
    # Strip trailing /
    # Lowercase
    ...
```

---

## Component Breakdown

### 1. Database Migration (`migration/018_scanner_tables.sql`)

Three new tables:

**`cortex_scan_results`** — Stores scan sessions
```sql
CREATE TABLE IF NOT EXISTS cortex_scan_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    directory_path TEXT NOT NULL,
    system_id UUID REFERENCES cortex_systems(id),
    total_found INTEGER NOT NULL DEFAULT 0,
    new_projects INTEGER NOT NULL DEFAULT 0,
    already_in_cortex INTEGER NOT NULL DEFAULT 0,
    project_groups INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'pending',  -- pending, applied, partial, expired
    template JSONB,                          -- template used when applied
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    applied_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ DEFAULT NOW() + INTERVAL '24 hours'
);
```

**`cortex_scan_projects`** — Individual detected projects within a scan
```sql
CREATE TABLE IF NOT EXISTS cortex_scan_projects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    scan_id UUID NOT NULL REFERENCES cortex_scan_results(id) ON DELETE CASCADE,
    directory_name TEXT NOT NULL,
    absolute_path TEXT NOT NULL,           -- path inside container (/projects/...)
    host_path TEXT NOT NULL,               -- original host path for display
    git_remote_url TEXT,
    github_owner TEXT,
    github_repo_name TEXT,
    github_url TEXT,                       -- normalized canonical URL
    default_branch TEXT,
    has_readme BOOLEAN NOT NULL DEFAULT FALSE,
    readme_content TEXT,                   -- full README.md for knowledge base ingestion
    readme_excerpt TEXT,                   -- first 5000 chars for description generation context
    detected_languages TEXT[] DEFAULT '{}',
    project_indicators TEXT[] DEFAULT '{}', -- e.g. ["node", "python", "rust"]
    dependencies JSONB DEFAULT '{}',       -- {"npm": ["react","next"], "pip": ["fastapi"]}
    infra_markers TEXT[] DEFAULT '{}',     -- ["docker", "github-actions", "supabase"]
    is_project_group BOOLEAN NOT NULL DEFAULT FALSE,
    group_name TEXT,                       -- parent group directory name, if nested
    already_in_cortex BOOLEAN NOT NULL DEFAULT FALSE,
    existing_project_id UUID,
    selected BOOLEAN NOT NULL DEFAULT TRUE,
    apply_status TEXT NOT NULL DEFAULT 'pending', -- pending, created, skipped, failed, duplicate_skipped
    cortex_project_id UUID,               -- set after successful creation
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_scan_projects_scan_id ON cortex_scan_projects(scan_id);
CREATE INDEX idx_scan_projects_github_url ON cortex_scan_projects(github_url);
```

**`cortex_scanner_templates`** — Saved scan templates
```sql
CREATE TABLE IF NOT EXISTS cortex_scanner_templates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    description TEXT,
    template JSONB NOT NULL,
    is_default BOOLEAN NOT NULL DEFAULT FALSE,
    system_id UUID REFERENCES cortex_systems(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Only one default template per system
CREATE UNIQUE INDEX idx_scanner_templates_default
    ON cortex_scanner_templates(system_id)
    WHERE is_default = TRUE;
```

### 2. Git Detector Module (`python/src/server/services/scanner/git_detector.py`)

Detects Git repositories using the smart recurse algorithm:

```python
@dataclass
class DetectedProject:
    directory_name: str         # Folder name (e.g. "my-app")
    absolute_path: str          # Container path (/projects/my-app)
    host_path: str              # Display path (~/projects/my-app)
    git_remote_url: str | None  # Raw origin remote URL
    github_owner: str | None    # Parsed from remote URL
    github_repo_name: str | None  # Parsed from remote URL
    github_url: str | None      # Normalized https://github.com/owner/repo
    default_branch: str | None  # HEAD branch
    has_readme: bool
    readme_content: str | None  # Full README.md content (for knowledge base ingestion)
    readme_excerpt: str | None  # First 5000 chars (for description generation context)
    detected_languages: list[str]  # From file extensions
    project_indicators: list[str]  # ["node", "python", "rust", ...]
    dependencies: dict[str, list[str]] | None  # {"npm": ["react", "next"], "pip": ["fastapi"]}
    infra_markers: list[str]    # ["docker", "github-actions", "firebase", ...]
    is_project_group: bool      # True if this is a group parent
    group_name: str | None      # Parent group name, if nested

@dataclass
class ScanSummary:
    directory_path: str
    host_path: str
    projects: list[DetectedProject]
    project_groups: list[str]   # Names of detected project groups
    total_found: int
    skipped_dirs: list[str]     # Directories that were skipped and why
```

**Detection logic:**
- Read `.git/config` to parse remote URL (faster than `git` subprocess)
- Parse GitHub owner/repo from SSH and HTTPS formats
- Normalize to canonical `https://github.com/{owner}/{repo}`
- Detect project type from marker files: `package.json` (node), `pyproject.toml`/`setup.py` (python), `Cargo.toml` (rust), `go.mod` (go), `pom.xml`/`build.gradle` (java)
- Detect languages from file extensions in top-level directory (shallow scan, not recursive)
- Read full README.md content (store both full content and 5000-char excerpt)
- Extract dependency names from manifest files (see Dependency & Infrastructure Capture below)
- Check for infrastructure marker files (see Dependency & Infrastructure Capture below)

**Non-GitHub remotes**: Detected during scan but **skipped by default** (`require_github_remote: true`). Logged in the post-scan report with reason "Non-GitHub remote" so the user has visibility. Users who want to include them can set `require_github_remote: false` in the template, but those projects will be created without knowledge sources (no crawling for non-GitHub hosts in v1).

### 3. Scan Template Models (`python/src/server/services/scanner/scan_template.py`)

```python
class ScanTemplate(BaseModel):
    """Template controlling how scanned projects are set up in Cortex"""

    # Cortex connection (user-overridable for non-default ports)
    cortex_api_url: str = "http://localhost:8181"   # Written into each project's cortex-config.json
    cortex_mcp_url: str = "http://localhost:8051"   # Written into each project's cortex-config.json

    # Project creation
    skip_existing: bool = True                  # Skip repos already in Cortex
    create_group_parents: bool = True           # Create parent projects for project groups
    set_github_repo: bool = True                # Set github_repo field on project
    auto_tag_languages: bool = True             # Add detected languages as project tags

    # Knowledge sources
    crawl_github_readme: bool = True            # Crawl GitHub README as knowledge source
    crawl_github_docs: bool = False             # Crawl /docs folder if present
    knowledge_type: str = "technical"           # "technical" or "business"

    # Setup files (replicating cortex-setup)
    write_config_files: bool = True             # Write .claude/cortex-config.json + cortex-state.json
    write_settings_local: bool = True           # Write .claude/settings.local.json with hooks
    install_extensions: bool = True             # Download and extract extensions to .claude/skills/
    update_gitignore: bool = True               # Add Cortex entries to .gitignore

    # Filtering
    include_patterns: list[str] = []            # Glob patterns to include (empty = all)
    exclude_patterns: list[str] = []            # Glob patterns to exclude
    require_github_remote: bool = True          # Only include repos with GitHub remotes (non-GitHub repos skipped)
```

### 4. Scanner Service (`python/src/server/services/scanner/scanner_service.py`)

```python
class ScannerService:
    def __init__(self, supabase_client=None):
        self.supabase = supabase_client or get_supabase_client()
        self.project_service = ProjectService(self.supabase)
        self.git_detector = GitDetector()

    async def scan_directory(
        self,
        container_path: str,
        host_path: str,
        system_id: str,
    ) -> tuple[bool, dict[str, Any]]:
        """
        Scan a directory for Git repos, cross-reference with existing Cortex projects,
        and persist results to cortex_scan_results + cortex_scan_projects tables.

        Returns (success, {"scan_id": "...", "summary": {...}})
        """

    async def apply_scan(
        self,
        scan_id: str,
        template: ScanTemplate,
        selected_project_ids: list[str] | None,
        descriptions: dict[str, str] | None,
        system_fingerprint: str,
        system_name: str,
        progress_id: str,
    ) -> tuple[bool, dict[str, Any]]:
        """
        Apply template to selected projects from a scan.
        Creates Cortex projects, writes config files, installs extensions, starts crawls.
        Generates CSV report on completion.

        Returns (success, {"operation_id": "...", "created": N, "skipped": N, "failed": N,
                           "report_csv_path": "...", "report_summary": "..."})
        """

    async def _setup_single_project(
        self,
        scan_project: dict,
        template: ScanTemplate,
        description: str | None,
        system_fingerprint: str,
        system_name: str,
    ) -> tuple[bool, dict[str, Any]]:
        """
        Set up a single project — equivalent to running /cortex-setup in that directory.

        Steps:
        1. Create Cortex project via ProjectService (with dependencies in metadata, infra in tags)
        2. Register system for project via sync endpoint
        3. Write .claude/cortex-config.json (using template.cortex_api_url, template.cortex_mcp_url)
        4. Write .claude/cortex-state.json
        5. Write .claude/settings.local.json (if template.write_settings_local)
        6. Install extensions to .claude/skills/ (if template.install_extensions)
        7. Update .gitignore (if template.update_gitignore)
        8. Ingest local README as knowledge document with embeddings
        9. Start GitHub README crawl (if template.crawl_github_readme and github_url present)
        """

    async def _write_project_config_files(
        self,
        project_path: str,
        project_id: str,
        system_fingerprint: str,
        system_name: str,
        system_id: str,
        template: ScanTemplate,
    ) -> None:
        """Write .claude/ config files into the project directory via mounted volume.
        Uses template.cortex_api_url and template.cortex_mcp_url for the URLs."""

    async def _install_extensions(self, project_path: str, cached_tarball_path: str) -> None:
        """Extract cached extensions tarball into project's .claude/skills/ directory."""

    async def _update_gitignore(self, project_path: str) -> None:
        """Append Cortex entries to .gitignore if not already present."""

    async def _cache_extensions_tarball(self, template: ScanTemplate) -> str:
        """Download extensions tarball once from {cortex_mcp_url}/cortex-setup/extensions.tar.gz.
        Returns path to cached tarball. Reused for all projects in the scan."""

    async def get_scan_results(self, scan_id: str) -> tuple[bool, dict[str, Any]]:
        """Fetch scan results from database."""

    async def estimate_apply_time(
        self,
        scan_id: str,
        template: ScanTemplate,
        selected_count: int,
    ) -> dict[str, Any]:
        """
        Estimate how long the apply phase will take.
        Returns {"estimated_minutes": N, "project_creation_seconds": N, "crawl_minutes": N}
        """

    async def generate_scan_report(
        self,
        scan_id: str,
    ) -> tuple[bool, dict[str, Any]]:
        """
        Generate a post-scan CSV report and summary.

        Returns (success, {"csv_path": "/projects/.cortex-scan-report-{scan_id}.csv", "summary": {...}})
        """
```

### 5. Scanner API (`python/src/server/api_routes/scanner_api.py`)

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/scanner/scan` | Scan a directory, persist results |
| `GET` | `/api/scanner/results/{scan_id}` | Get scan results with per-project details |
| `POST` | `/api/scanner/apply` | Apply template to selected projects |
| `GET` | `/api/scanner/estimate` | Get time estimate for apply |
| `GET` | `/api/scanner/report/{scan_id}` | Get scan report summary + CSV path |
| `GET` | `/api/scanner/templates` | List saved templates |
| `POST` | `/api/scanner/templates` | Save a template |
| `DELETE` | `/api/scanner/templates/{template_id}` | Delete a template |

**Request/Response Models:**

```python
class ScanRequest(BaseModel):
    directory_path: str | None = None  # Relative to mounted root; None = scan root
    system_fingerprint: str            # Required — validates system is registered

class ScanResponse(BaseModel):
    scan_id: str
    directory_path: str                # Host path for display
    total_found: int
    new_projects: int
    already_in_cortex: int
    project_groups: int
    projects: list[ScanProjectResponse]  # Full details per project

class ScanProjectResponse(BaseModel):
    id: str                            # UUID from cortex_scan_projects
    directory_name: str
    host_path: str
    github_url: str | None
    detected_languages: list[str]
    project_indicators: list[str]
    has_readme: bool
    readme_excerpt: str | None
    is_project_group: bool
    group_name: str | None
    already_in_cortex: bool
    existing_project_id: str | None

class ApplyRequest(BaseModel):
    scan_id: str
    template: ScanTemplate
    selected_project_ids: list[str] | None = None  # None = all new projects
    descriptions: dict[str, str] | None = None     # dir_name → AI description
    system_fingerprint: str
    system_name: str

class ApplyResponse(BaseModel):
    operation_id: str                  # For progress tracking
    estimated_minutes: float
    projects_to_create: int
    crawls_to_start: int

class EstimateRequest(BaseModel):
    scan_id: str
    template: ScanTemplate
    selected_count: int | None = None

class EstimateResponse(BaseModel):
    estimated_minutes: float
    project_creation_seconds: float
    crawl_minutes: float
    warning: str | None                # e.g. "50 crawls at 3 concurrent = ~50 minutes"
```

### 6. MCP Tools (`python/src/mcp_server/features/scanner/scanner_tools.py`)

Two MCP tools following existing patterns:

```python
def register_scanner_tools(mcp: FastMCP):

    @mcp.tool()
    async def scan_local_projects(
        ctx: Context,
        system_fingerprint: str,
        directory_path: str | None = None,
    ) -> str:
        """
        Scan the mounted projects directory for Git repositories.

        Detects repos, extracts GitHub metadata, reads README content,
        and identifies project groups (directories containing multiple repos).
        Cross-references with existing Cortex projects to flag duplicates.

        Args:
            system_fingerprint: Your system's fingerprint (from cortex-state.json)
            directory_path: Subdirectory within mounted projects root (optional)

        Returns: JSON with scan_id, project list, and summary statistics.
                 Each project includes readme_excerpt for description generation.
        """
        # POST /api/scanner/scan via ctx.service_client
        ...

    @mcp.tool()
    async def apply_scan_template(
        ctx: Context,
        scan_id: str,
        system_fingerprint: str,
        system_name: str,
        selected_project_ids: list[str] | None = None,
        descriptions: dict[str, str] | None = None,
        template: dict | None = None,
    ) -> str:
        """
        Apply setup to scanned projects — equivalent to running /cortex-setup
        in each project directory.

        Creates Cortex projects, writes .claude/ config files, updates .gitignore,
        and starts knowledge source crawling for each selected project.

        Args:
            scan_id: The scan_id from scan_local_projects
            system_fingerprint: Your system's fingerprint
            system_name: Your system's name
            selected_project_ids: Project IDs to include (None = all new projects)
            descriptions: Dict of directory_name → AI-generated description
            template: Override template (None = use default or saved template)

        Returns: JSON with operation_id for progress tracking and summary.
        """
        # POST /api/scanner/apply via ctx.service_client
        ...
```

### 7. Docker Configuration Changes

**`docker-compose.yml`** — Add volume mount to `cortex-server`:
```yaml
cortex-server:
  volumes:
    - ./python/src:/app/src
    - ./python/tests:/app/tests
    - ./migration:/app/migration
    - ./integrations:/app/integrations
    - cortex-server-data:/app/data
    - ${PROJECTS_DIRECTORY:-~/projects}:/projects:rw   # Scanner mount
  environment:
    # ... existing env vars ...
    - SCANNER_PROJECTS_ROOT=/projects
    - SCANNER_ENABLED=${SCANNER_ENABLED:-false}
```

**`.env.example`** — Add scanner configuration:
```bash
# Local Project Scanner
# Set to your projects directory and enable to use the scanner
PROJECTS_DIRECTORY=~/projects
SCANNER_ENABLED=false
```

**Server config** — Add scanner settings to `python/src/server/config/`:
```python
SCANNER_PROJECTS_ROOT = os.getenv("SCANNER_PROJECTS_ROOT", "/projects")
SCANNER_ENABLED = os.getenv("SCANNER_ENABLED", "false").lower() == "true"
```

The scanner API returns 503 if `SCANNER_ENABLED` is false, with a message explaining how to enable it.

---

## Config Files Written Per Project

### `.claude/cortex-config.json`

URLs come from the template's `cortex_api_url` and `cortex_mcp_url` fields, allowing users on non-default ports to configure once in the template.

```json
{
    "cortex_api_url": "<from template.cortex_api_url>",
    "cortex_mcp_url": "<from template.cortex_mcp_url>",
    "project_id": "uuid-of-created-project",
    "project_title": "RecipeRaiders",
    "machine_id": "md5-first-16-chars",
    "install_scope": "project",
    "installed_at": "2026-03-17T14:30:00Z",
    "installed_by": "scanner"
}
```

### `.claude/cortex-state.json`

```json
{
    "system_fingerprint": "sha256-hash",
    "system_name": "WIN_AI_PC_WSL",
    "cortex_project_id": "uuid-of-created-project"
}
```

### `.claude/settings.local.json`

```json
{
    "hooks": {
        "PostToolUse": [
            {
                "matcher": ".*",
                "hooks": [
                    {
                        "type": "command",
                        "command": "~/.claude/plugins/cortex-memory/scripts/observation_hook.sh"
                    }
                ]
            }
        ]
    }
}
```

### `.gitignore` additions

```
# Cortex
.claude/plugins/
.claude/skills/
.claude/cortex-config.json
.claude/cortex-state.json
.claude/cortex-memory-buffer.jsonl
.claude/settings.local.json
.cortex/
```

---

## Crawl Queue Management

### Semaphore Constraint

The existing crawl semaphore allows max 3 concurrent crawls. For bulk scanning, this means:
- 10 projects × ~3 min/crawl / 3 concurrent ≈ **10 minutes**
- 50 projects × ~3 min/crawl / 3 concurrent ≈ **50 minutes**
- 100 projects × ~3 min/crawl / 3 concurrent ≈ **100 minutes**

### Mitigation Strategy

1. **Time estimate before apply**: The `estimate` endpoint calculates expected time and the MCP tool reports it to the user before proceeding
2. **Project creation is fast**: All project creation, config file writing, and system registration happens first (seconds per project). Crawls are queued last.
3. **Crawl progress tracking**: Each crawl gets its own progress entry. The scanner's overall progress tracks completion across all crawls.
4. **User can cancel**: Cancelling stops queuing new crawls. Already-created projects remain valid without crawled knowledge sources — users can manually crawl later.
5. **README-only crawling**: The default template crawls only the README page (single-page crawl), which is much faster than a full site crawl.

### Progress Reporting

The scanner uses a parent `ProgressTracker` for the overall operation:
```
Progress 0-30%:  Creating projects and writing config files
Progress 30-40%: Registering system for each project
Progress 40-100%: Crawling knowledge sources (distributed across all crawl completions)
```

Per-project status updates are logged to the progress tracker:
```
[3/50] Created: RecipeRaiders (crawl queued)
[4/50] Skipped: reciperaiders-dashboard (already in Cortex)
[5/50] Failed: private-repo (README crawl failed — project created without knowledge source)
```

---

## Post-Scan Report Log

After the apply phase completes, the scanner generates a comprehensive CSV report and a human-readable summary. This provides a permanent record of what happened during the scan.

### CSV Report File

Written to the mounted projects directory at: `{projects_root}/.cortex-scan-report-{scan_id}.csv`

**CSV Columns:**

| Column | Description |
|--------|-------------|
| `directory_name` | Folder name |
| `host_path` | Full path on host filesystem |
| `github_url` | Normalized GitHub URL (or empty) |
| `group_name` | Parent project group (or empty) |
| `detected_languages` | Comma-separated language list |
| `status` | `created`, `skipped_existing`, `skipped_non_github`, `skipped_no_remote`, `skipped_filtered`, `duplicate_skipped`, `failed` |
| `cortex_project_id` | UUID of created project (or empty) |
| `crawl_status` | `queued`, `skipped`, `failed`, `n/a` |
| `error` | Error message if failed (or empty) |
| `description` | AI-generated description (or empty) |

### Human-Readable Summary

Returned by the MCP tool and also appended to the top of the CSV as comment lines:

```
# Cortex Local Project Scanner Report
# Scan ID: a1b2c3d4-...
# Directory: ~/projects
# Date: 2026-03-17T14:30:00Z
# System: WIN_AI_PC_WSL
#
# === Summary ===
# Total directories scanned: 52
# Git repositories found: 47
# Project groups detected: 2 (RecipeRaiders_Complete, MyOrgApps)
#
# === Results ===
# Created:              38
# Skipped (existing):    5
# Skipped (non-GitHub):  3  (gitlab.com/user/repo1, bitbucket.org/user/repo2, ...)
# Skipped (no remote):   1  (local-experiments)
# Failed:                0
#
# === Crawls ===
# README crawls queued:  38
# Estimated crawl time:  ~38 minutes (3 concurrent)
#
# === Errors ===
# (none)
```

### Report Generation Flow

1. After `apply_scan` completes, it calls `generate_scan_report(scan_id)` automatically
2. The report queries `cortex_scan_projects` for all projects in the scan
3. CSV is written to the mounted volume so the user can access it from their host filesystem
4. The summary text is returned in the apply response for Claude Code to display
5. Both the CSV path and summary are stored on the `cortex_scan_results` row

### Report API Endpoint

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/scanner/report/{scan_id}` | Get report summary + CSV download path |

This allows retrieving the report later if the user wants to review a past scan.

---

## Scan Result Expiration

### Why Scans Expire

Scan results represent a point-in-time snapshot of the filesystem. After 24 hours, the data may be stale:
- New repos may have been added to the projects directory
- Existing repos may have been deleted or moved
- GitHub remote URLs may have changed

The 24h TTL ensures users always work with fresh data. Since this is typically a one-time operation per system, most users will scan and apply within the same session.

### Cleanup Strategy

A **background cleanup task** runs periodically (on server startup and every 6 hours) to delete expired scans:

```python
async def cleanup_expired_scans():
    """Delete scan results where expires_at < NOW().
    CASCADE deletes associated cortex_scan_projects rows."""
```

This prevents unbounded growth of the scan tables without requiring user action.

---

## Extension Version Recording

When extensions are installed per-project, the scanner records a version hash so it's possible to tell what was installed and when. This is written into each project's `cortex-config.json`:

```json
{
    "cortex_api_url": "...",
    "cortex_mcp_url": "...",
    "project_id": "...",
    "project_title": "RecipeRaiders",
    "machine_id": "...",
    "install_scope": "project",
    "installed_at": "2026-03-17T14:30:00Z",
    "installed_by": "scanner",
    "extensions_hash": "sha256-of-tarball-content",
    "extensions_installed_at": "2026-03-17T14:30:00Z"
}
```

**How it works:**
1. When the scanner caches the extensions tarball, it computes a SHA-256 hash of the file content
2. The hash is written into every project's `cortex-config.json` alongside a timestamp
3. This creates a record of exactly which version of extensions each project received
4. A future tool could compare `extensions_hash` against the current tarball hash to detect stale installations

The hash is computed once per scan (all projects in a single scan get the same extensions version).

---

## Crash Recovery & Resume

### The Problem

The apply phase processes projects sequentially. If the server crashes or the operation is interrupted mid-apply (e.g., Docker restart, network failure, out of memory), some projects will be fully set up, some partially set up, and some untouched.

### Idempotent Apply Design

Every step in `_setup_single_project` is designed to be **idempotent** — safe to re-run:

| Step | Idempotency Strategy |
|------|---------------------|
| Create Cortex project | Pre-creation duplicate check by normalized `github_url`. If project exists, reuse the `project_id`. |
| Register system for project | `POST /api/projects/{project_id}/sync` is idempotent — updates `last_seen` if already registered. |
| Write `.claude/cortex-config.json` | Overwrite — always produces correct state. |
| Write `.claude/cortex-state.json` | Overwrite — always produces correct state. |
| Write `.claude/settings.local.json` | Overwrite — always produces correct state. |
| Install extensions to `.claude/skills/` | Extract overwrites existing files. |
| Update `.gitignore` | Checks for existing entries before appending — no duplicates. |
| Ingest local README to knowledge base | Check if document already exists for this project/source. Skip if present. |
| Start GitHub README crawl | Check if source already exists for this project before starting. Skip if already crawled. |

### Resume Flow

When the user calls `apply_scan_template` with the same `scan_id` after a crash:

1. Backend loads `cortex_scan_projects` for the scan
2. For each project, checks `apply_status`:
   - `"created"` → **skip** (already fully set up)
   - `"failed"` → **retry** (re-run all steps; idempotency ensures no damage)
   - `"pending"` → **process** (normal flow)
3. Progress tracker starts from where it left off (counts already-created projects as pre-completed)
4. A new CSV report is generated reflecting the combined results

### Per-Project Status Tracking

The `cortex_scan_projects.apply_status` column is updated atomically after ALL steps for a project succeed:

```
pending → [running all steps] → created  (success)
pending → [running all steps] → failed   (any step fails, error_message set)
```

A project is only marked `"created"` when every step completes. If the process crashes mid-step for a project, it stays `"pending"` and will be retried on resume. The idempotent design ensures partial work from the crashed attempt is harmlessly overwritten.

### User Experience

After a crash, the user simply invokes `apply_scan_template` again with the same `scan_id`:

```
Claude Code: "The previous apply was interrupted. Resuming: 23 of 50 projects
already set up, 27 remaining. Estimated time for remaining: ~27 minutes."
```

The MCP tool detects the partial state and communicates it clearly.

---

## Edge Cases & Error Handling

### Scan Phase
| Scenario | Behavior |
|----------|----------|
| Path doesn't exist | Return error: "Directory not found: /projects/subpath" |
| Permission denied | Return error with specific path |
| Empty directory | Return empty results with message |
| Very large directory (500+ subdirs) | Complete scan but warn user in results |
| Symlinks | Follow symlinks for `.git/` detection; don't recurse into symlinked trees |
| Non-GitHub remotes (GitLab, Bitbucket) | Skip by default; log in scan report as "Non-GitHub remote: {url}" |
| Bare git repos (no working tree) | Skip — these are not user project directories |
| `.git` file (submodule pointer) | Skip — submodules are part of parent repo |
| Scanner not enabled | Return 503 with setup instructions |

### Apply Phase
| Scenario | Behavior |
|----------|----------|
| Duplicate github_url detected at apply time | Skip with `duplicate_skipped` status |
| Crawl fails (private repo, 404, rate limit) | Project still created; log crawl failure in results |
| Config file write fails (permissions) | Log error; project still created in Cortex DB |
| `.gitignore` doesn't exist | Create new `.gitignore` with Cortex entries |
| `.gitignore` already has entries | Skip those entries, append only new ones |
| System not registered | Fail fast with error before creating any projects |
| Scan expired (24h TTL) | Return error: "Scan expired. Please run a new scan." |
| Concurrent apply on same scan | Second apply checks `apply_status` per project; skips already-created |
| Server crash during apply | Projects stay `pending`; user re-invokes `apply_scan_template` with same `scan_id` to resume. Idempotent steps ensure no corruption. |
| Extension tarball download fails | Fail fast before starting any project setup. Clear error: "Could not download extensions from {url}" |
| Disk full during config file writes | Current project marked `failed` with error. Remaining projects skipped. Report generated for completed work. |
| Docker volume not writable | Fail fast on first write attempt. Error: "Cannot write to projects directory. Check Docker volume mount permissions." |

### Project Group Edge Cases
| Scenario | Behavior |
|----------|----------|
| Group dir has `.git/` AND contains git subdirs | Treat as a regular project (not a group); subdirs ignored |
| Nested groups (group inside group) | Only recurse one level; inner groups detected as regular directories |
| Group with mix of git repos and non-git dirs | Only add git repos; ignore non-git subdirectories |

---

## Implementation Order

### Phase 1: Infrastructure (Tasks 1-3)

1. **Database migration** — `018_scanner_tables.sql` with `cortex_scan_results`, `cortex_scan_projects`, `cortex_scanner_templates` tables
2. **Docker configuration** — Volume mount in `docker-compose.yml`, env vars in `.env.example`, scanner config constants
3. **Git detector module** — `git_detector.py` with smart recurse algorithm, URL normalization, README reading

### Phase 2: Core Backend (Tasks 4-7)

4. **Scan template models** — `scan_template.py` with Pydantic models (including URL overrides)
5. **Scanner service** — `scanner_service.py` with scan, apply, config file writing, extension installation, and progress tracking
6. **Scan report generator** — CSV report output and summary generation, background cleanup task for expired scans
7. **Scanner API routes** — `scanner_api.py` with all endpoints (including `/report/{scan_id}`), registered in `main.py`

### Phase 3: MCP Integration (Tasks 8-9)

8. **MCP scanner tools** — `scan_local_projects` and `apply_scan_template` tools
9. **MCP registration** — Register in `mcp_server.py` module initialization

### Phase 4: Testing (Tasks 10-12)

10. **Git detector tests** — URL normalization, smart recurse, project group detection, skip list
11. **Scanner service tests** — Scan flow, apply flow, config file generation, extension installation, duplicate prevention, report generation
12. **Integration test** — End-to-end scan → apply with mock filesystem

### Phase 5: Documentation (Task 13)

13. **User documentation** — Setup guide for Docker volume mount, CLI usage examples, template reference, report format documentation

---

## File Inventory

### New Files

| File | Purpose |
|------|---------|
| `migration/018_scanner_tables.sql` | Database tables |
| `python/src/server/services/scanner/__init__.py` | Module init |
| `python/src/server/services/scanner/git_detector.py` | Git repo detection + smart recurse |
| `python/src/server/services/scanner/scan_template.py` | Template Pydantic models |
| `python/src/server/services/scanner/scanner_service.py` | Core orchestration + config file writing + extension install |
| `python/src/server/services/scanner/scan_report.py` | CSV report generation and summary formatting |
| `python/src/server/services/scanner/url_normalizer.py` | GitHub URL normalization |
| `python/src/server/services/scanner/cleanup.py` | Background task for expired scan cleanup |
| `python/src/server/api_routes/scanner_api.py` | REST endpoints |
| `python/src/mcp_server/features/scanner/__init__.py` | MCP module init |
| `python/src/mcp_server/features/scanner/scanner_tools.py` | MCP tools |
| `python/tests/server/services/scanner/__init__.py` | Test module init |
| `python/tests/server/services/scanner/test_git_detector.py` | Detector tests |
| `python/tests/server/services/scanner/test_scanner_service.py` | Service tests |
| `python/tests/server/services/scanner/test_url_normalizer.py` | URL normalization tests |
| `docs/plans/local-project-scanner-web-plan.md` | Deferred web UI plan |

### Modified Files

| File | Change |
|------|--------|
| `docker-compose.yml` | Add projects volume mount to cortex-server |
| `.env.example` | Add PROJECTS_DIRECTORY and SCANNER_ENABLED |
| `python/src/server/main.py` | Register scanner_api router |
| `python/src/server/config/` | Add scanner configuration constants |
| `python/src/mcp_server/mcp_server.py` | Register scanner tools |

---

## Decisions Log

| # | Decision | Rationale |
|---|----------|-----------|
| 1 | Docker volume mount for filesystem access | Simple, no new services needed. User configures once in `.env`. |
| 2 | CLI-first via MCP tools | Claude Code is the primary Cortex interface. Web UI deferred. |
| 3 | Scan results persisted in DB | Survives page refresh, enables resume, provides audit trail. |
| 4 | Replicate full /cortex-setup per project | Users expect identical end state to manual setup. |
| 5 | Smart recurse (max depth 2) | Handles project groups (RecipeRaiders) without arbitrary depth complexity. |
| 6 | Claude Code generates descriptions | No extra AI config needed. Claude Code IS the AI in the CLI flow. |
| 7 | Match duplicates only on normalized github_url | Title matching is too fragile. No-remote repos: user decides. |
| 8 | Pre-creation duplicate check | Prevents race conditions from double-click or concurrent apply. |
| 9 | `cortex_scanner_templates` table | DB persistence for templates. One default per system. |
| 10 | SCANNER_ENABLED flag (default false) | Opt-in feature. Volume mount without this flag has no effect. |
| 11 | 24-hour scan result TTL with background cleanup | Filesystem snapshots go stale. Background task cleans up every 6 hours. |
| 12 | README-only default crawl | Single-page crawl is fast. Full docs crawl is opt-in. |
| 13 | Extensions installed per-project | Projects frequently need different extension customizations. Global installs create conflicts. |
| 14 | Cortex URLs configurable in template | Supports non-default ports. User sets once in template, applies to all projects. |
| 15 | Skip non-GitHub repos by default | v1 only supports GitHub README crawling. Non-GitHub repos logged in scan report for visibility. |
| 16 | CSV scan report log | Permanent record of scan results written to projects directory. Easy to review in any spreadsheet tool. |
| 17 | One-time onboarding tool, no re-scan | New projects after initial scan use `/cortex-setup`. Scanner is for bulk onboarding only. |
| 18 | Record extension version hash per project | SHA-256 of tarball in `cortex-config.json`. Enables future update detection without ongoing scans. |
| 19 | Idempotent apply with crash resume | All setup steps are idempotent. Re-invoking `apply_scan_template` with same `scan_id` safely resumes from where it left off. |
| 20 | Capture dependencies and infra markers during scan | Scanner has one-time filesystem access. Capture now to enable future conversational AI cross-project queries. |
| 21 | Store full README + ingest to knowledge base | Local README ingested immediately with embeddings. Works for private repos, no crawl delay. GitHub crawl supplements. |
| 22 | Persist scan metadata to project records | Dependencies → project metadata, infra markers → project tags. Survives scan expiration. |

---

## Resolved Questions

| # | Question | Decision |
|---|----------|----------|
| 1 | Non-GitHub repos in future? | Yes — plan to support GitLab/Bitbucket in a future version (URL normalization + crawl strategies). Not v1. |
| 2 | Record extension version? | Yes — record a version hash in `cortex-config.json` per project (see Extension Version Recording). |
| 3 | Re-scan workflow? | No — this is a **one-time onboarding tool per machine**. New projects after initial scan use the existing `/cortex-setup` command. No re-scan mode needed. |

## Future Considerations

- **Non-GitHub repository support**: Add URL normalization and crawl strategies for GitLab and Bitbucket. Requires extending the URL normalizer and adding new crawl endpoint handlers.
- **Extension update detection**: With version hashes recorded per-project, a future tool could compare installed versions against the registry and flag stale installations.
- **Conversational AI interface**: The dependency snapshots, infra markers, project group relationships, and README knowledge documents captured by the scanner are designed to feed a future chat interface where users can ask questions across all their projects (e.g., "which projects use PostgreSQL?", "how do my RecipeRaiders services connect?", "what CI/CD do I have set up?"). The scanner's data capture is the foundation for this cross-project intelligence.
- **Cross-project dependency analysis**: With dependency data persisted to project metadata, a future service could build a dependency graph showing which projects share libraries, which projects might be affected by a library vulnerability, and which projects form logical clusters based on shared technology stacks.
