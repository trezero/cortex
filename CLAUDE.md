# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Beta Development Guidelines

**Local-only deployment** - each user runs their own instance.

### Extension Install Scope

**Never install extensions, commands, or plugins into `~/.claude` (the user's global folder).** Everything must be installed into the `.claude` directory within the repo the user is working in. If the `.claude` directory does not exist, create it. This applies to skills, commands, plugins, config files, and any other Archon-managed artifacts. The only exception is if the user has explicitly set `"install_scope": "global"` in their `archon-config.json`.

### Core Principles

- **No backwards compatibility; we follow a fix‑forward approach** — remove deprecated code immediately
- **Detailed errors over graceful failures** - we want to identify and fix issues fast
- **Break things to improve them** - beta is for rapid iteration
- **Continuous improvement** - embrace change and learn from mistakes
- **KISS** - keep it simple
- **DRY** when appropriate
- **YAGNI** — don't implement features that are not needed

### Error Handling

**Core Principle**: In beta, we need to intelligently decide when to fail hard and fast to quickly address issues, and when to allow processes to complete in critical services despite failures. Read below carefully and make intelligent decisions on a case-by-case basis.

#### When to Fail Fast and Loud (Let it Crash!)

These errors should stop execution and bubble up immediately: (except for crawling flows)

- **Service startup failures** - If credentials, database, or any service can't initialize, the system should crash with a clear error
- **Missing configuration** - Missing environment variables or invalid settings should stop the system
- **Database connection failures** - Don't hide connection issues, expose them
- **Authentication/authorization failures** - Security errors must be visible and halt the operation
- **Data corruption or validation errors** - Never silently accept bad data, Pydantic should raise
- **Critical dependencies unavailable** - If a required service is down, fail immediately
- **Invalid data that would corrupt state** - Never store zero embeddings, null foreign keys, or malformed JSON

#### When to Complete but Log Detailed Errors

These operations should continue but track and report failures clearly:

- **Batch processing** - When crawling websites or processing documents, complete what you can and report detailed failures for each item
- **Background tasks** - Embedding generation, async jobs should finish the queue but log failures
- **WebSocket events** - Don't crash on a single event failure, log it and continue serving other clients
- **Optional features** - If projects/tasks are disabled, log and skip rather than crash
- **External API calls** - Retry with exponential backoff, then fail with a clear message about what service failed and why

#### Critical Nuance: Never Accept Corrupted Data

When a process should continue despite failures, it must **skip the failed item entirely** rather than storing corrupted data

#### Error Message Guidelines

- Include context about what was being attempted when the error occurred
- Preserve full stack traces with `exc_info=True` in Python logging
- Use specific exception types, not generic Exception catching
- Include relevant IDs, URLs, or data that helps debug the issue
- Never return None/null to indicate failure - raise an exception with details
- For batch operations, always report both success count and detailed failure list

### User-Facing Change Propagation

After every code change, tell the user what steps are needed to see the effect on their running systems. Use this reference:

| What changed | How to propagate |
|---|---|
| **Backend Python** (`python/src/server/`, `python/src/mcp_server/`) | Restart Docker: `docker compose restart archon-server archon-mcp` (or re-run `uv run python -m src.server.main` if running locally) |
| **Frontend** (`archon-ui-main/`) | Auto-reloads if `npm run dev` is running; otherwise `npm run build` + refresh |
| **Setup scripts** (`integrations/claude-code/setup/archonSetup.sh`, `archonSetup.bat`) | Re-download and re-run the script on each target machine. The scripts are served dynamically by the backend, so restart the backend first, then re-download via `curl <archon_api_url>/api/setup/script-sh` (or `/script-bat`). Running `/archon-setup` inside Claude Code does NOT re-run these — it only bootstraps extensions. |
| **Scanner script** (`python/src/server/static/archon-scanner.py`) | Restart backend (script is served from static files), then re-run `/scan-projects` |
| **Extensions / skills** (`integrations/claude-code/skills/`, `integrations/claude-code/plugins/`) | Restart backend, then run `/archon-setup` or `/archon-extension-sync` in each project |
| **MCP tool definitions** (`python/src/mcp_server/features/`) | Restart Docker: `docker compose restart archon-mcp` |
| **Hook commands** (written into `~/.claude/settings.json` by setup scripts) | Re-download and re-run the setup script (`archonSetup.sh` / `.bat`). Existing hook entries must be overwritten — the script handles this. |
| **Docker Compose / Dockerfile** | `docker compose up --build -d` |
| **Database migrations** (`python/src/server/migrations/`) | Run migration manually against Supabase |
| **CLAUDE.md / ai_docs** | Takes effect on next Claude Code session (no restart needed) |

### Code Quality

- Remove dead code immediately rather than maintaining it - no backward compatibility or legacy functions
- Avoid backward compatibility mappings or legacy function wrappers
- Fix forward
- Focus on user experience and feature completeness
- When updating code, don't reference what is changing (avoid keywords like SIMPLIFIED, ENHANCED, LEGACY, CHANGED, REMOVED), instead focus on comments that document just the functionality of the code
- When commenting on code in the codebase, only comment on the functionality and reasoning behind the code. Refrain from speaking to Archon being in "beta" or referencing anything else that comes from these global rules.

## LeaveOff Point Protocol

### After Every Coding Task
After completing any coding task that adds, modifies, or removes functionality, you MUST
update the LeaveOff Point before moving to the next task:

1. Run `git status --porcelain` to check for uncommitted changes.
2. Call `manage_leaveoff_point(action="update")` with:
   - `content`: What was accomplished in this task (be specific about files changed and why)
   - `component`: The architectural module or feature area (e.g., "Authentication Module")
   - `next_steps`: Concrete, actionable items for the next session (not vague — include file paths)
   - `references`: PRPs, design docs, or key files that informed this work
   - `system_name`: Read from `.claude/archon-state.json` field "system_name", or fall back to hostname
   - `git_clean`: `true` if `git status --porcelain` output is empty, `false` otherwise
3. If `git_clean` is `false`, tell the user: "There are uncommitted changes. Consider
   committing your work to GitHub before ending this session."
4. This is NOT optional. Skipping this step means the next session starts with no context.

### Session Resource Management (The 90% Rule)
When you observe any of these signals, you are approaching resource limits:
- The conversation has exceeded 80+ tool uses
- You receive a system reminder about observation count
- You sense the conversation has been running extensively

Upon detecting these signals:
1. **Stop active coding immediately** — do not start new tasks
2. Run `git status --porcelain` to check for uncommitted changes
3. **Generate a final LeaveOff Point** via `manage_leaveoff_point(action="update")` with
   comprehensive next_steps covering all remaining planned work, including `system_name`
   and `git_clean`
4. If there are uncommitted changes, **advise the user to commit** before ending the session
5. **Advise the user**: "This session has reached its resource limit. The LeaveOff Point
   has been saved. Please start a new session to continue — context will be restored
   automatically."
6. **Do not continue coding** after generating the final LeaveOff Point

### Session Start
At the beginning of every session, the LeaveOff Point is automatically loaded via the
session start hook. You do not need to fetch it manually. Review the injected context
and orient your work around the documented next steps.

## Development Commands

### Frontend (archon-ui-main/)

```bash
npm run dev              # Start development server on port 3737
npm run build            # Build for production
npm run lint             # Run ESLint on legacy code (excludes /features)
npm run lint:files path/to/file.tsx  # Lint specific files

# Biome for /src/features directory only
npm run biome            # Check features directory
npm run biome:fix        # Auto-fix issues
npm run biome:format     # Format code (120 char lines)
npm run biome:ai         # Machine-readable JSON output for AI
npm run biome:ai-fix     # Auto-fix with JSON output

# Testing
npm run test             # Run all tests in watch mode
npm run test:ui          # Run with Vitest UI interface
npm run test:coverage:stream  # Run once with streaming output
vitest run src/features/projects  # Test specific directory

# TypeScript
npx tsc --noEmit         # Check all TypeScript errors
npx tsc --noEmit 2>&1 | grep "src/features"  # Check features only
```

### Backend (python/)

```bash
# Using uv package manager (preferred)
uv sync --group all      # Install all dependencies
uv run python -m src.server.main  # Run server locally on 8181
uv run pytest            # Run all tests
uv run pytest tests/test_api_essentials.py -v  # Run specific test
uv run ruff check        # Run linter
uv run ruff check --fix  # Auto-fix linting issues
uv run mypy src/         # Type check

# Agent Work Orders Service (independent microservice)
make agent-work-orders  # Run agent work orders service locally on 8053
# Or manually:
uv run python -m uvicorn src.agent_work_orders.server:app --port 8053 --reload

# Docker operations
docker compose up --build -d       # Start all services
docker compose --profile backend up -d  # Backend only (for hybrid dev)
docker compose --profile work-orders up -d   # Include agent work orders service
docker compose logs -f archon-server    # View server logs
docker compose logs -f archon-mcp       # View MCP server logs
docker compose logs -f archon-agent-work-orders  # View agent work orders service logs
docker compose restart archon-server    # Restart after code changes
docker compose down      # Stop all services
docker compose down -v   # Stop and remove volumes
```

### Quick Workflows

```bash
# Hybrid development (recommended) - backend in Docker, frontend local
make dev                 # Or manually: docker compose --profile backend up -d && cd archon-ui-main && npm run dev

# Hybrid with Agent Work Orders Service - backend in Docker, agent work orders local
make dev-work-orders     # Starts backend in Docker, prompts to run agent service in separate terminal
# Then in separate terminal:
make agent-work-orders   # Start agent work orders service locally

# Full Docker mode
make dev-docker          # Or: docker compose up --build -d
docker compose --profile work-orders up -d  # Include agent work orders service

# All Local (3 terminals) - for agent work orders service development
# Terminal 1: uv run python -m uvicorn src.server.main:app --port 8181 --reload
# Terminal 2: make agent-work-orders
# Terminal 3: cd archon-ui-main && npm run dev

# Run linters before committing
make lint                # Runs both frontend and backend linters
make lint-fe             # Frontend only (ESLint + Biome)
make lint-be             # Backend only (Ruff + MyPy)

# Testing
make test                # Run all tests
make test-fe             # Frontend tests only
make test-be             # Backend tests only
```

## Architecture Overview

@PRPs/ai_docs/ARCHITECTURE.md

#### TanStack Query Implementation

For architecture and file references:
@PRPs/ai_docs/DATA_FETCHING_ARCHITECTURE.md

For code patterns and examples:
@PRPs/ai_docs/QUERY_PATTERNS.md

#### Service Layer Pattern

See implementation examples:
- API routes: `python/src/server/api_routes/projects_api.py`
- Service layer: `python/src/server/services/project_service.py`
- Pattern: API Route → Service → Database

#### Error Handling Patterns

See implementation examples:
- Custom exceptions: `python/src/server/exceptions.py`
- Exception handlers: `python/src/server/main.py` (search for @app.exception_handler)
- Service error handling: `python/src/server/services/` (various services)

## ETag Implementation

@PRPs/ai_docs/ETAG_IMPLEMENTATION.md

## Database Schema

Key tables in Supabase:

- `sources` - Crawled websites and uploaded documents
  - Stores metadata, crawl status, and configuration
- `documents` - Processed document chunks with embeddings
  - Text chunks with vector embeddings for semantic search
- `projects` - Project management (optional feature)
  - Contains features array, documents, and metadata
- `tasks` - Task tracking linked to projects
  - Status: todo, doing, review, done
  - Assignee: User, Archon, AI IDE Agent
- `code_examples` - Extracted code snippets
  - Language, summary, and relevance metadata

## API Naming Conventions

@PRPs/ai_docs/API_NAMING_CONVENTIONS.md

Use database values directly (no FE mapping; type‑safe end‑to‑end from BE upward):

## Environment Variables

Required in `.env`:

```bash
SUPABASE_URL=https://your-project.supabase.co  # Or http://host.docker.internal:8000 for local
SUPABASE_SERVICE_KEY=your-service-key-here      # Use legacy key format for cloud Supabase
```

Optional variables and full configuration:
See `python/.env.example` for complete list

### Repository Configuration

Repository information (owner, name) is centralized in `python/src/server/config/version.py`:
- `GITHUB_REPO_OWNER` - GitHub repository owner (default: "coleam00")
- `GITHUB_REPO_NAME` - GitHub repository name (default: "Archon")

This is the single source of truth for repository configuration. All services (version checking, bug reports, etc.) should import these constants rather than hardcoding repository URLs.

Environment variable override: `GITHUB_REPO="owner/repo"` can be set to override defaults.

## Common Development Tasks

### Add a new API endpoint

1. Create route handler in `python/src/server/api_routes/`
2. Add service logic in `python/src/server/services/`
3. Include router in `python/src/server/main.py`
4. Update frontend service in `archon-ui-main/src/features/[feature]/services/`

### Add a new UI component in features directory

**IMPORTANT**: Review UI design standards in `@PRPs/ai_docs/UI_STANDARDS.md` before creating UI components.

1. Use Radix UI primitives from `src/features/ui/primitives/`
2. Create component in relevant feature folder under `src/features/[feature]/components/`
3. Define types in `src/features/[feature]/types/`
4. Use TanStack Query hook from `src/features/[feature]/hooks/`
5. Apply Tron-inspired glassmorphism styling with Tailwind
6. Follow responsive design patterns (mobile-first with breakpoints)
7. Ensure no dynamic Tailwind class construction (see UI_STANDARDS.md Section 2)

### Add or modify MCP tools

1. MCP tools are in `python/src/mcp_server/features/[feature]/[feature]_tools.py`
2. Follow the pattern:
   - `find_[resource]` - Handles list, search, and get single item operations
   - `manage_[resource]` - Handles create, update, delete with an "action" parameter
3. Register tools in the feature's `__init__.py` file

### Debug MCP connection issues

1. Check MCP health: `curl http://localhost:8051/health`
2. View MCP logs: `docker compose logs archon-mcp`
3. Test tool execution via UI MCP page
4. Verify Supabase connection and credentials

### Fix TypeScript/Linting Issues

```bash
# TypeScript errors in features
npx tsc --noEmit 2>&1 | grep "src/features"

# Biome auto-fix for features
npm run biome:fix

# ESLint for legacy code
npm run lint:files src/components/SomeComponent.tsx
```

## Code Quality Standards

### Frontend

- **TypeScript**: Strict mode enabled, no implicit any
- **Biome** for `/src/features/`: 120 char lines, double quotes, trailing commas
- **ESLint** for legacy code: Standard React rules
- **Testing**: Vitest with React Testing Library

### Backend

- **Python 3.12** with 120 character line length
- **Ruff** for linting - checks for errors, warnings, unused imports
- **Mypy** for type checking - ensures type safety
- **Pytest** for testing with async support

## MCP Tools Available

When connected to Claude/Cursor/Windsurf, the following tools are available:

### Knowledge Base Tools

- `archon:rag_search_knowledge_base` - Search knowledge base for relevant content
- `archon:rag_search_code_examples` - Find code snippets in the knowledge base
- `archon:rag_get_available_sources` - List available knowledge sources
- `archon:rag_list_pages_for_source` - List all pages for a given source (browse documentation structure)
- `archon:rag_read_full_page` - Retrieve full page content by page_id or URL

### Project Management

- `archon:find_projects` - Find all projects, search, or get specific project (by project_id)
- `archon:manage_project` - Manage projects with actions: "create", "update", "delete"

### Task Management

- `archon:find_tasks` - Find tasks with search, filters, or get specific task (by task_id)
- `archon:manage_task` - Manage tasks with actions: "create", "update", "delete"

### Document Management

- `archon:find_documents` - Find documents, search, or get specific document (by document_id)
- `archon:manage_document` - Manage documents with actions: "create", "update", "delete"

### Version Control

- `archon:find_versions` - Find version history or get specific version
- `archon:manage_version` - Manage versions with actions: "create", "restore"

### Extension Management

- `archon:find_extensions` - Find all extensions, search, or get specific extension (by extension_id)
- `archon:manage_extensions` - Manage extensions with actions: "create", "update", "delete"

### Session Memory

- `archon:archon_search_sessions` - Search session history across agents and machines
- `archon:archon_get_session` - Get a specific session with all its observations

## Important Notes

- Projects feature is optional - toggle in Settings UI
- TanStack Query handles all data fetching; smart HTTP polling is used where appropriate (no WebSockets)
- Frontend uses Vite proxy for API calls in development
- Python backend uses `uv` for dependency management
- Docker Compose handles service orchestration
- TanStack Query for all data fetching - NO PROP DRILLING
- Vertical slice architecture in `/features` - features own their sub-features
