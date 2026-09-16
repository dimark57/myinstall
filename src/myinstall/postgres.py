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
    admin_compose = str(config.get("admin_compose_path") or compose_file)
    command = [
        "docker",
        "compose",
        "-f",
        admin_compose,
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
        admin_compose,
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
            admin_compose,
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
        rolled_back = run(
            rollback,
            input_text=f"ALTER ROLE {identifier(role)} PASSWORD {literal(old_password)};",
            env=env,
        )
        return False, values, "rotation_failed" if rolled_back else "rotation_rollback_failed"

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


def provision(
    manifest: dict[str, Any],
    values: dict[str, str],
) -> tuple[bool, dict[str, str], str]:
    config = manifest.get("postgres")
    if not isinstance(config, dict) or config.get("mode") not in {"shared", "private"}:
        return True, values, "postgres not managed"
    compose_path = str(config.get("admin_compose_path") or manifest.get("compose_source", ""))
    service = str(config.get("service", "postgres"))
    role = str(config.get("role", ""))
    database = str(config.get("database", ""))
    role_key = str(config.get("role_password_key", "DATABASE_PASSWORD"))
    url_key = str(config.get("database_url_key", "DATABASE_URL"))
    if not role or not database or not compose_path:
        return False, values, "postgres requires role, database, and admin compose path"
    url_password = urlsplit(values.get(url_key, "")).password
    password = values.get(role_key) or url_password or secrets.token_urlsafe(48)
    admin_user = str(config.get("admin_user", "postgres"))
    admin_database = str(config.get("admin_database", "postgres"))
    env = {"PGPASSWORD": values.get(str(config.get("admin_password_key", "")), "")}
    command = ["docker", "compose", "-f", compose_path, "exec", "-T", service, "psql",
               "-v", "ON_ERROR_STOP=1", "-U", admin_user, "-d", admin_database, "-f", "-"]
    sql = (
        f"DO $$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = {literal(role)}) "
        f"THEN CREATE ROLE {identifier(role)} LOGIN PASSWORD {literal(password)}; "
        f"ELSE ALTER ROLE {identifier(role)} PASSWORD {literal(password)}; END IF; END $$;\n"
        f"SELECT 'CREATE DATABASE {database}' WHERE NOT EXISTS "
        f"(SELECT FROM pg_database WHERE datname = {literal(database)})\\gexec\n"
        f"GRANT ALL PRIVILEGES ON DATABASE {identifier(database)} TO {identifier(role)};"
    )
    if not run(command, input_text=sql, env=env, timeout=180):
        return False, values, "postgres provisioning failed"
    updated = dict(values)
    updated[role_key] = password
    host = str(config.get("host", "127.0.0.1"))
    port = str(config.get("port", "5432"))
    updated[url_key] = (
        f"postgresql://{quote(role, safe='')}:{quote(password, safe='')}@"
        f"{host}:{port}/{quote(database, safe='')}"
    )
    return True, updated, "postgres provisioned"


def restore_password(
    compose_file: str,
    manifest: dict[str, Any],
    values: dict[str, str],
) -> bool:
    config = manifest.get("postgres")
    if not isinstance(config, dict):
        return True
    url_key = str(config.get("database_url_key", "DATABASE_URL"))
    role = str(config.get("role", ""))
    parsed = urlsplit(values.get(url_key, ""))
    password = parsed.password
    if not role or not password:
        return False
    command = [
        "docker", "compose", "-f", compose_file, "exec", "-T",
        str(config.get("service", "postgres")), "psql", "-v", "ON_ERROR_STOP=1",
        "-U", str(config.get("admin_user", "postgres")),
        "-d", str(config.get("admin_database", "postgres")), "-f", "-",
    ]
    env = {"PGPASSWORD": values.get(str(config.get("admin_password_key", "")), "")}
    return run(
        command,
        input_text=f"ALTER ROLE {identifier(role)} PASSWORD {literal(password)};",
        env=env,
    )
