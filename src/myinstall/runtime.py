from __future__ import annotations

import fcntl
import os
import shutil
import subprocess
import urllib.request
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator


def run(
    command: list[str],
    *,
    input_text: str | None = None,
    timeout: int = 180,
    env: dict[str, str] | None = None,
) -> bool:
    try:
        result = subprocess.run(
            command,
            input=input_text,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            env={**os.environ, **(env or {})},
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def compose(compose_file: Path, args: list[str], *, timeout: int = 180) -> bool:
    return run(["docker", "compose", "-f", str(compose_file), *args], timeout=timeout)


@contextmanager
def lock(stack_path: Path) -> Iterator[None]:
    stack_path.mkdir(parents=True, exist_ok=True)
    with (stack_path / ".myinstall.lock").open("w", encoding="utf-8") as stream:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def materialize(manifest_path: Path, manifest: dict[str, Any]) -> Path:
    source = manifest_path.parent.parent.parent / str(
        manifest.get("compose_source", "deploy/bootstrap/stack-compose.yml")
    )
    target = Path(manifest["stack_path"]) / "docker-compose.yml"
    if not source.is_file():
        raise FileNotFoundError(f"compose source missing: {source}")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    return target


def health(manifest: dict[str, Any]) -> bool:
    try:
        with urllib.request.urlopen(
            str(manifest["healthcheck"]["url"]),
            timeout=int(manifest["healthcheck"].get("timeout_seconds", 60)),
        ) as response:
            return 200 <= response.status < 400
    except (OSError, ValueError):
        return False
