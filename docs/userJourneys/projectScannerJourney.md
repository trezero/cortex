# Journey Test — Local Project Scanner (Bulk Onboarding)

## Test Environment

This journey tests the client-side Local Project Scanner across multiple real systems, all
pointing at the same Cortex instance.

### Systems Under Test

| System | OS | Python Cmd | Projects Path | Cortex URL |
|--------|------|------------|---------------|------------|
| `WIN_AI_PC_WSL` | Ubuntu 22.04 (WSL2) | `python3` | `~/projects/` | `http://localhost:8181` (host) |
| `WIN_AI_PC` | Windows 11 | `python` or `py` | `C:\Users\winadmin\projects\` | `http://localhost:8181` |
| `MacBookPro_M1` | macOS (ARM) | `python3` | `~/projects/` | `http://<WSL_IP>:8181` (remote) |
| `WhiteShark_AI_Server` | Ubuntu 22.04 | `python3` | `~/projects/` | `http://<WSL_IP>:8181` (remote) |

**Cortex instance runs on `WIN_AI_PC_WSL` only.** All other systems connect remotely.

### WIN_AI_PC_WSL Projects Directory (Primary Test System)

```
~/projects/
├── cortex/                      # GitHub (trezero/cortex) — already in Cortex
├── RecipeRaiders/               # GitHub (trezero/RecipeRaiders) — already in Cortex
├── RecipeRaiders-Marketing/     # GitHub (trezero/RecipeRaiders-Marketing) — already in Cortex
├── reciperaiders-repdash/       # GitHub (trezero/reciperaiders-repdash) — already in Cortex
├── BrandAmbassador/             # GitHub (trezero/BrandAmbassador) — already in Cortex
├── AIOps/                       # GitHub (workflow-intelligence-nexus/aiops)
├── AIOpsDocs/                   # GitHub (workflow-intelligence-nexus/aiopsdocs) — python, docker
├── continuumMain/               # GitHub (trezero/continuum) — docker
├── continuumNG_ONLYREFERENCE/   # GitHub (trezero/continuum) — SAME remote URL as continuumMain
├── emailBrain/                  # GitHub (trezero/emailbrain) — docker
├── gravityClaw/                 # GitHub (trezero/gravityclaw)
├── link-in-bio-page-builder/    # GitHub (coleam00/link-in-bio-page-builder)
├── localSupabase/               # GitHub (trezero/localsupabase) — docker, supabase
├── openclaw/                    # GitHub (openclaw/openclaw) — docker, github-actions
├── remote-coding-agent/         # GitHub (trezero/remote-coding-agent) — docker, github-actions
├── space-molly/                 # GitHub (trezero/space-molly) — python, docker
├── teamsMCP/                    # GitHub (trezero/teamsmcp) — docker
├── teamsToRAG/                  # GitHub (trezero/teamstorag) — docker
├── reference_repos/             # NOT a git repo — project group
│   └── PostmanFastAPIDemo/      # GitHub (coleam00/postmanfastapidemo) — github-actions
├── AIDevTemplate/               # GitHub (trezero/aidevtemplate)
├── Canvas-Homework-Helper/      # GitHub (trezero/canvas-homework-helper)
├── MemeCoinInvestor2026/        # GitHub (trezero/memecoininvestor2026) — already in Cortex
├── kiro-hackathon-continuum/    # GitHub (trezero/kiro-hackathon-continuum)
├── linuxStorageCleanup/         # GitHub (trezero/linuxstoragecleanup)
├── localClaudeCodeSetup/        # GitHub (trezero/localclaudecodesetup)
├── localClaudeTasks/            # (check if git repo)
├── localLinuxDocker/            # (check if git repo)
├── LocalSystemAI_WorkspaceONLY/ # (check if git repo)
└── postman-claude-skill/        # GitHub (sterlingchin/postman-claude-skill)
```

**Key observations for testing:**
- 26 git repos detected, 1 group (`reference_repos`)
- ~6 projects already exist in Cortex (cortex, RecipeRaiders, RecipeRaiders-Marketing, reciperaiders-repdash, BrandAmbassador, MemeCoinInvestor2026)
- `continuumMain` and `continuumNG_ONLYREFERENCE` share the same GitHub remote URL (dedup edge case)
- All repos have GitHub remotes (no local-only or GitLab repos on this system)
- Multiple repos have Docker, GitHub Actions, and other infra markers

---

## Prerequisites

Before starting this journey, the following must already be in place:

- [ ] Cortex stack running on WIN_AI_PC_WSL (`docker compose up --build -d`)
- [ ] Cortex MCP server accessible at `http://localhost:8051`
- [ ] Claude Code CLI installed on all test systems
- [ ] At least one project already set up with `/cortex-setup` on WIN_AI_PC_WSL (system registered)
- [ ] Cortex MCP endpoint configured globally on WIN_AI_PC_WSL (`claude mcp add cortex ...`)
- [ ] Python 3.8+ available on each test system
- [ ] For remote systems: Cortex API/MCP ports accessible over the network

---

## Phase 0 — Verify Prerequisites (WIN_AI_PC_WSL)

### 0.1 Confirm Cortex is Running

```bash
curl -s http://localhost:8181/health
```

| # | Check | Expected | Status |
|---|-------|----------|--------|
| 0.1a | Cortex API responds | 200 OK from health endpoint | |
| 0.1b | MCP server responds | `curl http://localhost:8051/health` returns 200 OK | |

### 0.2 Verify Scanner Script Endpoint

```bash
curl -s http://localhost:8181/api/scanner/script | head -1
```

| # | Check | Expected | Status |
|---|-------|----------|--------|
| 0.2a | Script endpoint responds | 200 OK, not 404 | |
| 0.2b | Script is valid Python | First line is `#!/usr/bin/env python3` | |

### 0.3 Verify Python Available Locally

```bash
python3 --version
```

| # | Check | Expected | Status |
|---|-------|----------|--------|
| 0.3a | Python 3 available | Version 3.8 or higher | |

### 0.4 Verify Existing Projects in Cortex

```bash
curl -s http://localhost:8181/api/projects | python3 -m json.tool | grep title
```

| # | Check | Expected | Status |
|---|-------|----------|--------|
| 0.4a | `cortex` project exists | Has `github_repo` set | |
| 0.4b | `RecipeRaiders` project exists | Has `github_repo` set | |
| 0.4c | Multiple projects present | At least 5 pre-existing projects for dedup testing | |

---

## Phase 1 — Scan the Projects Directory (WIN_AI_PC_WSL)

### 1.1 Invoke the Scanner via `/scan-projects`

Open Claude Code from any project with Cortex MCP configured:

> "Scan my local projects directory for Git repositories that aren't in Cortex yet."

Claude Code should invoke the `/scan-projects` skill.

| # | Check | Expected | Status |
|---|-------|----------|--------|
| 1.1a | Skill invoked | `/scan-projects` skill appears in conversation | |
| 1.1b | Preflight passes | System fingerprint found in `cortex-state.json` | |
| 1.1c | Python detected | Skill finds `python3` and stores as PYTHON_CMD | |
| 1.1d | Temp dir detected | Skill resolves temp directory (e.g., `/tmp`) | |
| 1.1e | Script downloaded | `cortex-scanner.py` fetched from `GET /api/scanner/script` | |
| 1.1f | Directory prompt shown | Skill asks for the projects directory path | |
| 1.1g | Script runs successfully | `python3 cortex-scanner.py --scan ~/projects` exits 0 | |

### 1.2 Verify Scan Output — JSON Structure

| # | Check | Expected | Status |
|---|-------|----------|--------|
| 1.2a | Output is valid JSON | Parsed without error | |
| 1.2b | `projects` array present | Contains project objects | |
| 1.2c | `groups` array present | Contains group objects | |
| 1.2d | `warnings` array present | Empty or contains permission warnings | |
| 1.2e | `summary` present | Contains `total_found` and `groups_found` | |
| 1.2f | `scanner_version` present | Value is `"1.0"` | |

### 1.3 Verify Summary Statistics

| # | Check | Expected | Status |
|---|-------|----------|--------|
| 1.3a | Total count | ~26 repos (matches actual git repos in ~/projects) | |
| 1.3b | Groups count | 1 (`reference_repos`) | |
| 1.3c | Group children | `PostmanFastAPIDemo` inside `reference_repos` | |

### 1.4 Verify Per-Project Metadata (spot checks)

| # | Check | Expected | Status |
|---|-------|----------|--------|
| 1.4a | `cortex` | `github_url: "https://github.com/trezero/cortex"`, languages include `python` | |
| 1.4b | `AIOpsDocs` | `infra_markers` includes `"docker"` and `"github-actions"` | |
| 1.4c | `RecipeRaiders` | `infra_markers` includes `"firebase"`, `has_readme: true` | |
| 1.4d | `openclaw` | Languages include `typescript` and `swift` | |
| 1.4e | `PostmanFastAPIDemo` | `group_name: "reference_repos"` | |
| 1.4f | `localSupabase` | `infra_markers` includes `"docker"` and `"supabase"` | |

### 1.5 Verify Dependency and Infrastructure Capture

| # | Check | Expected | Status |
|---|-------|----------|--------|
| 1.5a | npm deps extracted | Projects with `package.json` have `dependencies.npm` | |
| 1.5b | pip deps extracted | Python projects have `dependencies.pip` | |
| 1.5c | Docker detected | `emailBrain`, `teamsMCP`, `teamsToRAG` etc. have `"docker"` in infra | |
| 1.5d | GitHub Actions detected | `openclaw`, `remote-coding-agent` have `"github-actions"` | |
| 1.5e | README excerpts | Projects with README.md have `readme_excerpt` (max 5000 chars) | |

### 1.6 Verify Dedup Edge Case: Same Remote URL

`continuumMain` and `continuumNG_ONLYREFERENCE` both resolve to `https://github.com/trezero/continuum`.

| # | Check | Expected | Status |
|---|-------|----------|--------|
| 1.6a | Both detected | Both appear in scan results as separate projects | |
| 1.6b | Same github_url | Both have `github_url: "https://github.com/trezero/continuum"` | |
| 1.6c | Different paths | Different `absolute_path` values | |

---

## Phase 2 — AI Description Generation

### 2.1 Claude Generates Descriptions

After scan results, Claude should generate descriptions from README excerpts.

| # | Check | Expected | Status |
|---|-------|----------|--------|
| 2.1a | Descriptions generated | Claude produces descriptions for projects with READMEs | |
| 2.1b | No-README projects | Given generic description based on detected languages | |
| 2.1c | Quality check | Descriptions accurately reflect project purpose | |

### 2.2 User Reviews and Approves

Claude presents the list for confirmation:

| # | Check | Expected | Status |
|---|-------|----------|--------|
| 2.2a | Confirmation prompt | Claude asks user to confirm before proceeding | |
| 2.2b | New projects listed | Only projects NOT already in Cortex shown for creation | |
| 2.2c | Existing projects noted | cortex, RecipeRaiders, BrandAmbassador etc. noted as "already in Cortex" | |
| 2.2d | Duplicate URL noted | `continuumNG_ONLYREFERENCE` noted as sharing URL with `continuumMain` | |

---

## Phase 3 — Dedup and Create Projects

### 3.1 Deduplication via `find_projects` MCP

| # | Check | Expected | Status |
|---|-------|----------|--------|
| 3.1a | `find_projects` MCP called | Tool call visible in conversation | |
| 3.1b | URL comparison performed | Normalized `github_url` compared against existing `github_repo` | |
| 3.1c | `cortex` flagged existing | Matched by GitHub URL | |
| 3.1d | `RecipeRaiders` flagged existing | Matched by GitHub URL | |
| 3.1e | `BrandAmbassador` flagged existing | Matched by GitHub URL | |
| 3.1f | URL normalization works | Case differences and `.git` suffix differences still match | |

### 3.2 Project Creation via `manage_project` MCP

| # | Check | Expected | Status |
|---|-------|----------|--------|
| 3.2a | `manage_project` called per new project | One call per new GitHub project | |
| 3.2b | New projects created | ~20 new projects (total 26 minus ~6 existing) | |
| 3.2c | Project titles correct | Match directory names | |
| 3.2d | `github_repo` set | Normalized URL for each | |
| 3.2e | Tags populated | Languages + infra markers merged into tags | |
| 3.2f | Metadata has deps | `metadata.dependencies` present | |
| 3.2g | Metadata has scanner info | `metadata.scanned_from` and `metadata.scanner_version` present | |

### 3.3 Project Group Parent Creation

| # | Check | Expected | Status |
|---|-------|----------|--------|
| 3.3a | Group parent created | `reference_repos` project exists in Cortex | |
| 3.3b | Parent has no github_repo | `github_repo` is null | |
| 3.3c | Parent tagged | Tags include `"project-group"` | |
| 3.3d | Children linked | `PostmanFastAPIDemo` has `parent_project_id` set to group parent | |

### 3.4 Duplicate Remote URL Handling

| # | Check | Expected | Status |
|---|-------|----------|--------|
| 3.4a | Both `continuumMain` and `continuumNG_ONLYREFERENCE` created | Both are valid local repos despite same remote | |
| 3.4b | OR one flagged as duplicate | Skill notes the URL collision and asks user how to handle | |

---

## Phase 4 — Verify Config Files Written

### 4.1 Apply Config Files via Script

After projects are created, the skill runs:
```bash
python3 cortex-scanner.py --apply --payload-file <TEMP_DIR>/cortex-apply-payload.json --extensions-tarball <TEMP_DIR>/cortex-extensions.tar.gz
```

| # | Check | Expected | Status |
|---|-------|----------|--------|
| 4.1a | `--apply` mode invoked | Script called with `--apply --payload-file` | |
| 4.1b | Payload written to temp file | JSON file contains project ID mappings | |
| 4.1c | Extensions tarball downloaded | Downloaded from Cortex MCP endpoint | |
| 4.1d | Script exits 0 | No errors from apply run | |

### 4.2 Spot Check: AIOps Project

```bash
cat ~/projects/AIOps/.claude/cortex-config.json
cat ~/projects/AIOps/.claude/cortex-state.json
ls ~/projects/AIOps/.claude/settings.local.json
```

| # | Check | Expected | Status |
|---|-------|----------|--------|
| 4.2a | `.claude/` directory exists | Created by scanner | |
| 4.2b | `cortex-config.json` valid | Contains `project_id`, `cortex_api_url`, `cortex_mcp_url` | |
| 4.2c | `installed_by` is `"scanner"` | Not `"setup"` | |
| 4.2d | `cortex-state.json` valid | Contains `system_fingerprint`, `system_name: "WIN_AI_PC_WSL"` | |
| 4.2e | `settings.local.json` present | Contains `hooks.PostToolUse` with observation hook | |
| 4.2f | `.gitignore` updated | Contains `# Cortex` section | |

### 4.3 Spot Check: Group Child Project

```bash
cat ~/projects/reference_repos/PostmanFastAPIDemo/.claude/cortex-config.json
```

| # | Check | Expected | Status |
|---|-------|----------|--------|
| 4.3a | Config written | File exists with valid JSON | |
| 4.3b | Project ID correct | Matches PostmanFastAPIDemo project in Cortex | |
| 4.3c | `installed_by: "scanner"` | Scanner provenance marker present | |

### 4.4 Verify .gitignore Idempotency

```bash
grep -c "# Cortex" ~/projects/AIOps/.gitignore
```

| # | Check | Expected | Status |
|---|-------|----------|--------|
| 4.4a | No duplicate entries | `"# Cortex"` appears exactly once | |
| 4.4b | Original entries preserved | Pre-existing `.gitignore` entries still present | |

### 4.5 Extension Installation

| # | Check | Expected | Status |
|---|-------|----------|--------|
| 4.5a | `.claude/skills/` exists | Created by scanner for new projects | |
| 4.5b | Extension files present | Skill files extracted from tarball | |
| 4.5c | `extensions_hash` in config | SHA-256 hash present in `cortex-config.json` | |
| 4.5d | All hashes match | Same hash across all projects from this scan | |

---

## Phase 5 — Verify Knowledge Base Ingestion

### 5.1 Inline README Ingestion via `manage_rag_source` MCP

| # | Check | Expected | Status |
|---|-------|----------|--------|
| 5.1a | `manage_rag_source` called | One call per created project with a `readme_excerpt` | |
| 5.1b | Source type is inline | `source_type: "inline"`, NOT `"url"` | |
| 5.1c | Content from local disk | `documents` contains locally-read README content | |
| 5.1d | Batched for large scans | Calls made in groups of 5 (20+ projects) | |
| 5.1e | Knowledge sources created | Sources appear in Cortex UI under Knowledge | |
| 5.1f | Project linking | Each source is linked to its project (`project_id` set) | |

### 5.2 Verify in Cortex UI

| # | Check | Expected | Status |
|---|-------|----------|--------|
| 5.2a | Sources listed | README sources visible for created projects | |
| 5.2b | Ingestion status | Shows completed (inline is near-instant) | |
| 5.2c | No external crawls | No URL-based sources created for READMEs | |

### 5.3 RAG Search Test

> "Search the Cortex knowledge base for information about recipe management."

| # | Check | Expected | Status |
|---|-------|----------|--------|
| 5.3a | Results returned | RAG search finds content from RecipeRaiders README | |

---

## Phase 6 — Post-Scanner Workflow Validation

### 6.1 Open Claude Code in a Scanned Project

```bash
cd ~/projects/AIOps
claude
```

| # | Check | Expected | Status |
|---|-------|----------|--------|
| 6.1a | cortex-context injected | SessionStart hook runs and injects `<cortex-context>` | |
| 6.1b | Project recognized | Context shows project with correct project ID | |
| 6.1c | System registered | System `WIN_AI_PC_WSL` is linked to this project | |
| 6.1d | Observation hook active | PostToolUse hook fires | |

### 6.2 Open Claude Code in a Group Child

```bash
cd ~/projects/reference_repos/PostmanFastAPIDemo
claude
```

| # | Check | Expected | Status |
|---|-------|----------|--------|
| 6.2a | Correct project context | Shows PostmanFastAPIDemo, not the group parent | |
| 6.2b | Config files valid | Both JSON files readable and correct | |

### 6.3 Verify Cortex UI

Open `http://localhost:3737` → Projects page.

| # | Check | Expected | Status |
|---|-------|----------|--------|
| 6.3a | All created projects visible | New projects from scan appear | |
| 6.3b | Group parent visible | `reference_repos` listed as a project | |
| 6.3c | Descriptions shown | AI-generated descriptions on project cards | |
| 6.3d | Tags populated | Language and infrastructure tags visible | |

---

## Phase 7 — Idempotency

### 7.1 Re-Run `/scan-projects`

> "Scan my projects directory again."

| # | Check | Expected | Status |
|---|-------|----------|--------|
| 7.1a | Skill re-downloads script | Fresh `cortex-scanner.py` fetched | |
| 7.1b | Scan runs successfully | Script exits 0 | |
| 7.1c | `find_projects` called | Dedup check runs against updated Cortex state | |
| 7.1d | All projects flagged existing | Every project from Phase 3 shows as already in Cortex | |
| 7.1e | New project count is 0 | No new `manage_project` calls | |

### 7.2 Re-Apply Is Safe

> "Write the config files again for my scanned projects."

| # | Check | Expected | Status |
|---|-------|----------|--------|
| 7.2a | No duplicate projects | No new projects created | |
| 7.2b | Config files overwritten cleanly | `.claude/` files valid after re-apply | |
| 7.2c | `.gitignore` not duplicated | `# Cortex` appears exactly once | |

---

## Phase 8 — Edge Cases

### 8.1 Python Not Found

On a machine where `python3`/`python` are not installed:

| # | Check | Expected | Status |
|---|-------|----------|--------|
| 8.1a | Clear error | "Python 3.8+ not found. Please install Python." | |
| 8.1b | Skill stops cleanly | No partial state created | |

### 8.2 Cortex Not Running

Stop Cortex, then invoke `/scan-projects`:

| # | Check | Expected | Status |
|---|-------|----------|--------|
| 8.2a | Script download fails | "Can't reach Cortex at http://localhost:8181" | |
| 8.2b | Skill aborts cleanly | No temp files left, no partial Cortex state | |

### 8.3 Empty Directory

```bash
mkdir ~/projects/empty-test
```

> "Scan ~/projects/empty-test"

| # | Check | Expected | Status |
|---|-------|----------|--------|
| 8.3a | No error | Scan completes successfully | |
| 8.3b | Zero results | `Total repositories found: 0` | |
| 8.3c | No MCP calls | No `manage_project` calls made | |

### 8.4 Permission Denied

| # | Check | Expected | Status |
|---|-------|----------|--------|
| 8.4a | Warning in output | Includes the specific unreadable path | |
| 8.4b | Other projects unaffected | Remaining dirs still scanned | |

---

## Phase 9 — Multi-System Registration

**This is the primary motivation for the client-side rearchitecture.** Multiple machines
scan their own local projects and register them against the same Cortex instance.

### 9.1 System 2: MacBookPro_M1

The MacBook has its own `~/projects/` directory with a different set of repos, plus
some repos that also exist on WIN_AI_PC_WSL (e.g., `cortex`, `RecipeRaiders`).

**Pre-requisites on MacBook:**
- [ ] Claude Code installed
- [ ] `/cortex-setup` run once (registers `MacBookPro_M1` as a system)
- [ ] Cortex MCP configured pointing at `http://<WSL_IP>:8181` and `http://<WSL_IP>:8051`

| # | Check | Expected | Status |
|---|-------|----------|--------|
| 9.1a | System registered | `MacBookPro_M1` appears in Cortex systems | |
| 9.1b | Unique fingerprint | Different `system_fingerprint` from `WIN_AI_PC_WSL` | |
| 9.1c | Cortex API reachable | `curl http://<WSL_IP>:8181/health` returns 200 | |
| 9.1d | Script endpoint reachable | `curl http://<WSL_IP>:8181/api/scanner/script | head -1` returns shebang | |

### 9.2 Run `/scan-projects` on MacBook

> "Scan my local projects directory."

| # | Check | Expected | Status |
|---|-------|----------|--------|
| 9.2a | Script downloaded from remote Cortex | `GET http://<WSL_IP>:8181/api/scanner/script` succeeds | |
| 9.2b | Scan runs locally on Mac | Script scans the Mac's `~/projects/`, NOT WSL's | |
| 9.2c | `find_projects` sees ALL Cortex projects | Dedup includes projects created by WSL scan | |
| 9.2d | Shared repos flagged existing | `cortex`, `RecipeRaiders` etc. detected as already in Cortex | |
| 9.2e | Mac-only repos flagged new | Repos only on Mac are created as new projects | |
| 9.2f | Config files written locally | `.claude/` dirs created on the Mac filesystem | |

### 9.3 Verify Per-System Config Files on MacBook

```bash
# On MacBookPro_M1
cat ~/projects/<new-mac-project>/.claude/cortex-state.json
```

| # | Check | Expected | Status |
|---|-------|----------|--------|
| 9.3a | `system_name` is `MacBookPro_M1` | NOT `WIN_AI_PC_WSL` | |
| 9.3b | `system_fingerprint` is Mac's | Different from WSL fingerprint | |
| 9.3c | `cortex_api_url` is remote | Points to `http://<WSL_IP>:8181`, not localhost | |

### 9.4 Verify No Cross-System Pollution

| # | Check | Expected | Status |
|---|-------|----------|--------|
| 9.4a | WSL config files unchanged | WSL's `cortex-state.json` files still say `WIN_AI_PC_WSL` | |
| 9.4b | Mac-only projects not on WSL | Mac-only repos have no `.claude/` dir on WSL | |
| 9.4c | Shared projects not duplicated | `cortex` project in Cortex DB still has ONE entry | |

### 9.5 System 3: WhiteShark_AI_Server (Ubuntu)

Repeat the scan from the Ubuntu server.

| # | Check | Expected | Status |
|---|-------|----------|--------|
| 9.5a | System registered | `WhiteShark_AI_Server` appears in Cortex | |
| 9.5b | `python3` detected | Skill finds python3 on Ubuntu | |
| 9.5c | Scan runs locally | Scans the server's `~/projects/` | |
| 9.5d | Dedup sees WSL + Mac projects | All previously created projects flagged existing | |
| 9.5e | Server-only repos created | New projects unique to this server | |
| 9.5f | Config files written on server | `.claude/cortex-state.json` has `system_name: "WhiteShark_AI_Server"` | |
| 9.5g | `cortex_api_url` is remote | Points to `http://<WSL_IP>:8181` | |

### 9.6 System 4: WIN_AI_PC (Windows, non-WSL)

Test the Windows-specific code paths.

| # | Check | Expected | Status |
|---|-------|----------|--------|
| 9.6a | Python detected | Skill finds `python` or `py` (not `python3`) on Windows | |
| 9.6b | Temp dir resolved | Uses `%TEMP%` (e.g., `C:\Users\winadmin\AppData\Local\Temp`) | |
| 9.6c | Script runs on Windows | `python cortex-scanner.py --scan C:\Users\winadmin\projects` works | |
| 9.6d | Config files use Windows paths | `absolute_path` in scan output uses Windows-style paths | |
| 9.6e | `.claude/` dirs created | Windows file system paths for config files | |
| 9.6f | System name is `WIN_AI_PC` | Distinct from `WIN_AI_PC_WSL` | |
| 9.6g | Cortex URL is localhost | Windows host can reach Docker via `http://localhost:8181` | |

### 9.7 Verify All Systems in Cortex

After all 4 systems have scanned:

| # | Check | Expected | Status |
|---|-------|----------|--------|
| 9.7a | 4 systems registered | All 4 system fingerprints in Cortex | |
| 9.7b | No duplicate projects | Shared repos (cortex, RecipeRaiders) each have ONE project in Cortex | |
| 9.7c | System-project links correct | Each system registered to its own set of projects | |
| 9.7d | Total project count reasonable | Sum of unique projects across all systems | |

---

## Phase 10 — Extension Version Tracking

### 10.1 Extension Hash Consistency (Single System)

All projects set up from a single scan should have the same extensions hash.

```bash
for dir in ~/projects/AIOps ~/projects/emailBrain ~/projects/gravityClaw; do
  echo "$(basename $dir): $(python3 -c "import json; d=json.load(open('$dir/.claude/cortex-config.json')); print(d.get('extensions_hash','N/A'))")"
done
```

| # | Check | Expected | Status |
|---|-------|----------|--------|
| 10.1a | Hashes match | All projects from same scan have identical `extensions_hash` | |
| 10.1b | Timestamps close | `extensions_installed_at` values within seconds of each other | |

---

## Test Results Summary

| Phase | Description | Checks | Pass | Fail | Skip |
|-------|-------------|--------|------|------|------|
| 0 | Verify Prerequisites | 7 | | | |
| 1 | Scan Directory | 22 | | | |
| 2 | AI Descriptions | 7 | | | |
| 3 | Dedup and Create | 18 | | | |
| 4 | Config Files | 15 | | | |
| 5 | Knowledge Base | 10 | | | |
| 6 | Post-Scanner Workflow | 8 | | | |
| 7 | Idempotency | 8 | | | |
| 8 | Edge Cases | 9 | | | |
| 9 | Multi-System | 25 | | | |
| 10 | Extension Versions | 2 | | | |
| **Total** | | **131** | | | |

---

## Bugs Found

| # | Phase | System | Severity | Description | Status |
|---|-------|--------|----------|-------------|--------|
| 1 | 5 | WIN_AI_PC_WSL | Critical | Crawl queue state was in-memory only — lost on server restart | Fixed: T5 |
| 2 | 5 | WIN_AI_PC_WSL | Critical | Recursive crawling followed hundreds of unrelated GitHub links for README crawls | Fixed: T1 (replaced with inline) |
| 3 | All | WIN_AI_PC_WSL | High | MCP session breaks on server restart — all tool calls fail | Mitigated: T8 (recovery guidance) |
| 4 | 5 | WIN_AI_PC_WSL | Medium | REST crawl endpoint didn't link project_id until after crawl completed | Fixed: T4 |
| 5 | 5 | WIN_AI_PC_WSL | Critical | Local README ingestion not used — unnecessary external crawls | Fixed: T1 |
| 6 | 3 | WIN_AI_PC_WSL | Medium | No dedup within scan results — same GitHub URL created twice | Fixed: T2 |
| 7 | 3 | WIN_AI_PC_WSL | Medium | No title-based fallback dedup for projects without github_repo | Fixed: T2 |
| 8 | 5 | WIN_AI_PC_WSL | Medium | No bulk progress monitoring — had to check 17 IDs individually | Fixed: T7 |
| 9 | 4 | WIN_AI_PC_WSL | Low | PostmanFastAPIDemo directory not found during apply step | Fixed: T3 |
| 10 | 5 | WIN_AI_PC_WSL | Critical | 17 simultaneous crawls overwhelmed server causing OOM crash | Fixed: T6 |

---

## Notes

- The scanner script runs locally on each machine — no Docker volume mount
- Script is fetched fresh from the Cortex API each time `/scan-projects` runs
- Dedup logic lives in the skill (client-side) — `find_projects` MCP is the source of truth
- Config files are written by the local Python script, not by Cortex server
- Private GitHub repos will have README crawl failures but projects are still created
- The scanner is a one-time bulk onboarding tool; new individual projects use `/cortex-setup`
- Cross-platform: Windows (`python`/`py`), Mac/Linux (`python3`) — same script
- `continuumMain` and `continuumNG_ONLYREFERENCE` share the same remote — tests URL-based dedup edge case
- Remote systems need Cortex ports (8181, 8051) accessible over the network
