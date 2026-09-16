from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Release:
    tag: str
    prerelease: bool
    assets: tuple[dict[str, Any], ...]
    etag: str | None = None


def repository(source: str) -> str:
    value = source.removeprefix("https://github.com/").removesuffix("/")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", value):
        raise ValueError("release_source must be a GitHub owner/repository")
    return value


def validate_token(token: str) -> str | None:
    """Validate a token without printing it and return the GitHub login."""
    previous = os.environ.get("MYINSTALL_GITHUB_TOKEN")
    os.environ["MYINSTALL_GITHUB_TOKEN"] = token
    try:
        status, body, _ = _request("https://api.github.com/user")
    except ValueError:
        return None
    finally:
        if previous is None:
            os.environ.pop("MYINSTALL_GITHUB_TOKEN", None)
        else:
            os.environ["MYINSTALL_GITHUB_TOKEN"] = previous
    if status != 200:
        return None
    try:
        login = json.loads(body).get("login")
    except (TypeError, json.JSONDecodeError):
        return None
    return str(login) if login else None


def _request(url: str, *, etag: str | None = None) -> tuple[int, bytes, str | None]:
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "myinstall"}
    token = os.environ.get("MYINSTALL_GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if etag:
        headers["If-None-Match"] = etag
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, response.read(), response.headers.get("ETag")
    except urllib.error.HTTPError as exc:
        if exc.code == 304:
            return 304, b"", etag
        if exc.code == 403:
            raise ValueError("GitHub API rate limit or authorization failure") from exc
        raise ValueError(f"GitHub request failed with HTTP {exc.code}") from exc
    except (OSError, urllib.error.URLError) as exc:
        raise ValueError("GitHub request failed") from exc


def latest(source: str, *, channel: str = "stable", etag: str | None = None) -> Release | None:
    endpoint = f"https://api.github.com/repos/{repository(source)}/releases/latest"
    if channel == "prerelease":
        endpoint = f"https://api.github.com/repos/{repository(source)}/releases?per_page=20"
    status, body, response_etag = _request(endpoint, etag=etag)
    if status == 304:
        return None
    payload = json.loads(body)
    if channel == "prerelease":
        payload = next((item for item in payload if item.get("prerelease")), None)
        if payload is None:
            raise ValueError("repository has no prerelease")
    elif payload.get("prerelease"):
        raise ValueError("latest GitHub release is prerelease")
    return Release(
        tag=str(payload["tag_name"]),
        prerelease=bool(payload.get("prerelease", False)),
        assets=tuple(payload.get("assets", [])),
        etag=response_etag,
    )


def by_tag(source: str, tag: str) -> Release:
    status, body, response_etag = _request(
        f"https://api.github.com/repos/{repository(source)}/releases/tags/{tag.lstrip('v')}"
    )
    if status == 304:
        raise ValueError("release lookup unexpectedly returned 304")
    payload = json.loads(body)
    if payload.get("prerelease"):
        raise ValueError("requested release is prerelease")
    return Release(
        tag=str(payload["tag_name"]),
        prerelease=bool(payload.get("prerelease", False)),
        assets=tuple(payload.get("assets", [])),
        etag=response_etag,
    )


def platform_name() -> str:
    system = platform.system().lower()
    machine = platform.machine().lower()
    arch = {"x86_64": "amd64", "amd64": "amd64", "aarch64": "arm64", "arm64": "arm64"}.get(machine, machine)
    return f"{'darwin' if system == 'darwin' else system}-{arch}"


def asset(release: Release, pattern: str | None = None) -> dict[str, Any]:
    names = {str(item.get("name")): item for item in release.assets}
    target_platform = platform_name()
    if pattern:
        expected = pattern.format(version=release.tag, platform=target_platform)
        if expected in names:
            return names[expected]
    candidates = [item for item in release.assets if target_platform in str(item.get("name", ""))]
    if len(candidates) == 1:
        return candidates[0]
    raise ValueError(f"GitHub release has no unique asset for {target_platform}")


def asset_sha256(release: Release, selected: dict[str, Any]) -> str:
    digest = str(selected.get("digest", ""))
    if digest.startswith("sha256:"):
        return digest.removeprefix("sha256:")
    checksums = next(
        (item for item in release.assets if str(item.get("name", "")).lower() in {"sha256sums", "sha256sums.txt"}),
        None,
    )
    if not checksums:
        raise ValueError("release has no SHA256SUMS asset")
    _, body, _ = _request(str(checksums["browser_download_url"]))
    selected_name = str(selected["name"])
    for line in body.decode("utf-8").splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[-1].lstrip("*") == selected_name:
            checksum = parts[0].lower()
            if re.fullmatch(r"[a-f0-9]{64}", checksum):
                return checksum
    raise ValueError("SHA256SUMS has no checksum for selected asset")


def verify_bytes(data: bytes, expected: str) -> bool:
    return hashlib.sha256(data).hexdigest() == expected.lower()
