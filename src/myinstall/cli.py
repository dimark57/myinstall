from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any

from . import manifest, postgres, runtime, secrets


def output(value: dict[str, Any], code: int = 0) -> int:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))
    return code


def report(manifest_path: Path, data: dict[str, Any]) -> dict[str, Any]:
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
            "status": "pass" if compose.is_file() else "warn",
            "actual": str(compose),
        },
    ]
    return {
        "schema_version": "1.0",
        "app": data["app"],
        "manifest": str(manifest_path),
        "summary": {status: sum(item["status"] == status for item in checks) for status in ("pass", "warn", "fail")},
        "checks": checks,
    }


def do_install(path: Path, data: dict[str, Any]) -> int:
    stack = Path(data["stack_path"])
    with runtime.lock(stack):
        Path(data["data_path"]).mkdir(parents=True, exist_ok=True)
        created = secrets.ensure(data)
        compose = runtime.materialize(path, data)
        if not runtime.compose(compose, ["config"], timeout=60):
            return output({"ok": False, "error": "docker compose config failed"}, 1)
        if not runtime.compose(compose, ["pull"], timeout=600):
            return output({"ok": False, "error": "image pull failed"}, 1)
        if not runtime.compose(compose, ["up", "-d"], timeout=300):
            return output({"ok": False, "error": "stack start failed"}, 1)
        healthy = runtime.health(data)
        result = {"mode": "install", "secret_keys_created": created, "health": healthy}
        return output(result, 0 if healthy else 1)


def do_upgrade(path: Path, data: dict[str, Any], image: str) -> int:
    if image.endswith(":latest") or (":" not in image and "@" not in image):
        return output({"ok": False, "error": "immutable image required"}, 1)
    stack = Path(data["stack_path"])
    with runtime.lock(stack):
        compose = runtime.materialize(path, data)
        before = compose.read_text(encoding="utf-8")
        compose.write_text(before.replace(str(data["image"]), image), encoding="utf-8")
        if not runtime.compose(compose, ["pull"], timeout=600) or not runtime.compose(
            compose, ["up", "-d"], timeout=300
        ):
            compose.write_text(before, encoding="utf-8")
            return output({"ok": False, "error": "upgrade failed; previous compose restored"}, 1)
        healthy = runtime.health(data)
        if not healthy:
            compose.write_text(before, encoding="utf-8")
            runtime.compose(compose, ["up", "-d"], timeout=300)
            return output({"ok": False, "error": "healthcheck failed; previous compose restored"}, 1)
        return output({"mode": "upgrade", "image": image, "secrets_changed": False}, 0)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="myinstall")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("plan", "doctor", "check", "install", "upgrade"):
        command = sub.add_parser(name)
        command.add_argument("--manifest", required=True, type=Path)
        if name in {"install", "upgrade"}:
            command.add_argument("--confirm", action="store_true")
        if name == "upgrade":
            command.add_argument("--image", required=True)
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
            return do_upgrade(path, data, args.image)
        if args.action == "status":
            return output({"mode": "secret status", **secrets.status(data)})
        if args.action == "ensure":
            with runtime.lock(Path(data["stack_path"])):
                return output({"mode": "secret ensure", "created": secrets.ensure(data)})
        if not args.confirm or not args.name:
            return output({"ok": False, "error": "secret mutation requires --name --confirm"}, 1)
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
                return output({"ok": False, "state": "rotation_failed"}, 1)
            return output({"mode": "secret rotate", "state": "completed"})
    except (OSError, ValueError) as exc:
        return output({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, 1)


if __name__ == "__main__":
    raise SystemExit(main())
