# Local Project Scanner Rearchitecture — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the server-side Docker-volume-mount scanner with a client-side standalone Python script orchestrated by a Claude Code skill, enabling multi-system project scanning.

**Architecture:** A standalone Python script (`cortex-scanner.py`) runs locally on each machine with two modes: `--scan` (reads filesystem, outputs JSON) and `--apply` (writes config files from JSON payload). A Claude Code skill (`/scan-projects`) orchestrates the flow: download script → scan → dedup via MCP → create projects via MCP → apply configs. No Docker volume mount needed.

**Tech Stack:** Python 3.8+ (stdlib only for scanner script), FastAPI (single endpoint), Claude Code skill (markdown)

**Spec:** `docs/superpowers/specs/2026-03-17-scanner-rearchitecture-design.md`

---

## File Structure

### New Files
| File | Responsibility |
|------|---------------|
| `python/src/server/static/cortex-scanner.py` | Standalone scanner script (~500 lines). Two modes: `--scan` outputs JSON, `--apply` writes config files. Stdlib only, runs on any machine with Python 3.8+. |
| `python/src/server/api_routes/scanner_script_api.py` | Single FastAPI route `GET /api/scanner/script` that serves the scanner script as `text/plain`. |
| `python/tests/test_cortex_scanner.py` | Tests for the standalone scanner script. Uses temp directories, no Docker/Cortex needed. |
| `integrations/claude-code/skills/scan-projects.md` | Claude Code skill that orchestrates the entire scan-and-setup flow. |
| `migration/0.1.0/022_drop_scanner_tables.sql` | Migration to drop the three scanner tables. |

### Files to Delete
| File | Why |
|------|-----|
| `python/src/server/api_routes/scanner_api.py` | All scanner endpoints replaced by single script endpoint |
| `python/src/server/services/scanner/scanner_service.py` | Logic moves to client-side script |
| `python/src/server/services/scanner/git_detector.py` | Extracted into `cortex-scanner.py` |
| `python/src/server/services/scanner/scan_template.py` | Templates become skill parameters |
| `python/src/server/services/scanner/scan_report.py` | Report generation moves to skill |
| `python/src/server/services/scanner/url_normalizer.py` | Logic duplicated into `cortex-scanner.py` |
| `python/src/server/services/scanner/cleanup.py` | Cleanup loop removed (tables dropped) |
| `python/src/server/services/scanner/__init__.py` | Package removed |
| `python/src/server/config/scanner_config.py` | No server-side config needed |
| `python/src/mcp_server/features/scanner/scanner_tools.py` | No MCP tools — skill only |
| `python/src/mcp_server/features/scanner/__init__.py` | Package removed |
| `python/tests/server/services/scanner/` | Entire test directory removed (includes test_scanner_service.py, test_git_detector.py, test_url_normalizer.py, test_integration.py) |

### Files to Modify
| File | Change |
|------|--------|
| `python/src/server/main.py` | Remove scanner router import (line 39) and include (line 228). Add scanner script router. |
| `python/src/mcp_server/mcp_server.py` | Remove scanner tools registration block (lines 660-674). |
| `docker-compose.yml` | Remove volume mount (line 51), env vars (lines 34-35). |
| `.env.example` (repo root) | Remove `PROJECTS_DIRECTORY` and `SCANNER_ENABLED` (lines 139-140). |

---

## Task 1: Write the Standalone Scanner Script — Scan Mode

**Files:**
- Create: `python/src/server/static/cortex-scanner.py`
- Test: `python/tests/test_cortex_scanner.py`

This is the largest task. The script is a single file with two modes. We build scan mode first.

- [ ] **Step 1: Create the script skeleton with argument parsing**

Create the `static/` directory first (it does not exist yet):
```bash
mkdir -p python/src/server/static
```

Create `python/src/server/static/cortex-scanner.py`:

```python
#!/usr/bin/env python3
"""Cortex Local Project Scanner — standalone, stdlib-only.

Usage:
    python3 cortex-scanner.py --scan <directory>
    python3 cortex-scanner.py --apply --payload-file <path> [--extensions-tarball <path>]
"""

import argparse
import configparser
import hashlib
import json
import os
import re
import sys
import tarfile
import uuid
from datetime import datetime, timezone

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
    "package.json": "node",
    "pyproject.toml": "python",
    "setup.py": "python",
    "requirements.txt": "python",
    "Cargo.toml": "rust",
    "go.mod": "go",
    "pom.xml": "java",
    "build.gradle": "java",
    "Gemfile": "ruby",
    "composer.json": "php",
    "Package.swift": "swift",
    "pubspec.yaml": "dart",
}

INFRA_MARKERS = {
    "docker-compose.yml": "docker",
    "docker-compose.yaml": "docker",
    "Dockerfile": "docker",
    ".github/workflows": "github-actions",
    ".gitlab-ci.yml": "gitlab-ci",
    "firebase.json": "firebase",
    ".firebaserc": "firebase",
    "vercel.json": "vercel",
    "netlify.toml": "netlify",
    "serverless.yml": "serverless",
    "terraform": "terraform",
    "k8s": "kubernetes",
    "Makefile": "make",
    ".env.example": "env-config",
    "supabase": "supabase",
    "prisma": "prisma",
    ".github/dependabot.yml": "dependabot",
}

DEPENDENCY_EXTRACTORS = {
    "package.json": "npm",
    "pyproject.toml": "pip",
    "requirements.txt": "pip",
    "Cargo.toml": "cargo",
    "go.mod": "go",
    "pom.xml": "maven",
    "build.gradle": "gradle",
}

README_EXCERPT_LENGTH = 5000

GITIGNORE_ENTRIES = [
    "# Cortex",
    ".claude/plugins/",
    ".claude/skills/",
    ".claude/cortex-config.json",
    ".claude/cortex-state.json",
    ".claude/cortex-memory-buffer.jsonl",
    ".claude/settings.local.json",
    ".cortex/",
]


def main():
    parser = argparse.ArgumentParser(description="Cortex Local Project Scanner")
    parser.add_argument("--scan", metavar="DIR", help="Scan directory for git repos")
    parser.add_argument("--apply", action="store_true", help="Apply configs to projects")
    parser.add_argument("--payload-file", metavar="FILE", help="JSON payload file for apply mode")
    parser.add_argument("--extensions-tarball", metavar="FILE", help="Extensions tarball path")
    parser.add_argument("--version", action="version", version=f"cortex-scanner {SCANNER_VERSION}")

    args = parser.parse_args()

    if args.scan:
        result = scan_directory(args.scan)
        print(json.dumps(result, indent=2))
    elif args.apply:
        if not args.payload_file:
            print(json.dumps({"error": "--payload-file required for --apply mode"}), file=sys.stderr)
            sys.exit(1)
        result = apply_configs(args.payload_file, args.extensions_tarball)
        print(json.dumps(result, indent=2))
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Write the URL normalization functions**

Add to `cortex-scanner.py` (before `main()`):

```python
def normalize_github_url(url):
    """Normalize GitHub URL to https://github.com/{owner}/{repo} (lowercase).

    Handles SSH (git@github.com:owner/repo.git) and HTTPS formats.
    Returns None for non-GitHub URLs.
    """
    if not url:
        return None
    url = url.strip()

    ssh_match = re.match(r"git@github\.com:(.+?)(?:\.git)?/?$", url)
    if ssh_match:
        path = ssh_match.group(1)
        parts = path.split("/")
        if len(parts) == 2:
            return f"https://github.com/{parts[0]}/{parts[1]}".lower()
        return None

    https_match = re.match(r"https?://github\.com/(.+?)(?:\.git)?/?$", url, re.IGNORECASE)
    if https_match:
        path = https_match.group(1).rstrip("/")
        parts = path.split("/")
        if len(parts) >= 2:
            return f"https://github.com/{parts[0]}/{parts[1]}".lower()
        return None

    return None


def extract_github_owner_repo(url):
    """Extract (owner, repo_name) from a GitHub URL. Returns (None, None) for non-GitHub."""
    normalized = normalize_github_url(url)
    if not normalized:
        return None, None
    parts = normalized.replace("https://github.com/", "").split("/")
    if len(parts) == 2:
        return parts[0], parts[1]
    return None, None
```

- [ ] **Step 3: Write the scan_directory function with two-pass detection**

Add to `cortex-scanner.py`:

```python
def scan_directory(root_path):
    """Scan a directory for git repositories using two-pass detection.

    Pass 1: Immediate children — .git/ means project, else potential group.
    Pass 2: For each potential group, scan its children for .git/.
    """
    root_path = os.path.expanduser(root_path)
    root_path = os.path.abspath(root_path)

    if not os.path.isdir(root_path):
        return {"error": f"Directory not found: {root_path}"}

    projects = []
    groups = []
    warnings = []
    potential_groups = []

    # Pass 1: Scan immediate children
    try:
        entries = sorted(os.listdir(root_path))
    except PermissionError:
        return {"error": f"Permission denied: {root_path}"}

    for entry in entries:
        if entry in SKIP_DIRS or entry.startswith("."):
            continue

        entry_path = os.path.join(root_path, entry)
        if not os.path.isdir(entry_path):
            continue

        git_dir = os.path.join(entry_path, ".git")
        if os.path.isdir(git_dir):
            project = _detect_project(entry_path, entry)
            projects.append(project)
        elif os.path.isfile(git_dir):
            # .git file = submodule pointer, skip
            continue
        else:
            potential_groups.append(entry)

    # Pass 2: Check potential groups
    for group_name in potential_groups:
        group_path = os.path.join(root_path, group_name)
        group_projects = []

        try:
            group_entries = sorted(os.listdir(group_path))
        except PermissionError:
            warnings.append(f"Permission denied: {group_path} (skipped)")
            continue

        for child in group_entries:
            if child in SKIP_DIRS or child.startswith("."):
                continue
            child_path = os.path.join(group_path, child)
            if not os.path.isdir(child_path):
                continue
            child_git = os.path.join(child_path, ".git")
            if os.path.isdir(child_git):
                project = _detect_project(child_path, child, group_name=group_name)
                group_projects.append(project)

        if group_projects:
            groups.append({
                "name": group_name,
                "path": group_path,
                "children": [p["directory_name"] for p in group_projects],
            })
            projects.extend(group_projects)

    return {
        "scan_id": str(uuid.uuid4()),
        "scanned_at": datetime.now(timezone.utc).isoformat(),
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
```

- [ ] **Step 4: Write the _detect_project helper**

Add to `cortex-scanner.py`:

```python
def _detect_project(project_path, directory_name, group_name=None):
    """Detect a single project's metadata from its directory."""
    project = {
        "directory_name": directory_name,
        "absolute_path": project_path,
        "git_remote_url": None,
        "github_url": None,
        "github_owner": None,
        "github_repo_name": None,
        "detected_languages": [],
        "dependencies": None,
        "infra_markers": [],
        "project_indicators": [],
        "default_branch": None,
        "has_readme": False,
        "readme_excerpt": None,
        "group_name": group_name,
        "is_group_parent": False,
    }

    # Parse git config for remote URL
    _parse_git_config(project)

    # Normalize GitHub URL
    if project["git_remote_url"]:
        project["github_url"] = normalize_github_url(project["git_remote_url"])
        owner, repo = extract_github_owner_repo(project["git_remote_url"])
        project["github_owner"] = owner
        project["github_repo_name"] = repo

    # Read README
    _read_readme(project)

    # Detect languages
    _detect_languages(project)

    # Detect project indicators
    _detect_project_indicators(project)

    # Extract dependencies
    _extract_dependencies(project)

    # Detect infrastructure markers
    _detect_infra_markers(project)

    # Read default branch
    _read_default_branch(project)

    return project
```

- [ ] **Step 5: Write the metadata extraction helpers**

Add to `cortex-scanner.py`:

```python
def _parse_git_config(project):
    """Parse .git/config to extract origin remote URL."""
    config_path = os.path.join(project["absolute_path"], ".git", "config")
    if not os.path.isfile(config_path):
        return
    try:
        config = configparser.ConfigParser()
        config.read(config_path)
        if config.has_section('remote "origin"'):
            url = config.get('remote "origin"', "url", fallback=None)
            if url:
                project["git_remote_url"] = url.strip()
    except Exception:
        pass


def _read_readme(project):
    """Read README.md content (excerpt only for scan output)."""
    readme_names = ["README.md", "readme.md", "README.MD", "Readme.md"]
    for name in readme_names:
        readme_path = os.path.join(project["absolute_path"], name)
        if os.path.isfile(readme_path):
            try:
                with open(readme_path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
                project["has_readme"] = True
                project["readme_excerpt"] = content[:README_EXCERPT_LENGTH]
            except Exception:
                pass
            return


def _detect_languages(project):
    """Detect languages from file extensions in top-level and src/ directories."""
    languages = set()
    try:
        for entry in os.listdir(project["absolute_path"]):
            if entry.startswith("."):
                continue
            _, ext = os.path.splitext(entry)
            if ext in LANGUAGE_EXTENSIONS:
                languages.add(LANGUAGE_EXTENSIONS[ext])
        src_path = os.path.join(project["absolute_path"], "src")
        if os.path.isdir(src_path):
            for entry in os.listdir(src_path):
                _, ext = os.path.splitext(entry)
                if ext in LANGUAGE_EXTENSIONS:
                    languages.add(LANGUAGE_EXTENSIONS[ext])
    except Exception:
        pass
    project["detected_languages"] = sorted(languages)


def _detect_project_indicators(project):
    """Detect project type from marker files."""
    indicators = set()
    for marker_file, indicator in PROJECT_INDICATORS.items():
        if os.path.exists(os.path.join(project["absolute_path"], marker_file)):
            indicators.add(indicator)
    project["project_indicators"] = sorted(indicators)


def _detect_infra_markers(project):
    """Check for infrastructure marker files/directories."""
    markers = set()
    for marker_path, marker_name in INFRA_MARKERS.items():
        full_path = os.path.join(project["absolute_path"], marker_path)
        if os.path.exists(full_path):
            markers.add(marker_name)
    project["infra_markers"] = sorted(markers)


def _read_default_branch(project):
    """Read the default branch from .git/HEAD."""
    head_path = os.path.join(project["absolute_path"], ".git", "HEAD")
    if not os.path.isfile(head_path):
        return
    try:
        with open(head_path, "r") as f:
            content = f.read().strip()
        if content.startswith("ref: refs/heads/"):
            project["default_branch"] = content.replace("ref: refs/heads/", "")
    except Exception:
        pass
```

- [ ] **Step 6: Write the dependency extraction functions**

Add to `cortex-scanner.py`:

```python
def _extract_dependencies(project):
    """Extract dependency names from manifest files."""
    deps = {}

    for manifest, ecosystem in DEPENDENCY_EXTRACTORS.items():
        manifest_path = os.path.join(project["absolute_path"], manifest)
        if not os.path.isfile(manifest_path):
            continue

        try:
            if manifest == "package.json":
                extracted = _extract_npm_deps(manifest_path)
            elif manifest == "pyproject.toml":
                extracted = _extract_toml_deps(manifest_path)
            elif manifest == "requirements.txt":
                extracted = _extract_requirements_deps(manifest_path)
            elif manifest == "Cargo.toml":
                extracted = _extract_cargo_deps(manifest_path)
            elif manifest == "go.mod":
                extracted = _extract_go_deps(manifest_path)
            elif manifest == "pom.xml":
                extracted = _extract_maven_deps(manifest_path)
            elif manifest == "build.gradle":
                extracted = _extract_gradle_deps(manifest_path)
            else:
                continue

            if extracted:
                if ecosystem in deps:
                    existing = set(deps[ecosystem])
                    existing.update(extracted)
                    deps[ecosystem] = sorted(existing)
                else:
                    deps[ecosystem] = sorted(extracted)
        except Exception:
            pass

    project["dependencies"] = deps if deps else None


def _extract_npm_deps(path):
    """Extract dependency names from package.json."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    names = set()
    for key in ("dependencies", "devDependencies"):
        if key in data and isinstance(data[key], dict):
            names.update(data[key].keys())
    return sorted(names)


def _extract_toml_deps(path):
    """Extract dependency names from pyproject.toml or Cargo.toml.

    Uses tomllib (Python 3.11+) with regex fallback for 3.8-3.10.
    """
    try:
        import tomllib
        with open(path, "rb") as f:
            data = tomllib.load(f)
        names = set()
        # pyproject.toml: project.dependencies
        proj_deps = data.get("project", {}).get("dependencies", [])
        for dep in proj_deps:
            name = re.split(r"[>=<!~\s;\[]", dep)[0].strip()
            if name:
                names.add(name)
        # Cargo.toml: dependencies section
        cargo_deps = data.get("dependencies", {})
        if isinstance(cargo_deps, dict):
            names.update(cargo_deps.keys())
        return sorted(names)
    except ImportError:
        # Python < 3.11 fallback: regex-based extraction
        return _extract_toml_deps_regex(path)


def _extract_toml_deps_regex(path):
    """Regex fallback for TOML dependency extraction (Python 3.8-3.10)."""
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    names = set()
    in_deps = False
    for line in content.split("\n"):
        stripped = line.strip()
        if stripped in ("[project.dependencies]", "[dependencies]",
                        "[dev-dependencies]", "[build-dependencies]"):
            in_deps = True
            continue
        if stripped == "dependencies = [":
            in_deps = True
            continue
        if in_deps:
            if stripped.startswith("[") and not stripped.startswith('"'):
                in_deps = False
                continue
            if stripped == "]":
                in_deps = False
                continue
            # Handle key = value lines (Cargo.toml style)
            if "=" in stripped and not stripped.startswith("#"):
                name = stripped.split("=")[0].strip()
                if name and not name.startswith("["):
                    names.add(name)
                continue
            # Handle string list entries (pyproject.toml style)
            cleaned = stripped.strip('"\'[], ')
            if cleaned and not cleaned.startswith("#"):
                name = re.split(r"[>=<!~\s;\[]", cleaned)[0].strip()
                if name:
                    names.add(name)
    return sorted(names)


def _extract_requirements_deps(path):
    """Extract package names from requirements.txt."""
    names = set()
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("-"):
                continue
            name = re.split(r"[>=<!~\s;\[]", line)[0].strip()
            if name:
                names.add(name)
    return sorted(names)


def _extract_cargo_deps(path):
    """Extract dependency names from Cargo.toml."""
    # Try tomllib first, fall back to regex
    return _extract_toml_deps(path)


def _extract_go_deps(path):
    """Extract module paths from go.mod require block."""
    names = set()
    in_require = False
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if stripped.startswith("require ("):
                in_require = True
                continue
            if stripped == ")" and in_require:
                in_require = False
                continue
            if in_require and stripped and not stripped.startswith("//"):
                parts = stripped.split()
                if parts:
                    names.add(parts[0])
            elif stripped.startswith("require ") and "(" not in stripped:
                parts = stripped.split()
                if len(parts) >= 2:
                    names.add(parts[1])
    return sorted(names)


def _extract_maven_deps(path):
    """Extract artifactId values from pom.xml dependencies."""
    names = set()
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        for match in re.finditer(r"<dependency>.*?</dependency>", content, re.DOTALL):
            dep_block = match.group()
            aid_match = re.search(r"<artifactId>(.*?)</artifactId>", dep_block)
            if aid_match:
                names.add(aid_match.group(1))
    except Exception:
        pass
    return sorted(names)


def _extract_gradle_deps(path):
    """Extract dependency strings from build.gradle."""
    names = set()
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                match = re.match(
                    r"(?:implementation|api|compile|testImplementation|testCompile)"
                    r"""[\s(]+['"]([^'"]+)['"]""",
                    stripped,
                )
                if match:
                    dep = match.group(1)
                    parts = dep.split(":")
                    if len(parts) >= 2:
                        names.add(f"{parts[0]}:{parts[1]}")
                    else:
                        names.add(dep)
    except Exception:
        pass
    return sorted(names)
```

- [ ] **Step 7: Run scan mode tests**

Run: `cd /home/winadmin/projects/Trinity/cortex && python python/src/server/static/cortex-scanner.py --scan ~/projects`

Expected: JSON output with detected projects from the real projects directory. Verify structure matches the spec schema.

- [ ] **Step 8: Commit scan mode**

```bash
git add python/src/server/static/cortex-scanner.py
git commit -m "feat: add cortex-scanner.py scan mode (client-side project detection)"
```

---

## Task 2: Write the Standalone Scanner Script — Apply Mode

**Files:**
- Modify: `python/src/server/static/cortex-scanner.py`
- Test: `python/tests/test_cortex_scanner.py`

- [ ] **Step 1: Write the apply_configs function**

Add to `cortex-scanner.py` (before `main()`):

```python
def apply_configs(payload_file, extensions_tarball=None):
    """Apply Cortex config files to projects from a JSON payload."""
    try:
        with open(payload_file, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        return {"error": f"Failed to read payload file: {e}"}

    projects = payload.get("projects", [])
    if not projects:
        return {"error": "No projects in payload"}

    # Compute extensions hash if tarball provided
    extensions_hash = None
    if extensions_tarball and os.path.isfile(extensions_tarball):
        extensions_hash = _compute_file_hash(extensions_tarball)

    results = []
    created = 0
    failed = 0

    for proj in projects:
        project_path = proj.get("absolute_path", "")
        project_id = proj.get("project_id", "")
        project_title = proj.get("project_title", os.path.basename(project_path))

        if not os.path.isdir(project_path):
            results.append({
                "directory_name": os.path.basename(project_path),
                "status": "failed",
                "error": f"Directory not found: {project_path}",
            })
            failed += 1
            continue

        try:
            _write_config_files(proj, extensions_hash)
            _write_settings_local(project_path)
            _update_gitignore(project_path)

            if extensions_tarball and os.path.isfile(extensions_tarball):
                _install_extensions(project_path, extensions_tarball)

            results.append({
                "directory_name": os.path.basename(project_path),
                "status": "created",
                "project_id": project_id,
            })
            created += 1
        except Exception as e:
            results.append({
                "directory_name": os.path.basename(project_path),
                "status": "failed",
                "error": str(e),
            })
            failed += 1

    return {
        "apply_summary": {
            "total": len(projects),
            "created": created,
            "failed": failed,
        },
        "results": results,
    }


def _compute_file_hash(path):
    """Compute SHA-256 hash of a file."""
    sha256 = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()
```

- [ ] **Step 2: Write the config file writers**

Add to `cortex-scanner.py`:

```python
def _write_config_files(proj, extensions_hash):
    """Write .claude/cortex-config.json and cortex-state.json."""
    project_path = proj["absolute_path"]
    claude_dir = os.path.join(project_path, ".claude")
    os.makedirs(claude_dir, exist_ok=True)

    now = datetime.now(timezone.utc).isoformat()
    fingerprint = proj.get("system_fingerprint", "")

    config = {
        "cortex_api_url": proj.get("cortex_api_url", "http://localhost:8181"),
        "cortex_mcp_url": proj.get("cortex_mcp_url", "http://localhost:8051"),
        "project_id": proj.get("project_id", ""),
        "project_title": proj.get("project_title", os.path.basename(project_path)),
        "machine_id": hashlib.md5(fingerprint.encode()).hexdigest()[:16],
        "install_scope": "project",
        "installed_at": now,
        "installed_by": "scanner",
    }
    if extensions_hash:
        config["extensions_hash"] = extensions_hash
        config["extensions_installed_at"] = now

    config_path = os.path.join(claude_dir, "cortex-config.json")
    with open(config_path, "w") as f:
        json.dump(config, f, indent=4)

    state = {
        "system_fingerprint": fingerprint,
        "system_name": proj.get("system_name", ""),
        "cortex_project_id": proj.get("project_id", ""),
    }
    state_path = os.path.join(claude_dir, "cortex-state.json")
    with open(state_path, "w") as f:
        json.dump(state, f, indent=4)


def _write_settings_local(project_path):
    """Write .claude/settings.local.json with PostToolUse hook."""
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
                            "command": "~/.claude/plugins/cortex-memory/scripts/observation_hook.sh",
                        }
                    ],
                }
            ]
        }
    }

    settings_path = os.path.join(claude_dir, "settings.local.json")
    with open(settings_path, "w") as f:
        json.dump(settings, f, indent=4)


def _update_gitignore(project_path):
    """Append Cortex entries to .gitignore if not already present."""
    gitignore_path = os.path.join(project_path, ".gitignore")

    existing_content = ""
    existing_lines = set()
    if os.path.isfile(gitignore_path):
        with open(gitignore_path, "r") as f:
            existing_content = f.read()
            existing_lines = {line.strip() for line in existing_content.split("\n")}

    # Check if Cortex block already present
    if "# Cortex" in existing_lines:
        return

    new_entries = [e for e in GITIGNORE_ENTRIES if e.strip() not in existing_lines]

    if new_entries:
        with open(gitignore_path, "a") as f:
            # Ensure file ends with newline before appending
            if existing_content and not existing_content.endswith("\n"):
                f.write("\n")
            f.write("\n".join(new_entries) + "\n")


def _install_extensions(project_path, tarball_path):
    """Extract extensions tarball into .claude/skills/."""
    skills_dir = os.path.join(project_path, ".claude", "skills")
    os.makedirs(skills_dir, exist_ok=True)

    try:
        with tarfile.open(tarball_path, "r:gz") as tar:
            # Use 'data' filter on Python 3.12+ for security (prevents path traversal)
            if sys.version_info >= (3, 12):
                tar.extractall(path=skills_dir, filter="data")
            else:
                tar.extractall(path=skills_dir)
    except (tarfile.TarError, OSError):
        # Skip extensions if tarball is corrupt, still succeed for config files
        pass
```

- [ ] **Step 3: Test apply mode manually**

Create a temp directory, write a test payload, and run apply:

```bash
mkdir -p /tmp/test-scanner-apply/test-project/.git
echo '{"projects":[{"absolute_path":"/tmp/test-scanner-apply/test-project","project_id":"test-uuid","project_title":"test-project","cortex_api_url":"http://localhost:8181","cortex_mcp_url":"http://localhost:8051","system_fingerprint":"abc123","system_name":"TEST"}]}' > /tmp/test-scanner-payload.json
python3 python/src/server/static/cortex-scanner.py --apply --payload-file /tmp/test-scanner-payload.json
```

Expected: JSON output with `created: 1`. Verify `.claude/cortex-config.json` and `.claude/cortex-state.json` exist in test project.

- [ ] **Step 4: Commit apply mode**

```bash
git add python/src/server/static/cortex-scanner.py
git commit -m "feat: add cortex-scanner.py apply mode (writes config files)"
```

---

## Task 3: Write Scanner Script Tests

**Files:**
- Create: `python/tests/test_cortex_scanner.py`

- [ ] **Step 1: Write scan mode tests**

Create `python/tests/test_cortex_scanner.py`:

```python
"""Tests for the standalone cortex-scanner.py script."""

import importlib.util
import json
import os
import sys
import tempfile

import pytest

# Import the script as a module
_script_path = os.path.join(
    os.path.dirname(__file__), "..", "src", "server", "static", "cortex-scanner.py"
)
_spec = importlib.util.spec_from_file_location("cortex_scanner", _script_path)
scanner = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(scanner)


def _make_git_repo(path, remote_url=None, readme_content=None, branch="main"):
    """Create a minimal fake git repo structure."""
    os.makedirs(os.path.join(path, ".git"), exist_ok=True)

    # Write HEAD
    with open(os.path.join(path, ".git", "HEAD"), "w") as f:
        f.write(f"ref: refs/heads/{branch}\n")

    # Write config with remote
    if remote_url:
        config_path = os.path.join(path, ".git", "config")
        with open(config_path, "w") as f:
            f.write(f'[remote "origin"]\n\turl = {remote_url}\n\tfetch = +refs/heads/*:refs/remotes/origin/*\n')

    # Write README
    if readme_content:
        with open(os.path.join(path, "README.md"), "w") as f:
            f.write(readme_content)


class TestScanEmpty:
    def test_empty_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = scanner.scan_directory(tmpdir)
            assert result["summary"]["total_found"] == 0
            assert result["projects"] == []
            assert "error" not in result

    def test_nonexistent_directory(self):
        result = scanner.scan_directory("/nonexistent/path")
        assert "error" in result


class TestScanDetection:
    def test_detects_git_repo(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = os.path.join(tmpdir, "my-project")
            _make_git_repo(repo, remote_url="https://github.com/user/my-project.git")
            result = scanner.scan_directory(tmpdir)
            assert result["summary"]["total_found"] == 1
            assert result["projects"][0]["directory_name"] == "my-project"
            assert result["projects"][0]["github_url"] == "https://github.com/user/my-project"

    def test_detects_group(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            group = os.path.join(tmpdir, "MyGroup")
            os.makedirs(group)
            _make_git_repo(os.path.join(group, "child1"), remote_url="https://github.com/u/c1")
            _make_git_repo(os.path.join(group, "child2"), remote_url="https://github.com/u/c2")
            result = scanner.scan_directory(tmpdir)
            assert result["summary"]["total_found"] == 2
            assert result["summary"]["groups_found"] == 1
            assert result["groups"][0]["name"] == "MyGroup"
            assert all(p["group_name"] == "MyGroup" for p in result["projects"])

    def test_skip_list_honored(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _make_git_repo(os.path.join(tmpdir, "node_modules"))
            _make_git_repo(os.path.join(tmpdir, "real-project"))
            result = scanner.scan_directory(tmpdir)
            assert result["summary"]["total_found"] == 1
            assert result["projects"][0]["directory_name"] == "real-project"

    def test_hidden_dirs_skipped(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _make_git_repo(os.path.join(tmpdir, ".hidden-project"))
            _make_git_repo(os.path.join(tmpdir, "visible-project"))
            result = scanner.scan_directory(tmpdir)
            assert result["summary"]["total_found"] == 1


class TestGitRemoteParsing:
    def test_ssh_remote(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _make_git_repo(os.path.join(tmpdir, "proj"), remote_url="git@github.com:user/repo.git")
            result = scanner.scan_directory(tmpdir)
            assert result["projects"][0]["github_url"] == "https://github.com/user/repo"

    def test_https_remote(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _make_git_repo(os.path.join(tmpdir, "proj"), remote_url="https://github.com/User/Repo.git")
            result = scanner.scan_directory(tmpdir)
            assert result["projects"][0]["github_url"] == "https://github.com/user/repo"

    def test_no_remote(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _make_git_repo(os.path.join(tmpdir, "proj"))
            result = scanner.scan_directory(tmpdir)
            assert result["projects"][0]["git_remote_url"] is None
            assert result["projects"][0]["github_url"] is None

    def test_non_github_remote(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _make_git_repo(os.path.join(tmpdir, "proj"), remote_url="https://gitlab.com/user/repo.git")
            result = scanner.scan_directory(tmpdir)
            assert result["projects"][0]["git_remote_url"] == "https://gitlab.com/user/repo.git"
            assert result["projects"][0]["github_url"] is None


class TestUrlNormalization:
    def test_ssh_to_https(self):
        assert scanner.normalize_github_url("git@github.com:user/repo.git") == "https://github.com/user/repo"

    def test_strip_dot_git(self):
        assert scanner.normalize_github_url("https://github.com/user/repo.git") == "https://github.com/user/repo"

    def test_case_insensitive(self):
        assert scanner.normalize_github_url("https://GitHub.com/User/Repo") == "https://github.com/user/repo"

    def test_non_github_returns_none(self):
        assert scanner.normalize_github_url("https://gitlab.com/user/repo") is None

    def test_none_input(self):
        assert scanner.normalize_github_url(None) is None


class TestReadme:
    def test_readme_excerpt(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            content = "# My Project\nThis is a test." + "x" * 6000
            _make_git_repo(os.path.join(tmpdir, "proj"), readme_content=content)
            result = scanner.scan_directory(tmpdir)
            assert result["projects"][0]["has_readme"] is True
            assert len(result["projects"][0]["readme_excerpt"]) == 5000

    def test_no_readme(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _make_git_repo(os.path.join(tmpdir, "proj"))
            result = scanner.scan_directory(tmpdir)
            assert result["projects"][0]["has_readme"] is False
            assert result["projects"][0]["readme_excerpt"] is None


class TestDependencyExtraction:
    def test_npm_deps(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = os.path.join(tmpdir, "proj")
            _make_git_repo(repo)
            with open(os.path.join(repo, "package.json"), "w") as f:
                json.dump({"dependencies": {"react": "^18", "express": "^4"}}, f)
            result = scanner.scan_directory(tmpdir)
            assert "npm" in result["projects"][0]["dependencies"]
            assert "react" in result["projects"][0]["dependencies"]["npm"]

    def test_requirements_deps(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = os.path.join(tmpdir, "proj")
            _make_git_repo(repo)
            with open(os.path.join(repo, "requirements.txt"), "w") as f:
                f.write("fastapi>=0.100\nuvicorn\n# comment\n-r other.txt\n")
            result = scanner.scan_directory(tmpdir)
            assert "pip" in result["projects"][0]["dependencies"]
            assert "fastapi" in result["projects"][0]["dependencies"]["pip"]
            assert "uvicorn" in result["projects"][0]["dependencies"]["pip"]


class TestInfraMarkers:
    def test_dockerfile_detected(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = os.path.join(tmpdir, "proj")
            _make_git_repo(repo)
            with open(os.path.join(repo, "Dockerfile"), "w") as f:
                f.write("FROM python:3.12\n")
            result = scanner.scan_directory(tmpdir)
            assert "docker" in result["projects"][0]["infra_markers"]

    def test_github_actions_detected(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = os.path.join(tmpdir, "proj")
            _make_git_repo(repo)
            os.makedirs(os.path.join(repo, ".github", "workflows"))
            result = scanner.scan_directory(tmpdir)
            assert "github-actions" in result["projects"][0]["infra_markers"]
```

- [ ] **Step 2: Run scan tests**

Run: `cd /home/winadmin/projects/Trinity/cortex && uv run pytest python/tests/test_cortex_scanner.py -v --tb=short -k "not Apply"`

Expected: All scan tests pass.

- [ ] **Step 3: Write apply mode tests**

Append to `python/tests/test_cortex_scanner.py`:

```python
class TestApplyConfigs:
    def _make_payload_file(self, tmpdir, projects):
        payload_path = os.path.join(tmpdir, "payload.json")
        with open(payload_path, "w") as f:
            json.dump({"projects": projects}, f)
        return payload_path

    def test_writes_config_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            proj_dir = os.path.join(tmpdir, "my-project")
            os.makedirs(proj_dir)
            payload = self._make_payload_file(tmpdir, [{
                "absolute_path": proj_dir,
                "project_id": "test-uuid",
                "project_title": "my-project",
                "cortex_api_url": "http://localhost:8181",
                "cortex_mcp_url": "http://localhost:8051",
                "system_fingerprint": "abc123",
                "system_name": "TEST",
            }])
            result = scanner.apply_configs(payload)
            assert result["apply_summary"]["created"] == 1

            config_path = os.path.join(proj_dir, ".claude", "cortex-config.json")
            assert os.path.isfile(config_path)
            with open(config_path) as f:
                config = json.load(f)
            assert config["project_id"] == "test-uuid"
            assert config["installed_by"] == "scanner"

            state_path = os.path.join(proj_dir, ".claude", "cortex-state.json")
            assert os.path.isfile(state_path)
            with open(state_path) as f:
                state = json.load(f)
            assert state["system_fingerprint"] == "abc123"

    def test_writes_settings_local(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            proj_dir = os.path.join(tmpdir, "my-project")
            os.makedirs(proj_dir)
            payload = self._make_payload_file(tmpdir, [{
                "absolute_path": proj_dir,
                "project_id": "id",
                "system_fingerprint": "fp",
                "system_name": "SYS",
            }])
            scanner.apply_configs(payload)

            settings_path = os.path.join(proj_dir, ".claude", "settings.local.json")
            assert os.path.isfile(settings_path)
            with open(settings_path) as f:
                settings = json.load(f)
            assert "PostToolUse" in settings["hooks"]

    def test_gitignore_appended(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            proj_dir = os.path.join(tmpdir, "my-project")
            os.makedirs(proj_dir)
            with open(os.path.join(proj_dir, ".gitignore"), "w") as f:
                f.write("node_modules\n")
            payload = self._make_payload_file(tmpdir, [{
                "absolute_path": proj_dir,
                "project_id": "id",
                "system_fingerprint": "fp",
                "system_name": "SYS",
            }])
            scanner.apply_configs(payload)

            with open(os.path.join(proj_dir, ".gitignore")) as f:
                content = f.read()
            assert "# Cortex" in content
            assert "node_modules" in content

    def test_gitignore_idempotent(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            proj_dir = os.path.join(tmpdir, "my-project")
            os.makedirs(proj_dir)
            payload = self._make_payload_file(tmpdir, [{
                "absolute_path": proj_dir,
                "project_id": "id",
                "system_fingerprint": "fp",
                "system_name": "SYS",
            }])
            scanner.apply_configs(payload)
            scanner.apply_configs(payload)

            with open(os.path.join(proj_dir, ".gitignore")) as f:
                content = f.read()
            assert content.count("# Cortex") == 1

    def test_gitignore_no_trailing_newline(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            proj_dir = os.path.join(tmpdir, "my-project")
            os.makedirs(proj_dir)
            with open(os.path.join(proj_dir, ".gitignore"), "w") as f:
                f.write("node_modules")  # No trailing newline
            payload = self._make_payload_file(tmpdir, [{
                "absolute_path": proj_dir,
                "project_id": "id",
                "system_fingerprint": "fp",
                "system_name": "SYS",
            }])
            scanner.apply_configs(payload)

            with open(os.path.join(proj_dir, ".gitignore")) as f:
                content = f.read()
            # node_modules should NOT be corrupted
            assert "node_modules\n" in content
            assert "node_modules# Cortex" not in content

    def test_nonexistent_path_fails_gracefully(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            payload = self._make_payload_file(tmpdir, [{
                "absolute_path": "/nonexistent/path",
                "project_id": "id",
                "system_fingerprint": "fp",
                "system_name": "SYS",
            }])
            result = scanner.apply_configs(payload)
            assert result["apply_summary"]["failed"] == 1
            assert result["results"][0]["status"] == "failed"

    def test_missing_tarball_still_writes_configs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            proj_dir = os.path.join(tmpdir, "my-project")
            os.makedirs(proj_dir)
            payload = self._make_payload_file(tmpdir, [{
                "absolute_path": proj_dir,
                "project_id": "id",
                "system_fingerprint": "fp",
                "system_name": "SYS",
            }])
            result = scanner.apply_configs(payload, extensions_tarball="/nonexistent.tar.gz")
            assert result["apply_summary"]["created"] == 1
            assert os.path.isfile(os.path.join(proj_dir, ".claude", "cortex-config.json"))

    def test_extracts_extensions_tarball(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            proj_dir = os.path.join(tmpdir, "my-project")
            os.makedirs(proj_dir)

            # Create a minimal tarball with a test file
            tarball_path = os.path.join(tmpdir, "extensions.tar.gz")
            import io
            with tarfile.open(tarball_path, "w:gz") as tar:
                content = b"# test skill content"
                info = tarfile.TarInfo(name="test-skill.md")
                info.size = len(content)
                tar.addfile(info, io.BytesIO(content))

            payload = self._make_payload_file(tmpdir, [{
                "absolute_path": proj_dir,
                "project_id": "id",
                "system_fingerprint": "fp",
                "system_name": "SYS",
            }])
            result = scanner.apply_configs(payload, extensions_tarball=tarball_path)
            assert result["apply_summary"]["created"] == 1
            assert os.path.isfile(os.path.join(proj_dir, ".claude", "skills", "test-skill.md"))

    def test_gitignore_with_trailing_newline(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            proj_dir = os.path.join(tmpdir, "my-project")
            os.makedirs(proj_dir)
            with open(os.path.join(proj_dir, ".gitignore"), "w") as f:
                f.write("node_modules\n")  # Has trailing newline
            payload = self._make_payload_file(tmpdir, [{
                "absolute_path": proj_dir,
                "project_id": "id",
                "system_fingerprint": "fp",
                "system_name": "SYS",
            }])
            scanner.apply_configs(payload)

            with open(os.path.join(proj_dir, ".gitignore")) as f:
                content = f.read()
            # Should not have a blank line between existing content and Cortex block
            assert "node_modules\n# Cortex" in content
            assert "node_modules\n\n# Cortex" not in content


class TestTomlParsing:
    def test_pyproject_toml_regex_fallback(self):
        """Test regex-based TOML parsing for Python 3.8-3.10."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = os.path.join(tmpdir, "proj")
            _make_git_repo(repo)
            with open(os.path.join(repo, "pyproject.toml"), "w") as f:
                f.write('[project]\nname = "myproject"\n\n'
                        'dependencies = [\n'
                        '    "fastapi>=0.100",\n'
                        '    "uvicorn",\n'
                        '    "pydantic>=2.0",\n'
                        ']\n')
            # Test the regex fallback directly
            deps = scanner._extract_toml_deps_regex(os.path.join(repo, "pyproject.toml"))
            assert "fastapi" in deps
            assert "uvicorn" in deps
            assert "pydantic" in deps

    def test_pyproject_toml_via_scan(self):
        """Test TOML parsing through the full scan pipeline (uses tomllib or fallback)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = os.path.join(tmpdir, "proj")
            _make_git_repo(repo)
            with open(os.path.join(repo, "pyproject.toml"), "w") as f:
                f.write('[project]\nname = "myproject"\n\n'
                        'dependencies = [\n'
                        '    "requests>=2.28",\n'
                        ']\n')
            result = scanner.scan_directory(tmpdir)
            assert result["projects"][0]["dependencies"] is not None
            assert "pip" in result["projects"][0]["dependencies"]
            assert "requests" in result["projects"][0]["dependencies"]["pip"]
```

- [ ] **Step 4: Run all tests**

Run: `cd /home/winadmin/projects/Trinity/cortex && uv run pytest python/tests/test_cortex_scanner.py -v --tb=short`

Expected: All tests pass.

- [ ] **Step 5: Commit tests**

```bash
git add python/tests/test_cortex_scanner.py
git commit -m "test: add comprehensive tests for cortex-scanner.py"
```

---

## Task 4: Add the Script Distribution Endpoint

**Files:**
- Create: `python/src/server/api_routes/scanner_script_api.py`
- Modify: `python/src/server/main.py`

- [ ] **Step 1: Create the endpoint**

Create `python/src/server/api_routes/scanner_script_api.py`:

```python
"""Scanner script distribution endpoint."""

import os

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

router = APIRouter(prefix="/api/scanner", tags=["scanner"])

SCRIPT_PATH = os.path.join(os.path.dirname(__file__), "..", "static", "cortex-scanner.py")
SCANNER_VERSION = "1.0"


@router.get("/script")
async def get_scanner_script():
    """Serve the standalone scanner script for client-side execution."""
    with open(SCRIPT_PATH, "r") as f:
        content = f.read()
    return PlainTextResponse(
        content=content,
        headers={"X-Scanner-Version": SCANNER_VERSION},
    )
```

- [ ] **Step 2: Register the new route in main.py**

In `python/src/server/main.py`, add the import and router inclusion. Do NOT remove the old scanner router yet (that's Task 5).

Add import:
```python
from .api_routes.scanner_script_api import router as scanner_script_router
```

Add inclusion (near the other router inclusions):
```python
app.include_router(scanner_script_router)
```

- [ ] **Step 3: Test the endpoint**

Run: `curl -s http://localhost:8181/api/scanner/script | head -5`

Expected: First 5 lines of `cortex-scanner.py` (the shebang line and docstring).

- [ ] **Step 4: Commit**

```bash
git add python/src/server/api_routes/scanner_script_api.py python/src/server/main.py
git commit -m "feat: add GET /api/scanner/script endpoint for scanner distribution"
```

---

## Task 5: Remove Old Server-Side Scanner Code

**Files:**
- Delete: entire `python/src/server/services/scanner/` directory
- Delete: `python/src/server/api_routes/scanner_api.py`
- Delete: `python/src/server/config/scanner_config.py`
- Delete: entire `python/src/mcp_server/features/scanner/` directory
- Delete: `python/tests/server/services/scanner/` directory
- Modify: `python/src/server/main.py` (remove old scanner router)
- Modify: `python/src/mcp_server/mcp_server.py` (remove scanner tools registration)
- Modify: `docker-compose.yml` (remove volume mount and env vars)
- Modify: `.env.example` (repo root — remove scanner env vars)

- [ ] **Step 1: Remove old scanner router from main.py**

In `python/src/server/main.py`:
- Remove the import: `from .api_routes.scanner_api import router as scanner_router` (line 39)
- Remove the inclusion: `app.include_router(scanner_router)` (line 228)

- [ ] **Step 2: Remove scanner tools from MCP server**

In `python/src/mcp_server/mcp_server.py`, remove lines 660-674 (the scanner tools registration block):

```python
# Scanner Tools (Local Project Scanner)
try:
    from src.mcp_server.features.scanner import register_scanner_tools
    ...
```

- [ ] **Step 3: Remove scanner volume mount and env vars from Docker**

In `docker-compose.yml`:
- Remove line 34: `- SCANNER_PROJECTS_ROOT=/projects`
- Remove line 35: `- SCANNER_ENABLED=${SCANNER_ENABLED:-false}`
- Remove line 51: `- ${PROJECTS_DIRECTORY:-~/projects}:/projects:rw   # Scanner mount`

In `.env.example` (repo root, NOT `python/.env.example`):
- Remove line 139: `PROJECTS_DIRECTORY=~/projects`
- Remove line 140: `SCANNER_ENABLED=false`

- [ ] **Step 4: Delete old scanner files**

```bash
rm -rf python/src/server/services/scanner/
rm -f python/src/server/api_routes/scanner_api.py
rm -f python/src/server/config/scanner_config.py
rm -rf python/src/mcp_server/features/scanner/
rm -rf python/tests/server/services/scanner/
```

- [ ] **Step 5: Verify no broken imports**

Run: `cd /home/winadmin/projects/Trinity/cortex && uv run python -c "from src.server.main import app; print('OK')"`

Expected: `OK` — no import errors.

Run: `cd /home/winadmin/projects/Trinity/cortex && uv run python -c "from src.mcp_server.mcp_server import mcp; print('OK')"`

Expected: `OK` — no import errors.

- [ ] **Step 6: Run existing tests to verify nothing broke**

Run: `cd /home/winadmin/projects/Trinity/cortex && uv run pytest python/tests/ -v --tb=short --ignore=python/tests/test_cortex_scanner.py -x`

Expected: All existing tests pass (scanner tests already removed in Step 4).

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "refactor: remove server-side scanner code (replaced by client-side script)"
```

---

## Task 6: Create the Database Migration

**Files:**
- Create: `migration/0.1.0/022_drop_scanner_tables.sql`

- [ ] **Step 1: Write the migration**

Create `migration/0.1.0/022_drop_scanner_tables.sql`:

```sql
-- Drop scanner tables (scanner rearchitected to client-side script)
-- These tables are no longer used — scanning and results are handled client-side.

DROP TABLE IF EXISTS cortex_scan_projects CASCADE;
DROP TABLE IF EXISTS cortex_scan_results CASCADE;
DROP TABLE IF EXISTS cortex_scanner_templates CASCADE;
```

- [ ] **Step 2: Commit**

```bash
git add migration/0.1.0/022_drop_scanner_tables.sql
git commit -m "migration: drop scanner tables (022)"
```

---

## Task 7: Write the `/scan-projects` Skill

**Files:**
- Create: `integrations/claude-code/skills/scan-projects.md`

- [ ] **Step 1: Write the skill**

Create `integrations/claude-code/skills/scan-projects.md`:

```markdown
---
name: scan-projects
description: Scan a local projects directory for Git repositories and bulk-onboard them into Cortex. Downloads a scanner script, detects repos, creates Cortex projects via MCP, and writes config files.
---

# Scan Local Projects

Bulk-onboard local Git repositories into Cortex. This skill scans a directory, detects repos, creates Cortex projects, and writes config files — all from the current machine.

## Prerequisites
- System must be registered with Cortex (run `/cortex-setup` in any project first)
- Cortex stack must be running

## Procedure

Follow these steps exactly in order. Do not skip steps.

### Step 1 — Preflight Checks

1. Look for `cortex-state.json` in `~/.claude/` or the current project's `.claude/` directory. Read it.
2. Extract `system_fingerprint` and `system_name`. If the file is not found, tell the user: "System not registered. Run /cortex-setup in any project first." and STOP.
3. Look for `cortex-config.json` in the same locations. Extract `cortex_api_url` (default: `http://localhost:8181`) and `cortex_mcp_url` (default: `http://localhost:8051`).
4. Detect the Python executable:
   - Try: `python3 --version`
   - If that fails, try: `python --version` and verify the output shows Python 3.x
   - If neither works: tell the user "Python 3.8+ not found. Please install Python and ensure it's on your PATH." and STOP.
   - Store the working command as PYTHON_CMD for later use.
5. Detect the temp directory:
   - Run: `<PYTHON_CMD> -c "import tempfile; print(tempfile.gettempdir())"`
   - Store the output as TEMP_DIR.

### Step 2 — Download Scanner Script

1. Run: `curl -s <cortex_api_url>/api/scanner/script -o <TEMP_DIR>/cortex-scanner.py`
2. If the download fails (curl error or empty file), tell the user: "Can't reach Cortex at <url>. Is the Cortex stack running?" and STOP.

### Step 3 — Run Scan

1. Ask the user: "What directory should I scan? (default: ~/projects)"
2. Run: `<PYTHON_CMD> <TEMP_DIR>/cortex-scanner.py --scan <directory>`
3. Parse the JSON output. If the output contains an `error` key, display the error and STOP.
4. Store the full scan result for use in later steps.

### Step 4 — Deduplicate Against Existing Cortex Projects

1. Call the `find_projects` MCP tool to get all existing Cortex projects.
2. For each project in the scan results, compare its `github_url` (normalized, lowercase) against the `github_repo` field of existing Cortex projects.
3. Mark matches by setting `already_in_cortex: true` and storing the `existing_project_id`.
4. Count: how many are new, how many already exist.

### Step 5 — Present Results to User

Display a summary like:
```
Scan complete!
- Total repositories found: <N>
- New (not in Cortex): <N>
- Already in Cortex: <N> (<names>)
- Project groups: <N>
```

For each NEW project:
- If it has a `readme_excerpt`, generate a 1-2 sentence description from it.
- If no README, note the detected languages and infra markers.

Present the list:
```
New projects to set up:
1. <name> — <description>
2. <name> — [no README, detected: python, docker]
...

Already in Cortex (will skip): <names>

Proceed with setting up these <N> projects? You can exclude any by number.
```

Wait for user confirmation. If they exclude projects, remove them from the list. If they cancel, STOP.

### Step 6 — Create Projects in Cortex

For each confirmed new project:
1. If the project belongs to a group and the group parent hasn't been created yet:
   - Call `manage_project` MCP tool with `action: "create"`, `title: "<group_name>"`, `tags: ["project-group"]`, `description: "Project group containing <child names>"`.
   - Store the returned `project_id` as the group parent ID.
2. Call `manage_project` MCP tool with:
   - `action: "create"`
   - `title`: directory_name
   - `description`: the AI-generated description
   - `github_repo`: the normalized `github_url` (or null if no GitHub remote)
   - `tags`: combine `detected_languages` + `infra_markers`
   - `metadata`: `{"dependencies": <deps>, "scanned_from": "<absolute_path>", "scanner_version": "1.0"}`
   - `parent_project_id`: group parent ID if applicable
3. Store the returned `project_id` for each project.

### Step 7 — Register System for Each Project

For each created project, call the `manage_extensions` MCP tool with:
- `action: "sync"`
- `project_id`: the created project's ID
- `system_fingerprint`: from Step 1

### Step 8 — Download Extensions Tarball

Run: `curl -s <cortex_mcp_url>/cortex-setup/extensions.tar.gz -o <TEMP_DIR>/cortex-extensions.tar.gz`

If the download fails, warn the user: "Extensions tarball download failed. Projects will be created without extensions." Continue to Step 9.

### Step 9 — Apply Config Files

1. Build a JSON payload with all created projects:
```json
{
  "projects": [
    {
      "absolute_path": "<path>",
      "project_id": "<id from Step 6>",
      "project_title": "<directory_name>",
      "cortex_api_url": "<from Step 1>",
      "cortex_mcp_url": "<from Step 1>",
      "system_fingerprint": "<from Step 1>",
      "system_name": "<from Step 1>"
    }
  ]
}
```
2. Write the payload to `<TEMP_DIR>/cortex-apply-payload.json` using the Write tool.
3. Run: `<PYTHON_CMD> <TEMP_DIR>/cortex-scanner.py --apply --payload-file <TEMP_DIR>/cortex-apply-payload.json --extensions-tarball <TEMP_DIR>/cortex-extensions.tar.gz`
4. Parse the JSON output for success/failure counts.

### Step 10 — Knowledge Base Ingestion

For each created project that has a `github_url` with `github_owner` and `github_repo_name`:
- Call `manage_rag_source` MCP tool with:
  - `action: "add"`
  - `source_type: "url"`
  - `title: "<directory_name> README"`
  - `url: "https://github.com/<owner>/<repo>#readme"`
  - `project_id: "<project_id>"`
  - `knowledge_type: "technical"`

For large scans (20+ projects), batch these in groups of 5 with a brief pause between batches.

### Step 11 — Display Final Summary

```
Setup complete!
- Projects created: <N>
- Projects skipped (already in Cortex): <N>
- Projects failed: <N>
- README crawls queued: <N>

<If any failures, list them with error messages>

You can now open Claude Code in any of these projects and Cortex context will be available.
```
```

- [ ] **Step 2: Commit**

```bash
git add integrations/claude-code/skills/scan-projects.md
git commit -m "feat: add /scan-projects skill for client-side project scanning"
```

---

## Task 8: Remove Scanner Environment Variables from .env

**Files:**
- Modify: `.env` (user's actual env file, if scanner vars present)

- [ ] **Step 1: Check and remove scanner env vars from .env**

If the user's `.env` file contains `PROJECTS_DIRECTORY` or `SCANNER_ENABLED`, remove those lines.

- [ ] **Step 2: Rebuild Docker**

```bash
docker compose down && docker compose up --build -d
```

- [ ] **Step 3: Verify clean startup**

Run: `docker compose logs cortex-server 2>&1 | tail -20`

Expected: No scanner-related errors. Server starts cleanly.

Run: `curl -s http://localhost:8181/api/scanner/script | head -3`

Expected: First lines of the scanner script.

- [ ] **Step 4: Commit .env changes if applicable**

Only commit `.env.example` changes (`.env` itself should be in `.gitignore`).

---

## Task 9: End-to-End Verification

No new files. This task verifies the complete flow works.

- [ ] **Step 1: Run all tests**

```bash
cd /home/winadmin/projects/Trinity/cortex && uv run pytest python/tests/test_cortex_scanner.py -v --tb=short
```

Expected: All scanner script tests pass.

```bash
cd /home/winadmin/projects/Trinity/cortex && uv run pytest python/tests/ -v --tb=short -x --ignore=python/tests/test_cortex_scanner.py
```

Expected: All existing tests pass.

- [ ] **Step 2: Verify script endpoint works**

```bash
curl -s -o /dev/null -w "%{http_code}" http://localhost:8181/api/scanner/script
```

Expected: `200`

- [ ] **Step 3: Verify scanner script runs locally**

```bash
python3 /tmp/cortex-scanner.py --scan ~/projects 2>/dev/null | python3 -m json.tool | head -20
```

Expected: Valid JSON with detected projects.

- [ ] **Step 4: Verify old scanner endpoints are gone**

```bash
curl -s -o /dev/null -w "%{http_code}" http://localhost:8181/api/scanner/scan
```

Expected: `404` or `405` (endpoint no longer exists).

- [ ] **Step 5: Verify Docker has no scanner volume mount**

```bash
docker inspect cortex-server --format '{{json .Mounts}}' | python3 -m json.tool
```

Expected: No `/projects` mount in the list.

---

## Task 10: Update Journey Test Document

**Files:**
- Modify: `docs/userJourneys/projectScannerJourney.md`

- [ ] **Step 1: Rewrite the journey test**

Update `docs/userJourneys/projectScannerJourney.md` to reflect the new client-side architecture:
- Phase 0: No Docker volume mount. Just verify Cortex is running and script endpoint responds.
- Phase 1: User invokes `/scan-projects` skill, not MCP tool. Script runs locally.
- Phase 2: Same (AI description generation by Claude).
- Phase 3: Skill creates projects via MCP, script writes configs locally.
- Phase 4: Same (verify config files). Paths are real local paths, not container paths.
- Phase 5: Knowledge base ingestion via MCP `manage_rag_source`.
- Phase 6: No CSV report (removed). Skill displays summary in conversation.
- Phase 7: Dedup happens client-side in the skill via `find_projects` MCP call.
- Phase 8: Templates are skill parameters, not backend-stored.
- Phase 9: Edge cases adjusted — no scanner-disabled test, add Python-not-found test.
- Phase 10: Same (post-scanner workflow validation).
- Phase 11: Same (extension version tracking).
- Phase 12: No scan expiry (no scan tables). Config files persist permanently.

- [ ] **Step 2: Commit**

```bash
git add docs/userJourneys/projectScannerJourney.md
git commit -m "docs: update journey test for client-side scanner architecture"
```
