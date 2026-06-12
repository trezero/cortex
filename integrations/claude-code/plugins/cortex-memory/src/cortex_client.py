"""Cortex HTTP client for the cortex-memory plugin.

Communicates with the Cortex backend API to flush session memory,
retrieve recent sessions, fetch active tasks, and query knowledge status.

Config is loaded from cortex-config.json, checked in order:
  1. Explicit path passed to the constructor
  2. .claude/cortex-config.json (relative to cwd)
  3. ~/.claude/cortex-config.json
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import httpx

_REQUIRED_FIELDS = ("cortex_api_url", "project_id", "machine_id")


class CortexClient:
    def __init__(self, config_path: str | None = None):
        self.config = self._load_config(config_path)
        self.api_url = self.config.get("cortex_api_url", "").rstrip("/")
        self.mcp_url = self.config.get("cortex_mcp_url", "").rstrip("/")
        self.project_id = self.config.get("project_id", "")
        self.machine_id = self.config.get("machine_id", "")

    # ── Config ─────────────────────────────────────────────────────────────────

    def _load_config(self, path: str | None) -> dict:
        """Try explicit path, then local .claude/, then ~/.claude/."""
        candidates: list[Path] = []

        if path:
            candidates.append(Path(path))
        else:
            candidates.append(Path.cwd() / ".claude" / "cortex-config.json")
            candidates.append(Path.home() / ".claude" / "cortex-config.json")

        for candidate in candidates:
            if candidate.is_file():
                try:
                    return json.loads(candidate.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, OSError):
                    pass

        return {}

    def is_configured(self) -> bool:
        """Return True when all required config fields are present and non-empty."""
        return all(self.config.get(f) for f in _REQUIRED_FIELDS)

    # ── HTTP helpers ───────────────────────────────────────────────────────────

    async def flush_session(self, session_data: dict) -> bool:
        """POST session_data to /api/sessions. Returns True on success."""
        if not self.is_configured():
            return False

        url = f"{self.api_url}/api/sessions"
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(url, json=session_data)
            return response.status_code < 400
        except Exception:
            return False

    async def get_recent_sessions(self, limit: int = 5) -> list[dict]:
        """GET /api/sessions?project_id=X&limit=N. Returns list of sessions."""
        if not self.is_configured():
            return []

        url = f"{self.api_url}/api/sessions"
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, params={"project_id": self.project_id, "limit": limit})
            if response.status_code >= 400:
                return []
            return response.json().get("sessions", [])
        except Exception:
            return []

    async def get_active_tasks(self, limit: int = 10) -> list[dict]:
        """GET /api/projects/{id}/tasks filtered to active statuses."""
        if not self.is_configured():
            return []

        url = f"{self.api_url}/api/projects/{self.project_id}/tasks"
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, params={"status": "doing,review,todo", "limit": limit})
            if response.status_code >= 400:
                return []
            return response.json().get("tasks", [])
        except Exception:
            return []

    async def get_knowledge_status(self) -> dict:
        """GET /api/knowledge/sources filtered by project_id."""
        if not self.is_configured():
            return {}

        url = f"{self.api_url}/api/knowledge/sources"
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, params={"project_id": self.project_id})
            if response.status_code >= 400:
                return {}
            return response.json()
        except Exception:
            return {}

    async def get_leaveoff_point(self) -> dict | None:
        """GET /api/projects/{id}/leaveoff. Returns the LeaveOff point or None."""
        if not self.is_configured():
            return None

        url = f"{self.api_url}/api/projects/{self.project_id}/leaveoff"
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url)
            if response.status_code >= 400:
                return None
            return response.json()
        except Exception:
            return None

    # ── Git status reporting ─────────────────────────────────────────────────

    async def report_git_status(self, system_id: str, git_dirty: bool) -> bool:
        """Report git dirty status for the current project + system."""
        if not self.is_configured() or not system_id:
            return False

        url = f"{self.api_url}/api/projects/{self.project_id}/systems/{system_id}/git-status"
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.put(url, json={"git_dirty": git_dirty})
                return resp.status_code == 200
        except httpx.HTTPError:
            return False

    # ── Postman .env sync ─────────────────────────────────────────────────────

    async def sync_postman_environment(self, system_name: str, env_content: str) -> bool:
        """POST .env content to Postman environment sync endpoint. Returns True on success."""
        if not self.is_configured():
            return False

        url = f"{self.api_url}/api/postman/environments/sync"
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(url, json={
                    "project_id": self.project_id,
                    "system_name": system_name,
                    "env_file_content": env_content,
                })
            return response.status_code < 400
        except Exception:
            return False

    async def get_postman_sync_mode(self) -> str:
        """GET the current Postman sync mode. Returns 'disabled' on error."""
        if not self.is_configured():
            return "disabled"

        url = f"{self.api_url}/api/credentials/POSTMAN_SYNC_MODE"
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url)
            if response.status_code >= 400:
                return "disabled"
            data = response.json()
            return data.get("value", "disabled")
        except Exception:
            return "disabled"
