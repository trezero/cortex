#!/usr/bin/env python3
"""Stop hook — flush the session observation buffer to Cortex and materialize LeaveOffPoint.md.

Runs when Claude Code ends a session (Stop event). Reads the local JSONL buffer,
sends all observations to Cortex as a single batch, then clears the buffer.
Also fetches the current LeaveOff point and writes it to .cortex/knowledge/LeaveOffPoint.md
so the next session has local access to it.

If Cortex is unreachable the buffer is left intact for flush_stale() on next start.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Add plugin src directory to path
_PLUGIN_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_PLUGIN_ROOT))

from src.cortex_client import CortexClient
from src.git_utils import check_git_dirty, load_system_id
from src.session_tracker import SessionTracker

_BUFFER_PATH = ".claude/cortex-memory-buffer.jsonl"
_TIMEOUT_SECONDS = 8
_LEAVEOFF_DIR = ".cortex/knowledge"
_LEAVEOFF_FILE = "LeaveOffPoint.md"


def _materialize_leaveoff(leaveoff: dict) -> None:
    """Write a LeaveOffPoint.md file into .cortex/knowledge/ in the project root.

    The file uses YAML-style frontmatter and markdown body so it can be read
    by both humans and the session_start_hook.
    """
    dir_path = Path.cwd() / _LEAVEOFF_DIR
    dir_path.mkdir(parents=True, exist_ok=True)
    file_path = dir_path / _LEAVEOFF_FILE

    project_id = leaveoff.get("project_id", "")
    component = leaveoff.get("component", "")
    updated_at = leaveoff.get("updated_at", "")
    machine_id = leaveoff.get("machine_id", "")
    system_name = leaveoff.get("system_name", "")
    git_clean = leaveoff.get("git_clean")
    content = leaveoff.get("content", "")
    next_steps = leaveoff.get("next_steps") or []
    references = leaveoff.get("references") or []

    lines: list[str] = []
    lines.append("---")
    lines.append(f"project_id: {project_id}")
    lines.append(f"component: {component}")
    lines.append(f"updated_at: {updated_at}")
    lines.append(f"machine_id: {machine_id}")
    lines.append(f"system_name: {system_name}")
    if git_clean is not None:
        lines.append(f"git_clean: {str(git_clean).lower()}")
    lines.append("---")
    lines.append("")
    lines.append(content)

    if next_steps:
        lines.append("")
        lines.append("## Next Steps")
        for step in next_steps:
            lines.append(f"- {step}")

    if references:
        lines.append("")
        lines.append("## References")
        for ref in references:
            lines.append(f"- {ref}")

    lines.append("")
    file_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"cortex-memory: LeaveOffPoint.md materialized at {file_path}", file=sys.stderr)


async def main() -> None:
    client = CortexClient()
    tracker = SessionTracker(buffer_path=_BUFFER_PATH)

    # ── Flush observation buffer ────────────────────────────────────────────
    if tracker.has_stale_buffer():
        if not client.is_configured():
            # Leave buffer intact so it can be flushed when Cortex is configured
            print("cortex-memory: Cortex not configured — buffer preserved", file=sys.stderr)
        else:
            tracker.session_id = tracker.session_id or "session-end-flush"
            tracker.started_at = tracker.started_at or ""
            try:
                success = await asyncio.wait_for(tracker.flush(client), timeout=_TIMEOUT_SECONDS)
                if success:
                    print("cortex-memory: session flushed to Cortex", file=sys.stderr)
                else:
                    print("cortex-memory: flush failed — buffer preserved for next session", file=sys.stderr)
            except asyncio.TimeoutError:
                print("cortex-memory: Cortex unreachable (timeout) — buffer preserved", file=sys.stderr)
            except Exception as e:
                print(f"cortex-memory: unexpected error during flush: {e}", file=sys.stderr)

    # ── Materialize LeaveOffPoint.md locally ────────────────────────────────
    if client.is_configured():
        try:
            leaveoff = await asyncio.wait_for(client.get_leaveoff_point(), timeout=5.0)
            if leaveoff:
                _materialize_leaveoff(leaveoff)
        except asyncio.TimeoutError:
            print("cortex-memory: timeout fetching LeaveOff point", file=sys.stderr)
        except Exception as e:
            print(f"cortex-memory: error materializing LeaveOffPoint.md: {e}", file=sys.stderr)

    # ── Report git dirty status ──────────────────────────────────────────
    if client.is_configured():
        system_id = load_system_id()
        if system_id:
            try:
                git_dirty = check_git_dirty()
                success = await asyncio.wait_for(
                    client.report_git_status(system_id, git_dirty),
                    timeout=3.0,
                )
                if success:
                    status = "dirty" if git_dirty else "clean"
                    print(f"cortex-memory: git status reported ({status})", file=sys.stderr)
            except asyncio.TimeoutError:
                print("cortex-memory: git status report timed out", file=sys.stderr)
            except Exception as e:
                print(f"cortex-memory: git status report failed: {e}", file=sys.stderr)


if __name__ == "__main__":
    asyncio.run(main())
