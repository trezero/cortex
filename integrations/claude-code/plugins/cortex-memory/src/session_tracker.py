"""Session tracker — local buffering and flushing of session memory.

Observations are appended to a local JSONL buffer file as they accumulate,
then flushed to Cortex in a single batch when the session ends.

If a session crashes before flushing, flush_stale() recovers the leftover buffer
on the next session start.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path


class SessionTracker:
    def __init__(self, buffer_path: str = ".claude/cortex-memory-buffer.jsonl"):
        self.buffer_path = buffer_path
        self.session_id: str | None = None
        self.started_at: str | None = None

    # ── Session lifecycle ──────────────────────────────────────────────────────

    def start_session(self) -> str:
        """Generate a session_id, record start time, and return the session_id."""
        self.session_id = str(uuid.uuid4())
        self.started_at = datetime.now(timezone.utc).isoformat()
        return self.session_id

    def append_observation(self, tool_name: str, files: list[str], summary: str) -> None:
        """Append one observation record to the local JSONL buffer.

        Raises RuntimeError if start_session() has not been called.
        """
        if self.session_id is None:
            raise RuntimeError("No active session — call start_session() first")

        observation = {
            "session_id": self.session_id,
            "tool_name": tool_name,
            "files": files,
            "summary": summary,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        buffer = Path(self.buffer_path)
        buffer.parent.mkdir(parents=True, exist_ok=True)
        with buffer.open("a", encoding="utf-8") as f:
            f.write(json.dumps(observation) + "\n")

    # ── Buffer inspection ──────────────────────────────────────────────────────

    def has_stale_buffer(self) -> bool:
        """Return True if the buffer file exists and contains at least one line."""
        p = Path(self.buffer_path)
        if not p.exists():
            return False
        return bool(p.read_text(encoding="utf-8").strip())

    # ── Flushing ───────────────────────────────────────────────────────────────

    async def flush(self, cortex_client) -> bool:
        """Read the buffer, POST a batch to Cortex, clear the buffer on success."""
        observations = self._read_buffer()
        payload = {
            "session_id": self.session_id,
            "machine_id": cortex_client.machine_id,
            "project_id": cortex_client.project_id,
            "started_at": self.started_at,
            "ended_at": datetime.now(timezone.utc).isoformat(),
            "observations": observations,
        }

        success = await cortex_client.flush_session(payload)
        if success:
            self._clear_buffer()
        return success

    async def flush_stale(self, cortex_client) -> bool:
        """Flush a buffer left over from a previous crashed session."""
        if not self.has_stale_buffer():
            return False

        observations = self._read_buffer()

        # Extract session_id from first observation if available
        session_id = observations[0].get("session_id", str(uuid.uuid4())) if observations else str(uuid.uuid4())

        payload = {
            "session_id": session_id,
            "machine_id": cortex_client.machine_id,
            "project_id": cortex_client.project_id,
            "started_at": None,
            "ended_at": datetime.now(timezone.utc).isoformat(),
            "observations": observations,
            "recovered": True,
        }

        success = await cortex_client.flush_session(payload)
        if success:
            self._clear_buffer()
        return success

    # ── Internal helpers ───────────────────────────────────────────────────────

    def _read_buffer(self) -> list[dict]:
        p = Path(self.buffer_path)
        if not p.exists():
            return []
        lines = p.read_text(encoding="utf-8").splitlines()
        result = []
        for line in lines:
            line = line.strip()
            if line:
                try:
                    result.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
        return result

    def _clear_buffer(self) -> None:
        p = Path(self.buffer_path)
        if p.exists():
            p.unlink()
