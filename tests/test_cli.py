import pytest
import json
import os
from unittest.mock import patch
from pathlib import Path

from myinstall import cli


def test_bare_app_name_is_normalized_to_sync_command() -> None:
    with patch("myinstall.cli.do_app_sync", return_value=0) as sync:
        assert cli.main(["mytask"]) == 0
    sync.assert_called_once_with("mytask", None, None)


def test_sync_parser_accepts_explicit_release() -> None:
    args = cli.build_parser().parse_args(["sync", "mytask", "--version", "v0.1.60"])
    assert args.command == "sync"
    assert args.app_id == "mytask"
    assert args.version == "v0.1.60"


def test_remove_parser_supports_explicit_data_and_secret_purge() -> None:
    args = cli.build_parser().parse_args(
        [
            "remove",
            "--manifest",
            "/srv/nas/stacks/apps/mytask/manifest.json",
            "--confirm",
            "--purge-data",
            "--purge-secrets",
            "--interactive",
        ]
    )
    assert args.command == "remove"
    assert args.confirm is True
    assert args.purge_data is True
    assert args.purge_secrets is True
    assert args.interactive is True


def test_update_alias_delegates_to_application_sync() -> None:
    with patch("myinstall.cli.do_app_sync", return_value=0) as sync:
        assert cli.main(["update", "mytask"]) == 0
    sync.assert_called_once_with("mytask", None, None)


def test_application_update_flag_delegates_to_application_sync() -> None:
    with patch("myinstall.cli.do_app_sync", return_value=0) as sync:
        assert cli.main(["mytask", "--update"]) == 0
    sync.assert_called_once_with("mytask", None, None)


def test_application_install_helper_alias_delegates_selection() -> None:
    with patch("myinstall.cli.do_app_install_alias", return_value=0) as install:
        assert cli.main(["mytask", "--install", "--helper", "--test"]) == 0
    install.assert_called_once_with("mytask", helper=True, docker=False, test=True)


def test_application_helper_lifecycle_alias_delegates() -> None:
    with patch("myinstall.cli.do_helper_command", return_value=0) as helper:
        assert cli.main(["mytask", "helper", "status"]) == 0
    helper.assert_called_once_with("mytask", "status")


def test_self_update_flag_is_explicitly_handled(capsys) -> None:
    with patch("myinstall.cli.do_self_update", return_value=0) as update:
        assert cli.main(["--update"]) == 0
    update.assert_called_once_with()


def test_global_plan_is_a_read_only_internal_flag() -> None:
    with patch("myinstall.cli.do_global_plan", return_value=0) as plan:
        assert cli.main(["--plan"]) == 0
    plan.assert_called_once_with()


def test_global_doctor_is_a_read_only_internal_flag() -> None:
    with patch("myinstall.cli.do_apps_doctor", return_value=0) as doctor:
        assert cli.main(["--doctor"]) == 0
    doctor.assert_called_once_with(None)


def test_auth_setup_is_an_explicit_command() -> None:
    with patch("myinstall.cli.auth.setup", return_value=0) as setup:
        assert cli.main(["auth", "setup"]) == 0
    setup.assert_called_once_with()


def test_auth_status_reports_token_state(capsys) -> None:
    with patch(
        "myinstall.cli.auth.status",
        return_value=({"state": "expired_or_invalid", "hint": "run auth setup"}, 1),
    ):
        assert cli.main(["auth", "status"]) == 1
    assert '"expired_or_invalid"' in capsys.readouterr().out


def test_application_command_wrapper_delegates_update(tmp_path) -> None:
    manifest = tmp_path / "manifest.json"
    target = tmp_path / "bin" / "mytask"
    path = cli.install_app_command(
        manifest,
        {
            "app": "mytask",
            "current_version": "v1.2.3",
            "cli": {"name": "mytask", "bin_path": str(target)},
        },
    )
    assert path == target
    assert target.stat().st_mode & 0o111
    wrapper = target.read_text(encoding="utf-8")
    assert "myinstall mytask --update" in wrapper
    assert "myinstall uninstall --manifest" in wrapper
    assert "shift\n    exec myinstall uninstall" in wrapper


def test_self_remove_deletes_only_myinstall_binary(tmp_path, capsys) -> None:
    target = tmp_path / "myinstall"
    target.write_text("#!/bin/sh\n", encoding="utf-8")
    target.chmod(0o755)
    with patch.dict(os.environ, {"MYINSTALL_EXECUTABLE": str(target)}), patch(
        "myinstall.cli.ask_yes_no", return_value=False
    ):
        assert cli.main(["--uninstall"]) == 0
    assert not target.exists()
    assert '"applications": "preserved"' in capsys.readouterr().out


def test_missing_local_manifest_is_materialized_from_public_catalog(tmp_path) -> None:
    entry = {
        "schema_version": "1.0",
        "kind": "application",
        "app": "mytask",
        "zone": "apps",
        "runtime": "docker",
        "image": "ghcr.io/example/mytask:v1.2.3",
        "stack_path": str(tmp_path / "stack"),
        "data_path": str(tmp_path / "data"),
        "secret_path": str(tmp_path / "secret.env"),
        "secret_mount": "/run/mytask.env",
        "required_secrets": [],
        "healthcheck": {"url": "http://127.0.0.1:9/health"},
        "cli": {"name": "mytask", "commands": ["--version"]},
    }
    with patch(
        "myinstall.cli.discovery.find_app_manifest",
        side_effect=ValueError("application manifest not found: mytask"),
    ), \
        patch("myinstall.cli.catalog.fetch", return_value=entry), \
        patch("myinstall.cli.install_app_command"), \
        patch("myinstall.cli.do_install", return_value=0) as install:
        assert cli.main(["mytask"]) == 0
    install.assert_called_once()
    assert (tmp_path / "stack" / "manifest.json").is_file()


def test_help_is_an_internal_flag(capsys) -> None:
    with pytest.raises(SystemExit) as exit_info:
        cli.main(["--help"])
    assert exit_info.value.code == 0
    assert "usage: myinstall" in capsys.readouterr().out


def test_man_is_not_an_internal_command() -> None:
    with patch("myinstall.cli.do_app_sync", return_value=0) as sync:
        assert cli.main(["man"]) == 0
    sync.assert_called_once_with("man", None, None)


def test_myqa_catalog_entry_declares_native_application_contract() -> None:
    catalog = json.loads(
        (Path(__file__).parents[1] / "catalog" / "apps.json").read_text(
            encoding="utf-8"
        )
    )
    entry = catalog["apps"]["myqa"]
    assert entry["runtime"] == "native"
    assert entry["release_asset_pattern"] == "myqa-{version}-{platform}"
    assert entry["cli"]["name"] == "myqa"
    assert set(entry["cli"]["commands"]) == {
        "--version",
        "--help",
        "--man",
        "--doctor",
        "--update",
        "help",
        "man",
        "doctor",
        "update",
    }


def _docker_upgrade_data(tmp_path: Path) -> tuple[Path, dict]:
    stack = tmp_path / "stack"
    stack.mkdir()
    compose = stack / "docker-compose.yml"
    compose.write_text(
        "services:\n  app:\n    image: ghcr.io/example/mytask:v1.0.0\n",
        encoding="utf-8",
    )
    return compose, {
        "runtime": "docker",
        "image": "ghcr.io/example/mytask:v1.0.0",
        "stack_path": str(stack),
        "secret_path": str(tmp_path / "secret.env"),
        "secret_mount": "/run/mytask.env",
        "data_path": str(tmp_path / "data"),
        "healthcheck": {"url": "http://127.0.0.1:8080/health"},
    }


def test_docker_upgrade_reports_image_pull_stage_and_stable_code(tmp_path, capsys) -> None:
    compose, data = _docker_upgrade_data(tmp_path)
    with patch("myinstall.cli.runtime.materialize", return_value=compose), \
        patch("myinstall.cli.runtime.validate_compose", return_value=[]), \
        patch("myinstall.cli.runtime.ensure_registry_login", return_value=True), \
        patch("myinstall.cli.runtime.compose", return_value=False):
        assert cli.do_upgrade(tmp_path / "manifest.json", data, "ghcr.io/example/mytask:v1.0.1", None) == 1

    result = json.loads(capsys.readouterr().out)
    assert result["error_code"] == "UPG-008"
    assert result["error_number"] == 8
    assert result["stage"] == "Загрузка образа"
    assert result["rollback"] == "previous compose restored"
    assert result["rollback_code"] == "UPG-012"
    assert "v1.0.0" in compose.read_text(encoding="utf-8")


def test_docker_upgrade_reports_runtime_start_stage_separately(tmp_path, capsys) -> None:
    compose, data = _docker_upgrade_data(tmp_path)
    with patch("myinstall.cli.runtime.materialize", return_value=compose), \
        patch("myinstall.cli.runtime.validate_compose", return_value=[]), \
        patch("myinstall.cli.runtime.ensure_registry_login", return_value=True), \
        patch("myinstall.cli.runtime.compose", side_effect=[True, False, True]):
        assert cli.do_upgrade(tmp_path / "manifest.json", data, "ghcr.io/example/mytask:v1.0.1", None) == 1

    result = json.loads(capsys.readouterr().out)
    assert result["error_code"] == "UPG-009"
    assert result["stage"] == "Запуск runtime"
    assert result["rollback_code"] == "UPG-012"


def test_docker_upgrade_reports_failed_rollback(tmp_path, capsys) -> None:
    compose, data = _docker_upgrade_data(tmp_path)
    with patch("myinstall.cli.runtime.materialize", return_value=compose), \
        patch("myinstall.cli.runtime.validate_compose", return_value=[]), \
        patch("myinstall.cli.runtime.ensure_registry_login", return_value=True), \
        patch("myinstall.cli.runtime.compose", side_effect=[True, True, False]), \
        patch("myinstall.cli.native.run_hook", return_value=(False, "migration exit 1")), \
        patch("myinstall.cli.runtime.health", return_value=True):
        assert cli.do_upgrade(tmp_path / "manifest.json", data, "ghcr.io/example/mytask:v1.0.1", None) == 1

    result = json.loads(capsys.readouterr().out)
    assert result["error_code"] == "UPG-013"
    assert result["stage"] == "Rollback"
    assert result["rollback"] == "previous compose restart failed"


def test_docker_upgrade_snapshots_compose_before_materialize(tmp_path, capsys) -> None:
    compose, data = _docker_upgrade_data(tmp_path)
    previous = compose.read_text(encoding="utf-8")

    def materialize_new_compose(*args, **kwargs):
        compose.write_text(
            previous.replace("v1.0.0", "v1.0.1"),
            encoding="utf-8",
        )
        return compose

    with patch(
        "myinstall.cli.runtime.materialize",
        side_effect=materialize_new_compose,
    ), patch("myinstall.cli.runtime.validate_compose", return_value=[]), \
        patch("myinstall.cli.runtime.ensure_registry_login", return_value=True), \
        patch("myinstall.cli.runtime.compose", side_effect=[True, False, True]):
        assert cli.do_upgrade(
            tmp_path / "manifest.json",
            data,
            "ghcr.io/example/mytask:v1.0.1",
            None,
        ) == 1

    result = json.loads(capsys.readouterr().out)
    assert result["rollback_code"] == "UPG-012"
    assert "v1.0.0" in (tmp_path / "stack" / ".myinstall.previous-compose").read_text()
