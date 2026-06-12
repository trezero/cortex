"""Tests for SessionTracker — local session buffering and flushing.

Uses temp directories so no real filesystem state leaks between tests.
Async tests use @pytest.mark.anyio.
"""

import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch


# ── Helpers ────────────────────────────────────────────────────────────────────


def _make_tracker(tmp_path):
    """Create a SessionTracker with a buffer inside tmp_path."""
    from src.session_tracker import SessionTracker

    buffer_path = str(tmp_path / ".claude" / "cortex-memory-buffer.jsonl")
    return SessionTracker(buffer_path=buffer_path)


def _make_cortex_client(flush_ok: bool = True):
    """Return a mock CortexClient."""
    mock = MagicMock()
    mock.is_configured.return_value = True
    mock.flush_session = AsyncMock(return_value=flush_ok)
    mock.machine_id = "m-abc"
    mock.project_id = "proj-1"
    return mock


# ── start_session ──────────────────────────────────────────────────────────────


def test_start_session_returns_nonempty_session_id(tmp_path):
    """start_session generates and returns a non-empty session_id."""
    tracker = _make_tracker(tmp_path)
    session_id = tracker.start_session()
    assert session_id
    assert len(session_id) > 8


def test_start_session_records_started_at(tmp_path):
    """start_session sets started_at timestamp."""
    tracker = _make_tracker(tmp_path)
    tracker.start_session()
    assert tracker.started_at is not None


def test_start_session_sets_session_id_on_tracker(tmp_path):
    """start_session stores the session_id on the tracker instance."""
    tracker = _make_tracker(tmp_path)
    session_id = tracker.start_session()
    assert tracker.session_id == session_id


# ── append_observation ─────────────────────────────────────────────────────────


def test_append_observation_creates_buffer_file(tmp_path):
    """append_observation creates the buffer file if it doesn't exist."""
    tracker = _make_tracker(tmp_path)
    tracker.start_session()
    tracker.append_observation(tool_name="Edit", files=["src/main.py"], summary="Fixed null check")

    assert Path(tracker.buffer_path).exists()


def test_append_observation_writes_valid_jsonl(tmp_path):
    """Each observation is a valid JSON line in the buffer file."""
    tracker = _make_tracker(tmp_path)
    tracker.start_session()
    tracker.append_observation(tool_name="Edit", files=["a.py"], summary="First change")
    tracker.append_observation(tool_name="Bash", files=[], summary="Ran tests")

    lines = Path(tracker.buffer_path).read_text().splitlines()
    assert len(lines) == 2
    obs1 = json.loads(lines[0])
    assert obs1["tool_name"] == "Edit"
    assert obs1["files"] == ["a.py"]
    assert obs1["summary"] == "First change"
    assert "timestamp" in obs1


def test_append_observation_requires_active_session(tmp_path):
    """append_observation before start_session raises RuntimeError."""
    tracker = _make_tracker(tmp_path)
    with pytest.raises(RuntimeError, match="session"):
        tracker.append_observation(tool_name="Edit", files=[], summary="No session started")


# ── has_stale_buffer ───────────────────────────────────────────────────────────


def test_has_stale_buffer_false_when_no_file(tmp_path):
    """has_stale_buffer returns False when buffer file does not exist."""
    tracker = _make_tracker(tmp_path)
    assert tracker.has_stale_buffer() is False


def test_has_stale_buffer_false_when_file_empty(tmp_path):
    """has_stale_buffer returns False when buffer file is empty."""
    tracker = _make_tracker(tmp_path)
    Path(tracker.buffer_path).parent.mkdir(parents=True, exist_ok=True)
    Path(tracker.buffer_path).write_text("")
    assert tracker.has_stale_buffer() is False


def test_has_stale_buffer_true_when_file_has_data(tmp_path):
    """has_stale_buffer returns True when buffer file has content."""
    tracker = _make_tracker(tmp_path)
    tracker.start_session()
    tracker.append_observation(tool_name="Edit", files=[], summary="Some work")
    assert tracker.has_stale_buffer() is True


# ── flush ──────────────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_flush_sends_session_data_to_cortex(tmp_path):
    """flush reads the buffer, calls cortex_client.flush_session, then clears buffer."""
    tracker = _make_tracker(tmp_path)
    tracker.start_session()
    tracker.append_observation(tool_name="Edit", files=["main.py"], summary="Fix")

    mock_client = _make_cortex_client(flush_ok=True)
    result = await tracker.flush(mock_client)

    assert result is True
    mock_client.flush_session.assert_called_once()
    call_payload = mock_client.flush_session.call_args[0][0]
    assert call_payload["session_id"] == tracker.session_id
    assert len(call_payload["observations"]) == 1
    assert call_payload["observations"][0]["tool_name"] == "Edit"


@pytest.mark.anyio
async def test_flush_clears_buffer_on_success(tmp_path):
    """Buffer file is removed after a successful flush."""
    tracker = _make_tracker(tmp_path)
    tracker.start_session()
    tracker.append_observation(tool_name="Edit", files=[], summary="Work")

    mock_client = _make_cortex_client(flush_ok=True)
    await tracker.flush(mock_client)

    assert not Path(tracker.buffer_path).exists()


@pytest.mark.anyio
async def test_flush_keeps_buffer_on_failure(tmp_path):
    """Buffer file is retained when the flush fails so data is not lost."""
    tracker = _make_tracker(tmp_path)
    tracker.start_session()
    tracker.append_observation(tool_name="Edit", files=[], summary="Work")

    mock_client = _make_cortex_client(flush_ok=False)
    result = await tracker.flush(mock_client)

    assert result is False
    assert Path(tracker.buffer_path).exists()


@pytest.mark.anyio
async def test_flush_returns_true_when_no_observations(tmp_path):
    """flush with an empty session (no observations) succeeds without error."""
    tracker = _make_tracker(tmp_path)
    tracker.start_session()

    mock_client = _make_cortex_client(flush_ok=True)
    result = await tracker.flush(mock_client)

    assert result is True


# ── flush_stale ────────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_flush_stale_sends_stale_buffer(tmp_path):
    """flush_stale reads leftover buffer and flushes it to Cortex."""
    # Simulate a buffer left by a previous session
    tracker = _make_tracker(tmp_path)
    Path(tracker.buffer_path).parent.mkdir(parents=True, exist_ok=True)
    stale_obs = {"session_id": "old-sess", "tool_name": "Edit", "files": ["x.py"], "summary": "Stale", "timestamp": "2026-03-05T10:00:00Z"}
    Path(tracker.buffer_path).write_text(json.dumps(stale_obs) + "\n")

    mock_client = _make_cortex_client(flush_ok=True)
    result = await tracker.flush_stale(mock_client)

    assert result is True
    mock_client.flush_session.assert_called_once()


@pytest.mark.anyio
async def test_flush_stale_returns_false_when_no_buffer(tmp_path):
    """flush_stale returns False immediately when there's nothing to flush."""
    tracker = _make_tracker(tmp_path)
    mock_client = _make_cortex_client(flush_ok=True)
    result = await tracker.flush_stale(mock_client)
    assert result is False
