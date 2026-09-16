from __future__ import annotations

import plistlib
import os
import pwd
import shutil
import tempfile
from pathlib import Path
from typing import Any

from . import runtime


def _name(manifest: dict[str, Any]) -> str:
    name = str(manifest.get("service_name", manifest["app"]))
    if not name.replace("-", "").replace(".", "").isalnum():
        raise ValueError("unsafe service name")
    return name


def _manager(manifest: dict[str, Any]) -> str:
    runtime_kind = str(manifest["runtime"])
    if runtime_kind == "systemd":
        return "systemd"
    if runtime_kind == "launchd":
        return "launchd"
    return "none"


def install_unit(manifest: dict[str, Any]) -> tuple[bool, str]:
    manager = _manager(manifest)
    name = _name(manifest)
    executable = str(manifest["install_path"])
    working_directory = str(manifest.get("working_directory", Path(executable).parent))
    if manager == "systemd":
        unit = (
            "[Unit]\n"
            f"Description={name}\nAfter=network-online.target\n\n"
            "[Service]\n"
            "Type=simple\n"
            f"ExecStart={executable}\n"
            f"WorkingDirectory={working_directory}\n"
            f"EnvironmentFile=-{manifest['secret_path']}\n"
            "Restart=on-failure\n\n"
            "[Install]\nWantedBy=multi-user.target\n"
        )
        with tempfile.NamedTemporaryFile("w", suffix=".service", encoding="utf-8") as stream:
            stream.write(unit)
            stream.flush()
            ok, diagnostic = runtime.run_result(["sudo", "cp", stream.name, f"/etc/systemd/system/{name}.service"])
        if not ok:
            return ok, diagnostic
        return runtime.run_result(["sudo", "systemctl", "daemon-reload"])
    if manager == "launchd":
        plist = {
            "Label": name,
            "ProgramArguments": [executable],
            "WorkingDirectory": working_directory,
            "EnvironmentVariables": {"MYINSTALL_ENV_FILE": str(manifest["secret_path"])},
            "RunAtLoad": True,
            "KeepAlive": True,
        }
        destination = Path.home() / "Library" / "LaunchAgents" / f"{name}.plist"
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(plistlib.dumps(plist))
    return True, ""


def action(manifest: dict[str, Any], command: str) -> tuple[bool, str]:
    manager = _manager(manifest)
    name = _name(manifest)
    if manager == "systemd":
        return runtime.run_result(["sudo", "systemctl", command, f"{name}.service"], timeout=120)
    if manager == "launchd":
        label = f"{name}.plist"
        if command in {"start", "restart"}:
            return runtime.run_result(["launchctl", "load", str(Path.home() / "Library/LaunchAgents" / label)])
        if command == "stop":
            return runtime.run_result(["launchctl", "unload", str(Path.home() / "Library/LaunchAgents" / label)])
    return True, ""


def remove_unit(manifest: dict[str, Any]) -> tuple[bool, str]:
    """Stop and remove the service definition owned by this application."""
    manager = _manager(manifest)
    name = _name(manifest)
    if manager == "systemd":
        ok, diagnostic = action(manifest, "stop")
        if not ok:
            return ok, diagnostic
        ok, diagnostic = runtime.run_result(
            ["sudo", "rm", "-f", f"/etc/systemd/system/{name}.service"],
            timeout=120,
        )
        if not ok:
            return ok, diagnostic
        return runtime.run_result(["sudo", "systemctl", "daemon-reload"], timeout=120)
    if manager == "launchd":
        ok, diagnostic = action(manifest, "stop")
        if not ok:
            return ok, diagnostic
        plist = Path.home() / "Library" / "LaunchAgents" / f"{name}.plist"
        plist.unlink(missing_ok=True)
    return True, ""


def _launch_user() -> tuple[str, int, Path]:
    username = os.environ.get("SUDO_USER", "").strip() if os.geteuid() == 0 else ""
    if not username:
        username = pwd.getpwuid(os.getuid()).pw_name
    record = pwd.getpwnam(username)
    return username, record.pw_uid, Path(record.pw_dir)


def install_helper(manifest: dict[str, Any], executable: Path, server: str) -> tuple[bool, str]:
    config = manifest.get("helper")
    if not isinstance(config, dict):
        return False, "manifest does not declare a Mac helper"
    label = str(config.get("label", f"com.{manifest['app']}.helper"))
    username, uid, home = _launch_user()
    plist = home / "Library" / "LaunchAgents" / f"{label}.plist"
    plist.parent.mkdir(parents=True, exist_ok=True)
    plist_data = {
        "Label": label,
        "ProgramArguments": [str(executable), "--server", server],
        "RunAtLoad": True,
        "KeepAlive": True,
        "ProcessType": "Background",
        "WorkingDirectory": str(home),
        "StandardOutPath": str(home / "Library" / "Logs" / f"{label}.log"),
        "StandardErrorPath": str(home / "Library" / "Logs" / f"{label}.error.log"),
    }
    plist.write_bytes(plistlib.dumps(plist_data))
    os.chown(plist, uid, pwd.getpwnam(username).pw_gid)
    return runtime.run_result(["launchctl", "bootstrap", f"gui/{uid}", str(plist)], timeout=30)


def helper_action(manifest: dict[str, Any], command: str) -> tuple[bool, str]:
    config = manifest.get("helper")
    if not isinstance(config, dict):
        return False, "manifest does not declare a Mac helper"
    label = str(config.get("label", f"com.{manifest['app']}.helper"))
    _, uid, home = _launch_user()
    plist = home / "Library" / "LaunchAgents" / f"{label}.plist"
    target = f"gui/{uid}/{label}"
    if command == "status":
        return runtime.run_result(["launchctl", "print", target], timeout=30)
    if command == "start":
        return runtime.run_result(["launchctl", "bootstrap", f"gui/{uid}", str(plist)], timeout=30)
    if command == "stop":
        return runtime.run_result(["launchctl", "bootout", target], timeout=30)
    if command == "uninstall":
        stopped, diagnostic = runtime.run_result(["launchctl", "bootout", target], timeout=30)
        if not stopped and plist.exists():
            return False, diagnostic
        plist.unlink(missing_ok=True)
        shutil.rmtree(
            home / "Library" / "Application Support" / "myinstall" / str(manifest["app"]),
            ignore_errors=True,
        )
        return True, diagnostic
    return False, f"unknown helper action: {command}"


def install_menu_bar(manifest: dict[str, Any], executable: Path) -> tuple[bool, str]:
    config = manifest.get("menu_bar")
    if not isinstance(config, dict):
        return False, "manifest does not declare a menu bar app"
    label = str(config.get("label", f"com.{manifest['app']}.menubar"))
    username, uid, home = _launch_user()
    plist = home / "Library" / "LaunchAgents" / f"{label}.plist"
    plist.parent.mkdir(parents=True, exist_ok=True)
    plist.write_bytes(plistlib.dumps({
        "Label": label,
        "ProgramArguments": [str(executable)],
        "RunAtLoad": True,
        "KeepAlive": True,
        "ProcessType": "Interactive",
    }))
    os.chown(plist, uid, pwd.getpwnam(username).pw_gid)
    return runtime.run_result(["launchctl", "bootstrap", f"gui/{uid}", str(plist)], timeout=30)
