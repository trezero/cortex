"""Filesystem behavior tests for the dependency-free Codex client."""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).parents[3] / "integrations/codex/cortex_codex.py"
SPEC = importlib.util.spec_from_file_location("cortex_codex", MODULE_PATH)
assert SPEC and SPEC.loader
cortex_codex = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = cortex_codex
SPEC.loader.exec_module(cortex_codex)


def config(tmp_path: Path):
    return cortex_codex.Config(
        api_url="http://cortex.test",
        project_id="project-1",
        project_root=tmp_path / "repo",
    )


def state(name: str = "example", scope: str = "repository") -> dict:
    content = f"---\nname: {name}\ndescription: Example test skill content.\n---\n# Example\n"
    payload_hash = cortex_codex.digest(content)
    return {
        "extension_id": "ext-1",
        "name": name,
        "action": "install",
        "target": {
            "mode": "direct",
            "scope": scope,
            "reviewed_source_hash": "source-hash",
            "payload_hash": payload_hash,
            "payload_content": content,
        },
    }


@pytest.fixture
def isolated_roots(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setattr(cortex_codex.Path, "home", classmethod(lambda cls: home))
    return home


def test_repository_install_and_scan(tmp_path, isolated_roots):
    cfg = config(tmp_path)
    cortex_codex.install_state(cfg, state())

    skill = cfg.project_root / ".agents/skills/example"
    assert (skill / "SKILL.md").is_file()
    marker = json.loads((skill / cortex_codex.MARKER).read_text())
    assert marker["scope"] == "repository"
    assert cortex_codex.scan_skills(cfg)[0]["managed"] is True


def test_global_install(tmp_path, isolated_roots):
    cfg = config(tmp_path)
    cortex_codex.install_state(cfg, state(scope="global"))

    assert (isolated_roots / ".agents/skills/example/SKILL.md").is_file()


def test_scope_migration_archives_old_install(tmp_path, isolated_roots):
    cfg = config(tmp_path)
    cortex_codex.install_state(cfg, state(scope="repository"))
    cortex_codex.install_state(cfg, state(scope="global"))

    assert not (cfg.project_root / ".agents/skills/example").exists()
    assert (isolated_roots / ".agents/skills/example/SKILL.md").is_file()
    assert list((cfg.project_root / ".cortex/backups/codex-skills").iterdir())


def test_unmanaged_conflict_is_not_overwritten(tmp_path, isolated_roots):
    cfg = config(tmp_path)
    skill = cfg.project_root / ".agents/skills/example"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("user content", encoding="utf-8")

    with pytest.raises(cortex_codex.CortexError, match="unmanaged"):
        cortex_codex.install_state(cfg, state())
    assert (skill / "SKILL.md").read_text(encoding="utf-8") == "user content"


def test_failed_install_restores_previous_version(tmp_path, isolated_roots, monkeypatch):
    cfg = config(tmp_path)
    first = state()
    cortex_codex.install_state(cfg, first)
    destination = cfg.project_root / ".agents/skills/example"
    original_content = (destination / "SKILL.md").read_text(encoding="utf-8")

    replacement = state()
    replacement["target"]["payload_content"] += "\nUpdated.\n"
    replacement["target"]["payload_hash"] = cortex_codex.digest(replacement["target"]["payload_content"])
    original_replace = Path.replace

    def fail_stage_replace(path, target):
        if path.name.startswith(".example-") and Path(target) == destination:
            raise OSError("simulated replacement failure")
        return original_replace(path, target)

    monkeypatch.setattr(Path, "replace", fail_stage_replace)
    with pytest.raises(OSError, match="simulated"):
        cortex_codex.install_state(cfg, replacement)

    assert (destination / "SKILL.md").read_text(encoding="utf-8") == original_content
