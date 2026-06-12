"""Tests for session_start_hook — _auto_update_plugin and _parse_version."""

import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

# Ensure plugin src is importable
_PLUGIN_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_PLUGIN_ROOT))

from scripts.session_start_hook import _auto_update_plugin, _parse_version


# ── _parse_version ──────────────────────────────────────────────────────────


class TestParseVersion:
    def test_simple_semver(self):
        assert _parse_version("1.2.3") == (1, 2, 3)

    def test_major_only(self):
        assert _parse_version("2") == (2,)

    def test_two_part(self):
        assert _parse_version("1.0") == (1, 0)

    def test_comparison_major(self):
        assert _parse_version("2.0.0") > _parse_version("1.9.9")

    def test_comparison_minor(self):
        assert _parse_version("1.1.0") > _parse_version("1.0.9")

    def test_comparison_patch(self):
        assert _parse_version("1.0.1") > _parse_version("1.0.0")

    def test_equal(self):
        assert _parse_version("1.0.0") == _parse_version("1.0.0")

    def test_invalid_returns_zero(self):
        assert _parse_version("not-a-version") == (0, 0, 0)

    def test_none_returns_zero(self):
        assert _parse_version(None) == (0, 0, 0)

    def test_empty_string_returns_zero(self):
        assert _parse_version("") == (0, 0, 0)


# ── _auto_update_plugin ────────────────────────────────────────────────────


def _make_plugin_dir(tmp_path: Path, version: str = "1.0.0", reqs: str = "httpx>=0.27.0\n") -> Path:
    """Create a minimal plugin directory structure for testing."""
    plugin_dir = tmp_path / "cortex-memory"
    plugin_dir.mkdir()
    meta_dir = plugin_dir / ".claude-plugin"
    meta_dir.mkdir()
    (meta_dir / "plugin.json").write_text(json.dumps({"name": "cortex-memory", "version": version}))
    (plugin_dir / "requirements.txt").write_text(reqs)
    # Create some source files to verify they get replaced
    src_dir = plugin_dir / "src"
    src_dir.mkdir()
    (src_dir / "old_file.py").write_text("# old version")
    (plugin_dir / "README.md").write_text("# Old readme")
    return plugin_dir


def _make_tarball(version: str = "1.1.0", reqs: str = "httpx>=0.27.0\n", extra_file: str | None = None) -> bytes:
    """Build an in-memory tarball matching what the server would produce."""
    import io
    import tarfile

    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        # plugin.json
        manifest = json.dumps({"name": "cortex-memory", "version": version}).encode()
        info = tarfile.TarInfo(name="cortex-memory/.claude-plugin/plugin.json")
        info.size = len(manifest)
        tar.addfile(info, io.BytesIO(manifest))

        # requirements.txt
        reqs_bytes = reqs.encode()
        info = tarfile.TarInfo(name="cortex-memory/requirements.txt")
        info.size = len(reqs_bytes)
        tar.addfile(info, io.BytesIO(reqs_bytes))

        # A new source file
        new_src = b"# new version"
        info = tarfile.TarInfo(name="cortex-memory/src/new_file.py")
        info.size = len(new_src)
        tar.addfile(info, io.BytesIO(new_src))

        # README
        readme = b"# New readme"
        info = tarfile.TarInfo(name="cortex-memory/README.md")
        info.size = len(readme)
        tar.addfile(info, io.BytesIO(readme))

        if extra_file:
            data = extra_file.encode()
            info = tarfile.TarInfo(name=f"cortex-memory/{extra_file}")
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))

    buf.seek(0)
    return buf.read()


class TestAutoUpdatePlugin:
    @pytest.mark.anyio
    async def test_skips_when_no_manifest(self, tmp_path):
        plugin_dir = tmp_path / "cortex-memory"
        plugin_dir.mkdir()
        result = await _auto_update_plugin("http://localhost:8051", plugin_dir)
        assert result is None

    @pytest.mark.anyio
    async def test_skips_when_no_mcp_url(self, tmp_path):
        plugin_dir = _make_plugin_dir(tmp_path)
        result = await _auto_update_plugin("", plugin_dir)
        assert result is None

    @pytest.mark.anyio
    async def test_skips_when_already_up_to_date(self, tmp_path):
        plugin_dir = _make_plugin_dir(tmp_path, version="1.1.0")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"version": "1.1.0"}

        with patch("httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            result = await _auto_update_plugin("http://localhost:8051", plugin_dir)
            assert result is None

    @pytest.mark.anyio
    async def test_skips_when_server_unreachable(self, tmp_path):
        plugin_dir = _make_plugin_dir(tmp_path)

        with patch("httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get.side_effect = Exception("Connection refused")
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            result = await _auto_update_plugin("http://localhost:8051", plugin_dir)
            assert result is None

    @pytest.mark.anyio
    async def test_updates_when_newer_version_available(self, tmp_path):
        plugin_dir = _make_plugin_dir(tmp_path, version="1.0.0")
        tarball_bytes = _make_tarball(version="1.1.0")

        manifest_resp = MagicMock()
        manifest_resp.status_code = 200
        manifest_resp.json.return_value = {"version": "1.1.0"}

        tarball_resp = MagicMock()
        tarball_resp.status_code = 200
        tarball_resp.content = tarball_bytes

        call_count = 0

        async def mock_get(url, **kwargs):
            nonlocal call_count
            call_count += 1
            if "plugin-manifest" in url:
                return manifest_resp
            return tarball_resp

        with patch("httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get = mock_get
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            result = await _auto_update_plugin("http://localhost:8051", plugin_dir)

        assert result is not None
        assert "1.0.0" in result
        assert "1.1.0" in result

        # Verify files were updated
        new_manifest = json.loads((plugin_dir / ".claude-plugin" / "plugin.json").read_text())
        assert new_manifest["version"] == "1.1.0"
        assert (plugin_dir / "README.md").read_text() == "# New readme"
        assert (plugin_dir / "src" / "new_file.py").read_text() == "# new version"

    @pytest.mark.anyio
    async def test_preserves_venv(self, tmp_path):
        plugin_dir = _make_plugin_dir(tmp_path, version="1.0.0")
        # Create a fake .venv
        venv_dir = plugin_dir / ".venv"
        venv_dir.mkdir()
        (venv_dir / "pyvenv.cfg").write_text("home = /usr/bin")

        tarball_bytes = _make_tarball(version="1.1.0")

        manifest_resp = MagicMock()
        manifest_resp.status_code = 200
        manifest_resp.json.return_value = {"version": "1.1.0"}

        tarball_resp = MagicMock()
        tarball_resp.status_code = 200
        tarball_resp.content = tarball_bytes

        async def mock_get(url, **kwargs):
            if "plugin-manifest" in url:
                return manifest_resp
            return tarball_resp

        with patch("httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get = mock_get
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            result = await _auto_update_plugin("http://localhost:8051", plugin_dir)

        assert result is not None
        # .venv must still exist with its original content
        assert venv_dir.exists()
        assert (venv_dir / "pyvenv.cfg").read_text() == "home = /usr/bin"

    @pytest.mark.anyio
    async def test_removes_old_files_not_in_new_version(self, tmp_path):
        plugin_dir = _make_plugin_dir(tmp_path, version="1.0.0")
        # old_file.py exists in the old version but not in the tarball
        assert (plugin_dir / "src" / "old_file.py").exists()

        tarball_bytes = _make_tarball(version="1.1.0")

        manifest_resp = MagicMock()
        manifest_resp.status_code = 200
        manifest_resp.json.return_value = {"version": "1.1.0"}

        tarball_resp = MagicMock()
        tarball_resp.status_code = 200
        tarball_resp.content = tarball_bytes

        async def mock_get(url, **kwargs):
            if "plugin-manifest" in url:
                return manifest_resp
            return tarball_resp

        with patch("httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get = mock_get
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            await _auto_update_plugin("http://localhost:8051", plugin_dir)

        # old_file.py should be gone (old src/ was removed and replaced)
        assert not (plugin_dir / "src" / "old_file.py").exists()
        # new_file.py should be present
        assert (plugin_dir / "src" / "new_file.py").exists()

    @pytest.mark.anyio
    async def test_reinstalls_deps_when_requirements_change(self, tmp_path):
        plugin_dir = _make_plugin_dir(tmp_path, version="1.0.0", reqs="httpx>=0.27.0\n")
        # Create a fake venv with pip
        venv_dir = plugin_dir / ".venv"
        bin_dir = venv_dir / "bin"
        bin_dir.mkdir(parents=True)
        fake_pip = bin_dir / "pip"
        fake_pip.write_text("#!/bin/sh\necho pip")
        fake_pip.chmod(0o755)

        # Tarball has different requirements
        tarball_bytes = _make_tarball(version="1.1.0", reqs="httpx>=0.28.0\ntree-sitter>=0.25.0\n")

        manifest_resp = MagicMock()
        manifest_resp.status_code = 200
        manifest_resp.json.return_value = {"version": "1.1.0"}

        tarball_resp = MagicMock()
        tarball_resp.status_code = 200
        tarball_resp.content = tarball_bytes

        async def mock_get(url, **kwargs):
            if "plugin-manifest" in url:
                return manifest_resp
            return tarball_resp

        with patch("httpx.AsyncClient") as MockClient, \
             patch("subprocess.run") as mock_subprocess:
            mock_client = AsyncMock()
            mock_client.get = mock_get
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            await _auto_update_plugin("http://localhost:8051", plugin_dir)

        # subprocess.run should have been called with pip install
        mock_subprocess.assert_called_once()
        call_args = mock_subprocess.call_args
        assert "pip" in str(call_args)
        assert "-r" in call_args[0][0]

    @pytest.mark.anyio
    async def test_skips_pip_when_requirements_unchanged(self, tmp_path):
        plugin_dir = _make_plugin_dir(tmp_path, version="1.0.0", reqs="httpx>=0.27.0\n")
        # Create a fake venv with pip
        venv_dir = plugin_dir / ".venv"
        bin_dir = venv_dir / "bin"
        bin_dir.mkdir(parents=True)
        (bin_dir / "pip").write_text("#!/bin/sh\necho pip")

        # Tarball has same requirements
        tarball_bytes = _make_tarball(version="1.1.0", reqs="httpx>=0.27.0\n")

        manifest_resp = MagicMock()
        manifest_resp.status_code = 200
        manifest_resp.json.return_value = {"version": "1.1.0"}

        tarball_resp = MagicMock()
        tarball_resp.status_code = 200
        tarball_resp.content = tarball_bytes

        async def mock_get(url, **kwargs):
            if "plugin-manifest" in url:
                return manifest_resp
            return tarball_resp

        with patch("httpx.AsyncClient") as MockClient, \
             patch("subprocess.run") as mock_subprocess:
            mock_client = AsyncMock()
            mock_client.get = mock_get
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            await _auto_update_plugin("http://localhost:8051", plugin_dir)

        # subprocess.run should NOT have been called
        mock_subprocess.assert_not_called()

    @pytest.mark.anyio
    async def test_skips_when_remote_older(self, tmp_path):
        plugin_dir = _make_plugin_dir(tmp_path, version="2.0.0")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"version": "1.0.0"}

        with patch("httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            result = await _auto_update_plugin("http://localhost:8051", plugin_dir)
            assert result is None
