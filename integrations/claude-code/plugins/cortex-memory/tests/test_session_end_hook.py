"""Tests for session_end_hook — _materialize_leaveoff function."""

import sys
from pathlib import Path

# Ensure plugin src is importable
_PLUGIN_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_PLUGIN_ROOT))

from scripts.session_end_hook import _materialize_leaveoff


class TestMaterializeLeaveoff:
    """Test the _materialize_leaveoff function writes correct markdown files."""

    def _make_leaveoff(self, **overrides):
        base = {
            "project_id": "proj-abc-123",
            "component": "Auth Module",
            "updated_at": "2026-03-15T22:00:00+00:00",
            "machine_id": "abc123def456",
            "content": "Implemented login and registration endpoints.",
            "next_steps": ["Add password reset", "Write integration tests"],
            "references": ["src/auth/login.py", "src/auth/register.py"],
        }
        base.update(overrides)
        return base

    def test_creates_directory_and_file(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        _materialize_leaveoff(self._make_leaveoff())
        file_path = tmp_path / ".cortex" / "knowledge" / "LeaveOffPoint.md"
        assert file_path.exists()

    def test_frontmatter_contains_project_id(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        _materialize_leaveoff(self._make_leaveoff())
        content = (tmp_path / ".cortex" / "knowledge" / "LeaveOffPoint.md").read_text()
        assert "project_id: proj-abc-123" in content

    def test_frontmatter_contains_component(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        _materialize_leaveoff(self._make_leaveoff())
        content = (tmp_path / ".cortex" / "knowledge" / "LeaveOffPoint.md").read_text()
        assert "component: Auth Module" in content

    def test_frontmatter_contains_updated_at(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        _materialize_leaveoff(self._make_leaveoff())
        content = (tmp_path / ".cortex" / "knowledge" / "LeaveOffPoint.md").read_text()
        assert "updated_at: 2026-03-15T22:00:00+00:00" in content

    def test_frontmatter_contains_machine_id(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        _materialize_leaveoff(self._make_leaveoff())
        content = (tmp_path / ".cortex" / "knowledge" / "LeaveOffPoint.md").read_text()
        assert "machine_id: abc123def456" in content

    def test_content_body_present(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        _materialize_leaveoff(self._make_leaveoff())
        content = (tmp_path / ".cortex" / "knowledge" / "LeaveOffPoint.md").read_text()
        assert "Implemented login and registration endpoints." in content

    def test_next_steps_section(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        _materialize_leaveoff(self._make_leaveoff())
        content = (tmp_path / ".cortex" / "knowledge" / "LeaveOffPoint.md").read_text()
        assert "## Next Steps" in content
        assert "- Add password reset" in content
        assert "- Write integration tests" in content

    def test_references_section(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        _materialize_leaveoff(self._make_leaveoff())
        content = (tmp_path / ".cortex" / "knowledge" / "LeaveOffPoint.md").read_text()
        assert "## References" in content
        assert "- src/auth/login.py" in content
        assert "- src/auth/register.py" in content

    def test_no_next_steps_when_empty(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        _materialize_leaveoff(self._make_leaveoff(next_steps=[]))
        content = (tmp_path / ".cortex" / "knowledge" / "LeaveOffPoint.md").read_text()
        assert "## Next Steps" not in content

    def test_no_references_when_empty(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        _materialize_leaveoff(self._make_leaveoff(references=[]))
        content = (tmp_path / ".cortex" / "knowledge" / "LeaveOffPoint.md").read_text()
        assert "## References" not in content

    def test_yaml_frontmatter_delimiters(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        _materialize_leaveoff(self._make_leaveoff())
        content = (tmp_path / ".cortex" / "knowledge" / "LeaveOffPoint.md").read_text()
        assert content.startswith("---\n")
        # Should have opening and closing frontmatter delimiters
        parts = content.split("---")
        assert len(parts) >= 3  # before, frontmatter, after

    def test_overwrites_existing_file(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        _materialize_leaveoff(self._make_leaveoff(content="First version"))
        _materialize_leaveoff(self._make_leaveoff(content="Second version"))
        content = (tmp_path / ".cortex" / "knowledge" / "LeaveOffPoint.md").read_text()
        assert "Second version" in content
        assert "First version" not in content

    def test_handles_none_values_gracefully(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        leaveoff = {
            "project_id": "proj-1",
            "component": None,
            "updated_at": None,
            "machine_id": None,
            "content": "",
            "next_steps": None,
            "references": None,
        }
        _materialize_leaveoff(leaveoff)
        file_path = tmp_path / ".cortex" / "knowledge" / "LeaveOffPoint.md"
        assert file_path.exists()
        content = file_path.read_text()
        assert "component: None" in content
