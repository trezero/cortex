#!/usr/bin/env python3
"""PostToolUse hook — append tool usage as an observation to the local buffer.

Receives JSON from Claude Code via stdin describing the tool that was just used.
Appends a compact observation record to the JSONL buffer. No network calls —
this must complete in <50ms.

Claude Code PostToolUse hook stdin format:
{
  "tool_name": "Edit",
  "tool_input": {"file_path": "src/main.py", ...},
  "tool_response": {...},
  "session_id": "...",
  ...
}
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Add plugin src directory to path
_PLUGIN_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_PLUGIN_ROOT))

from src.session_tracker import SessionTracker

_BUFFER_PATH = ".claude/cortex-memory-buffer.jsonl"

# Tools that produce meaningful observations worth recording
_TRACKED_TOOLS = {
    "Edit", "Write", "Bash", "Glob", "Grep", "Read",
    "mcp__ide__executeCode",
}

_WARNING_THRESHOLD = 80
_WARNING_REPEAT_INTERVAL = 10


def _extract_files(tool_name: str, tool_input: dict) -> list[str]:
    """Extract file paths from tool input based on tool type."""
    files: list[str] = []
    for key in ("file_path", "path", "file_paths"):
        val = tool_input.get(key)
        if isinstance(val, str) and val:
            files.append(val)
        elif isinstance(val, list):
            files.extend(v for v in val if isinstance(v, str) and v)
    return files


def _build_summary(tool_name: str, tool_input: dict) -> str:
    """Build a short summary string for the observation."""
    if tool_name in ("Edit", "Write"):
        path = tool_input.get("file_path", "")
        return f"{tool_name}: {path}" if path else tool_name
    if tool_name == "Bash":
        cmd = tool_input.get("command", "")
        return f"Bash: {cmd[:80]}" if cmd else "Bash"
    if tool_name in ("Glob", "Grep"):
        pattern = tool_input.get("pattern", tool_input.get("query", ""))
        return f"{tool_name}: {pattern}" if pattern else tool_name
    return tool_name


def _check_observation_count(buffer_path: str) -> None:
    """Count observations and emit a warning if approaching resource limits."""
    try:
        buf = Path(buffer_path)
        if not buf.exists():
            return

        count = sum(1 for _ in buf.open())

        if count >= _WARNING_THRESHOLD and (count - _WARNING_THRESHOLD) % _WARNING_REPEAT_INTERVAL == 0:
            print(
                f"\n<system-reminder>\n"
                f"SESSION RESOURCE WARNING: This session has recorded {count} tool operations. "
                f"You are approaching resource limits. After completing your current task, "
                f"generate a final LeaveOff Point via manage_leaveoff_point(action=\"update\") "
                f"and advise the user to start a new session.\n"
                f"</system-reminder>"
            )
    except Exception:
        pass  # Never block Claude Code


def main() -> None:
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            return

        hook_input = json.loads(raw)
    except (json.JSONDecodeError, OSError):
        return

    tool_name = hook_input.get("tool_name", "")
    if tool_name not in _TRACKED_TOOLS:
        return

    tool_input = hook_input.get("tool_input", {})
    files = _extract_files(tool_name, tool_input)
    summary = _build_summary(tool_name, tool_input)

    tracker = SessionTracker(buffer_path=_BUFFER_PATH)
    # Restore session_id from hook input if available so observations link correctly
    tracker.session_id = hook_input.get("session_id") or "unknown"

    try:
        tracker.append_observation(tool_name=tool_name, files=files, summary=summary)
    except Exception:
        pass  # Never block Claude Code for a failed observation

    _check_observation_count(_BUFFER_PATH)


if __name__ == "__main__":
    main()
