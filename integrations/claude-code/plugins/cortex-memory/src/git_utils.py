"""Shared git status helpers for session hooks."""

from __future__ import annotations

import json as _json
import subprocess
from pathlib import Path


def check_git_dirty() -> bool:
    """Run git status --porcelain and return True if there are uncommitted changes."""
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True, text=True, timeout=5,
        )
        return bool(result.stdout.strip())
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return False


def load_system_id() -> str:
    """Read system_id from .claude/cortex-state.json."""
    state_path = Path.cwd() / ".claude" / "cortex-state.json"
    if state_path.is_file():
        try:
            data = _json.loads(state_path.read_text(encoding="utf-8"))
            return data.get("system_id", "")
        except (ValueError, OSError):
            pass
    return ""
