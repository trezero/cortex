# Archon v0.3.2 Upgrade Analysis Report

**Generated:** 2026-04-08
**Current Version:** 0.1.0 (Python/FastAPI + React)
**Target Version:** 0.3.2 (TypeScript/Bun CLI - "Archon CLI")
**Recommendation:** DO NOT UPGRADE. The upstream is a completely different product.

---

## Executive Summary

The "Update Available: v0.3.2" banner in the Archon UI is **misleading**. The upstream `coleam00/Archon` repository has undergone a **complete rewrite** — it is no longer a Python/FastAPI + React knowledge management platform. It has been rebuilt from scratch as a **TypeScript/Bun CLI tool** called "Archon CLI." There is **no common git ancestor** between our v0.1.0 tag and the v0.3.2 tag. These are fundamentally different products that happen to share a GitHub repository URL.

**A merge or upgrade is not possible.** This report documents the findings and recommends concrete actions.

---

## What Happened to Upstream Archon

### Before (v0.1.0 — our fork point)
| Aspect | Details |
|--------|---------|
| **Language** | Python 3.12 + TypeScript/React |
| **Backend** | FastAPI on port 8181 |
| **Frontend** | React 18 + Vite + TanStack Query |
| **Database** | Supabase (PostgreSQL + pgvector) |
| **Purpose** | Knowledge management platform with RAG, project management, MCP tools |
| **Architecture** | Monolithic with vertical slice frontend |
| **Structure** | `python/`, `archon-ui-main/`, `integrations/` |

### After (v0.3.2 — current upstream)
| Aspect | Details |
|--------|---------|
| **Language** | TypeScript (Bun runtime) |
| **Architecture** | Monorepo with compiled CLI binaries |
| **Purpose** | CLI tool for AI workflow orchestration |
| **Packages** | `packages/core`, `packages/cli`, `packages/web`, `packages/workflows`, `packages/adapters`, `packages/server`, `packages/docs-web`, `packages/git`, `packages/isolation`, `packages/paths` |
| **Adapters** | Slack, Telegram, Discord, Gitea |
| **Distribution** | Homebrew, curl install script, Docker, compiled binaries |
| **Python files** | **Zero** (0 Python files in entire repo) |
| **Our directories** | `python/` and `archon-ui-main/` **do not exist** upstream |

### Evidence of Complete Rewrite
1. **No common git ancestor** — `gh api repos/coleam00/Archon/compare/v0.1.0...v0.3.2` returns 404 ("No common ancestor")
2. **Zero Python files** in the upstream repository
3. **No `python/` or `archon-ui-main/` directories** exist upstream
4. All releases are titled "**Archon CLI**" — a different product category
5. The v0.1.0 tag appears to be the last tag before the complete rewrite; the next tag is v0.2.13, which is already the new TypeScript CLI

---

## Release Timeline (Upstream)

| Version | Date | Type | Notes |
|---------|------|------|-------|
| v0.1.0 | Pre-rewrite | Tag | Last version of Python/React Archon (our fork point) |
| v0.2.13 | 2026-04-07 | CLI Release | First available CLI release (rewrite already complete) |
| v0.3.0 | 2026-04-08 10:15 UTC | CLI Release | Env-leak-gate polish, build fixes, cloud-init hardening |
| v0.3.1 | 2026-04-08 12:14 UTC | Hotfix | Release workflow fix, SQLite schema migration |
| v0.3.2 | 2026-04-08 12:49 UTC | Hotfix | Claude SDK spawn fix, env-leak false positive fix |

All v0.2.x and v0.3.x releases are the **new TypeScript CLI product**, not updates to the Python/React platform we're running.

---

## Our Fork: Scale of Custom Development

Our fork has diverged massively from the original v0.1.0 baseline:

| Metric | Value |
|--------|-------|
| **Files modified** | 615 |
| **Lines added** | 120,650+ |
| **Lines removed** | 16,318 |
| **Custom services** | 11 major systems |
| **Custom API routes** | 11 new routes |
| **Custom frontend features** | 5 major modules |
| **Database migrations** | 033-034+ (custom) |

### Major Custom Systems (would be lost in any rewrite)
1. **Workflow Engine 2.0** — Full orchestration with HITL approvals, SSE, Telegram/UI channels
2. **Pattern Discovery Service** — AI-powered sequence mining with Haiku normalization, PrefixSpan, clustering
3. **Extensions System** — Custom type system with command support, registry-backed distribution
4. **Generative UI (A2UI)** — Deterministic approval templates, workflow rendering
5. **Auto-Research System** — Prompt optimization with evaluation framework
6. **LeaveOff Points** — Session persistence across machines
7. **Postman Integration** — Full API lifecycle management (80KB+ of code)
8. **Enhanced Chat System** — Complete UI rewrite with streaming, tool use cards
9. **Agent Work Orders** — Legacy workflow system (deprecated but present)
10. **Claude Code Integrations** — 7 extensions, plugins, setup scripts, scanner
11. **Knowledge Materialization** — Enhanced RAG pipeline

---

## Risk Analysis

### Risks of Attempting an "Upgrade"

| Risk | Severity | Details |
|------|----------|---------|
| **Total code loss** | CRITICAL | A merge is impossible — there's no common ancestor. Any attempt would require choosing one codebase entirely. |
| **Feature regression** | CRITICAL | All 11 custom systems would be lost. The upstream CLI has zero overlap with our feature set. |
| **Architecture incompatibility** | CRITICAL | Python/FastAPI vs TypeScript/Bun — completely different tech stacks, deployment models, and runtime requirements. |
| **Database loss** | HIGH | Upstream uses SQLite; we use Supabase/PostgreSQL with pgvector embeddings. Migration path does not exist. |
| **Integration breakage** | HIGH | All Claude Code extensions, MCP server, setup scripts reference our Python backend. |
| **Trinity platform breakage** | HIGH | Remote-Agent and Second-Brain (A2UI) integrate with our Python API — they cannot talk to a Bun CLI. |

### Risks of NOT Upgrading

| Risk | Severity | Details |
|------|----------|---------|
| **Misleading banner** | LOW | Users see "Update Available" for a product they can't use. Cosmetic issue only. |
| **Missing upstream bugfixes** | NONE | The upstream bugs (CLI binary spawn, env-leak gate) are in TypeScript code that doesn't exist in our fork. |
| **Community divergence** | LOW | Our fork serves a different use case. Community contributions to the CLI don't benefit us. |
| **Security patches** | LOW | Monitor upstream for any security advisories that might apply to shared concepts, but code-level patches won't apply. |

---

## Benefits Analysis

### Benefits of the Upstream v0.3.2
These benefits **do not apply to us** because the code is completely different:

- Fix for Claude SDK spawn failure in compiled Bun binaries — **N/A** (we don't use Bun)
- Fix for env-leak-gate false positive — **N/A** (we don't have this feature)
- Homebrew distribution — **N/A** (we deploy via Docker)

### Benefits of Staying on Our Fork
- All 120K+ lines of custom development preserved
- Stable Python/FastAPI backend with Supabase integration
- Full Trinity platform compatibility (Remote-Agent, A2UI)
- Active development on Pattern Discovery, Workflows 2.0
- MCP server, extensions system, and Claude Code integrations all working

---

## Recommended Actions

### Immediate (This Week)

#### 1. Suppress the Misleading Update Banner

**Option A: Point version checker at our own fork** (Recommended)

Update `python/src/server/config/version.py` to use our fork's repository:

```python
# Current (points to upstream — now a different product)
GITHUB_REPO_OWNER = "coleam00"
GITHUB_REPO_NAME = "Archon"

# Updated (points to our fork)
GITHUB_REPO_OWNER = "trezero"
GITHUB_REPO_NAME = "Archon"
```

This makes the version checker compare against our own releases. When we tag releases on our fork, the banner will correctly reflect our update status.

**Option B: Disable the version checker entirely**

If we don't plan to publish releases on our fork, disable the checker:
- Set `ARCHON_VERSION` to a high sentinel value, or
- Add a feature flag to disable version checking in settings

**Option C: Update ARCHON_VERSION to reflect our fork's maturity**

Our codebase has far surpassed v0.1.0. Consider bumping to a version that reflects reality (e.g., `1.0.0-trinity`) and tagging releases on our fork.

#### 2. Document the Fork Status

Add a note to `CLAUDE.md` or a `FORK_STATUS.md` documenting:
- We forked from `coleam00/Archon` at v0.1.0
- The upstream has been rewritten as a TypeScript CLI tool
- Our fork is the continuation of the original Python/React platform
- Version comparisons with upstream are no longer meaningful

### Medium-Term (This Month)

#### 3. Establish Our Own Release Process

- Tag meaningful milestones on the `trezero/Archon` fork
- Adopt a versioning scheme (e.g., `1.x.x-trinity` or simply `1.x.x`)
- The version checker will then correctly detect updates within our ecosystem

#### 4. Evaluate Upstream Concepts (Not Code)

While the upstream code is incompatible, some **concepts** may be worth evaluating:

| Upstream Concept | Our Equivalent | Worth Investigating? |
|-----------------|----------------|---------------------|
| Workflow orchestration | Workflows 2.0 | No — ours is more mature |
| Chat adapters (Slack, Telegram, Discord) | Telegram channel (HITL) | Maybe — multi-channel approval patterns |
| Env-leak protection | N/A | Yes — useful security concept for our MCP server |
| Compiled binary distribution | Docker + setup scripts | No — Docker serves us well |
| SQLite local storage | Supabase cloud | No — pgvector is critical for RAG |

#### 5. Cherry-Pick Design Ideas, Not Code

If any upstream architectural patterns are useful, implement them from scratch in our Python/React stack rather than attempting any merge.

### Long-Term

#### 6. Monitor Upstream for Conceptual Insights

The upstream Archon CLI may develop useful patterns around:
- AI workflow orchestration
- Multi-provider agent management
- Security hardening for AI tools

Track these at a design level, not a code level.

---

## What NOT To Do

| Action | Why It's Wrong |
|--------|---------------|
| `git merge upstream/main` | No common ancestor. Will fail or produce a franken-repo. |
| `git rebase` onto upstream | Would replace our entire codebase with the TypeScript CLI. |
| Manual file-by-file merge | Zero files overlap. There is nothing to merge. |
| Attempt to "port" upstream features | The upstream solves different problems. Our systems are more feature-complete for our use case. |
| Delete our version checker | The checker is good infrastructure — just needs to point at the right repo. |

---

## Implementation Plan

### Phase 1: Fix the Banner (30 minutes)

1. Update `GITHUB_REPO_OWNER` in `python/src/server/config/version.py` to `"trezero"`
2. Bump `ARCHON_VERSION` to `"1.0.0"` (or appropriate version)
3. Update `archon-ui-main/package.json` version to match
4. Restart backend services
5. Verify banner no longer shows

### Phase 2: Tag a Release (1 hour)

1. Create a `v1.0.0` tag on our fork's main branch
2. Write release notes summarizing our custom features
3. Push tag to `trezero/Archon`
4. Verify version checker works against our own releases

### Phase 3: Document Fork Status (30 minutes)

1. Add fork documentation explaining the divergence
2. Update any references to upstream that are no longer applicable
3. Ensure `CLAUDE.md` reflects our independent development status

---

## Conclusion

The v0.3.2 "update" is not an update to our software — it's a notification about a completely different product that happens to live in the same GitHub repository we originally forked from. Our fork represents **120,000+ lines of custom development** across 11 major systems that have no equivalent in the upstream. The recommended path is to acknowledge our fork's independence, fix the version checker to point at our own repository, and continue building on our platform.
