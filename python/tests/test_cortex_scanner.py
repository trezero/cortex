"""
Tests for cortex-scanner.py — the standalone local project scanner.

Imports the script as a module using importlib so no package restructuring
is required.
"""
import importlib.util
import io
import json
import os
import sys
import tarfile
import tempfile

import pytest

# ---------------------------------------------------------------------------
# Module import
# ---------------------------------------------------------------------------

_script_path = os.path.join(
    os.path.dirname(__file__), "..", "src", "server", "static", "cortex-scanner.py"
)
_spec = importlib.util.spec_from_file_location("cortex_scanner", _script_path)
scanner = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(scanner)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_git_repo(path, remote_url=None, readme_content=None, branch="main"):
    """Create a minimal fake git repo structure."""
    os.makedirs(os.path.join(path, ".git"), exist_ok=True)
    with open(os.path.join(path, ".git", "HEAD"), "w") as f:
        f.write(f"ref: refs/heads/{branch}\n")
    if remote_url:
        config_path = os.path.join(path, ".git", "config")
        with open(config_path, "w") as f:
            f.write(
                f'[remote "origin"]\n'
                f'\turl = {remote_url}\n'
                f'\tfetch = +refs/heads/*:refs/remotes/origin/*\n'
            )
    if readme_content:
        with open(os.path.join(path, "README.md"), "w") as f:
            f.write(readme_content)


# ---------------------------------------------------------------------------
# TestScanEmpty
# ---------------------------------------------------------------------------

class TestScanEmpty:
    def test_empty_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = scanner.scan_directory(tmpdir)
            assert "error" not in result
            assert result["summary"]["total_found"] == 0

    def test_nonexistent_directory(self):
        result = scanner.scan_directory("/tmp/__nonexistent_cortex_test_dir__")
        assert "error" in result


# ---------------------------------------------------------------------------
# TestScanDetection
# ---------------------------------------------------------------------------

class TestScanDetection:
    def test_detects_git_repo(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = os.path.join(tmpdir, "my-project")
            os.makedirs(repo_path)
            _make_git_repo(repo_path, remote_url="git@github.com:user/my-project.git")

            result = scanner.scan_directory(tmpdir)

            assert result["summary"]["total_found"] == 1
            project = result["projects"][0]
            assert project["directory_name"] == "my-project"
            assert project["github_url"] == "https://github.com/user/my-project"

    def test_detects_group(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a group directory containing two git repos
            group_path = os.path.join(tmpdir, "work-projects")
            os.makedirs(group_path)

            for repo_name in ("repo-a", "repo-b"):
                repo_path = os.path.join(group_path, repo_name)
                os.makedirs(repo_path)
                _make_git_repo(repo_path)

            result = scanner.scan_directory(tmpdir)

            assert result["summary"]["total_found"] == 2
            assert result["summary"]["groups_found"] == 1
            assert result["groups"][0]["name"] == "work-projects"

            # All discovered projects should carry the group_name
            for project in result["projects"]:
                assert project["group_name"] == "work-projects"

    def test_skip_list_honored(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # node_modules with a .git dir — should be skipped
            skip_path = os.path.join(tmpdir, "node_modules", "some-pkg")
            os.makedirs(skip_path)
            _make_git_repo(skip_path)

            # Real project — should be detected
            real_path = os.path.join(tmpdir, "real-project")
            os.makedirs(real_path)
            _make_git_repo(real_path)

            result = scanner.scan_directory(tmpdir)
            names = [p["directory_name"] for p in result["projects"]]
            assert "real-project" in names
            assert "node_modules" not in names
            assert result["summary"]["total_found"] == 1

    def test_hidden_dirs_skipped(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # Hidden project — must be skipped
            hidden_path = os.path.join(tmpdir, ".hidden-project")
            os.makedirs(hidden_path)
            _make_git_repo(hidden_path)

            # Visible project — must be detected
            visible_path = os.path.join(tmpdir, "visible-project")
            os.makedirs(visible_path)
            _make_git_repo(visible_path)

            result = scanner.scan_directory(tmpdir)
            names = [p["directory_name"] for p in result["projects"]]
            assert "visible-project" in names
            assert ".hidden-project" not in names
            assert result["summary"]["total_found"] == 1


# ---------------------------------------------------------------------------
# TestGitRemoteParsing
# ---------------------------------------------------------------------------

class TestGitRemoteParsing:
    def _scan_single_repo(self, tmpdir, remote_url):
        repo_path = os.path.join(tmpdir, "test-repo")
        os.makedirs(repo_path)
        _make_git_repo(repo_path, remote_url=remote_url)
        result = scanner.scan_directory(tmpdir)
        assert result["summary"]["total_found"] == 1
        return result["projects"][0]

    def test_ssh_remote(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project = self._scan_single_repo(tmpdir, "git@github.com:user/repo.git")
            assert project["git_remote_url"] == "git@github.com:user/repo.git"
            assert project["github_url"] == "https://github.com/user/repo"

    def test_https_remote(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project = self._scan_single_repo(tmpdir, "https://github.com/User/Repo.git")
            # github_url must be lowercased
            assert project["github_url"] == "https://github.com/user/repo"

    def test_no_remote(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = os.path.join(tmpdir, "no-remote")
            os.makedirs(repo_path)
            _make_git_repo(repo_path)  # No remote_url arg

            result = scanner.scan_directory(tmpdir)
            project = result["projects"][0]
            assert project["git_remote_url"] is None
            assert project["github_url"] is None

    def test_non_github_remote(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project = self._scan_single_repo(
                tmpdir, "https://gitlab.com/user/repo.git"
            )
            assert project["git_remote_url"] == "https://gitlab.com/user/repo.git"
            assert project["github_url"] is None


# ---------------------------------------------------------------------------
# TestUrlNormalization
# ---------------------------------------------------------------------------

class TestUrlNormalization:
    def test_ssh_to_https(self):
        result = scanner.normalize_github_url("git@github.com:owner/repo.git")
        assert result == "https://github.com/owner/repo"

    def test_strip_dot_git(self):
        result = scanner.normalize_github_url("https://github.com/owner/repo.git")
        assert result == "https://github.com/owner/repo"

    def test_case_insensitive(self):
        result = scanner.normalize_github_url("https://GitHub.com/User/Repo")
        assert result == "https://github.com/user/repo"

    def test_non_github_returns_none(self):
        result = scanner.normalize_github_url("https://gitlab.com/user/repo.git")
        assert result is None

    def test_none_input(self):
        result = scanner.normalize_github_url(None)
        assert result is None


# ---------------------------------------------------------------------------
# TestReadme
# ---------------------------------------------------------------------------

class TestReadme:
    def test_readme_excerpt(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = os.path.join(tmpdir, "readme-project")
            os.makedirs(repo_path)
            long_content = "A" * 6000
            _make_git_repo(repo_path, readme_content=long_content)

            result = scanner.scan_directory(tmpdir)
            project = result["projects"][0]
            assert project["has_readme"] is True
            # README_EXCERPT_LENGTH is 5000 — excerpt should be at most that
            assert len(project["readme_excerpt"]) == 5000

    def test_no_readme(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = os.path.join(tmpdir, "no-readme-project")
            os.makedirs(repo_path)
            _make_git_repo(repo_path)  # No readme_content

            result = scanner.scan_directory(tmpdir)
            project = result["projects"][0]
            assert project["has_readme"] is False
            assert project["readme_excerpt"] is None


# ---------------------------------------------------------------------------
# TestDependencyExtraction
# ---------------------------------------------------------------------------

class TestDependencyExtraction:
    def test_npm_deps(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = os.path.join(tmpdir, "node-project")
            os.makedirs(repo_path)
            _make_git_repo(repo_path)

            pkg = {
                "name": "node-project",
                "dependencies": {"react": "^18.0.0", "axios": "^1.0.0"},
                "devDependencies": {"jest": "^29.0.0"},
            }
            with open(os.path.join(repo_path, "package.json"), "w") as f:
                json.dump(pkg, f)

            result = scanner.scan_directory(tmpdir)
            project = result["projects"][0]
            deps = project["dependencies"]
            assert deps is not None
            npm_entry = deps.get("package.json")
            assert npm_entry is not None
            assert npm_entry["type"] == "npm"
            assert "react" in npm_entry["data"]["dependencies"]
            assert "jest" in npm_entry["data"]["devDependencies"]

    def test_requirements_deps(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = os.path.join(tmpdir, "python-project")
            os.makedirs(repo_path)
            _make_git_repo(repo_path)

            req_content = (
                "# This is a comment\n"
                "-r base.txt\n"
                "requests>=2.28.0\n"
                "fastapi==0.110.0\n"
            )
            with open(os.path.join(repo_path, "requirements.txt"), "w") as f:
                f.write(req_content)

            result = scanner.scan_directory(tmpdir)
            project = result["projects"][0]
            deps = project["dependencies"]
            assert deps is not None
            pip_entry = deps.get("requirements.txt")
            assert pip_entry is not None
            assert pip_entry["type"] == "pip"
            packages = pip_entry["data"]["packages"]
            # Comments and -r lines must be excluded
            assert not any(p.startswith("#") for p in packages)
            assert not any(p.startswith("-") for p in packages)
            assert any("requests" in p for p in packages)
            assert any("fastapi" in p for p in packages)


# ---------------------------------------------------------------------------
# TestInfraMarkers
# ---------------------------------------------------------------------------

class TestInfraMarkers:
    def test_dockerfile_detected(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = os.path.join(tmpdir, "docker-project")
            os.makedirs(repo_path)
            _make_git_repo(repo_path)

            # Create a Dockerfile
            with open(os.path.join(repo_path, "Dockerfile"), "w") as f:
                f.write("FROM python:3.12\n")

            result = scanner.scan_directory(tmpdir)
            project = result["projects"][0]
            assert "docker" in project["infra_markers"]

    def test_github_actions_detected(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = os.path.join(tmpdir, "actions-project")
            os.makedirs(repo_path)
            _make_git_repo(repo_path)

            # Create the .github/workflows directory
            workflows_dir = os.path.join(repo_path, ".github", "workflows")
            os.makedirs(workflows_dir)
            with open(os.path.join(workflows_dir, "ci.yml"), "w") as f:
                f.write("name: CI\n")

            result = scanner.scan_directory(tmpdir)
            project = result["projects"][0]
            assert "github-actions" in project["infra_markers"]


# ---------------------------------------------------------------------------
# TestApplyConfigs
# ---------------------------------------------------------------------------

class TestApplyConfigs:
    def _make_payload_file(self, tmpdir, projects):
        payload_path = os.path.join(tmpdir, "payload.json")
        with open(payload_path, "w") as f:
            json.dump({"projects": projects}, f)
        return payload_path

    def _make_project_entry(self, project_path, **extra):
        entry = {
            "absolute_path": project_path,
            "project_id": "test-project-id-123",
            "system_fingerprint": "test-fingerprint",
            "system_name": "test-machine",
            "cortex_api_url": "http://localhost:8181",
            "cortex_mcp_url": "http://localhost:8051",
        }
        entry.update(extra)
        return entry

    def test_writes_config_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = os.path.join(tmpdir, "my-project")
            os.makedirs(project_path)

            payload = {"projects": [self._make_project_entry(project_path)]}
            result = scanner.apply_configs(payload)

            assert result["apply_summary"]["created"] == 1
            assert result["apply_summary"]["failed"] == 0

            # cortex-config.json
            config_path = os.path.join(project_path, ".claude", "cortex-config.json")
            assert os.path.isfile(config_path)
            with open(config_path) as f:
                config = json.load(f)
            assert config["project_id"] == "test-project-id-123"
            assert config["installed_by"] == "scanner"

            # cortex-state.json
            state_path = os.path.join(project_path, ".claude", "cortex-state.json")
            assert os.path.isfile(state_path)
            with open(state_path) as f:
                state = json.load(f)
            assert state["system_fingerprint"] == "test-fingerprint"

    def test_writes_settings_local(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = os.path.join(tmpdir, "my-project")
            os.makedirs(project_path)

            payload = {"projects": [self._make_project_entry(project_path)]}
            scanner.apply_configs(payload)

            settings_path = os.path.join(project_path, ".claude", "settings.local.json")
            assert os.path.isfile(settings_path)
            with open(settings_path) as f:
                settings = json.load(f)
            assert "PostToolUse" in settings["hooks"]

    def test_gitignore_appended(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = os.path.join(tmpdir, "my-project")
            os.makedirs(project_path)

            # Pre-existing .gitignore
            gitignore_path = os.path.join(project_path, ".gitignore")
            with open(gitignore_path, "w") as f:
                f.write("*.pyc\n__pycache__/\n")

            payload = {"projects": [self._make_project_entry(project_path)]}
            scanner.apply_configs(payload)

            with open(gitignore_path) as f:
                content = f.read()

            # Original entries must be preserved
            assert "*.pyc" in content
            assert "__pycache__/" in content
            # Cortex block must be added
            assert "# Cortex" in content

    def test_gitignore_idempotent(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = os.path.join(tmpdir, "my-project")
            os.makedirs(project_path)

            payload = {"projects": [self._make_project_entry(project_path)]}

            # Apply twice
            scanner.apply_configs(payload)
            scanner.apply_configs(payload)

            gitignore_path = os.path.join(project_path, ".gitignore")
            with open(gitignore_path) as f:
                content = f.read()

            # Only one "# Cortex" block should exist
            assert content.count("# Cortex") == 1

    def test_gitignore_no_trailing_newline(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = os.path.join(tmpdir, "my-project")
            os.makedirs(project_path)

            gitignore_path = os.path.join(project_path, ".gitignore")
            # Write without trailing newline
            with open(gitignore_path, "w") as f:
                f.write("*.log")

            payload = {"projects": [self._make_project_entry(project_path)]}
            scanner.apply_configs(payload)

            with open(gitignore_path) as f:
                content = f.read()

            # "*.log" must remain intact (not corrupted by the Cortex block)
            assert "*.log" in content
            assert "# Cortex" in content
            # The original entry must be on its own line, not merged with # Cortex
            lines = content.splitlines()
            log_line = next((l for l in lines if "*.log" in l), None)
            assert log_line is not None
            assert log_line.strip() == "*.log"

    def test_gitignore_with_trailing_newline(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = os.path.join(tmpdir, "my-project")
            os.makedirs(project_path)

            gitignore_path = os.path.join(project_path, ".gitignore")
            with open(gitignore_path, "w") as f:
                f.write("*.log\n")

            payload = {"projects": [self._make_project_entry(project_path)]}
            scanner.apply_configs(payload)

            with open(gitignore_path) as f:
                content = f.read()

            # Should not produce a double blank line between existing content and Cortex block
            assert "\n\n\n" not in content
            assert "# Cortex" in content

    def test_nonexistent_path_fails_gracefully(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            payload = {
                "projects": [
                    self._make_project_entry(
                        os.path.join(tmpdir, "does-not-exist")
                    )
                ]
            }
            result = scanner.apply_configs(payload)

            assert result["apply_summary"]["failed"] == 1
            assert result["apply_summary"]["created"] == 0
            assert result["results"][0]["status"] == "failed"

    def test_missing_tarball_still_writes_configs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = os.path.join(tmpdir, "my-project")
            os.makedirs(project_path)

            payload = {"projects": [self._make_project_entry(project_path)]}
            # Tarball path does not exist
            result = scanner.apply_configs(
                payload,
                extensions_tarball=os.path.join(tmpdir, "nonexistent.tar.gz"),
            )

            # Config files should still be written
            assert result["apply_summary"]["created"] == 1
            config_path = os.path.join(project_path, ".claude", "cortex-config.json")
            assert os.path.isfile(config_path)

    def test_extracts_extensions_tarball(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = os.path.join(tmpdir, "my-project")
            os.makedirs(project_path)

            # Build a real .tar.gz with one test file
            tarball_path = os.path.join(tmpdir, "extensions.tar.gz")
            file_content = b"# test extension\n"
            with tarfile.open(tarball_path, "w:gz") as tar:
                info = tarfile.TarInfo(name="test-extension/init.sh")
                info.size = len(file_content)
                tar.addfile(info, io.BytesIO(file_content))

            payload = {"projects": [self._make_project_entry(project_path)]}
            result = scanner.apply_configs(payload, extensions_tarball=tarball_path)

            assert result["apply_summary"]["created"] == 1

            extracted_file = os.path.join(
                project_path, ".claude", "skills", "test-extension", "init.sh"
            )
            assert os.path.isfile(extracted_file)
            with open(extracted_file) as f:
                assert "test extension" in f.read()


# ---------------------------------------------------------------------------
# TestTomlParsing
# ---------------------------------------------------------------------------

class TestTomlParsing:
    def test_pyproject_toml_regex_fallback(self):
        """Test _parse_toml_regex directly with a realistic pyproject.toml."""
        toml_text = """\
[project]
name = "my-package"
version = "1.0.0"
dependencies = []

[tool.poetry]
name = "my-package"

[tool.poetry.dependencies]
python = "^3.10"
requests = "^2.28"
fastapi = ">=0.100"
"""
        result = scanner._parse_toml_regex(toml_text)

        # [project] section
        assert result["project"]["name"] == "my-package"

        # [tool.poetry.dependencies]
        poetry_deps = result.get("tool", {}).get("poetry", {}).get("dependencies", {})
        assert "requests" in poetry_deps
        assert "fastapi" in poetry_deps

    def test_pyproject_toml_via_scan(self):
        """Test pyproject.toml dependency extraction through the full scan pipeline."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = os.path.join(tmpdir, "python-project")
            os.makedirs(repo_path)
            _make_git_repo(repo_path)

            pyproject_content = """\
[project]
name = "python-project"
version = "0.1.0"
dependencies = ["httpx>=0.24", "pydantic>=2.0"]
"""
            with open(os.path.join(repo_path, "pyproject.toml"), "w") as f:
                f.write(pyproject_content)

            result = scanner.scan_directory(tmpdir)
            project = result["projects"][0]
            deps = project["dependencies"]
            assert deps is not None

            pip_entry = deps.get("pyproject.toml")
            assert pip_entry is not None
            assert pip_entry["type"] == "pip"
            # The dependencies list should contain the httpx and pydantic entries
            dep_list = pip_entry["data"].get("dependencies", [])
            assert any("httpx" in d for d in dep_list)
            assert any("pydantic" in d for d in dep_list)
