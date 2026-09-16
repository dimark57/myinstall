from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from . import paths

try:
    from jsonschema import Draft202012Validator, FormatChecker
except ImportError:  # The release zipapp keeps a dependency-free fallback.
    Draft202012Validator = None
    FormatChecker = None


REQUIRED = (
    "schema_version",
    "app",
    "zone",
    "runtime",
    "stack_path",
    "data_path",
    "secret_path",
    "secret_mount",
    "required_secrets",
    "healthcheck",
)
RUNTIMES = frozenset({"native", "docker", "systemd", "launchd", "mixed", "none"})


def immutable_image(value: str) -> bool:
    return bool(
        re.search(r"@sha256:[a-fA-F0-9]{64}$", value)
        or re.search(r":v\d+\.\d+\.\d+$", value)
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
    schema_path = Path(__file__).resolve().parents[2] / "schema" / "manifest.schema.json"
    if schema_path.is_file() and Draft202012Validator is not None:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        errors = sorted(
            Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(value),
            key=lambda error: list(error.path),
        )
        if errors:
            location = ".".join(str(part) for part in errors[0].path) or "manifest"
            raise ValueError(f"invalid {location}: {errors[0].message}")
    runtime = value.get("runtime", "native")
    if not isinstance(runtime, str) or runtime not in RUNTIMES:
        raise ValueError(f"unsupported runtime: {runtime}")
    if runtime in {"native", "systemd", "launchd"}:
        artifact = value.get("artifact")
        if not isinstance(artifact, dict) or not str(artifact.get("url", "")).startswith("https://"):
            raise ValueError("service runtime requires an HTTPS artifact")
    if isinstance(value.get("postgres"), dict):
        from .postgres import validate_config

        errors = validate_config(value)
        if errors:
            raise ValueError("; ".join(errors))
    if "release_source" in value and not value.get("current_version"):
        raise ValueError("release_source requires current_version")
    return value


def compose_source(path: Path, manifest: dict[str, Any]) -> Path:
    source = manifest.get("compose_source")
    if not source:
        return path.parent / "stack-compose.yml"
    return (path.parent.parent.parent / str(source)).resolve()


def validate_paths(manifest: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    roots = (
        Path("/srv/nas").resolve(),
        Path("/Volumes/Nas").resolve(),
        paths.nas_root().resolve(),
        Path("/run").resolve(),
    )
    for key in ("stack_path", "data_path", "secret_path", "secret_mount"):
        value = str(manifest[key])
        path = Path(value).expanduser()
        try:
            resolved = path.resolve(strict=False)
        except OSError:
            errors.append(f"{key} cannot be resolved")
            continue
        if not any(resolved == root or root in resolved.parents for root in roots):
            errors.append(f"{key} is outside canonical roots")
    runtime = manifest.get("runtime", "native")
    if runtime in {"docker", "mixed"}:
        image = str(manifest.get("image", ""))
        if not image or not immutable_image(image) or image.endswith(":latest"):
            errors.append("docker/mixed runtime requires an immutable image tag or digest")
    if runtime in {"native", "systemd", "launchd"}:
        artifact = manifest.get("artifact", {})
        if not isinstance(artifact, dict) or not artifact.get("url") or not artifact.get("sha256"):
            errors.append("native/service runtime requires an HTTPS artifact and SHA-256")
        install_path = manifest.get("install_path")
        if not install_path:
            errors.append("native/service runtime requires install_path")
    postgres = manifest.get("postgres")
    if isinstance(postgres, dict):
        for key in ("admin_compose_path", "infrastructure_compose_path", "admin_secret_path"):
            if postgres.get(key):
                path = Path(str(postgres[key])).expanduser().resolve(strict=False)
                if not any(path == root or root in path.parents for root in roots):
                    errors.append(f"{key} is outside canonical roots")
        if postgres.get("mode") == "shared" and postgres.get("admin_secret_path"):
            if Path(str(postgres["admin_secret_path"])).resolve() == Path(str(manifest["secret_path"])).resolve():
                errors.append("shared PostgreSQL admin secret must be separate from application secret")
    return errors
