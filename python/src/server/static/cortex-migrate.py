#!/usr/bin/env python3
"""Migrate projects from Archon naming to Cortex naming.

Run once per machine:

    python3 cortex-migrate.py --api-url http://HOST:8181 --mcp-url http://HOST:8051

Optional arguments:
    --roots DIR [DIR ...]   Directories to search for projects (default: ~/projects)
    --dry-run               Print what would be done without making any changes
    --skip-machine          Skip machine-level migration even if all projects succeed
    --cf-client-id ID       Cloudflare Access client ID (for remote machines)
    --cf-client-secret SEC  Cloudflare Access client secret (for remote machines)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

KNOWN_HOST_PAT = re.compile(
    r"(localhost|127\.0\.0\.1|172\.16\.\d+\.\d+|[a-z0-9.-]*persalto\.io)"
)

OLD_SKILLS = [
    "archon-memory",
    "archon-bootstrap",
    "archon-link-project",
    "archon-extension-sync",
    "archon-skill-sync",
    "archon-move-project",
    "archon-prime",
    "archon-prime-simple",
    "archon-setup",
    "archon-ui-consistency-review",
    "archon-coderabbit-helper",
    "archon-rca",
    "archon-alpha-review",
    "archon-onboarding",
    "api-docs",
    "postman-integration",
    "scan-projects",
]
# Skills named exactly "archon" or "archon-dev" belong to the upstream
# Archon V2 CLI (a different product) and must never be removed or renamed.
OLD_COMMANDS = ["archon-setup.md", "scan-projects.md", "archon"]

RULES_RE = re.compile(
    r"<!-- archon-rules-start -->.*?<!-- archon-rules-end -->",
    re.DOTALL,
)


# ---------------------------------------------------------------------------
# Rename helpers
# ---------------------------------------------------------------------------


def ren(s: str) -> str:
    """Rename archon -> cortex in all case variants."""
    return s.replace("ARCHON", "CORTEX").replace("Archon", "Cortex").replace("archon", "cortex")


def ren_keys(obj):
    """Recursively rename archon -> cortex in dict keys, string values (persalto.io URLs only)."""
    if isinstance(obj, dict):
        return {ren(k): ren_keys(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [ren_keys(v) for v in obj]
    if isinstance(obj, str) and "persalto.io" in obj:
        return obj.replace("archon.persalto.io", "cortex.persalto.io")
    return obj


# ---------------------------------------------------------------------------
# HTTP fetch helper
# ---------------------------------------------------------------------------


def fetch_url(url: str, cf_headers: dict) -> bytes:
    """Fetch URL bytes, sending Cloudflare Access headers if provided."""
    req = urllib.request.Request(url, headers=cf_headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


def extract_tar(tf: tarfile.TarFile, dest: Path) -> None:
    """Extract a tar archive safely; falls back for Pythons without the filter arg."""
    try:
        tf.extractall(dest, filter="data")
    except TypeError:
        tf.extractall(dest)


# ---------------------------------------------------------------------------
# Migrator
# ---------------------------------------------------------------------------


class Migrator:
    def __init__(self, args: argparse.Namespace):
        self.api_url: str = args.api_url.rstrip("/")
        self.mcp_url: str = args.mcp_url.rstrip("/")
        self.dry_run: bool = args.dry_run
        self.skip_machine: bool = args.skip_machine

        self.cf_headers: dict = {}
        if args.cf_client_id:
            self.cf_headers["CF-Access-Client-Id"] = args.cf_client_id
        if args.cf_client_secret:
            self.cf_headers["CF-Access-Client-Secret"] = args.cf_client_secret

        self.migrated: list[Path] = []
        self.skipped: list[Path] = []
        self.failed: list[tuple[Path, str]] = []

        # Cache fetched bundles (url -> bytes) so we don't re-download per project
        self._bundle_cache: dict[str, bytes] = {}
        self._snippet_cache: str | None = None

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------

    def log(self, msg: str, prefix: str = "  ") -> None:
        tag = "[dry-run] " if self.dry_run else ""
        print(f"{prefix}{tag}{msg}")

    def log_action(self, msg: str) -> None:
        self.log(msg, prefix="  ")

    def log_ok(self, msg: str) -> None:
        print(f"  + {msg}")

    def log_skip(self, msg: str) -> None:
        print(f"  ~ {msg}")

    def log_warn(self, msg: str) -> None:
        print(f"  ! {msg}", file=sys.stderr)

    # ------------------------------------------------------------------
    # Bundle fetch helpers (cached)
    # ------------------------------------------------------------------

    def _fetch_bundle(self, url: str) -> bytes:
        if url not in self._bundle_cache:
            self.log_action(f"Fetching {url}")
            self._bundle_cache[url] = fetch_url(url, self.cf_headers)
        return self._bundle_cache[url]

    def _fetch_snippet(self) -> str:
        if self._snippet_cache is None:
            url = f"{self.mcp_url}/cortex-setup/claude-md-snippet.md"
            self.log_action(f"Fetching {url}")
            self._snippet_cache = fetch_url(url, self.cf_headers).decode("utf-8")
        return self._snippet_cache

    # ------------------------------------------------------------------
    # Project discovery
    # ------------------------------------------------------------------

    def discover_projects(self, roots: list[Path]) -> list[Path]:
        """Find projects at depth 1 and 2 under each root.

        Matches both unmigrated (.claude/archon-config.json) and already
        migrated (.claude/cortex-config.json) projects so re-runs report
        migrated projects as skipped instead of not finding anything.
        """
        found: list[Path] = []
        seen: set[Path] = set()

        for root in roots:
            if not root.is_dir():
                continue
            for marker in ("archon-config.json", "cortex-config.json"):
                for depth in (1, 2):
                    pattern = "/".join(["*"] * depth) + f"/.claude/{marker}"
                    for config_file in root.glob(pattern):
                        proj_dir = config_file.parent.parent
                        if proj_dir not in seen:
                            seen.add(proj_dir)
                            found.append(proj_dir)

        return sorted(found)

    # ------------------------------------------------------------------
    # Per-project migration
    # ------------------------------------------------------------------

    def migrate_project(self, proj_dir: Path) -> bool:
        """Migrate a single project directory. Returns True on success."""
        dot_claude = proj_dir / ".claude"
        cortex_config = dot_claude / "cortex-config.json"

        # Idempotency: already migrated
        if cortex_config.exists():
            self.log_skip(f"{proj_dir}: already migrated (cortex-config.json exists)")
            self.skipped.append(proj_dir)
            return True

        archon_config_path = dot_claude / "archon-config.json"
        if not archon_config_path.exists():
            self.log_skip(f"{proj_dir}: no archon-config.json found")
            self.skipped.append(proj_dir)
            return True

        print(f"\nMigrating: {proj_dir}")

        try:
            # Read archon-config content now; will be written last as the marker
            archon_config_content = json.loads(archon_config_path.read_text(encoding="utf-8-sig"))

            # 1. Rename state files (archon-state, archon-memory-buffer)
            self._step_rename_state_files(dot_claude)

            # 2. Update .mcp.json
            self._step_update_mcp_json(proj_dir)

            # 3. Replace extensions, commands, plugin
            self._step_replace_extensions(dot_claude)

            # 4. Update CLAUDE.md
            self._step_update_claude_md(proj_dir)

            # 5. Update .gitignore and settings.local.json
            self._step_update_gitignore(proj_dir)
            self._step_update_settings_local(dot_claude)

            # 6. Rename .archon -> .cortex
            self._step_rename_archon_dir(proj_dir)

            # 7. Write cortex-config.json (LAST — this is the migration marker)
            #    then delete archon-config.json
            self._step_write_cortex_config(dot_claude, archon_config_content, archon_config_path)

            self.log_ok(f"Migration complete: {proj_dir}")
            self.migrated.append(proj_dir)
            return True

        except Exception as exc:  # noqa: BLE001
            import traceback

            msg = f"{exc}\n{traceback.format_exc()}"
            self.log_warn(f"FAILED: {proj_dir}: {exc}")
            self.failed.append((proj_dir, str(exc)))
            return False

    def _step_rename_state_files(self, dot_claude: Path) -> None:
        """Rename archon-state.json (with key renames) and archon-memory-buffer.jsonl."""
        # archon-state.json contains archon-named keys (e.g. archon_project_id);
        # rewrite keys while preserving all values.
        state_path = dot_claude / "archon-state.json"
        if state_path.exists():
            new_state_path = dot_claude / "cortex-state.json"
            self.log_action(f"Rename {state_path.name} -> {new_state_path.name} with key renames")
            if not self.dry_run:
                state_data = json.loads(state_path.read_text(encoding="utf-8-sig"))
                new_state_path.write_text(
                    json.dumps(ren_keys(state_data), indent=2) + "\n",
                    encoding="utf-8",
                )
                state_path.unlink()

        # Memory buffer is observation data; rename only.
        buffer_path = dot_claude / "archon-memory-buffer.jsonl"
        if buffer_path.exists():
            new_buffer_path = dot_claude / "cortex-memory-buffer.jsonl"
            self.log_action(f"Rename {buffer_path.name} -> {new_buffer_path.name}")
            if not self.dry_run:
                buffer_path.rename(new_buffer_path)

        # Docs-sync state (present on machines using the docs-sync flow).
        docs_sync_path = dot_claude / "archon-docs-sync.json"
        if docs_sync_path.exists():
            new_docs_sync_path = dot_claude / "cortex-docs-sync.json"
            self.log_action(f"Rename {docs_sync_path.name} -> {new_docs_sync_path.name} with key renames")
            if not self.dry_run:
                try:
                    docs_data = json.loads(docs_sync_path.read_text(encoding="utf-8-sig"))
                    new_docs_sync_path.write_text(
                        json.dumps(ren_keys(docs_data), indent=2) + "\n",
                        encoding="utf-8",
                    )
                    docs_sync_path.unlink()
                except (json.JSONDecodeError, OSError):
                    docs_sync_path.rename(new_docs_sync_path)

    def _step_update_mcp_json(self, proj_dir: Path) -> None:
        """Rename 'archon' key -> 'cortex' in .mcp.json if URL matches known host pattern."""
        mcp_path = proj_dir / ".mcp.json"
        if not mcp_path.exists():
            return

        raw = mcp_path.read_text(encoding="utf-8-sig")
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            self.log_warn(f".mcp.json is not valid JSON, skipping: {mcp_path}")
            return

        # Work on the mcpServers dict (or top-level dict fallback)
        servers: dict = data.get("mcpServers", data if isinstance(data, dict) else {})
        changed = False

        if "archon" in servers:
            entry = servers["archon"]
            url_val: str = ""
            # Support both {url: ...} and {command: ..., args: [...]} style entries
            if isinstance(entry, dict):
                url_val = entry.get("url", "")
                if not url_val:
                    # Try to find url inside args
                    for arg in entry.get("args", []):
                        if isinstance(arg, str) and ("archon" in arg or "cortex" in arg):
                            url_val = arg
                            break

            if KNOWN_HOST_PAT.search(url_val):
                self.log_action(f".mcp.json: rename 'archon' key -> 'cortex'")
                if not self.dry_run:
                    servers["cortex"] = servers.pop("archon")
                    # Swap archon.persalto.io -> cortex.persalto.io in the entry
                    servers["cortex"] = ren_keys(servers["cortex"])
                    changed = True
            else:
                self.log_action(
                    f".mcp.json: 'archon' entry URL '{url_val}' does not match known host, skipping rename"
                )

        # Also fix persalto.io URLs in any existing cortex entry
        if "cortex" in servers and not changed:
            entry_str = json.dumps(servers["cortex"])
            if "archon.persalto.io" in entry_str:
                self.log_action(".mcp.json: fix archon.persalto.io -> cortex.persalto.io in 'cortex' entry")
                if not self.dry_run:
                    servers["cortex"] = ren_keys(servers["cortex"])
                    changed = True

        if changed and not self.dry_run:
            if "mcpServers" in data:
                data["mcpServers"] = servers
            mcp_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    def _step_replace_extensions(self, dot_claude: Path) -> None:
        """Install new cortex bundles, then remove old archon skills/commands/plugin.

        Install happens first so that old archon-named items are removed even if
        the served bundles still contain them — removal is the final word.
        """
        skills_dir = dot_claude / "skills"
        commands_dir = dot_claude / "commands"
        plugins_dir = dot_claude / "plugins"
        plugin_dir = plugins_dir / "cortex-memory"

        if self.dry_run:
            self.log_action(f"Would download+extract extensions.tar.gz to {skills_dir}/")
            self.log_action(f"Would download+extract commands.tar.gz to {commands_dir}/")
            self.log_action(f"Would download+extract cortex-memory.tar.gz to {plugin_dir}/")
            self.log_action(f"Would create venv at {plugin_dir}/.venv")
        else:
            # Install new bundles. Failures here raise so the project is marked
            # FAILED and the cortex-config.json marker is never written — a re-run
            # will then retry the install instead of skipping a half-migrated project.
            extensions_url = f"{self.mcp_url}/cortex-setup/extensions.tar.gz"
            bundle = self._fetch_bundle(extensions_url)
            skills_dir.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory() as tmpdir:
                tmp_path = Path(tmpdir) / "extensions.tar.gz"
                tmp_path.write_bytes(bundle)
                with tarfile.open(tmp_path, "r:gz") as tf:
                    extract_tar(tf, skills_dir)
            self.log_ok(f"Installed extensions -> {skills_dir}/")

            commands_url = f"{self.mcp_url}/cortex-setup/commands.tar.gz"
            bundle = self._fetch_bundle(commands_url)
            commands_dir.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory() as tmpdir:
                tmp_path = Path(tmpdir) / "commands.tar.gz"
                tmp_path.write_bytes(bundle)
                with tarfile.open(tmp_path, "r:gz") as tf:
                    extract_tar(tf, commands_dir)
            self.log_ok(f"Installed commands -> {commands_dir}/")

            plugin_url = f"{self.mcp_url}/cortex-setup/plugin/cortex-memory.tar.gz"
            bundle = self._fetch_bundle(plugin_url)
            plugins_dir.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory() as tmpdir:
                tmp_path = Path(tmpdir) / "cortex-memory.tar.gz"
                tmp_path.write_bytes(bundle)
                with tarfile.open(tmp_path, "r:gz") as tf:
                    extract_tar(tf, plugins_dir)

            # Ensure extracted files are at least owner-readable
            if plugin_dir.is_dir():
                for item in plugin_dir.rglob("*"):
                    try:
                        item.chmod(item.stat().st_mode | 0o400)
                    except OSError:
                        pass

            self.log_ok(f"Installed plugin -> {plugin_dir}/")

        # Remove old skills (after install, so stale bundle content cannot
        # re-introduce archon-named extensions)
        if skills_dir.is_dir():
            for skill_name in OLD_SKILLS:
                skill_path = skills_dir / skill_name
                if skill_path.is_dir():
                    self.log_action(f"Remove skill: {skill_path}")
                    if not self.dry_run:
                        shutil.rmtree(skill_path)

        # Remove old commands
        if commands_dir.is_dir():
            for cmd_name in OLD_COMMANDS:
                cmd_path = commands_dir / cmd_name
                if cmd_path.exists():
                    self.log_action(f"Remove command: {cmd_path}")
                    if not self.dry_run:
                        if cmd_path.is_dir():
                            shutil.rmtree(cmd_path)
                        else:
                            cmd_path.unlink()

        # Remove old plugin
        old_plugin = plugins_dir / "archon-memory"
        if old_plugin.is_dir():
            self.log_action(f"Remove plugin: {old_plugin}")
            if not self.dry_run:
                shutil.rmtree(old_plugin)

        if self.dry_run:
            return

        # Create plugin venv after old plugin removal so a failure here still
        # leaves the new plugin tree in place for a retry.
        self._create_plugin_venv(plugin_dir)

    def _create_plugin_venv(self, plugin_dir: Path) -> None:
        """Create .venv inside plugin_dir and install requirements.txt, mirroring cortexSetup.sh."""
        requirements = plugin_dir / "requirements.txt"
        if not requirements.exists():
            return

        venv_dir = plugin_dir / ".venv"

        # Remove stale venv
        if venv_dir.exists():
            self.log_action(f"Removing stale venv: {venv_dir}")
            shutil.rmtree(venv_dir)

        # Find Python 3.10+
        best_python: str | None = None
        for candidate in ["python3.13", "python3.12", "python3.11", "python3.10", "python3", "python"]:
            if shutil.which(candidate):
                try:
                    result = subprocess.run(
                        [candidate, "-c", "import sys; print(sys.version_info[:2] >= (3,10))"],
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )
                    if result.stdout.strip() == "True":
                        best_python = candidate
                        break
                except (subprocess.SubprocessError, OSError):
                    continue

        if best_python is None:
            self.log_warn("Python 3.10+ not found; skipping venv creation for cortex-memory plugin")
            return

        self.log_action(f"Creating plugin venv with {best_python}: {venv_dir}")
        try:
            subprocess.run(
                [best_python, "-m", "venv", str(venv_dir)],
                check=True,
                capture_output=True,
                timeout=60,
            )
        except subprocess.CalledProcessError as exc:
            self.log_warn(f"venv creation failed: {exc}; trying system pip install")
            try:
                subprocess.run(
                    [best_python, "-m", "pip", "install", "-q", "-r", str(requirements)],
                    check=True,
                    capture_output=True,
                    timeout=120,
                )
                self.log_ok("Plugin dependencies installed (system-wide)")
            except subprocess.CalledProcessError as exc2:
                self.log_warn(f"System pip install also failed: {exc2}")
            return

        pip_exe = venv_dir / "bin" / "pip"
        if not pip_exe.exists():
            # Windows layout
            pip_exe = venv_dir / "Scripts" / "pip.exe"

        try:
            subprocess.run(
                [str(pip_exe), "install", "-q", "--upgrade", "pip"],
                check=True,
                capture_output=True,
                timeout=60,
            )
            subprocess.run(
                [str(pip_exe), "install", "-q", "-r", str(requirements)],
                check=True,
                capture_output=True,
                timeout=180,
            )
            self.log_ok("Plugin dependencies installed in venv")
        except subprocess.CalledProcessError as exc:
            self.log_warn(f"pip install failed: {exc}")

    def _step_update_claude_md(self, proj_dir: Path) -> None:
        """Replace <!-- archon-rules-start/end --> block with cortex-wrapped snippet."""
        claude_md = proj_dir / "CLAUDE.md"
        if not claude_md.exists():
            return

        content = claude_md.read_text(encoding="utf-8-sig")
        if not RULES_RE.search(content):
            return

        self.log_action("CLAUDE.md: replace archon-rules block with cortex-rules")

        if self.dry_run:
            return

        # Snippet fetch failure raises so the project is marked FAILED and the
        # migration marker is never written; a re-run will retry.
        snippet = self._fetch_snippet()

        replacement = f"<!-- cortex-rules-start -->\n{snippet}\n<!-- cortex-rules-end -->"
        new_content = RULES_RE.sub(replacement, content)
        claude_md.write_text(new_content, encoding="utf-8")

    def _step_update_gitignore(self, proj_dir: Path) -> None:
        """Rename archon lines in .gitignore."""
        gitignore = proj_dir / ".gitignore"
        if not gitignore.exists():
            return

        lines = gitignore.read_text(encoding="utf-8-sig").splitlines(keepends=True)
        new_lines = []
        changed = False
        for line in lines:
            stripped = line.rstrip("\n\r")
            if "archon" in stripped.lower():
                renamed = ren(stripped)
                if renamed != stripped:
                    self.log_action(f".gitignore: {stripped!r} -> {renamed!r}")
                    if not self.dry_run:
                        new_lines.append(renamed + ("\n" if line.endswith("\n") else ""))
                        changed = True
                    else:
                        new_lines.append(line)
                    continue
            new_lines.append(line)

        if changed and not self.dry_run:
            gitignore.write_text("".join(new_lines), encoding="utf-8")

    def _step_update_settings_local(self, dot_claude: Path) -> None:
        """Replace mcp__archon__* with mcp__cortex__* in settings.local.json."""
        settings_path = dot_claude / "settings.local.json"
        if not settings_path.exists():
            return

        raw = settings_path.read_text(encoding="utf-8-sig")
        if "mcp__archon__" not in raw:
            return

        self.log_action("settings.local.json: replace mcp__archon__* -> mcp__cortex__*")
        if self.dry_run:
            return

        new_raw = raw.replace("mcp__archon__", "mcp__cortex__")
        settings_path.write_text(new_raw, encoding="utf-8")

    def _step_rename_archon_dir(self, proj_dir: Path) -> None:
        """Rename .archon/ -> .cortex/ if present and owned by this system.

        The upstream Archon V2 CLI (a different product) also uses .archon/
        with a workflows/ + config.yaml layout — leave those alone.
        """
        archon_dir = proj_dir / ".archon"
        cortex_dir = proj_dir / ".cortex"
        if not archon_dir.is_dir():
            return
        if (archon_dir / "workflows").is_dir() or (archon_dir / "config.yaml").exists():
            self.log_skip(".archon/ has the Archon V2 CLI layout (workflows/config.yaml) — left untouched")
            return
        self.log_action(f"Rename .archon -> .cortex")
        if not self.dry_run:
            archon_dir.rename(cortex_dir)

    def _step_write_cortex_config(
        self,
        dot_claude: Path,
        archon_config: dict,
        archon_config_path: Path,
    ) -> None:
        """Write cortex-config.json (with renamed keys) then delete archon-config.json."""
        cortex_config = ren_keys(archon_config)
        cortex_config_path = dot_claude / "cortex-config.json"

        self.log_action(f"Write {cortex_config_path}")
        if not self.dry_run:
            cortex_config_path.write_text(
                json.dumps(cortex_config, indent=2) + "\n",
                encoding="utf-8",
            )

        self.log_action(f"Delete {archon_config_path}")
        if not self.dry_run:
            archon_config_path.unlink()

    # ------------------------------------------------------------------
    # Machine-level migration
    # ------------------------------------------------------------------

    def migrate_machine(self) -> None:
        """Migrate machine-level Archon artifacts (hooks, state, config dir)."""
        home = Path.home()
        global_settings = home / ".claude" / "settings.json"

        print("\n--- Machine-level migration ---")

        # Update ~/.claude/settings.json (hook paths)
        if global_settings.exists():
            raw = global_settings.read_text(encoding="utf-8-sig")
            if "archon" in raw or "ARCHON" in raw:
                self.log_action("~/.claude/settings.json: rename archon references (hook paths)")
                if not self.dry_run:
                    global_settings.write_text(ren(raw), encoding="utf-8")
                    self.log_ok("Updated ~/.claude/settings.json")
            else:
                self.log_skip("~/.claude/settings.json: no archon references found")

        # Rename user-scoped MCP entries in ~/.claude.json (projects configured
        # via `claude mcp add` without a project .mcp.json live here). Key
        # "archon" -> "cortex", gated on the URL matching our known hosts so an
        # upstream Archon V2 entry is never touched.
        claude_json = home / ".claude.json"
        if claude_json.exists():
            try:
                data = json.loads(claude_json.read_text(encoding="utf-8-sig"))
                changed = 0
                scopes = [data] + list(data.get("projects", {}).values())
                for scope in scopes:
                    servers = scope.get("mcpServers")
                    if not isinstance(servers, dict) or "archon" not in servers:
                        continue
                    entry = servers["archon"]
                    url = entry.get("url", "") or " ".join(entry.get("args", []) or [])
                    if KNOWN_HOST_PAT.search(url):
                        if isinstance(entry.get("url"), str):
                            entry["url"] = entry["url"].replace(
                                "archon.persalto.io", "cortex.persalto.io"
                            )
                        servers["cortex"] = entry
                        del servers["archon"]
                        changed += 1
                if changed:
                    self.log_action(
                        f"~/.claude.json: rename {changed} user-scoped 'archon' MCP entries -> 'cortex'"
                    )
                    if not self.dry_run:
                        backup = claude_json.with_name(".claude.json.pre-cortex-rename.bak")
                        if not backup.exists():
                            shutil.copy2(claude_json, backup)
                        claude_json.write_text(
                            json.dumps(data, indent=2) + "\n", encoding="utf-8"
                        )
                        self.log_ok(f"Updated ~/.claude.json ({changed} entries; backup kept)")
            except Exception as exc:  # noqa: BLE001
                self.log_warn(f"Could not migrate ~/.claude.json MCP entries: {exc}")

        # Rename ~/.claude/archon-state.json -> cortex-state.json with ren_keys
        archon_state = home / ".claude" / "archon-state.json"
        cortex_state = home / ".claude" / "cortex-state.json"
        if archon_state.exists():
            self.log_action(f"Rename {archon_state} -> {cortex_state.name} with key renames")
            if not self.dry_run:
                try:
                    state_data = json.loads(archon_state.read_text(encoding="utf-8-sig"))
                    renamed_data = ren_keys(state_data)
                    cortex_state.write_text(json.dumps(renamed_data, indent=2) + "\n", encoding="utf-8")
                    archon_state.unlink()
                    self.log_ok("Renamed ~/.claude/archon-state.json -> cortex-state.json")
                except Exception as exc:  # noqa: BLE001
                    self.log_warn(f"Could not migrate ~/.claude/archon-state.json: {exc}")

        # ~/.config/archon -> ~/.config/cortex (including file content renames)
        xdg_config = home / ".config"
        archon_config_dir = xdg_config / "archon"
        cortex_config_dir = xdg_config / "cortex"
        if archon_config_dir.is_dir():
            self.log_action(f"Rename ~/.config/archon -> ~/.config/cortex with content renames")
            if not self.dry_run:
                try:
                    # Copy tree, then rename archon-> cortex in filenames and file content
                    if cortex_config_dir.exists():
                        shutil.rmtree(cortex_config_dir)
                    shutil.copytree(str(archon_config_dir), str(cortex_config_dir))

                    # Rename files whose names contain "archon"
                    for old_file in sorted(cortex_config_dir.rglob("*"), reverse=True):
                        if "archon" in old_file.name:
                            new_name = old_file.parent / ren(old_file.name)
                            old_file.rename(new_name)

                    # Rename content in .env and .json files
                    for item in cortex_config_dir.rglob("*"):
                        if item.is_file() and item.suffix in (".env", ".json", ""):
                            try:
                                text = item.read_text(encoding="utf-8-sig")
                                new_text = ren(text)
                                if new_text != text:
                                    item.write_text(new_text, encoding="utf-8")
                            except (UnicodeDecodeError, OSError):
                                pass

                    shutil.rmtree(str(archon_config_dir))
                    self.log_ok("Renamed ~/.config/archon -> ~/.config/cortex")
                except Exception as exc:  # noqa: BLE001
                    self.log_warn(f"Could not migrate ~/.config/archon: {exc}")

        self._remove_global_archon_extensions()

    def _remove_global_archon_extensions(self) -> None:
        """Remove globally-installed archon-* extensions from ~/.claude.

        Extensions are meant to be project-scoped, so any archon-named skills,
        commands, or the archon-memory plugin installed in the global ~/.claude
        are removed (not reinstalled). The upstream Archon V2 CLI skills named
        exactly 'archon' or 'archon-dev' are preserved.
        """
        gclaude = Path.home() / ".claude"
        removed: list[str] = []

        def _rm(target: Path, label: str) -> None:
            removed.append(label)
            if not self.dry_run:
                if target.is_dir():
                    shutil.rmtree(target, ignore_errors=True)
                else:
                    try:
                        target.unlink()
                    except OSError:
                        pass

        skills_dir = gclaude / "skills"
        if skills_dir.is_dir():
            for child in sorted(skills_dir.iterdir()):
                name = child.name
                if name in ("archon", "archon-dev"):
                    continue  # upstream Archon V2 CLI — never touch
                if name.startswith("archon-"):
                    _rm(child, f"skills/{name}")

        commands_dir = gclaude / "commands"
        if commands_dir.is_dir():
            archon_group = commands_dir / "archon"
            if archon_group.is_dir():
                _rm(archon_group, "commands/archon")
            for child in sorted(commands_dir.glob("archon-*")):
                _rm(child, f"commands/{child.name}")

        plugin_dir = gclaude / "plugins" / "archon-memory"
        if plugin_dir.is_dir():
            _rm(plugin_dir, "plugins/archon-memory")

        if removed:
            self.log_action(
                f"~/.claude: remove {len(removed)} global archon extension(s): {', '.join(removed)}"
            )
            if not self.dry_run:
                self.log_ok(f"Removed {len(removed)} global archon extension(s)")
        else:
            self.log_skip("~/.claude: no global archon extensions found")

    # ------------------------------------------------------------------
    # Main run
    # ------------------------------------------------------------------

    def run(self, roots: list[Path]) -> int:
        projects = self.discover_projects(roots)

        if not projects:
            print("No Archon-connected projects found in the specified roots.")
            return 0

        print(f"Found {len(projects)} project(s) to check:")
        for p in projects:
            print(f"  {p}")

        for proj_dir in projects:
            self.migrate_project(proj_dir)

        all_ok = len(self.failed) == 0

        if all_ok and not self.skip_machine:
            self.migrate_machine()
        elif not all_ok:
            print(
                "\nMachine-level migration skipped because some projects failed.",
                file=sys.stderr,
            )
        elif self.skip_machine:
            print("\nMachine-level migration skipped (--skip-machine).")

        # Summary
        print("\n" + "=" * 50)
        print("Summary")
        print("=" * 50)
        print(f"  Migrated : {len(self.migrated)}")
        print(f"  Skipped  : {len(self.skipped)}")
        print(f"  Failed   : {len(self.failed)}")
        if self.failed:
            print("\nFailed projects:")
            for path, reason in self.failed:
                print(f"  {path}: {reason}")

        return 1 if self.failed else 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def default_roots() -> list[str]:
    """Common project-root locations that actually exist on this machine.

    Repos don't always live under ~/projects — on Windows they're often on a
    secondary drive (e.g. E:\\Projects). Scan the home dir plus common drive
    roots so a default run doesn't silently miss them.
    """
    candidates = [Path.home() / "projects", Path.home() / "Projects"]
    if os.name == "nt":
        for drive in ("C", "D", "E", "F", "G"):
            candidates.append(Path(f"{drive}:\\Projects"))
            candidates.append(Path(f"{drive}:\\projects"))
    roots: list[str] = []
    for c in candidates:
        s = str(c)
        if c.is_dir() and s not in roots:
            roots.append(s)
    return roots or [str(Path.home() / "projects")]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Migrate Archon-connected projects to Cortex naming.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--api-url",
        required=True,
        help="Cortex API URL (e.g. http://172.16.1.230:8181)",
    )
    parser.add_argument(
        "--mcp-url",
        required=True,
        help="Cortex MCP URL (e.g. http://172.16.1.230:8051)",
    )
    parser.add_argument(
        "--roots",
        nargs="+",
        default=default_roots(),
        help="Root directories to search for projects "
        "(default: ~/projects plus common drive roots like E:\\Projects on Windows)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print actions without making any filesystem changes",
    )
    parser.add_argument(
        "--skip-machine",
        action="store_true",
        help="Skip machine-level migration even if all projects succeed",
    )
    parser.add_argument(
        "--cf-client-id",
        default="",
        help="Cloudflare Access client ID (for remote machines behind CF Access)",
    )
    parser.add_argument(
        "--cf-client-secret",
        default="",
        help="Cloudflare Access client secret",
    )

    args = parser.parse_args()
    roots = [Path(r).expanduser() for r in args.roots]

    migrator = Migrator(args)
    return migrator.run(roots)


if __name__ == "__main__":
    sys.exit(main())
