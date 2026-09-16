from __future__ import annotations

import getpass
import os
import sys
from pathlib import Path

from . import github, secrets


AUTH_SECRET_PATH = Path("/srv/nas/secrets/myinstall.env")
AUTH_KEYS = ("MYINSTALL_GITHUB_TOKEN", "MYINSTALL_GITHUB_USER")


def load() -> None:
    """Load only myinstall credentials; never override explicit environment."""
    values = secrets.read(AUTH_SECRET_PATH)
    for key in AUTH_KEYS:
        if values.get(key):
            os.environ.setdefault(key, values[key])


def setup() -> int:
    """Interactively validate and persist a GitHub read-only token."""
    if not os.isatty(0):
        print("auth setup requires an interactive terminal", file=sys.stderr)
        return 2
    token = getpass.getpass("GitHub PAT (input hidden): ").strip()
    if not token:
        print("GitHub PAT cannot be empty", file=os.sys.stderr)
        return 2
    login = github.validate_token(token)
    if not login:
        print("GitHub token validation failed", file=os.sys.stderr)
        return 1
    os.environ["MYINSTALL_GITHUB_TOKEN"] = token
    os.environ["MYINSTALL_GITHUB_USER"] = login
    secrets.write(
        AUTH_SECRET_PATH,
        {
            "MYINSTALL_GITHUB_TOKEN": token,
            "MYINSTALL_GITHUB_USER": login,
        },
    )
    print(f"GitHub credentials saved to {AUTH_SECRET_PATH} (mode 0600)")
    return 0
