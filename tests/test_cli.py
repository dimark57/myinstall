from unittest.mock import patch

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
