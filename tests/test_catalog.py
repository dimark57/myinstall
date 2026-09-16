from __future__ import annotations

from unittest.mock import patch

from myinstall import paths


def test_new_machine_paths_follow_macos_nas_layout() -> None:
    entry = {
        "app": "myqa",
        "runtime": "native",
        "stack_path": "/srv/nas/stacks/apps/myqa",
        "data_path": "/srv/nas/data/myqa",
        "secret_path": "/srv/nas/secrets/myqa.env",
        "release_source": "dimark57/myqa",
        "nested": {"admin_secret_path": "/srv/nas/secrets/admin.env"},
    }
    with patch("myinstall.paths.platform.system", return_value="Darwin"), patch(
        "myinstall.paths.Path.home", return_value=paths.Path("/Users/tester")
    ):
        localized = paths.localize_manifest_paths(entry)

    assert localized["stack_path"] == "/Users/tester/nas/stacks/utilites/myqa"
    assert localized["data_path"] == "/Users/tester/nas/data/myqa"
    assert localized["secret_path"] == "/Users/tester/nas/secrets/myqa.env"
    assert localized["install_path"] == (
        "/Users/tester/nas/stacks/utilites/myqa/releases/current/myqa"
    )
    assert entry["stack_path"] == "/srv/nas/stacks/apps/myqa"
