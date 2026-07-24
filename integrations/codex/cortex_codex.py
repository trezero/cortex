#!/usr/bin/env python3
"""Deterministic Cortex skill distribution client for Codex."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import socket
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

AGENT = "codex"
CONFIG_PATH = Path(".cortex/codex.json")
GLOBAL_CONFIG_PATH = Path.home() / ".config/cortex/codex.json"
MARKER = ".cortex-extension.json"
SKILL_FILE = "SKILL.md"


class CortexError(RuntimeError):
    """Actionable client failure."""


def digest(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def json_dump(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def find_project_root(start: Path) -> Path:
    current = start.resolve()
    for candidate in (current, *current.parents):
        if (candidate / CONFIG_PATH).is_file():
            return candidate
    return current


@dataclass(frozen=True)
class Config:
    api_url: str
    project_id: str
    project_root: Path
    api_key: str | None = None

    @classmethod
    def load(cls, start: Path, explicit: Path | None = None) -> Config:
        project_root = find_project_root(start)
        candidates = [explicit] if explicit else [project_root / CONFIG_PATH, GLOBAL_CONFIG_PATH]
        config_path = next((path for path in candidates if path and path.is_file()), None)
        if config_path is None:
            raise CortexError(
                f"No Cortex Codex config found. Expected {project_root / CONFIG_PATH} "
                f"or {GLOBAL_CONFIG_PATH}."
            )
        raw = json.loads(config_path.read_text(encoding="utf-8"))
        missing = [key for key in ("api_url", "project_id") if not raw.get(key)]
        if missing:
            raise CortexError(f"{config_path} is missing: {', '.join(missing)}")
        configured_root = raw.get("project_root")
        if configured_root:
            project_root = Path(configured_root).expanduser().resolve()
        return cls(
            api_url=raw["api_url"].rstrip("/"),
            project_id=raw["project_id"],
            project_root=project_root,
            api_key=raw.get("api_key"),
        )


class Api:
    def __init__(self, config: Config):
        self.config = config

    def request(self, method: str, path: str, body: dict[str, Any] | None = None) -> Any:
        data = json.dumps(body).encode() if body is not None else None
        headers = {"Accept": "application/json"}
        if data is not None:
            headers["Content-Type"] = "application/json"
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        request = urllib.request.Request(
            f"{self.config.api_url}{path}",
            data=data,
            headers=headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                content = response.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise CortexError(f"Cortex API returned HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise CortexError(f"Cannot reach Cortex API at {self.config.api_url}: {exc.reason}") from exc
        return json.loads(content) if content else None


def roots(config: Config) -> dict[str, Path]:
    return {
        "repository": config.project_root / ".agents/skills",
        "global": Path.home() / ".agents/skills",
    }


def read_marker(skill_dir: Path) -> dict[str, Any] | None:
    try:
        value = json.loads((skill_dir / MARKER).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
    return value if value.get("agent") == AGENT else None


def scan_skills(config: Config) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for scope, root in roots(config).items():
        if not root.is_dir():
            continue
        for skill_dir in sorted(root.iterdir()):
            skill_file = skill_dir / SKILL_FILE
            if not skill_dir.is_dir() or not skill_file.is_file():
                continue
            content = skill_file.read_text(encoding="utf-8")
            marker = read_marker(skill_dir)
            result.append(
                {
                    "name": skill_dir.name,
                    "scope": scope,
                    "payload_hash": digest(content),
                    "reviewed_source_hash": marker.get("reviewed_source_hash") if marker else None,
                    "extension_id": marker.get("extension_id") if marker else None,
                    "managed": marker is not None,
                }
            )
    return result


def fingerprint() -> str:
    machine_id = ""
    for path in (Path("/etc/machine-id"), Path("/var/lib/dbus/machine-id")):
        try:
            machine_id = path.read_text(encoding="utf-8").strip()
            break
        except OSError:
            pass
    raw = "\0".join((machine_id, socket.gethostname(), os.environ.get("USER", ""), AGENT))
    return f"codex-{hashlib.sha256(raw.encode()).hexdigest()[:24]}"


def sync_request(config: Config, api: Api) -> dict[str, Any]:
    return api.request(
        "POST",
        f"/api/projects/{config.project_id}/agent-sync",
        {
            "agent": AGENT,
            "fingerprint": fingerprint(),
            "system_name": f"{socket.gethostname()} Codex",
            "hostname": socket.gethostname(),
            "os": f"{platform.system()} {platform.release()}",
            "local_extensions": scan_skills(config),
        },
    )


def backup_root(config: Config, scope: str) -> Path:
    if scope == "repository":
        return config.project_root / ".cortex/backups/codex-skills"
    return Path.home() / ".local/state/cortex/backups/codex-skills"


def archive(config: Config, skill_dir: Path, scope: str) -> Path:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S.%fZ")
    destination = backup_root(config, scope) / f"{skill_dir.name}-{timestamp}"
    destination.parent.mkdir(parents=True, exist_ok=True)
    skill_dir.replace(destination)
    return destination


def install_state(config: Config, state: dict[str, Any]) -> None:
    target = state["target"]
    scope = target["scope"]
    destination = roots(config)[scope] / state["name"]
    existing_marker = read_marker(destination) if destination.exists() else None
    if destination.exists() and existing_marker is None:
        raise CortexError(f"Refusing to overwrite unmanaged skill: {destination}")

    destination.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{state['name']}-", dir=destination.parent))
    previous: Path | None = None
    try:
        (stage / SKILL_FILE).write_text(target["payload_content"], encoding="utf-8")
        json_dump(
            stage / MARKER,
            {
                "schema_version": 1,
                "agent": AGENT,
                "extension_id": state["extension_id"],
                "name": state["name"],
                "mode": target["mode"],
                "scope": scope,
                "reviewed_source_hash": target["reviewed_source_hash"],
                "payload_hash": target["payload_hash"],
                "installed_at": datetime.now(UTC).isoformat(),
            },
        )
        if destination.exists():
            previous = archive(config, destination, scope)
        stage.replace(destination)
    except Exception:
        if destination.exists() and read_marker(destination):
            shutil.rmtree(destination)
        if previous is not None and previous.exists():
            previous.replace(destination)
        if stage.exists():
            shutil.rmtree(stage)
        raise

    for other_scope, other_root in roots(config).items():
        other = other_root / state["name"]
        if other_scope != scope and other.exists():
            marker = read_marker(other)
            if marker and marker.get("extension_id") == state["extension_id"]:
                archive(config, other, other_scope)


def remove_state(config: Config, state: dict[str, Any]) -> None:
    for scope, root in roots(config).items():
        skill_dir = root / state["name"]
        marker = read_marker(skill_dir)
        if marker and marker.get("extension_id") == state["extension_id"]:
            archive(config, skill_dir, scope)


def print_report(report: dict[str, Any]) -> int:
    failures = 0
    for state in report["states"]:
        label = f"{state['review_state']}/{state['installation']}"
        action = f" -> {state['action']}" if state["action"] != "none" else ""
        print(f"{state['name']}: {label}{action}")
        if state["installation"] == "conflict" or state["review_state"] == "invalid":
            failures += 1
    for name in report.get("duplicate_names", []):
        print(f"{name}: conflict/duplicate-name")
        failures += 1
    for item in report.get("unknown_local", []):
        print(f"{item['name']}: unmanaged-or-unlinked")
    return failures


def report_failures(report: dict[str, Any]) -> int:
    return sum(
        state["installation"] == "conflict" or state["review_state"] == "invalid"
        for state in report["states"]
    ) + len(report.get("duplicate_names", []))


def command_status(config: Config, api: Api, _args: argparse.Namespace) -> int:
    report = sync_request(config, api)
    failures = report_failures(report)
    if not _args.quiet:
        print_report(report)
    return 2 if failures else 0


def command_sync(config: Config, api: Api, args: argparse.Namespace) -> int:
    report = sync_request(config, api)
    if report.get("duplicate_names"):
        print_report(report)
        raise CortexError("Duplicate skill names must be resolved before synchronization")
    failures = 0
    for state in report["states"]:
        try:
            if state["action"] == "install":
                install_state(config, state)
                if not args.quiet:
                    print(f"installed {state['name']} ({state['target']['scope']})")
            elif state["action"] == "remove":
                remove_state(config, state)
                if not args.quiet:
                    print(f"removed {state['name']}")
        except (CortexError, OSError) as exc:
            failures += 1
            print(f"failed {state['name']}: {exc}", file=sys.stderr)
            if not args.keep_going:
                break
    final_report = sync_request(config, api)
    failures += report_failures(final_report)
    if not args.quiet:
        print_report(final_report)
    return 2 if failures else 0


def find_extension(api: Api, name: str, include_content: bool = True) -> dict[str, Any]:
    suffix = "?include_content=true" if include_content else ""
    response = api.request("GET", f"/api/extensions{suffix}")
    matches = [extension for extension in response["extensions"] if extension["name"] == name]
    if len(matches) != 1:
        raise CortexError(f"Expected exactly one Cortex extension named '{name}', found {len(matches)}")
    return matches[0]


def command_review(config: Config, api: Api, args: argparse.Namespace) -> int:
    extension = find_extension(api, args.name)
    adapted_content = None
    if args.mode == "adapted":
        if args.payload is None:
            raise CortexError("--payload is required for adapted mode")
        adapted_content = args.payload.read_text(encoding="utf-8")
    response = api.request(
        "PUT",
        f"/api/extensions/{extension['id']}/targets/{AGENT}",
        {
            "mode": args.mode,
            "scope": args.scope,
            "reviewed_by": args.reviewed_by,
            "adapted_content": adapted_content,
            "expected_source_hash": extension["content_hash"],
        },
    )
    print(
        f"reviewed {args.name}: {response['compatibility_state']} "
        f"{response['mode']}/{response['scope']}"
    )
    return 0


def publish_shared_skill(
    api: Api,
    project_id: str,
    name: str,
    content: str,
    entry: dict[str, Any],
    adapted_root: Path | None,
) -> None:
    try:
        extension = find_extension(api, name)
        if extension["content_hash"] != digest(content):
            extension = api.request(
                "PUT",
                f"/api/extensions/{extension['id']}",
                {
                    "content": content,
                    "description": None,
                    "updated_by": entry.get("reviewed_by", AGENT),
                },
            )
    except CortexError as exc:
        if "found 0" not in str(exc):
            raise
        description = f"Imported agent-neutral shared skill: {name}"
        extension = api.request(
            "POST",
            "/api/extensions",
            {
                "name": name,
                "description": description,
                "content": content,
                "created_by": entry.get("reviewed_by", AGENT),
                "skill_groups": [project_id],
                "type": "skill",
            },
        )
    api.request("POST", f"/api/projects/{project_id}/extensions/{extension['id']}/link")
    expected = entry["shared_digest"].removeprefix("sha256:")
    if expected != digest(content):
        raise CortexError(f"Registry digest does not match shared source for {name}")
    adapted_content = None
    if entry["mode"] == "adapted":
        if adapted_root is None:
            raise CortexError("--adapted-root is required when importing adapted skills")
        adapted_content = (adapted_root / name / SKILL_FILE).read_text(encoding="utf-8")
    api.request(
        "PUT",
        f"/api/extensions/{extension['id']}/targets/{AGENT}",
        {
            "mode": entry["mode"],
            "scope": entry["scope"],
            "reviewed_by": entry.get("reviewed_by", AGENT),
            "adapted_content": adapted_content,
            "expected_source_hash": digest(content),
        },
    )


def command_import_registry(config: Config, api: Api, args: argparse.Namespace) -> int:
    registry = json.loads(args.registry.read_text(encoding="utf-8"))
    if registry.get("agent") != AGENT:
        raise CortexError(f"Registry agent must be '{AGENT}'")
    failures = 0
    for name, entry in sorted(registry["skills"].items()):
        try:
            content = (args.shared_root / name / SKILL_FILE).read_text(encoding="utf-8")
            publish_shared_skill(
                api,
                config.project_id,
                name,
                content,
                entry,
                args.adapted_root,
            )
            print(f"imported {name}: {entry['mode']}/{entry['scope']}")
        except (CortexError, OSError) as exc:
            failures += 1
            print(f"failed {name}: {exc}", file=sys.stderr)
            if not args.keep_going:
                break
    return 2 if failures else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cortex-codex")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    commands = parser.add_subparsers(dest="command", required=True)

    status = commands.add_parser("status", help="Report deterministic compatibility and install state")
    status.add_argument("--quiet", action="store_true")
    status.set_defaults(handler=command_status)

    sync = commands.add_parser("sync", help="Apply reviewed Cortex skill targets")
    sync.add_argument("--keep-going", action="store_true")
    sync.add_argument("--quiet", action="store_true")
    sync.set_defaults(handler=command_sync)

    review = commands.add_parser("review", help="Publish a reviewed Codex target")
    review.add_argument("name")
    review.add_argument("--mode", choices=("direct", "adapted"), required=True)
    review.add_argument("--scope", choices=("repository", "global"), default="repository")
    review.add_argument("--payload", type=Path)
    review.add_argument("--reviewed-by", default=os.environ.get("USER", AGENT))
    review.set_defaults(handler=command_review)

    import_registry = commands.add_parser(
        "import-registry",
        help="One-time import of the operating-space Codex registry into Cortex",
    )
    import_registry.add_argument("--registry", type=Path, required=True)
    import_registry.add_argument("--shared-root", type=Path, required=True)
    import_registry.add_argument("--adapted-root", type=Path)
    import_registry.add_argument("--keep-going", action="store_true")
    import_registry.set_defaults(handler=command_import_registry)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        config = Config.load(args.project_root, args.config)
        return args.handler(config, Api(config), args)
    except (CortexError, json.JSONDecodeError, OSError) as exc:
        print(f"cortex-codex: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
