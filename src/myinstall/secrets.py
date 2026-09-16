from __future__ import annotations

import os
import secrets as random_secrets
import tempfile
from pathlib import Path
from typing import Any

KEY = __import__("re").compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _parse_value(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
        return value[1:-1]
    return value


def read(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not KEY.fullmatch(key):
            raise ValueError(f"invalid secret key: {key}")
        if key in values:
            raise ValueError(f"duplicate secret key: {key}")
        values[key] = _parse_value(value)
    return values


def write(path: Path, values: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            for key, value in sorted(values.items()):
                if not KEY.fullmatch(key):
                    raise ValueError(f"invalid secret key: {key}")
                if "\n" in value or "\r" in value:
                    raise ValueError(f"secret value contains a newline: {key}")
                stream.write(f"{key}={value}\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def ensure(manifest: dict[str, Any]) -> list[str]:
    path = Path(manifest["secret_path"])
    values = read(path)
    created: list[str] = []
    for item in manifest.get("generated_secrets", []):
        name = str(item["name"])
        if name in values:
            continue
        length = max(16, min(256, int(item.get("length", 64))))
        values[name] = random_secrets.token_urlsafe(length)[:length]
        created.append(name)
    if created:
        write(path, values)
    return created


def status(manifest: dict[str, Any]) -> dict[str, Any]:
    path = Path(manifest["secret_path"])
    return {
        "path": str(path),
        "keys": sorted(read(path)),
        "mode": oct(path.stat().st_mode & 0o777) if path.exists() else None,
    }


def validate_required(manifest: dict[str, Any]) -> list[str]:
    path = Path(manifest["secret_path"])
    values = read(path)
    missing = [name for name in manifest["required_secrets"] if name not in values or not values[name]]
    if missing:
        return missing
    if path.exists() and (path.stat().st_mode & 0o077):
        raise ValueError("secret file must not be group/world writable or readable")
    return []
