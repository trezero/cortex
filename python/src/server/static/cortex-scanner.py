#!/usr/bin/env python3
from __future__ import annotations
"""
cortex-scanner.py — Cortex Local Project Scanner

Usage:
    python3 cortex-scanner.py --scan <directory>
        Scan a directory for Git repositories and output JSON to stdout.

    python3 cortex-scanner.py --scan <directory> --apply
        Scan and apply configuration to discovered projects.

    python3 cortex-scanner.py --payload-file <path>
        Apply configuration from a pre-generated payload JSON file.

    python3 cortex-scanner.py --extensions-tarball <path>
        Install extensions from a tarball.

    python3 cortex-scanner.py --version
        Print scanner version.

This script runs on the user's machine (NOT inside Docker). It uses Python
stdlib only and requires Python 3.10+.
"""

import sys
if sys.version_info < (3, 10):
    print(
        f"WARNING: Python {sys.version_info.major}.{sys.version_info.minor} detected. "
        "Python 3.10+ is recommended for the Cortex scanner.\n"
        "Install Python 3.10: https://www.python.org/downloads/",
        file=sys.stderr,
    )

import argparse
import configparser
import hashlib
import json
import os
import re
import tarfile
import uuid
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SCANNER_VERSION = "1.0"

SKIP_DIRS = {
    "node_modules", ".git", "__pycache__", ".venv", "venv",
    ".cache", ".npm", ".nvm", "dist", "build", ".tox",
    "vendor", "target", ".gradle", "Pods",
}

LANGUAGE_EXTENSIONS = {
    ".py": "python", ".js": "javascript", ".ts": "typescript",
    ".tsx": "typescript", ".jsx": "javascript", ".rs": "rust",
    ".go": "go", ".java": "java", ".rb": "ruby", ".php": "php",
    ".cs": "csharp", ".cpp": "cpp", ".c": "c", ".swift": "swift",
    ".kt": "kotlin", ".scala": "scala", ".dart": "dart",
    ".vue": "vue", ".svelte": "svelte",
}

PROJECT_INDICATORS = {
    "package.json": "node", "pyproject.toml": "python", "setup.py": "python",
    "requirements.txt": "python", "Cargo.toml": "rust", "go.mod": "go",
    "pom.xml": "java", "build.gradle": "java", "Gemfile": "ruby",
    "composer.json": "php", "Package.swift": "swift", "pubspec.yaml": "dart",
}

INFRA_MARKERS = {
    "docker-compose.yml": "docker", "docker-compose.yaml": "docker",
    "Dockerfile": "docker", ".github/workflows": "github-actions",
    ".gitlab-ci.yml": "gitlab-ci", "firebase.json": "firebase",
    ".firebaserc": "firebase", "vercel.json": "vercel",
    "netlify.toml": "netlify", "serverless.yml": "serverless",
    "terraform": "terraform", "k8s": "kubernetes",
    "Makefile": "make", ".env.example": "env-config",
    "supabase": "supabase", "prisma": "prisma",
    ".github/dependabot.yml": "dependabot",
}

DEPENDENCY_EXTRACTORS = {
    "package.json": "npm", "pyproject.toml": "pip", "requirements.txt": "pip",
    "Cargo.toml": "cargo", "go.mod": "go", "pom.xml": "maven", "build.gradle": "gradle",
}

README_EXCERPT_LENGTH = 5000

GITIGNORE_ENTRIES = [
    "# Cortex", ".claude/plugins/", ".claude/skills/",
    ".claude/cortex-config.json", ".claude/cortex-state.json",
    ".claude/cortex-memory-buffer.jsonl", ".claude/settings.local.json",
    ".mcp.json", ".cortex/",
]


# ---------------------------------------------------------------------------
# URL normalization helpers
# ---------------------------------------------------------------------------

def normalize_github_url(url: str) -> str | None:
    """
    Normalize a raw Git remote URL to a canonical https://github.com/owner/repo form.

    Handles SSH (git@github.com:owner/repo.git) and HTTPS variants.
    Returns None for non-GitHub remotes.
    """
    if not url:
        return None

    url = url.strip()

    # SSH form: git@github.com:owner/repo.git
    ssh_match = re.match(r"^git@github\.com[:/](.+?)(?:\.git)?$", url, re.IGNORECASE)
    if ssh_match:
        path = ssh_match.group(1).strip("/")
        return f"https://github.com/{path.lower()}"

    # HTTPS form: https://github.com/owner/repo or https://github.com/owner/repo.git
    https_match = re.match(r"^https?://github\.com/(.+?)(?:\.git)?$", url, re.IGNORECASE)
    if https_match:
        path = https_match.group(1).strip("/")
        return f"https://github.com/{path.lower()}"

    return None


def extract_github_owner_repo(url: str) -> tuple:
    """
    Extract (owner, repo_name) from a GitHub URL string (normalized or raw).

    Returns (None, None) if extraction fails.
    """
    normalized = normalize_github_url(url)
    if not normalized:
        return (None, None)

    # https://github.com/owner/repo
    match = re.match(r"^https://github\.com/([^/]+)/([^/]+)$", normalized)
    if match:
        return (match.group(1), match.group(2))

    return (None, None)


# ---------------------------------------------------------------------------
# TOML parsing (stdlib tomllib on 3.11+, regex fallback for 3.8–3.10)
# ---------------------------------------------------------------------------

def _load_toml(file_path: str) -> dict:
    """Load a TOML file, using tomllib (3.11+) or regex fallback."""
    try:
        import tomllib  # Python 3.11+
        with open(file_path, "rb") as f:
            return tomllib.load(f)
    except ImportError:
        pass

    # Fallback: read raw text and parse with regex
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            return _parse_toml_regex(f.read())
    except Exception:
        return {}


def _parse_toml_regex(text: str) -> dict:
    """
    Minimal regex-based TOML parser sufficient for extracting dependency sections.

    Only handles simple key = "value" and [section] / [[array-of-tables]] headers.
    Good enough for pyproject.toml, Cargo.toml dependency extraction.
    """
    result: dict = {}
    current_section: list = []

    for raw_line in text.splitlines():
        line = raw_line.strip()

        # Skip comments and blank lines
        if not line or line.startswith("#"):
            continue

        # Array-of-tables header: [[section.sub]]
        aat_match = re.match(r"^\[\[([^\]]+)\]\]$", line)
        if aat_match:
            current_section = aat_match.group(1).strip().split(".")
            continue

        # Table header: [section.sub]
        table_match = re.match(r"^\[([^\]]+)\]$", line)
        if table_match:
            current_section = table_match.group(1).strip().split(".")
            continue

        # Key = value
        kv_match = re.match(r'^(\w[\w\-\.]*)\s*=\s*(.+)$', line)
        if kv_match:
            key = kv_match.group(1).strip()
            raw_value = kv_match.group(2).strip()

            # Parse value: quoted string
            str_match = re.match(r'^["\'](.+)["\']$', raw_value)
            if str_match:
                value = str_match.group(1)
            elif raw_value.lower() == "true":
                value = True
            elif raw_value.lower() == "false":
                value = False
            else:
                # Leave as string for numbers and other types
                value = raw_value

            # Navigate/create nested dict
            node = result
            for part in current_section:
                node = node.setdefault(part, {})
            node[key] = value

    return result


# ---------------------------------------------------------------------------
# Dependency extraction helpers
# ---------------------------------------------------------------------------

def _extract_npm_deps(project_path: str) -> dict:
    """Extract dependencies from package.json."""
    pkg_file = os.path.join(project_path, "package.json")
    try:
        with open(pkg_file, "r", encoding="utf-8", errors="replace") as f:
            data = json.load(f)
    except Exception:
        return {}

    deps: dict = {}
    for section in ("dependencies", "devDependencies", "peerDependencies"):
        section_data = data.get(section)
        if isinstance(section_data, dict):
            deps[section] = section_data
    return deps


def _extract_toml_deps(project_path: str, filename: str) -> dict:
    """Extract dependencies from a TOML file (pyproject.toml or Cargo.toml)."""
    toml_file = os.path.join(project_path, filename)
    if not os.path.isfile(toml_file):
        return {}

    data = _load_toml(toml_file)
    if not data:
        return {}

    deps: dict = {}

    if filename == "pyproject.toml":
        # PEP 517/518: [project] dependencies
        project_section = data.get("project", {})
        project_deps = project_section.get("dependencies", [])
        if isinstance(project_deps, list):
            deps["dependencies"] = project_deps

        optional_deps = project_section.get("optional-dependencies", {})
        if isinstance(optional_deps, dict):
            deps["optional-dependencies"] = optional_deps

        # Poetry: [tool.poetry.dependencies]
        poetry = data.get("tool", {}).get("poetry", {})
        poetry_deps = poetry.get("dependencies", {})
        if isinstance(poetry_deps, dict):
            deps.setdefault("dependencies", poetry_deps)
        poetry_dev = poetry.get("dev-dependencies", {})
        if isinstance(poetry_dev, dict):
            deps["dev-dependencies"] = poetry_dev

    elif filename == "Cargo.toml":
        # Cargo [dependencies], [dev-dependencies], [build-dependencies]
        for section in ("dependencies", "dev-dependencies", "build-dependencies"):
            section_data = data.get(section)
            if isinstance(section_data, dict):
                deps[section] = section_data

    return deps


def _extract_toml_deps_regex(project_path: str, filename: str) -> dict:
    """
    Regex-based fallback for TOML dependency extraction (Python 3.8-3.10).

    This delegates to _extract_toml_deps which already uses the regex fallback
    when tomllib is not available.
    """
    return _extract_toml_deps(project_path, filename)


def _extract_requirements_deps(project_path: str) -> dict:
    """Extract packages from requirements.txt."""
    req_file = os.path.join(project_path, "requirements.txt")
    try:
        with open(req_file, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except Exception:
        return {}

    packages = []
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("-"):
            continue
        # Strip version specifiers for the package name
        pkg_match = re.match(r"^([A-Za-z0-9_\-\.]+)", line)
        if pkg_match:
            packages.append(line)  # Keep original spec

    return {"packages": packages} if packages else {}


def _extract_cargo_deps(project_path: str) -> dict:
    """Extract dependencies from Cargo.toml (reuses TOML extractor)."""
    return _extract_toml_deps(project_path, "Cargo.toml")


def _extract_go_deps(project_path: str) -> dict:
    """Extract module requirements from go.mod."""
    go_mod = os.path.join(project_path, "go.mod")
    try:
        with open(go_mod, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except Exception:
        return {}

    # Extract module name
    module_match = re.search(r"^module\s+(\S+)", content, re.MULTILINE)
    module_name = module_match.group(1) if module_match else None

    # Extract require blocks
    requires = re.findall(r"^\s+(\S+)\s+(v[\S]+)", content, re.MULTILINE)
    deps = {pkg: ver for pkg, ver in requires}

    result: dict = {}
    if module_name:
        result["module"] = module_name
    if deps:
        result["require"] = deps

    return result


def _extract_maven_deps(project_path: str) -> dict:
    """Extract dependencies from pom.xml using regex."""
    pom_file = os.path.join(project_path, "pom.xml")
    try:
        with open(pom_file, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except Exception:
        return {}

    # Extract groupId:artifactId pairs from <dependency> blocks
    dep_pattern = re.compile(
        r"<dependency>.*?<groupId>([^<]+)</groupId>.*?<artifactId>([^<]+)</artifactId>",
        re.DOTALL
    )
    deps = [f"{m.group(1).strip()}:{m.group(2).strip()}" for m in dep_pattern.finditer(content)]

    return {"dependencies": deps} if deps else {}


def _extract_gradle_deps(project_path: str) -> dict:
    """Extract dependencies from build.gradle using regex."""
    gradle_file = os.path.join(project_path, "build.gradle")
    try:
        with open(gradle_file, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except Exception:
        return {}

    # Match implementation/api/compile/testImplementation 'group:artifact:version'
    dep_pattern = re.compile(
        r"""(?:implementation|api|compile|testImplementation|testApi)\s+['"]([^'"]+)['"]""",
        re.MULTILINE
    )
    deps = dep_pattern.findall(content)

    return {"dependencies": deps} if deps else {}


def _extract_dependencies(project_path: str) -> dict | None:
    """
    Detect and extract dependency information for a project.

    Returns a dict mapping extractor type to extracted data, or None if no
    recognized dependency file is found.
    """
    results: dict = {}

    for dep_file, extractor_type in DEPENDENCY_EXTRACTORS.items():
        full_path = os.path.join(project_path, dep_file)
        if not os.path.isfile(full_path):
            continue

        if extractor_type == "npm":
            data = _extract_npm_deps(project_path)
        elif extractor_type == "pip" and dep_file == "pyproject.toml":
            data = _extract_toml_deps(project_path, "pyproject.toml")
        elif extractor_type == "pip" and dep_file == "requirements.txt":
            data = _extract_requirements_deps(project_path)
        elif extractor_type == "cargo":
            data = _extract_cargo_deps(project_path)
        elif extractor_type == "go":
            data = _extract_go_deps(project_path)
        elif extractor_type == "maven":
            data = _extract_maven_deps(project_path)
        elif extractor_type == "gradle":
            data = _extract_gradle_deps(project_path)
        else:
            data = {}

        if data:
            results[dep_file] = {"type": extractor_type, "data": data}

    return results if results else None


# ---------------------------------------------------------------------------
# Git metadata helpers
# ---------------------------------------------------------------------------

def _parse_git_config(project_path: str) -> str | None:
    """
    Parse .git/config and return the remote 'origin' URL, or None.
    """
    git_config_path = os.path.join(project_path, ".git", "config")
    if not os.path.isfile(git_config_path):
        return None

    parser = configparser.RawConfigParser()
    try:
        parser.read(git_config_path, encoding="utf-8")
    except Exception:
        return None

    # configparser normalizes section names — remote "origin" → 'remote "origin"'
    for section in parser.sections():
        if section.lower() == 'remote "origin"':
            url = parser.get(section, "url", fallback=None)
            return url

    return None


def _read_default_branch(project_path: str) -> str | None:
    """
    Read the default branch name from .git/HEAD.

    HEAD typically contains: ref: refs/heads/<branch>
    """
    head_path = os.path.join(project_path, ".git", "HEAD")
    if not os.path.isfile(head_path):
        return None

    try:
        with open(head_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read().strip()
    except Exception:
        return None

    match = re.match(r"^ref:\s+refs/heads/(.+)$", content)
    if match:
        return match.group(1).strip()

    return None


def _read_readme(project_path: str) -> tuple:
    """
    Find and read the README file for a project.

    Returns (has_readme: bool, excerpt: str | None).
    """
    readme_candidates = [
        "README.md", "README.rst", "README.txt", "README",
        "readme.md", "readme.rst", "readme.txt",
        "Readme.md", "Readme.rst",
    ]

    for candidate in readme_candidates:
        readme_path = os.path.join(project_path, candidate)
        if os.path.isfile(readme_path):
            try:
                with open(readme_path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read(README_EXCERPT_LENGTH)
                return (True, content if content else None)
            except Exception:
                return (True, None)

    return (False, None)


def _detect_languages(project_path: str) -> list:
    """
    Walk the project directory (skipping SKIP_DIRS) and count source files by language.

    Returns a list of detected language names sorted by file count descending.
    """
    language_counts: dict = {}

    for dirpath, dirnames, filenames in os.walk(project_path):
        # Prune skip directories in-place
        dirnames[:] = [
            d for d in dirnames
            if d not in SKIP_DIRS and not d.startswith(".")
        ]

        for filename in filenames:
            _, ext = os.path.splitext(filename)
            lang = LANGUAGE_EXTENSIONS.get(ext.lower())
            if lang:
                language_counts[lang] = language_counts.get(lang, 0) + 1

    return sorted(language_counts.keys(), key=lambda l: -language_counts[l])


def _detect_project_indicators(project_path: str) -> list:
    """
    Detect which project indicator files are present.

    Returns a list of (filename, ecosystem) tuples as dicts.
    """
    found = []
    for indicator_file, ecosystem in PROJECT_INDICATORS.items():
        if os.path.isfile(os.path.join(project_path, indicator_file)):
            found.append({"file": indicator_file, "ecosystem": ecosystem})
    return found


def _detect_infra_markers(project_path: str) -> list:
    """
    Detect which infrastructure marker files or directories are present.

    Returns a list of marker type strings.
    """
    found = []
    for marker, marker_type in INFRA_MARKERS.items():
        marker_path = os.path.join(project_path, marker)
        if os.path.isfile(marker_path) or os.path.isdir(marker_path):
            if marker_type not in found:
                found.append(marker_type)
    return found


# ---------------------------------------------------------------------------
# Project detection
# ---------------------------------------------------------------------------

def _detect_project(
    project_path: str,
    directory_name: str,
    group_name: str | None = None,
) -> dict:
    """
    Build a project metadata dict for a discovered Git repository.

    Reads Git config, README, language files, and indicator files.
    """
    # Git remote URL
    git_remote_url = _parse_git_config(project_path)

    # GitHub normalization
    github_url = normalize_github_url(git_remote_url) if git_remote_url else None
    github_owner, github_repo_name = (
        extract_github_owner_repo(git_remote_url)
        if git_remote_url
        else (None, None)
    )

    # Metadata
    has_readme, readme_excerpt = _read_readme(project_path)
    detected_languages = _detect_languages(project_path)
    project_indicators = _detect_project_indicators(project_path)
    infra_markers = _detect_infra_markers(project_path)
    default_branch = _read_default_branch(project_path)
    dependencies = _extract_dependencies(project_path)

    return {
        "directory_name": directory_name,
        "absolute_path": project_path,
        "git_remote_url": git_remote_url,
        "github_url": github_url,
        "github_owner": github_owner,
        "github_repo_name": github_repo_name,
        "detected_languages": detected_languages,
        "dependencies": dependencies,
        "infra_markers": infra_markers,
        "project_indicators": project_indicators,
        "default_branch": default_branch,
        "has_readme": has_readme,
        "readme_excerpt": readme_excerpt,
        "group_name": group_name,
        "is_group_parent": False,
    }


# ---------------------------------------------------------------------------
# Main scan function
# ---------------------------------------------------------------------------

def scan_directory(root_path: str) -> dict:
    """
    Scan root_path for Git repositories using a two-pass algorithm.

    Pass 1: Check each immediate child directory for a .git/ directory.
            These are direct Git repos.

    Pass 2: For directories that are NOT Git repos themselves, check their
            children for .git/ directories. These become "groups" (e.g. a
            ~/projects folder containing many repos).

    Returns a scan result dict conforming to the output JSON schema.
    """
    root_path = os.path.expanduser(root_path)
    root_path = os.path.abspath(root_path)

    if not os.path.isdir(root_path):
        return {"error": f"Directory not found: {root_path}"}

    projects: list = []
    groups: list = []
    warnings: list = []

    scan_id = str(uuid.uuid4())
    scanned_at = datetime.now(timezone.utc).isoformat()

    # Enumerate immediate children
    try:
        children = os.listdir(root_path)
    except PermissionError as e:
        return {"error": f"Permission denied reading directory: {root_path}: {e}"}

    direct_git_dirs: list = []      # Children that are Git repos
    potential_groups: list = []     # Children that are plain dirs (possible groups)

    for entry in sorted(children):
        # Skip hidden entries and known non-project dirs
        if entry.startswith(".") or entry in SKIP_DIRS:
            continue

        entry_path = os.path.join(root_path, entry)

        if not os.path.isdir(entry_path):
            continue

        git_path = os.path.join(entry_path, ".git")

        if os.path.isdir(git_path):
            # Genuine Git repo (not a submodule pointer file)
            direct_git_dirs.append((entry, entry_path))
        elif os.path.isfile(git_path):
            # Submodule pointer — skip, the parent repo handles it
            continue
        else:
            # Plain directory — candidate for grouping
            potential_groups.append((entry, entry_path))

    # Pass 1: process direct Git repos (children of root)
    for dir_name, dir_path in direct_git_dirs:
        project = _detect_project(dir_path, dir_name, group_name=None)
        projects.append(project)

    # Pass 2: check potential groups for child Git repos
    for group_dir_name, group_dir_path in potential_groups:
        try:
            group_children = os.listdir(group_dir_path)
        except PermissionError:
            warnings.append(f"Permission denied reading directory: {group_dir_path}")
            continue

        child_repos: list = []

        for entry in sorted(group_children):
            if entry.startswith(".") or entry in SKIP_DIRS:
                continue

            entry_path = os.path.join(group_dir_path, entry)

            if not os.path.isdir(entry_path):
                continue

            git_path = os.path.join(entry_path, ".git")

            if os.path.isdir(git_path):
                child_repos.append((entry, entry_path))
            elif os.path.isfile(git_path):
                # Submodule pointer — skip
                continue

        if child_repos:
            # This directory is a group
            group_project_names = []

            for child_name, child_path in child_repos:
                try:
                    project = _detect_project(
                        child_path, child_name, group_name=group_dir_name
                    )
                    projects.append(project)
                    group_project_names.append(child_name)
                except PermissionError:
                    warnings.append(
                        f"Permission denied reading project: {child_path}"
                    )

            groups.append({
                "name": group_dir_name,
                "path": group_dir_path,
                "children": group_project_names,
            })

    return {
        "scan_id": scan_id,
        "scanned_at": scanned_at,
        "scanner_version": SCANNER_VERSION,
        "root_directory": root_path,
        "projects": projects,
        "groups": groups,
        "warnings": warnings,
        "summary": {
            "total_found": len(projects),
            "groups_found": len(groups),
        },
    }


# ---------------------------------------------------------------------------
# Apply mode
# ---------------------------------------------------------------------------

def _compute_file_hash(path: str) -> str:
    """Compute SHA-256 hash of a file, reading in 8192-byte chunks."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(8192)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _write_config_files(proj: dict, extensions_hash: str | None) -> None:
    """
    Write .claude/cortex-config.json and .claude/cortex-state.json into the project directory.

    Creates .claude/ if it does not exist.
    """
    project_path = proj["absolute_path"]
    claude_dir = os.path.join(project_path, ".claude")
    os.makedirs(claude_dir, exist_ok=True)

    project_id = proj.get("project_id", "")
    system_fingerprint = proj.get("system_fingerprint", "")
    machine_id = hashlib.md5(system_fingerprint.encode()).hexdigest()[:16]
    now_iso = datetime.now(timezone.utc).isoformat()
    project_title = proj.get("project_title") or os.path.basename(project_path)

    cortex_config = {
        "cortex_api_url": proj.get("cortex_api_url", ""),
        "cortex_mcp_url": proj.get("cortex_mcp_url", ""),
        "project_id": project_id,
        "project_title": project_title,
        "machine_id": machine_id,
        "install_scope": "project",
        "installed_at": now_iso,
        "installed_by": "scanner",
    }
    if extensions_hash:
        cortex_config["extensions_hash"] = extensions_hash
        cortex_config["extensions_installed_at"] = now_iso

    config_path = os.path.join(claude_dir, "cortex-config.json")
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(cortex_config, f, indent=4)

    cortex_state: dict = {
        "system_fingerprint": system_fingerprint,
        "system_name": proj.get("system_name", ""),
        "cortex_project_id": project_id,
    }
    system_id = proj.get("system_id")
    if system_id:
        cortex_state["system_id"] = system_id

    state_path = os.path.join(claude_dir, "cortex-state.json")
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump(cortex_state, f, indent=4)


def _write_mcp_json(project_path: str, mcp_url: str) -> None:
    """Write .mcp.json with the Cortex MCP server configuration.

    This enables Claude Code to connect to the Cortex MCP server when
    opening the project, matching what `claude mcp add --transport http`
    would produce.
    """
    mcp_json_path = os.path.join(project_path, ".mcp.json")

    # Merge with existing config if present
    existing: dict = {}
    if os.path.isfile(mcp_json_path):
        try:
            with open(mcp_json_path, "r", encoding="utf-8", errors="replace") as f:
                existing = json.load(f)
        except (json.JSONDecodeError, OSError):
            existing = {}

    servers = existing.setdefault("mcpServers", {})
    servers["cortex"] = {
        "type": "http",
        "url": f"{mcp_url}/mcp",
    }

    with open(mcp_json_path, "w", encoding="utf-8") as f:
        json.dump(existing, f, indent=2)
        f.write("\n")


def _write_settings_local(project_path: str) -> None:
    """Write .claude/settings.local.json with the Cortex observation hook."""
    claude_dir = os.path.join(project_path, ".claude")
    os.makedirs(claude_dir, exist_ok=True)

    settings = {
        "hooks": {
            "PostToolUse": [
                {
                    "matcher": ".*",
                    "hooks": [
                        {
                            "type": "command",
                            "command": 'test -f "$HOME/.claude/plugins/cortex-memory/scripts/observation_hook.py" && "$HOME/.claude/plugins/cortex-memory/.venv/bin/python" "$HOME/.claude/plugins/cortex-memory/scripts/observation_hook.py" || true',
                        }
                    ],
                }
            ]
        }
    }

    settings_path = os.path.join(claude_dir, "settings.local.json")
    with open(settings_path, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=4)


def _update_gitignore(project_path: str) -> None:
    """
    Append Cortex entries to .gitignore if not already present.

    Idempotent: skips if '# Cortex' is already in the file.
    Ensures existing last line is not corrupted by prepending a newline when needed.
    """
    gitignore_path = os.path.join(project_path, ".gitignore")
    existing_content = ""

    if os.path.isfile(gitignore_path):
        with open(gitignore_path, "r", encoding="utf-8", errors="replace") as f:
            existing_content = f.read()

    # Idempotency check
    if "# Cortex" in existing_content:
        return

    entries_block = "\n".join(GITIGNORE_ENTRIES) + "\n"

    # Prevent corrupting the last line when existing content has no trailing newline
    if existing_content and not existing_content.endswith("\n"):
        entries_block = "\n" + entries_block

    with open(gitignore_path, "a", encoding="utf-8") as f:
        f.write(entries_block)


def _install_extensions(project_path: str, tarball_path: str) -> None:
    """
    Extract an extensions tarball into .claude/skills/ inside the project directory.

    Skips silently on tarfile or OS errors so config files are still written.
    """
    claude_dir = os.path.join(project_path, ".claude")
    skills_dir = os.path.join(claude_dir, "skills")
    os.makedirs(skills_dir, exist_ok=True)

    try:
        with tarfile.open(tarball_path, "r:gz") as tar:
            if sys.version_info >= (3, 12):
                tar.extractall(path=skills_dir, filter="data")
            else:
                tar.extractall(path=skills_dir)
    except (tarfile.TarError, OSError):
        pass


def apply_configs(payload: dict, extensions_tarball: str | None = None) -> dict:
    """
    Apply Cortex configuration to projects listed in payload.

    Writes config files, settings.local.json, updates .gitignore, and optionally
    installs extensions from a tarball into each project directory.
    Returns a JSON-serializable summary with per-project results.
    """
    projects = payload.get("projects", [])

    extensions_hash: str | None = None
    if extensions_tarball and os.path.isfile(extensions_tarball):
        extensions_hash = _compute_file_hash(extensions_tarball)

    total = len(projects)
    created = 0
    failed = 0
    skipped = 0
    results = []

    for proj in projects:
        project_path = proj.get("absolute_path", "")
        project_title = proj.get("project_title") or os.path.basename(project_path)

        if not project_path or not os.path.isdir(project_path):
            skipped += 1
            results.append({
                "path": project_path,
                "title": project_title,
                "status": "skipped",
                "reason": "directory not found",
            })
            continue

        try:
            _write_config_files(proj, extensions_hash)
            _write_settings_local(project_path)

            # Write .mcp.json so Claude Code auto-connects to Cortex MCP
            mcp_url = proj.get("cortex_mcp_url", "")
            if mcp_url:
                _write_mcp_json(project_path, mcp_url)

            _update_gitignore(project_path)

            if extensions_tarball and os.path.isfile(extensions_tarball):
                _install_extensions(project_path, extensions_tarball)

            created += 1
            results.append({
                "path": project_path,
                "title": project_title,
                "status": "created",
            })
        except Exception as e:
            failed += 1
            results.append({
                "path": project_path,
                "title": project_title,
                "status": "failed",
                "error": str(e),
            })

    return {
        "apply_summary": {
            "total": total,
            "created": created,
            "skipped": skipped,
            "failed": failed,
        },
        "results": results,
    }


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Cortex Local Project Scanner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument(
        "--scan",
        metavar="DIRECTORY",
        help="Scan DIRECTORY for Git repositories and output JSON to stdout.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        default=False,
        help="After scanning, apply Cortex configuration to discovered projects.",
    )
    parser.add_argument(
        "--payload-file",
        metavar="PATH",
        help="Apply configuration from a pre-generated payload JSON file.",
    )
    parser.add_argument(
        "--extensions-tarball",
        metavar="PATH",
        help="Install Cortex extensions from a tarball.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"cortex-scanner {SCANNER_VERSION}",
    )

    args = parser.parse_args()

    # --scan mode
    if args.scan:
        result = scan_directory(args.scan)

        if args.apply and "error" not in result:
            apply_result = apply_configs(result, extensions_tarball=args.extensions_tarball)
            result["apply_result"] = apply_result

        print(json.dumps(result, indent=2, default=str))
        sys.exit(0)

    # --payload-file mode
    if args.payload_file:
        try:
            with open(args.payload_file, "r", encoding="utf-8") as f:
                payload = json.load(f)
        except FileNotFoundError:
            print(
                json.dumps({"error": f"Payload file not found: {args.payload_file}"}),
                file=sys.stderr,
            )
            sys.exit(1)
        except json.JSONDecodeError as e:
            print(
                json.dumps({"error": f"Invalid JSON in payload file: {e}"}),
                file=sys.stderr,
            )
            sys.exit(1)

        result = apply_configs(payload, extensions_tarball=args.extensions_tarball)
        print(json.dumps(result, indent=2, default=str))
        sys.exit(0)

    # --extensions-tarball mode
    if args.extensions_tarball:
        tarball_path = args.extensions_tarball
        if not os.path.isfile(tarball_path):
            print(
                json.dumps({"error": f"Tarball not found: {tarball_path}"}),
                file=sys.stderr,
            )
            sys.exit(1)

        try:
            with tarfile.open(tarball_path, "r:*") as tar:
                members = tar.getnames()
            print(json.dumps({"status": "ok", "members": members}, indent=2))
        except Exception as e:
            print(
                json.dumps({"error": f"Failed to read tarball: {e}"}),
                file=sys.stderr,
            )
            sys.exit(1)

        sys.exit(0)

    # No recognized mode — show help
    parser.print_help(sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
