from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REQUIRED = (
    "schema_version",
    "app",
    "zone",
    "image",
    "stack_path",
    "data_path",
    "secret_path",
    "secret_mount",
    "required_secrets",
    "healthcheck",
)


def load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"manifest unreadable: {type(exc).__name__}") from exc
    if not isinstance(value, dict):
        raise ValueError("manifest must be an object")
    missing = [key for key in REQUIRED if key not in value]
    if missing:
        raise ValueError(f"manifest missing keys: {', '.join(missing)}")
    if value["schema_version"] != "1.0":
        raise ValueError("unsupported manifest schema_version")
    return value


def compose_source(path: Path, manifest: dict[str, Any]) -> Path:
    source = manifest.get("compose_source")
    if not source:
        return path.parent / "stack-compose.yml"
    return (path.parent.parent.parent / str(source)).resolve()


def validate_paths(manifest: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for key in ("stack_path", "data_path", "secret_path", "secret_mount"):
        value = str(manifest[key])
        if not value.startswith(("/srv/nas/", "/Volumes/Nas/", "/run/")):
            errors.append(f"{key} is outside canonical roots")
    image = str(manifest["image"])
    if ("@" not in image and ":" not in image) or image.endswith(":latest"):
        errors.append("image must use an immutable tag or digest")
    return errors
