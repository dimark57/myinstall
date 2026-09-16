from __future__ import annotations

import json
import os
import urllib.request
from typing import Any

from .paths import localize_manifest_paths


DEFAULT_CATALOG_URL = (
    "https://raw.githubusercontent.com/dimark57/myinstall/main/catalog/apps.json"
)


def fetch(app_id: str) -> dict[str, Any] | None:
    """Fetch a public catalog entry; catalog data must contain no secrets."""
    url = os.environ.get("MYINSTALL_CATALOG_URL", DEFAULT_CATALOG_URL)
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": "myinstall"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read())
    apps = payload.get("apps") if isinstance(payload, dict) else None
    entry = apps.get(app_id) if isinstance(apps, dict) else None
    if not isinstance(entry, dict):
        return None
    if str(entry.get("app", "")) != app_id:
        raise ValueError(f"catalog app id mismatch: {app_id}")
    return localize_manifest_paths(entry)
