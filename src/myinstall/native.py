from __future__ import annotations

import hashlib
import os
import shutil
import shlex
import tempfile
import re
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

from . import runtime


class _GitHubRedirectHandler(urllib.request.HTTPRedirectHandler):
    def __init__(self, authorization: str | None) -> None:
        super().__init__()
        self.authorization = authorization

    def redirect_request(self, req: urllib.request.Request, newurl: str, code: int, msg: str,
                         headers: Any, fp: Any) -> urllib.request.Request | None:
        redirected = super().redirect_request(req, newurl, code, msg, headers, fp)
        if redirected is not None and self.authorization:
            redirected.add_header("Authorization", self.authorization)
        return redirected


def _artifact(manifest: dict[str, Any]) -> tuple[str, str]:
    artifact = manifest.get("artifact")
    if not isinstance(artifact, dict):
        raise ValueError("native runtime requires artifact")
    url = str(artifact.get("url", ""))
    checksum = str(artifact.get("sha256", "")).lower()
    if not url.startswith("https://") or len(checksum) != 64:
        raise ValueError("artifact requires HTTPS URL and SHA-256")
    return url, checksum


def download(manifest: dict[str, Any]) -> Path:
    url, expected = _artifact(manifest)
    fd, temporary = tempfile.mkstemp(prefix=".myinstall-artifact.")
    os.close(fd)
    path = Path(temporary)
    try:
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "application/octet-stream",
                "User-Agent": "myinstall",
                **(
                    {"Authorization": f"Bearer {os.environ['MYINSTALL_GITHUB_TOKEN']}"}
                    if "github.com" in url and os.environ.get("MYINSTALL_GITHUB_TOKEN")
                    else {}
                ),
            },
        )
        token = os.environ.get("MYINSTALL_GITHUB_TOKEN")
        opener = urllib.request.build_opener(
            _GitHubRedirectHandler(f"Bearer {token}" if token else None)
        )
        with opener.open(request, timeout=600) as response, path.open("wb") as stream:
            shutil.copyfileobj(response, stream)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != expected:
            raise ValueError("artifact checksum mismatch")
        os.chmod(path, 0o755)
        return path
    except Exception:
        path.unlink(missing_ok=True)
        raise


def install_artifact(manifest: dict[str, Any], *, version: str = "current") -> Path:
    if version != "current" and not re.fullmatch(r"\d+\.\d+\.\d+", version.lstrip("v")):
        raise ValueError("version must be a semantic vMAJOR.MINOR.PATCH value")
    target = Path(str(manifest["install_path"])).expanduser()
    release_dir = target.parent.parent / version.lstrip("v")
    release_dir.mkdir(parents=True, exist_ok=True)
    artifact = download(manifest)
    staged = release_dir / f".{target.name}.new"
    try:
        if zipfile.is_zipfile(artifact):
            with zipfile.ZipFile(artifact) as archive:
                for member in archive.infolist():
                    destination = (release_dir / member.filename).resolve()
                    if release_dir.resolve() not in destination.parents and destination != release_dir.resolve():
                        raise ValueError("artifact archive contains an unsafe path")
                archive.extractall(release_dir)
            executable = release_dir / "bin" / target.name
            if not executable.is_file():
                raise ValueError(f"artifact archive does not contain bin/{target.name}")
            executable.chmod(executable.stat().st_mode | 0o111)
            menubar = release_dir / "mytask-menubar"
            if menubar.is_file():
                menubar.chmod(menubar.stat().st_mode | 0o111)
            staged.write_text(
                f"#!/bin/sh\nexec {shlex.quote(str(executable))} \"$@\"\n",
                encoding="utf-8",
            )
            os.chmod(staged, 0o755)
        else:
            os.replace(artifact, staged)
            os.chmod(staged, 0o755)
        target.parent.mkdir(parents=True, exist_ok=True)
        previous = target.with_name(f".{target.name}.previous")
        if target.exists():
            os.replace(target, previous)
        os.replace(staged, target)
        return target
    finally:
        artifact.unlink(missing_ok=True)
        staged.unlink(missing_ok=True)


def run_hook(manifest: dict[str, Any], name: str) -> tuple[bool, str]:
    command = manifest.get(name, [])
    if not command:
        return True, ""
    if not isinstance(command, list) or not all(isinstance(item, str) for item in command):
        return False, f"{name} must be an argv list"
    return runtime.run_result(command, timeout=900)
