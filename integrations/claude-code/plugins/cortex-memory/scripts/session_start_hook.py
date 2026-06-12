#!/usr/bin/env python3
"""SessionStart hook — inject Cortex context into the new conversation.

Runs on SessionStart (startup, clear, compact). Outputs a context block to
stdout that Claude Code injects into the system prompt.

Also flushes any stale buffer left by a previous crashed session and
auto-updates the plugin if a newer version is available on the Cortex server.
"""

from __future__ import annotations

import asyncio
import io
import json
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

# Add plugin src directory to path so imports work regardless of cwd
_PLUGIN_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_PLUGIN_ROOT))

from src.cortex_client import CortexClient
from src.git_utils import check_git_dirty, load_system_id
from src.session_tracker import SessionTracker

_BUFFER_PATH = ".claude/cortex-memory-buffer.jsonl"
_TIMEOUT_SECONDS = 5


def _parse_version(v: str) -> tuple[int, ...]:
    """Parse a semver string like '1.2.3' into a comparable tuple."""
    try:
        return tuple(int(x) for x in v.split("."))
    except (ValueError, AttributeError):
        return (0, 0, 0)


async def _auto_update_plugin(mcp_url: str, plugin_dir: Path) -> str | None:
    """Check the Cortex server for a newer plugin version and apply it automatically.

    Returns a status message if updated, None if no update was needed or possible.
    """
    import httpx

    local_manifest = plugin_dir / ".claude-plugin" / "plugin.json"
    if not local_manifest.exists() or not mcp_url:
        return None

    try:
        local_version = json.loads(local_manifest.read_text(encoding="utf-8")).get("version", "0.0.0")
    except (json.JSONDecodeError, OSError):
        return None

    # Fetch remote version
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"{mcp_url}/cortex-setup/plugin-manifest")
            if resp.status_code != 200:
                return None
            remote_version = resp.json().get("version", "0.0.0")
    except Exception:
        return None

    if _parse_version(remote_version) <= _parse_version(local_version):
        return None

    # Download tarball
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{mcp_url}/cortex-setup/plugin/cortex-memory.tar.gz")
            if resp.status_code != 200:
                return None
    except Exception:
        return None

    # Extract and apply
    tmp_dir = Path(tempfile.mkdtemp())
    try:
        buf = io.BytesIO(resp.content)
        with tarfile.open(fileobj=buf, mode="r:gz") as tar:
            tar.extractall(tmp_dir, filter="data")

        extracted = tmp_dir / "cortex-memory"
        if not extracted.is_dir():
            return None

        # Check if requirements changed before overwriting
        old_reqs = (plugin_dir / "requirements.txt").read_text(encoding="utf-8") if (plugin_dir / "requirements.txt").exists() else ""
        new_reqs = (extracted / "requirements.txt").read_text(encoding="utf-8") if (extracted / "requirements.txt").exists() else ""
        reqs_changed = old_reqs.strip() != new_reqs.strip()

        # Copy new files into plugin dir, preserving .venv
        for item in list(plugin_dir.iterdir()):
            if item.name in (".venv", ".pytest_cache"):
                continue
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()

        for item in extracted.iterdir():
            if item.name in (".venv", ".pytest_cache"):
                continue
            dst = plugin_dir / item.name
            if item.is_dir():
                shutil.copytree(item, dst)
            else:
                shutil.copy2(item, dst)

        # Reinstall deps if requirements.txt changed
        if reqs_changed:
            venv_pip = plugin_dir / ".venv" / "bin" / "pip"
            reqs_file = plugin_dir / "requirements.txt"
            if venv_pip.exists() and reqs_file.exists():
                subprocess.run(
                    [str(venv_pip), "install", "-q", "-r", str(reqs_file)],
                    capture_output=True,
                    timeout=30,
                )

        return f"cortex-memory: plugin updated {local_version} → {remote_version}"
    except Exception:
        return None
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _setup_message() -> str:
    return """<cortex-setup-needed>
Cortex is not configured for this project. Run the Cortex setup script to enable
session memory, smart code exploration, and project context injection.

  bash <(curl -s https://your-cortex-instance/setup)  # or see Cortex docs

Until configured, smart_search / smart_outline / smart_unfold tools are still available.
</cortex-setup-needed>"""


def _leaveoff_protocol_section(project_id: str, system_name: str = "") -> str:
    """Return the LeaveOff Point Protocol instructions for injection into the system prompt."""
    system_line = f'   - `system_name`: `{system_name}`' if system_name else '   - `system_name`: Read from `.claude/cortex-state.json` field "system_name", or fall back to hostname'
    return f"""
## LeaveOff Point Protocol

### After Every Coding Task
After completing any coding task that adds, modifies, or removes functionality, you MUST
update the LeaveOff Point before moving to the next task:

1. Run `git status --porcelain` to check for uncommitted changes.
2. Call `manage_leaveoff_point(action="update")` with:
   - `project_id`: `{project_id}`
   - `content`: What was accomplished in this task (be specific about files changed and why)
   - `component`: The architectural module or feature area being worked on
   - `next_steps`: Concrete, actionable items for the next session (include file paths, not vague descriptions)
   - `references`: Key files that were changed or informed this work
{system_line}
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
1. Stop active coding immediately
2. Run `git status --porcelain` to check for uncommitted changes
3. Generate a final LeaveOff Point via `manage_leaveoff_point(action="update")` with
   comprehensive next_steps covering all remaining planned work, including `system_name`
   and `git_clean`
4. If there are uncommitted changes, advise the user to commit before ending the session
5. Advise the user: "This session has reached its resource limit. The LeaveOff Point
   has been saved. Please start a new session to continue."
6. Do not continue coding after generating the final LeaveOff Point"""


def _format_context(
    sessions: list[dict],
    tasks: list[dict],
    knowledge: dict,
    leaveoff: dict | None = None,
    project_id: str | None = None,
    system_name: str = "",
) -> str:
    parts: list[str] = ["<cortex-context>"]

    # LeaveOff Point goes first — most important context
    if leaveoff:
        component = leaveoff.get("component", "Unknown")
        updated = leaveoff.get("updated_at", "")[:10] if leaveoff.get("updated_at") else ""
        content = leaveoff.get("content", "")
        next_steps = leaveoff.get("next_steps", [])
        references = leaveoff.get("references", [])
        generated_by = leaveoff.get("system_name", "")
        git_clean = leaveoff.get("git_clean")

        parts.append("\n## LeaveOff Point (Last Session State)")
        parts.append(f"**Component:** {component}")
        parts.append(f"**Updated:** {updated}")
        if generated_by:
            parts.append(f"**Generated on:** {generated_by}")
        if git_clean is not None:
            git_label = "All changes committed" if git_clean else "UNCOMMITTED CHANGES present"
            parts.append(f"**Git status:** {git_label}")
        if content:
            parts.append(f"\n{content}")
        if next_steps:
            parts.append("\n### Next Steps")
            for step in next_steps:
                parts.append(f"- {step}")
        if references:
            parts.append("\n### References")
            for ref in references:
                parts.append(f"- {ref}")

    if sessions:
        parts.append("\n## Recent Sessions")
        for s in sessions[:5]:
            summary = s.get("summary", "No summary")
            started = s.get("started_at", "")[:10] if s.get("started_at") else ""
            parts.append(f"- [{started}] {summary}")

    if tasks:
        parts.append("\n## Active Tasks")
        for t in tasks[:10]:
            status = t.get("status", "")
            title = t.get("title", t.get("name", "Untitled"))
            parts.append(f"- [{status}] {title}")

    sources = knowledge.get("sources", [])
    if sources:
        parts.append(f"\n## Knowledge Sources ({len(sources)} indexed)")
        for src in sources[:5]:
            name = src.get("name", src.get("url", "Unknown"))
            parts.append(f"- {name}")

    if len(parts) == 1:
        parts.append("\nNo recent context available.")

    # Inject LeaveOff Point Protocol so Claude knows to update it after coding tasks
    if project_id:
        parts.append(_leaveoff_protocol_section(project_id, system_name=system_name))

    parts.append("\n</cortex-context>")
    return "\n".join(parts)


def _load_system_name() -> str:
    """Load the system_name from cortex-state.json, falling back to empty string."""
    state_path = Path.cwd() / ".claude" / "cortex-state.json"
    if state_path.is_file():
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
            return state.get("system_name", "")
        except (json.JSONDecodeError, OSError):
            pass
    return ""


async def main() -> None:
    client = CortexClient()

    if not client.is_configured():
        print(_setup_message())
        return

    system_name = _load_system_name()

    # Auto-update plugin if a newer version is available on the server
    try:
        update_msg = await asyncio.wait_for(
            _auto_update_plugin(client.mcp_url, _PLUGIN_ROOT),
            timeout=8.0,
        )
        if update_msg:
            print(update_msg, file=sys.stderr)
    except asyncio.TimeoutError:
        print("cortex-memory: plugin update check timed out", file=sys.stderr)
    except Exception:
        pass  # Never block session start for an update failure

    tracker = SessionTracker(buffer_path=_BUFFER_PATH)
    tracker.start_session()

    # Flush stale buffer from a previous crashed session (best-effort)
    if tracker.has_stale_buffer():
        try:
            await asyncio.wait_for(tracker.flush_stale(client), timeout=3.0)
        except Exception:
            pass

    # Fetch context in parallel with a total timeout
    try:
        sessions, tasks, knowledge, leaveoff = await asyncio.wait_for(
            asyncio.gather(
                client.get_recent_sessions(limit=5),
                client.get_active_tasks(limit=10),
                client.get_knowledge_status(),
                client.get_leaveoff_point(),
                return_exceptions=True,
            ),
            timeout=_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        print("<!-- cortex-memory: Cortex unreachable (timeout), skipping context -->")
        return
    except Exception:
        return

    # Replace exceptions from gather with empty defaults
    if isinstance(sessions, Exception):
        sessions = []
    if isinstance(tasks, Exception):
        tasks = []
    if isinstance(knowledge, Exception):
        knowledge = {}
    if isinstance(leaveoff, Exception):
        leaveoff = None

    print(_format_context(sessions, tasks, knowledge, leaveoff, project_id=client.project_id, system_name=system_name))  # type: ignore[arg-type]

    # Postman environment sync (API mode only, best-effort)
    try:
        postman_mode = await asyncio.wait_for(client.get_postman_sync_mode(), timeout=2.0)
        if postman_mode == "api":
            env_path = Path.cwd() / ".env"
            if env_path.is_file():
                env_content = env_path.read_text(encoding="utf-8")
                state_path = Path.cwd() / ".claude" / "cortex-state.json"
                system_name = "default"
                if state_path.is_file():
                    state = json.loads(state_path.read_text(encoding="utf-8"))
                    system_name = state.get("system_name", "default")
                await asyncio.wait_for(
                    client.sync_postman_environment(system_name, env_content),
                    timeout=3.0,
                )
    except Exception:
        pass  # Best-effort, don't block session start

    # ── Report git dirty status (correction signal for commits made outside Claude Code) ──
    if client.is_configured():
        system_id = load_system_id()
        if system_id:
            try:
                git_dirty = check_git_dirty()
                await asyncio.wait_for(
                    client.report_git_status(system_id, git_dirty),
                    timeout=3.0,
                )
            except Exception:
                pass  # Best-effort, don't block session start


if __name__ == "__main__":
    asyncio.run(main())
