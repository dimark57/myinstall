from __future__ import annotations

import getpass
import os
import sys

from . import github, paths, secrets


AUTH_SECRET_PATH = paths.nas_root() / "secrets" / "myinstall.env"
AUTH_KEYS = (
    "MYINSTALL_GITHUB_TOKEN",
    "MYINSTALL_GITHUB_USER",
    "MYINSTALL_GHCR_TOKEN",
    "MYINSTALL_GHCR_USER",
)
TOKEN_SETUP_HINT = (
    "Получите два токена: Fine-grained token с Contents: Read-only для private-репозиториев "
    "и Classic PAT с read:packages для GHCR на "
    "https://github.com/settings/personal-access-tokens, затем выполните: "
    "sudo myinstall auth setup"
)


def load() -> None:
    """Load only myinstall credentials; never override explicit environment."""
    values = secrets.read(AUTH_SECRET_PATH)
    for key in AUTH_KEYS:
        if values.get(key):
            os.environ.setdefault(key, values[key])


def setup() -> int:
    """Interactively validate and persist GitHub API and GHCR tokens."""
    if not os.isatty(0):
        print("auth setup requires an interactive terminal", file=sys.stderr)
        return 2

    github_token = getpass.getpass(
        "GitHub source/release token (Fine-grained, input hidden): "
    ).strip()
    if not github_token:
        print("GitHub source/release token cannot be empty", file=sys.stderr)
        return 2
    github_user = github.validate_token(github_token)
    if not github_user:
        print(f"GitHub source token validation failed. {TOKEN_SETUP_HINT}", file=sys.stderr)
        return 1

    ghcr_token = getpass.getpass(
        "GHCR token (Classic PAT read:packages, input hidden): "
    ).strip()
    if not ghcr_token:
        print("GHCR token cannot be empty", file=sys.stderr)
        return 2
    ghcr_user = github.validate_token(ghcr_token)
    if not ghcr_user:
        print(f"GHCR token validation failed. {TOKEN_SETUP_HINT}", file=sys.stderr)
        return 1

    os.environ["MYINSTALL_GITHUB_TOKEN"] = github_token
    os.environ["MYINSTALL_GITHUB_USER"] = github_user
    os.environ["MYINSTALL_GHCR_TOKEN"] = ghcr_token
    os.environ["MYINSTALL_GHCR_USER"] = ghcr_user
    secrets.write(
        AUTH_SECRET_PATH,
        {
            "MYINSTALL_GITHUB_TOKEN": github_token,
            "MYINSTALL_GITHUB_USER": github_user,
            "MYINSTALL_GHCR_TOKEN": ghcr_token,
            "MYINSTALL_GHCR_USER": ghcr_user,
        },
    )
    print(f"GitHub and GHCR credentials saved to {AUTH_SECRET_PATH} (mode 0600)")
    return 0


def status() -> tuple[dict[str, str], int]:
    """Check both configured tokens without exposing their values."""
    github_token = os.environ.get("MYINSTALL_GITHUB_TOKEN")
    ghcr_token = os.environ.get("MYINSTALL_GHCR_TOKEN")
    if not github_token or not ghcr_token:
        return (
            {
                "state": "missing",
                "github_token": "configured" if github_token else "missing",
                "ghcr_token": "configured" if ghcr_token else "missing",
                "hint": TOKEN_SETUP_HINT,
            },
            1,
        )
    github_valid = github.validate_token(github_token)
    ghcr_valid = github.validate_token(ghcr_token)
    if not github_valid or not ghcr_valid:
        return (
            {
                "state": "expired_or_invalid",
                "github_token": "valid" if github_valid else "expired_or_invalid",
                "ghcr_token": "valid" if ghcr_valid else "expired_or_invalid",
                "hint": TOKEN_SETUP_HINT,
            },
            1,
        )
    return {
        "state": "valid",
        "github_user": github_valid,
        "ghcr_user": ghcr_valid,
        "github_token": "valid",
        "ghcr_token": "valid",
    }, 0
