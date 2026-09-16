from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from . import github, manifest, paths


DEFAULT_ROOTS = (
    paths.stack_root(),
    Path("/srv/nas/Project"),
    Path("/srv/nas/stacks"),
    Path("/Volumes/Nas/Project"),
    Path("/Volumes/Nas/stacks"),
)


def find_app_manifest(app_id: str, roots: list[Path] | None = None) -> Path:
    """Find the unique manifest whose application id matches ``app_id``."""
    normalized = app_id.casefold()
    if not re.fullmatch(r"[a-zA-Z][a-zA-Z0-9_-]*", app_id):
        raise ValueError(f"unsafe application name: {app_id}")

    # Uses paths.app_stack() from paths.py to resolve the canonical per-app
    # location without recursively scanning large NAS project directories.
    search_roots = roots or DEFAULT_ROOTS
    candidates: set[Path] = {
        paths.app_stack(app_id) / "manifest.json",
    }
    for root in search_roots:
        candidates.update(
            {
                root / app_id / "manifest.json",
                root / "apps" / app_id / "manifest.json",
            }
        )

    matches = []
    for path in sorted(candidates):
        if not path.is_file():
            continue
        try:
            data = manifest.load(path)
        except (OSError, ValueError):
            continue
        if str(data.get("app", "")).casefold() == normalized:
            matches.append(path)
    if not matches:
        raise ValueError(f"application manifest not found: {app_id}")
    if len(matches) > 1:
        paths = ", ".join(str(path) for path in matches)
        raise ValueError(f"multiple manifests found for {app_id}: {paths}")
    return matches[0]


def find_manifests(roots: list[Path] | None = None) -> list[Path]:
    paths = roots or [path for path in DEFAULT_ROOTS if path.exists()]
    found: list[Path] = []
    for root in paths:
        if root.is_file() and root.name == "manifest.json":
            found.append(root)
            continue
        if not root.is_dir():
            continue
        for path in root.rglob("manifest.json"):
            if any(part in {".git", ".venv", "node_modules", "secrets"} for part in path.parts):
                continue
            found.append(path)
    return sorted(set(path.resolve() for path in found))


def load_all(roots: list[Path] | None = None) -> list[tuple[Path, dict[str, Any]]]:
    result: list[tuple[Path, dict[str, Any]]] = []
    seen: set[str] = set()
    for path in find_manifests(roots):
        try:
            data = manifest.load(path)
        except (OSError, ValueError):
            continue
        app = str(data["app"])
        if app in seen:
            raise ValueError(f"duplicate discovered app: {app}")
        seen.add(app)
        result.append((path, data))
    return result


def _version(value: str) -> tuple[int, int, int]:
    match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", value)
    if not match:
        raise ValueError(f"unsupported release version: {value}")
    return tuple(int(part) for part in match.groups())


def check(roots: list[Path] | None = None) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for path, data in load_all(roots):
        item: dict[str, Any] = {
            "app": data["app"],
            "manifest": str(path),
            "current": data.get("current_version"),
            "release_source": data.get("release_source"),
            "update_available": False,
        }
        if data.get("release_source"):
            release = github.latest(
                str(data["release_source"]),
                channel=str(data.get("release_channel", "stable")),
            )
            item["latest"] = release.tag if release else None
            item["update_available"] = bool(
                release and data.get("current_version") and _version(release.tag) > _version(str(data["current_version"]))
            )
        output.append(item)
    return output
