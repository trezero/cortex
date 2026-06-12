"""Tests for session_start_hook — _format_context and _leaveoff_protocol_section."""

import sys
from pathlib import Path

# Ensure plugin src is importable
_PLUGIN_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_PLUGIN_ROOT))

from scripts.session_start_hook import _format_context, _leaveoff_protocol_section


# ── _leaveoff_protocol_section ────────────────────────────────────────────────


class TestLeaveoffProtocolSection:
    def test_contains_project_id(self):
        result = _leaveoff_protocol_section("proj-abc-123")
        assert "proj-abc-123" in result

    def test_contains_protocol_heading(self):
        result = _leaveoff_protocol_section("proj-1")
        assert "## LeaveOff Point Protocol" in result

    def test_contains_manage_leaveoff_point_instruction(self):
        result = _leaveoff_protocol_section("proj-1")
        assert "manage_leaveoff_point" in result
        assert 'action="update"' in result

    def test_contains_90_percent_rule(self):
        result = _leaveoff_protocol_section("proj-1")
        assert "90% Rule" in result
        assert "80+ tool uses" in result


# ── _format_context with protocol injection ───────────────────────────────────


class TestFormatContextProtocol:
    def test_protocol_injected_when_project_id_provided(self):
        result = _format_context([], [], {}, project_id="proj-42")
        assert "## LeaveOff Point Protocol" in result
        assert "proj-42" in result

    def test_protocol_not_injected_when_project_id_none(self):
        result = _format_context([], [], {}, project_id=None)
        assert "## LeaveOff Point Protocol" not in result

    def test_protocol_not_injected_when_project_id_empty(self):
        result = _format_context([], [], {}, project_id="")
        assert "## LeaveOff Point Protocol" not in result

    def test_protocol_not_injected_when_project_id_omitted(self):
        result = _format_context([], [], {})
        assert "## LeaveOff Point Protocol" not in result

    def test_protocol_appears_before_closing_tag(self):
        result = _format_context([], [], {}, project_id="proj-1")
        protocol_pos = result.index("## LeaveOff Point Protocol")
        closing_pos = result.index("</cortex-context>")
        assert protocol_pos < closing_pos

    def test_protocol_appears_after_leaveoff_data(self):
        leaveoff = {
            "component": "Auth",
            "updated_at": "2026-03-14T12:00:00",
            "content": "Implemented login flow",
            "next_steps": ["Add logout"],
            "references": ["src/auth.py"],
        }
        result = _format_context([], [], {}, leaveoff=leaveoff, project_id="proj-1")
        data_pos = result.index("## LeaveOff Point (Last Session State)")
        protocol_pos = result.index("## LeaveOff Point Protocol")
        assert data_pos < protocol_pos

    def test_protocol_appears_after_other_sections(self):
        sessions = [{"summary": "Did stuff", "started_at": "2026-03-14T10:00:00"}]
        tasks = [{"status": "doing", "title": "Fix bug"}]
        knowledge = {"sources": [{"name": "docs"}]}
        result = _format_context(sessions, tasks, knowledge, project_id="proj-1")
        # Protocol should come after all data sections
        assert result.index("## Recent Sessions") < result.index("## LeaveOff Point Protocol")
        assert result.index("## Active Tasks") < result.index("## LeaveOff Point Protocol")
        assert result.index("## Knowledge Sources") < result.index("## LeaveOff Point Protocol")

    def test_full_context_structure_with_protocol(self):
        """Verify cortex-context wrapping is intact with protocol injected."""
        result = _format_context([], [], {}, project_id="proj-1")
        assert result.startswith("<cortex-context>")
        assert result.strip().endswith("</cortex-context>")
