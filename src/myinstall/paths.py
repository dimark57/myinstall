from __future__ import annotations

import platform
import re
from pathlib import Path
from typing import Any


APP_NAME = re.compile(r"^[a-zA-Z][a-zA-Z0-9_-]*$")


def nas_root() -> Path:
    """Return the canonical NAS root for the current host."""
    if platform.system().lower() == "darwin":
        return Path.home() / "nas"
    return Path("/srv/nas")


def stack_root() -> Path:
    return nas_root() / "stacks" / "utilites"


def app_stack(app: str) -> Path:
    if not APP_NAME.fullmatch(app):
        raise ValueError(f"unsafe application name: {app}")
    return stack_root() / app


def app_data(app: str) -> Path:
    if not APP_NAME.fullmatch(app):
        raise ValueError(f"unsafe application name: {app}")
    return nas_root() / "data" / app


def app_secret(app: str) -> Path:
    if not APP_NAME.fullmatch(app):
        raise ValueError(f"unsafe application name: {app}")
    return nas_root() / "secrets" / f"{app}.env"


def localize_manifest_paths(entry: dict[str, Any]) -> dict[str, Any]:
    """Create a new-machine manifest under the canonical per-app layout."""
    localized = dict(entry)
    app = str(localized.get("app", ""))
    stack = app_stack(app)
    data = app_data(app)
    secret = app_secret(app)
    runtime = str(localized.get("runtime", "native"))

    localized["stack_path"] = str(stack)
    localized["data_path"] = str(data)
    localized["secret_path"] = str(secret)
    if runtime in {"native", "systemd", "launchd"}:
        localized["install_path"] = str(stack / "releases" / "current" / app)

    postgres = localized.get("postgres")
    if isinstance(postgres, dict):
        postgres = dict(postgres)
        for key in ("infrastructure_compose_path", "admin_compose_path"):
            value = postgres.get(key)
            if isinstance(value, str) and value.startswith("/srv/nas/"):
                postgres[key] = str(nas_root() / value.removeprefix("/srv/nas/"))
        if postgres.get("admin_secret_path"):
            postgres["admin_secret_path"] = str(
                nas_root() / "secrets" / "infrastructure-postgres.env"
            )
        localized["postgres"] = postgres
    return localized
