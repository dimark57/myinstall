from __future__ import annotations

import fcntl
import os
import re
import re
import subprocess
import time
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
    return run_result(command, input_text=input_text, timeout=timeout, env=env)[0]


def run_result(
    command: list[str],
    *,
    input_text: str | None = None,
    timeout: int = 180,
    env: dict[str, str] | None = None,
) -> tuple[bool, str]:
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
        return False, "command could not be started"
    diagnostic = (result.stderr or result.stdout or "").strip()
    # Docker/psql can echo connection strings or environment fragments.
    diagnostic = re.sub(r"(?i)(postgres(?:ql)?://)[^\\s\"']+", r"\1[redacted]", diagnostic)
    diagnostic = re.sub(r"(?i)(password|token|secret)([=:])[^\\s\"']+", r"\1\2[redacted]", diagnostic)
    return result.returncode == 0, diagnostic[-2000:]


def compose(compose_file: Path, args: list[str], *, timeout: int = 180) -> bool:
    return run(["docker", "compose", "-f", str(compose_file), *args], timeout=timeout)


def validate_compose(compose_file: Path, manifest: dict[str, Any]) -> list[str]:
    text = compose_file.read_text(encoding="utf-8")
    errors: list[str] = []
    runtime_kind = str(manifest.get("runtime", "native"))
    if runtime_kind in {"docker", "mixed"}:
        if str(manifest.get("image", "")) not in text:
            errors.append("compose does not contain the manifest image")
        if str(manifest["secret_path"]) not in text or str(manifest["secret_mount"]) not in text:
            errors.append("compose does not mount the configured secret file")
        if re.search(r"(?m)^\s{2,}postgres(?:ql)?:\s*$", text):
            errors.append("application Compose must not own shared PostgreSQL")
        if re.search(r"(?m)^\s*-\s*[^#\n]*postgres[^#\n]*data", text, re.IGNORECASE):
            errors.append("application Compose must not mount shared PostgreSQL data")
        if re.search(r"(?m)^\\s{2,}(postgres|postgresql)\\s*:", text):
            errors.append("application Compose must not declare a PostgreSQL service")
    return errors


def dependencies(manifest: dict[str, Any]) -> list[str]:
    runtime_kind = str(manifest.get("runtime", "native"))
    required = []
    if runtime_kind in {"docker", "mixed"}:
        if shutil.which("docker") is None:
            required.append("docker")
        elif not run_result(["docker", "compose", "version"], timeout=20)[0]:
            required.append("docker compose")
    elif runtime_kind == "systemd" and shutil.which("systemctl") is None:
        required.append("systemctl")
    elif runtime_kind == "launchd" and shutil.which("launchctl") is None:
        required.append("launchctl")
    return required


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
    source_url = manifest.get("compose_source_url")
    source = manifest_path.parent.parent.parent / str(
        manifest.get("compose_source", "deploy/bootstrap/stack-compose.yml")
    )
    target = Path(manifest["stack_path"]) / "docker-compose.yml"
    if source_url:
        with urllib.request.urlopen(str(source_url), timeout=30) as response:
            text = response.read().decode("utf-8")
    elif source.is_file():
        text = source.read_text(encoding="utf-8")
    else:
        raise FileNotFoundError(f"compose source missing: {source}")
    target.parent.mkdir(parents=True, exist_ok=True)
    replacements = {
        "{{IMAGE}}": str(manifest.get("image", "")),
        "{{SECRET_PATH}}": str(manifest["secret_path"]),
        "{{SECRET_MOUNT}}": str(manifest["secret_mount"]),
        "{{DATA_PATH}}": str(manifest["data_path"]),
        "{{HEALTH_URL}}": str(manifest["healthcheck"]["url"]),
    }
    for placeholder, value in replacements.items():
        text = text.replace(placeholder, value)
    target.write_text(text, encoding="utf-8")
    return target


def health(manifest: dict[str, Any]) -> bool:
    config = manifest["healthcheck"]
    retries = max(1, int(config.get("retries", 3)))
    timeout = int(config.get("timeout_seconds", 60))
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(str(config["url"]), timeout=timeout) as response:
                if 200 <= response.status < 400:
                    return True
        except (OSError, ValueError):
            pass
        if attempt + 1 < retries:
            time.sleep(min(2**attempt, 5))
    return False
