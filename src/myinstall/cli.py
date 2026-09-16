from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any

from . import manifest, native, postgres, runtime, secrets, service


def output(value: dict[str, Any], code: int = 0) -> int:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))
    return code


def report(manifest_path: Path, data: dict[str, Any]) -> dict[str, Any]:
    runtime_kind = str(data.get("runtime", "native"))
    stack = Path(data["stack_path"])
    data_path = Path(data["data_path"])
    secret = Path(data["secret_path"])
    compose = manifest.compose_source(manifest_path, data)
    values = secrets.read(secret)
    missing = [key for key in data["required_secrets"] if key not in values]
    checks = [
        {
            "id": "manifest.paths",
            "status": "pass" if not manifest.validate_paths(data) else "fail",
            "actual": manifest.validate_paths(data),
        },
        {
            "id": "runtime.stack",
            "status": "pass" if stack.is_dir() else "warn",
            "actual": stack.exists(),
        },
        {
            "id": "runtime.data",
            "status": "pass" if data_path.is_dir() else "warn",
            "actual": data_path.exists(),
        },
        {
            "id": "secrets.required",
            "status": "pass" if not missing else "fail",
            "actual": missing,
        },
        {
            "id": "secrets.permissions",
            "status": (
                "pass"
                if secret.exists() and oct(secret.stat().st_mode & 0o777) in {"0o600", "0o640"}
                else "warn"
            ),
            "actual": {
                "exists": secret.exists(),
                "mode": oct(secret.stat().st_mode & 0o777) if secret.exists() else None,
            },
        },
        {
            "id": "runtime.compose",
            "status": (
                "pass"
                if runtime_kind in {"docker", "mixed"} and compose.is_file()
                else "warn"
                if runtime_kind in {"docker", "mixed"}
                else "not_applicable"
            ),
            "actual": {"runtime": runtime_kind, "compose": str(compose)},
        },
    ]
    return {
        "schema_version": "1.0",
        "app": data["app"],
        "manifest": str(manifest_path),
        "summary": {status: sum(item["status"] == status for item in checks) for status in ("pass", "warn", "fail")},
        "checks": checks,
        "runtime": runtime_kind,
    }


def do_install(path: Path, data: dict[str, Any]) -> int:
    errors = manifest.validate_paths(data)
    if errors:
        return output({"ok": False, "error": "invalid manifest paths", "details": errors}, 1)
    stack = Path(data["stack_path"])
    with runtime.lock(stack):
        Path(data["data_path"]).mkdir(parents=True, exist_ok=True)
        created = secrets.ensure(data)
        values = secrets.read(Path(data["secret_path"]))
        provisioned, values, postgres_state = postgres.provision(data, values)
        if not provisioned:
            return output({"ok": False, "error": postgres_state}, 1)
        if values:
            secrets.write(Path(data["secret_path"]), values)
        missing = secrets.validate_required(data)
        if missing:
            return output({"ok": False, "error": "required secrets missing", "keys": missing}, 1)
        runtime_kind = str(data.get("runtime", "native"))
        if runtime_kind in {"native", "systemd", "launchd"}:
            installed = native.install_artifact(data)
            if runtime_kind in {"systemd", "launchd"}:
                ok, diagnostic = service.install_unit(data)
                if not ok:
                    return output({"ok": False, "error": "service install failed", "diagnostic": diagnostic}, 1)
                ok, diagnostic = service.action(data, "restart")
                if not ok:
                    return output({"ok": False, "error": "service start failed", "diagnostic": diagnostic}, 1)
            ok, diagnostic = native.run_hook(data, "install_command")
            if not ok:
                return output({"ok": False, "error": "native install hook failed", "diagnostic": diagnostic}, 1)
            ok, diagnostic = native.run_hook(data, "migration_command")
            if not ok:
                return output({"ok": False, "error": "migration failed", "diagnostic": diagnostic}, 1)
            return output({"mode": "install", "runtime": runtime_kind, "path": str(installed), "secret_keys_created": created})
        if runtime_kind == "none":
            return output({"mode": "install", "runtime": "none", "secret_keys_created": created})
        if runtime_kind not in {"docker", "mixed"}:
            return output(
                {"ok": False, "error": "manifest must declare runtime=native|systemd|launchd|docker|mixed|none"},
                1,
            )
        compose = runtime.materialize(path, data)
        compose_errors = runtime.validate_compose(compose, data)
        if compose_errors:
            return output({"ok": False, "error": "invalid Compose contract", "details": compose_errors}, 1)
        if not runtime.compose(compose, ["config"], timeout=60):
            return output({"ok": False, "error": "docker compose config failed"}, 1)
        if not runtime.compose(compose, ["pull"], timeout=600):
            return output({"ok": False, "error": "image pull failed"}, 1)
        if not runtime.compose(compose, ["up", "-d"], timeout=300):
            return output({"ok": False, "error": "stack start failed"}, 1)
        ok, diagnostic = native.run_hook(data, "migration_command")
        if not ok:
            return output({"ok": False, "error": "migration failed", "diagnostic": diagnostic}, 1)
        healthy = runtime.health(data)
        result = {"mode": "install", "secret_keys_created": created, "health": healthy}
        return output(result, 0 if healthy else 1)


def do_upgrade(path: Path, data: dict[str, Any], image: str | None, version: str | None) -> int:
    runtime_kind = str(data.get("runtime", "native"))
    if runtime_kind in {"native", "systemd", "launchd"}:
        errors = manifest.validate_paths(data)
        if errors:
            return output({"ok": False, "error": "invalid manifest paths", "details": errors}, 1)
        with runtime.lock(Path(data["stack_path"])):
            previous = Path(str(data["install_path"])).read_bytes()
            installed = native.install_artifact(data, version=(version or "current").lstrip("v"))
            if runtime_kind in {"systemd", "launchd"}:
                ok, diagnostic = service.action(data, "restart")
                if not ok:
                    return output({"ok": False, "error": "service restart failed", "diagnostic": diagnostic}, 1)
            if not runtime.health(data):
                Path(installed).write_bytes(previous)
                if runtime_kind in {"systemd", "launchd"}:
                    service.action(data, "restart")
                return output({"ok": False, "error": "healthcheck failed; previous artifact restored"}, 1)
            ok, diagnostic = native.run_hook(data, "upgrade_command")
            if not ok:
                return output({"ok": False, "error": "native upgrade hook failed", "diagnostic": diagnostic}, 1)
            return output({"mode": "upgrade", "runtime": runtime_kind, "version": version or "current"})
    if runtime_kind not in {"docker", "mixed"}:
        return output({"ok": False, "error": "runtime does not support upgrade"}, 1)
    if not image or not manifest.immutable_image(image) or image.endswith(":latest"):
        return output({"ok": False, "error": "Docker upgrade requires an immutable vX.Y.Z tag or digest"}, 1)
    stack = Path(data["stack_path"])
    with runtime.lock(stack):
        compose = runtime.materialize(path, data)
        before = compose.read_text(encoding="utf-8")
        backup = stack / ".myinstall.previous-compose"
        backup.write_text(before, encoding="utf-8")
        compose.write_text(before.replace(str(data["image"]), image), encoding="utf-8")
        compose_errors = runtime.validate_compose(compose, {**data, "image": image})
        if compose_errors:
            compose.write_text(before, encoding="utf-8")
            return output({"ok": False, "error": "invalid Compose contract", "details": compose_errors}, 1)
        if not runtime.compose(compose, ["pull"], timeout=600) or not runtime.compose(
            compose, ["up", "-d"], timeout=300
        ):
            compose.write_text(before, encoding="utf-8")
            return output({"ok": False, "error": "upgrade failed; previous compose restored"}, 1)
        ok, diagnostic = native.run_hook(data, "migration_command")
        if not ok:
            compose.write_text(before, encoding="utf-8")
            runtime.compose(compose, ["up", "-d"], timeout=300)
            return output({"ok": False, "error": "migration failed; previous compose restored", "diagnostic": diagnostic}, 1)
        healthy = runtime.health(data)
        if not healthy:
            compose.write_text(before, encoding="utf-8")
            runtime.compose(compose, ["up", "-d"], timeout=300)
            return output({"ok": False, "error": "healthcheck failed; previous compose restored"}, 1)
        return output({"mode": "upgrade", "image": image, "secrets_changed": False}, 0)


def do_rollback(data: dict[str, Any]) -> int:
    runtime_kind = str(data.get("runtime", "native"))
    if runtime_kind in {"native", "systemd", "launchd"}:
        target = Path(str(data["install_path"]))
        previous = target.with_name(f".{target.name}.previous")
        if not previous.is_file():
            return output({"ok": False, "error": "no previous native release"}, 1)
        target.unlink(missing_ok=True)
        previous.rename(target)
        if runtime_kind in {"systemd", "launchd"}:
            ok, diagnostic = service.action(data, "restart")
            if not ok:
                return output({"ok": False, "error": "rollback restart failed", "diagnostic": diagnostic}, 1)
        return output({"mode": "rollback", "runtime": runtime_kind, "health": runtime.health(data)})
    if runtime_kind in {"docker", "mixed"}:
        stack = Path(data["stack_path"])
        compose = stack / "docker-compose.yml"
        backup = stack / ".myinstall.previous-compose"
        if not backup.is_file() or not compose.is_file():
            return output({"ok": False, "error": "no previous Docker release"}, 1)
        current = compose.read_text(encoding="utf-8")
        compose.write_text(backup.read_text(encoding="utf-8"), encoding="utf-8")
        if not runtime.compose(compose, ["up", "-d"], timeout=300) or not runtime.health(data):
            compose.write_text(current, encoding="utf-8")
            return output({"ok": False, "error": "Docker rollback failed"}, 1)
        return output({"mode": "rollback", "runtime": runtime_kind, "health": True})
    return output({"ok": False, "error": "runtime does not support rollback"}, 1)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="myinstall")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("plan", "doctor", "check", "install", "upgrade", "rollback"):
        command = sub.add_parser(name)
        command.add_argument("--manifest", required=True, type=Path)
        if name in {"install", "upgrade", "rollback"}:
            command.add_argument("--confirm", action="store_true")
        if name == "upgrade":
            command.add_argument("--image")
            command.add_argument("--version")
    secret = sub.add_parser("secret")
    secret.add_argument("action", choices=("ensure", "status", "rotate", "remove"))
    secret.add_argument("--manifest", required=True, type=Path)
    secret.add_argument("--name")
    secret.add_argument("--confirm", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        path = args.manifest.expanduser().resolve()
        data = manifest.load(path)
        if (
            args.command in {"install", "upgrade", "rollback"}
            or args.command == "secret" and args.action != "status"
        ):
            errors = manifest.validate_paths(data)
            if errors:
                return output({"ok": False, "error": "invalid manifest paths", "details": errors}, 1)
        if args.command == "plan":
            return output({"mode": "plan", "will_write": False, **report(path, data)})
        if args.command in {"doctor", "check"}:
            result = report(path, data)
            return output({"mode": args.command, **result}, 1 if result["summary"]["fail"] else 0)
        if args.command == "install":
            if not args.confirm:
                return output({"ok": False, "error": "install requires --confirm"}, 1)
            return do_install(path, data)
        if args.command == "upgrade":
            if not args.confirm:
                return output({"ok": False, "error": "upgrade requires --confirm"}, 1)
            return do_upgrade(path, data, args.image, args.version)
        if args.command == "rollback":
            if not args.confirm:
                return output({"ok": False, "error": "rollback requires --confirm"}, 1)
            return do_rollback(data)
        if args.action == "status":
            return output({"mode": "secret status", **secrets.status(data)})
        if args.action == "ensure":
            with runtime.lock(Path(data["stack_path"])):
                return output({"mode": "secret ensure", "created": secrets.ensure(data)})
        if not args.confirm or not args.name:
            return output({"ok": False, "error": "secret mutation requires --name --confirm"}, 1)
        if args.action == "rotate":
            postgres_config = data.get("postgres") or {}
            allowed_name = str(postgres_config.get("database_url_key", "DATABASE_URL"))
            if args.name not in {"database", allowed_name}:
                return output({"ok": False, "error": "only the database credential can be rotated"}, 1)
        if args.action == "remove":
            if args.name in data["required_secrets"]:
                return output({"ok": False, "error": "cannot remove required secret"}, 1)
            with runtime.lock(Path(data["stack_path"])):
                values = secrets.read(Path(data["secret_path"]))
                values.pop(args.name, None)
                secrets.write(Path(data["secret_path"]), values)
                return output({"mode": "secret remove", "name": args.name})
        values = secrets.read(Path(data["secret_path"]))
        with runtime.lock(Path(data["stack_path"])):
            compose = runtime.materialize(path, data)
            ok, updated, state = postgres.rotate(str(compose), data, values)
            if not ok:
                return output({"ok": False, "state": state}, 1)
            secrets.write(Path(data["secret_path"]), updated)
            if not runtime.compose(compose, ["up", "-d"], timeout=300) or not runtime.health(data):
                secrets.write(Path(data["secret_path"]), values)
                restored = postgres.restore_password(str(compose), data, values)
                return output(
                    {
                        "ok": False,
                        "state": "rotation_failed" if restored else "rotation_rollback_failed",
                    },
                    1,
                )
            return output({"mode": "secret rotate", "state": "completed"})
    except (OSError, ValueError) as exc:
        return output({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, 1)


if __name__ == "__main__":
    raise SystemExit(main())
