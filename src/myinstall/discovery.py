from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from . import github, manifest


DEFAULT_ROOTS = (Path("/srv/nas/stacks"), Path("/Volumes/Nas/stacks"))


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
