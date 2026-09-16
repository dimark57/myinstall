from __future__ import annotations

import secrets
from typing import Any
from urllib.parse import quote, urlsplit, urlunsplit

from .runtime import run


def identifier(value: str) -> str:
    if not value or not value.replace("_", "").replace("-", "").isalnum():
        raise ValueError("unsafe PostgreSQL identifier")
    return f'"{value}"'


def literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def rotate(
    compose_file: str,
    manifest: dict[str, Any],
    values: dict[str, str],
) -> tuple[bool, dict[str, str], str]:
    config = manifest.get("postgres")
    if not isinstance(config, dict):
        return False, values, "postgres is not declared"
    url_key = str(config.get("database_url_key", "DATABASE_URL"))
    role = str(config.get("role", ""))
    old_url = values.get(url_key, "")
    parsed = urlsplit(old_url)
    old_password = parsed.password
    if not role or not old_url or not old_password:
        return False, values, "database URL or PostgreSQL role is missing"

    new_password = secrets.token_urlsafe(64)
    service = str(config.get("service", "postgres"))
    admin_user = str(config.get("admin_user", "postgres"))
    admin_database = str(config.get("admin_database", "postgres"))
    command = [
        "docker",
        "compose",
        "-f",
        compose_file,
        "exec",
        "-T",
        service,
        "psql",
        "-v",
        "ON_ERROR_STOP=1",
        "-U",
        admin_user,
        "-d",
        admin_database,
        "-f",
        "-",
    ]
    env = {"PGPASSWORD": values.get(str(config.get("admin_password_key", "")), "")}
    if not run(
        command,
        input_text=f"ALTER ROLE {identifier(role)} PASSWORD {literal(new_password)};",
        env=env,
    ):
        return False, values, "ALTER ROLE failed"

    check = [
        "docker",
        "compose",
        "-f",
        compose_file,
        "exec",
        "-T",
        service,
        "psql",
        "-v",
        "ON_ERROR_STOP=1",
        "-U",
        role,
        "-d",
        str(config.get("database", "postgres")),
        "-c",
        "SELECT 1",
    ]
    if not run(check, timeout=60, env={"PGPASSWORD": new_password}):
        rollback = [
            "docker",
            "compose",
            "-f",
            compose_file,
            "exec",
            "-T",
            service,
            "psql",
            "-v",
            "ON_ERROR_STOP=1",
            "-U",
            admin_user,
            "-d",
            admin_database,
            "-f",
            "-",
        ]
        run(
            rollback,
            input_text=f"ALTER ROLE {identifier(role)} PASSWORD {literal(old_password)};",
            env=env,
        )
        return False, values, "rotation_failed"

    updated = dict(values)
    updated[url_key] = urlunsplit(
        (
            parsed.scheme,
            f"{quote(parsed.username or '', safe='')}:{quote(new_password, safe='')}@"
            f"{parsed.hostname or ''}{f':{parsed.port}' if parsed.port else ''}",
            parsed.path,
            parsed.query,
            parsed.fragment,
        )
    )
    return True, updated, "postgres credential verified"
