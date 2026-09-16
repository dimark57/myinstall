from __future__ import annotations

import secrets
import socket
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlsplit, urlunsplit

from . import secrets as secret_store
from .runtime import run, run_result


def identifier(value: str) -> str:
    if not value or not value.replace("_", "").replace("-", "").isalnum():
        raise ValueError("unsafe PostgreSQL identifier")
    return f'"{value}"'


def literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def config_values(manifest: dict[str, Any]) -> dict[str, str]:
    config = manifest.get("postgres")
    if not isinstance(config, dict):
        return {}
    return {
        "mode": str(config.get("mode", "")),
        "cluster": str(config.get("cluster") or config.get("cluster_name") or ""),
        "compose": str(
            config.get("infrastructure_compose_path")
            or config.get("admin_compose_path")
            or ""
        ),
        "service": str(config.get("service_name") or config.get("service") or "postgres"),
        "network": str(config.get("network_name") or ""),
        "admin_user": str(config.get("admin_user") or "postgres"),
        "admin_database": str(config.get("admin_database") or "postgres"),
        "role": str(config.get("app_role") or config.get("role") or ""),
        "database": str(config.get("app_database") or config.get("database") or ""),
        "role_key": str(config.get("role_password_key") or ""),
        "url_key": str(config.get("database_url_key") or "DATABASE_URL"),
        "admin_secret_path": str(config.get("admin_secret_path") or ""),
        "admin_password_key": str(config.get("admin_password_key") or ""),
        "host": str(config.get("host") or ""),
        "port": str(config.get("port") or "5432"),
        "data_path": str(config.get("data_path") or ""),
        "expected_major": str(config.get("postgres_major") or "16"),
    }


def validate_config(manifest: dict[str, Any]) -> list[str]:
    config = config_values(manifest)
    if not config:
        return []
    if config["mode"] not in {"shared", "private", "dedicated"}:
        return ["postgres.mode must be shared or dedicated"]
    if config["mode"] == "shared":
        required = {
            "cluster": "cluster name",
            "compose": "infrastructure compose path",
            "service": "service name",
            "network": "network name",
            "role": "app role",
            "database": "app database",
            "role_key": "role password key",
            "url_key": "database URL key",
            "host": "database host",
        }
        errors = [f"postgres.{key} is required ({label})" for key, label in required.items() if not config[key]]
        for key in ("role", "database"):
            if config[key] and not config[key].replace("_", "").replace("-", "").isalnum():
                errors.append(f"postgres.{key} is not a safe identifier")
        if config["role"] == config["admin_user"]:
            errors.append("application PostgreSQL role must differ from admin_user")
        if config["role_key"] == config["admin_password_key"] and config["admin_password_key"]:
            errors.append("application and infrastructure password keys must differ")
        if manifest.get("runtime") in {"docker", "mixed"} and config["host"] in {"localhost", "127.0.0.1", "::1"}:
            errors.append("Docker shared PostgreSQL host must not be loopback")
        return errors
    return []


def _compose(config: dict[str, str], args: list[str]) -> list[str]:
    command = ["docker", "compose", "-f", config["compose"]]
    if config["cluster"]:
        command.extend(["-p", config["cluster"]])
    return command + args


def _admin_env(config: dict[str, str], values: dict[str, str]) -> dict[str, str]:
    source = values
    if config["admin_secret_path"]:
        source = secret_store.read(Path(config["admin_secret_path"]))
    # The admin credential is read only from the infrastructure secret. It is
    # never copied into the application runtime secret.
    return {"PGPASSWORD": source.get(config["admin_password_key"], "")} if config["admin_password_key"] else {}


def cluster_exists(manifest: dict[str, Any]) -> bool:
    config = config_values(manifest)
    if not config.get("compose"):
        return False
    ok, output = run_result(_compose(config, ["ps", "-q", config["service"]]), timeout=60)
    return ok and bool(output.strip())


def wait_healthy(manifest: dict[str, Any], retries: int = 30, delay: float = 2.0) -> bool:
    config = config_values(manifest)
    container = _compose(config, ["ps", "-q", config["service"]])
    for attempt in range(max(1, retries)):
        ok, output = run_result(container, timeout=60)
        container_id = output.strip().splitlines()[-1] if ok and output.strip() else ""
        if container_id:
            healthy, state = run_result(
                ["docker", "inspect", "--format", "{{.State.Health.Status}}", container_id],
                timeout=30,
            )
            if healthy and state.strip() in {"healthy", "running"}:
                return True
        if attempt + 1 < retries:
            time.sleep(delay)
    return False


def tcp_ready(manifest: dict[str, Any], values: dict[str, str] | None = None) -> bool:
    config = config_values(manifest)
    ok, _ = run_result(
        _compose(
            config,
            [
                "exec",
                "-T",
                config["service"],
                "pg_isready",
                "-U",
                config["admin_user"],
                "-d",
                config["admin_database"],
            ],
        ),
        timeout=60,
        env=_admin_env(config, values or {}),
    )
    if ok:
        return True
    # Keep a direct TCP check for externally advertised shared endpoints.
    try:
        with socket.create_connection((config["host"], int(config["port"])), timeout=5):
            return True
    except (OSError, ValueError):
        return False


def _query(config: dict[str, str], sql: str, values: dict[str, str]) -> tuple[bool, str]:
    return run_result(
        _compose(
            config,
            [
                "exec",
                "-T",
                config["service"],
                "psql",
                "-Atq",
                "-v",
                "ON_ERROR_STOP=1",
                "-U",
                config["admin_user"],
                "-d",
                config["admin_database"],
                "-c",
                sql,
            ],
        ),
        timeout=60,
        env=_admin_env(config, values),
    )


def _app_secret(values: dict[str, str], config: dict[str, str]) -> tuple[str, str]:
    url = values.get(config["url_key"], "")
    password = values.get(config["role_key"], "") or (urlsplit(url).password if url else None) or ""
    return password, url


def ensure_shared(manifest: dict[str, Any], values: dict[str, str]) -> tuple[bool, dict[str, str], str]:
    config = config_values(manifest)
    errors = validate_config(manifest)
    if errors:
        return False, values, "; ".join(errors)
    if config["admin_secret_path"] and Path(config["admin_secret_path"]).resolve() == Path(
        str(manifest["secret_path"])
    ).resolve():
        return False, values, "infrastructure admin secret must not be the application secret"

    existed = cluster_exists(manifest)
    if not existed:
        if not run(_compose(config, ["up", "-d", config["service"]]), timeout=300):
            return False, values, "shared PostgreSQL cluster start failed"
    if not wait_healthy(manifest) or not tcp_ready(manifest, values):
        return False, values, "shared PostgreSQL is not ready"
    if config["network"]:
        network_ok, _ = run_result(["docker", "network", "inspect", config["network"]], timeout=30)
        if not network_ok:
            return False, values, "shared PostgreSQL network is missing"

    role_ok, role_output = _query(
        config, f"SELECT 1 FROM pg_roles WHERE rolname = {literal(config['role'])};", values
    )
    db_ok, db_output = _query(
        config, f"SELECT 1 FROM pg_database WHERE datname = {literal(config['database'])};", values
    )
    if not role_ok or not db_ok:
        return False, values, "shared PostgreSQL catalog check failed"
    role_exists = role_output.strip() == "1"
    database_exists = db_output.strip() == "1"
    password, old_url = _app_secret(values, config)
    updated = dict(values)
    if not role_exists:
        if not password:
            password = secrets.token_urlsafe(48)
        if not run(
            _compose(config, ["exec", "-T", config["service"], "psql", "-v", "ON_ERROR_STOP=1",
                              "-U", config["admin_user"], "-d", config["admin_database"], "-f", "-"]),
            input_text=(
                f"CREATE ROLE {identifier(config['role'])} LOGIN PASSWORD {literal(password)};"
            ),
            env=_admin_env(config, values),
            timeout=60,
        ):
            return False, values, "shared PostgreSQL role creation failed"
        updated[config["role_key"]] = password
    elif not password:
        return False, values, "existing PostgreSQL role has no application credential"

    if not database_exists:
        sql = f"CREATE DATABASE {identifier(config['database'])} OWNER {identifier(config['role'])};"
        if not run(
            _compose(config, ["exec", "-T", config["service"], "psql", "-v", "ON_ERROR_STOP=1",
                              "-U", config["admin_user"], "-d", config["admin_database"], "-f", "-"]),
            input_text=sql,
            env=_admin_env(config, values),
            timeout=60,
        ):
            return False, values, "shared PostgreSQL database creation failed"
    if not run(
        _compose(config, ["exec", "-T", config["service"], "psql", "-v", "ON_ERROR_STOP=1",
                          "-U", config["admin_user"], "-d", config["admin_database"], "-f", "-"]),
        input_text=f"ALTER DATABASE {identifier(config['database'])} OWNER TO {identifier(config['role'])};",
        env=_admin_env(config, values),
        timeout=60,
    ):
        return False, values, "shared PostgreSQL ownership check failed"
    if not password:
        password = _app_secret(updated, config)[0]
    if config["role_key"] not in updated:
        updated[config["role_key"]] = password
    if config["url_key"] not in updated:
        updated[config["url_key"]] = (
            f"postgresql://{quote(config['role'], safe='')}:{quote(password, safe='')}@"
            f"{config['host']}:{config['port']}/{quote(config['database'], safe='')}"
        )
    if not run(
        _compose(
            config,
            ["exec", "-T", config["service"], "psql", "-v", "ON_ERROR_STOP=1",
             "-U", config["role"], "-d", config["database"], "-c", "SELECT 1"],
        ),
        env={"PGPASSWORD": password},
        timeout=60,
    ):
        return False, values, "application PostgreSQL credentials failed"
    return True, updated, "shared PostgreSQL provisioned" if not existed else "shared PostgreSQL verified"


def doctor(manifest: dict[str, Any], values: dict[str, str]) -> list[dict[str, Any]]:
    config = config_values(manifest)
    if not config or config["mode"] not in {"shared", "dedicated", "private"}:
        return []
    checks: list[dict[str, Any]] = []

    def add(check_id: str, ok: bool, actual: Any = None, status: str | None = None) -> None:
        checks.append({"id": f"postgres.{check_id}", "status": status or ("pass" if ok else "fail"), "actual": actual})

    if config["mode"] != "shared":
        add("mode", True, config["mode"], "warn")
        return checks
    config_errors = validate_config(manifest)
    if config_errors:
        add("manifest", False, config_errors)
        return checks
    exists = cluster_exists(manifest)
    add("container", exists)
    container_ok, container_output = run_result(
        _compose(config, ["ps", "-q", config["service"]]), timeout=30
    ) if exists else (False, "")
    container_id = container_output.strip().splitlines()[-1] if container_ok and container_output.strip() else ""
    if exists:
        healthy = wait_healthy(manifest, retries=1)
        add("health", healthy)
        add("tcp", tcp_ready(manifest, values))
        image_ok, image = run_result(
            ["docker", "inspect", "--format", "{{.Config.Image}}", container_id], timeout=30
        ) if container_id else (False, "")
        add("image_major", image_ok and f"postgres:{config['expected_major']}" in image, {"major": config["expected_major"]})
    network_ok, _ = run_result(["docker", "network", "inspect", config["network"]], timeout=30)
    add("network", network_ok)
    role_ok, role_output = _query(
        config, f"SELECT 1 FROM pg_roles WHERE rolname = {literal(config['role'])};", values
    ) if exists else (False, "")
    db_ok, db_output = _query(
        config, f"SELECT 1 FROM pg_database WHERE datname = {literal(config['database'])};", values
    ) if exists else (False, "")
    add("database", db_ok and db_output.strip() == "1")
    add("role", role_ok and role_output.strip() == "1")
    admin_ok, admin_output = _query(
        config,
        f"SELECT rolsuper OR rolcreaterole OR rolcreatedb FROM pg_roles WHERE rolname = {literal(config['role'])};",
        values,
    ) if exists else (False, "")
    add("role_not_admin", admin_ok and admin_output.strip().lower() in {"f", "false", "0"})
    password, _ = _app_secret(values, config)
    credential_ok = bool(password and run(
        _compose(
            config,
            ["exec", "-T", config["service"], "psql", "-v", "ON_ERROR_STOP=1",
             "-U", config["role"], "-d", config["database"], "-c", "SELECT 1"],
        ),
        env={"PGPASSWORD": password},
        timeout=60,
    )) if exists else False
    add("credentials", credential_ok)
    data_path = config.get("data_path") or str(manifest.get("data_path", ""))
    if data_path:
        config["data_path"] = data_path
    if data_path:
        volume_ok, volume_output = run_result(
            ["docker", "inspect", "--format", "{{json .Mounts}}", container_id], timeout=30
        ) if container_id else (False, "")
        add("data_volume", volume_ok and data_path in volume_output, {"expected": data_path})
    else:
        add("data_volume", False, "postgres.data_path is not declared", "warn")
    duplicate_ok, duplicate_output = run_result(
        _compose(config, ["ps", "-q", config["service"]]), timeout=30
    )
    names = [line for line in duplicate_output.splitlines() if line.strip()]
    add("duplicate_cluster", duplicate_ok and len(names) <= 1, {"containers": len(names)})
    if data_path:
        volume_ok, volume_output = run_result(
            ["docker", "ps", "-a", "--filter", f"volume={data_path}", "--format", "{{.Names}}"],
            timeout=30,
        )
        volume_containers = [line for line in volume_output.splitlines() if line.strip()]
        add("duplicate_data_path", volume_ok and len(volume_containers) <= 1, {"containers": len(volume_containers)})
    else:
        add("duplicate_data_path", False, "postgres.data_path is not declared", "warn")
    add("app_compose_no_postgres", True, "checked by runtime adapter", "pass")
    return checks


def rotate(
    compose_file: str,
    manifest: dict[str, Any],
    values: dict[str, str],
) -> tuple[bool, dict[str, str], str]:
    config = manifest.get("postgres")
    if not isinstance(config, dict):
        return False, values, "postgres is not declared"
    normalized = config_values(manifest)
    url_key = normalized["url_key"]
    role = normalized["role"]
    old_url = values.get(url_key, "")
    parsed = urlsplit(old_url)
    old_password = parsed.password
    if not role or not old_url or not old_password:
        return False, values, "database URL or PostgreSQL role is missing"

    new_password = secrets.token_urlsafe(64)
    service = normalized["service"]
    admin_user = normalized["admin_user"]
    admin_database = normalized["admin_database"]
    admin_compose = str(normalized["compose"] or compose_file)
    compose_config = {**normalized, "compose": admin_compose}
    command = _compose(
        compose_config,
        ["exec", "-T", service, "psql", "-v", "ON_ERROR_STOP=1",
         "-U", admin_user, "-d", admin_database, "-f", "-"],
    )
    admin_values = values
    if normalized["admin_secret_path"]:
        admin_values = secret_store.read(Path(normalized["admin_secret_path"]))
        if not admin_values.get(normalized["admin_password_key"]):
            return False, values, "PostgreSQL admin secret is missing"
    env = {"PGPASSWORD": admin_values.get(normalized["admin_password_key"], "")}
    if not run(
        command,
        input_text=f"ALTER ROLE {identifier(role)} PASSWORD {literal(new_password)};",
        env=env,
    ):
        return False, values, "ALTER ROLE failed"

    check = _compose(
        compose_config,
        ["exec", "-T", service, "psql", "-v", "ON_ERROR_STOP=1",
         "-U", role, "-d", normalized["database"] or "postgres", "-c", "SELECT 1"],
    )
    if not run(check, timeout=60, env={"PGPASSWORD": new_password}):
        rollback = _compose(
            compose_config,
            ["exec", "-T", service, "psql", "-v", "ON_ERROR_STOP=1",
             "-U", admin_user, "-d", admin_database, "-f", "-"],
        )
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
    if not isinstance(config, dict) or config.get("mode") not in {"shared", "private", "dedicated"}:
        return True, values, "postgres not managed"
    if config.get("mode") == "shared":
        return ensure_shared(manifest, values)
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
    admin_values = values
    if config.get("admin_secret_path"):
        admin_values = secret_store.read(Path(str(config["admin_secret_path"])))
        if not admin_values.get(str(config.get("admin_password_key", ""))):
            return False, values, "PostgreSQL admin secret is missing"
    env = {"PGPASSWORD": admin_values.get(str(config.get("admin_password_key", "")), "")}
    command = ["docker", "compose", "-f", compose_path, "exec", "-T", service, "psql",
               "-v", "ON_ERROR_STOP=1", "-U", admin_user, "-d", admin_database, "-f", "-"]
    sql = (
        f"DO $$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = {literal(role)}) "
        f"THEN CREATE ROLE {identifier(role)} LOGIN PASSWORD {literal(password)}; "
        f"ELSE ALTER ROLE {identifier(role)} PASSWORD {literal(password)}; END IF; END $$;\n"
        f"SELECT 'CREATE DATABASE ' || quote_ident({literal(database)}) WHERE NOT EXISTS "
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
    normalized = config_values(manifest)
    url_key = normalized["url_key"]
    role = normalized["role"]
    parsed = urlsplit(values.get(url_key, ""))
    password = parsed.password
    if not role or not password:
        return False
    compose_config = {**normalized, "compose": normalized["compose"] or compose_file}
    command = _compose(
        compose_config,
        ["exec", "-T", normalized["service"], "psql", "-v", "ON_ERROR_STOP=1",
         "-U", normalized["admin_user"], "-d", normalized["admin_database"], "-f", "-"],
    )
    admin_values = values
    if normalized["admin_secret_path"]:
        admin_values = secret_store.read(Path(normalized["admin_secret_path"]))
    env = {"PGPASSWORD": admin_values.get(normalized["admin_password_key"], "")}
    return run(
        command,
        input_text=f"ALTER ROLE {identifier(role)} PASSWORD {literal(password)};",
        env=env,
    )
