from pathlib import Path
from unittest.mock import patch

from myinstall import auth


def test_setup_persists_separate_github_and_ghcr_tokens(tmp_path: Path) -> None:
    secret_path = tmp_path / "myinstall.env"
    with patch.object(auth, "AUTH_SECRET_PATH", secret_path), \
        patch("myinstall.auth.os.isatty", return_value=True), \
        patch(
            "myinstall.auth.getpass.getpass",
            side_effect=["github-token", "ghcr-token"],
        ), \
        patch(
            "myinstall.auth.github.validate_token",
            side_effect=["github-user", "ghcr-user"],
        ):
        assert auth.setup() == 0

    assert auth.secrets.read(secret_path) == {
        "MYINSTALL_GHCR_TOKEN": "ghcr-token",
        "MYINSTALL_GHCR_USER": "ghcr-user",
        "MYINSTALL_GITHUB_TOKEN": "github-token",
        "MYINSTALL_GITHUB_USER": "github-user",
    }


def test_status_requires_both_tokens() -> None:
    with patch.dict(
        "os.environ",
        {"MYINSTALL_GITHUB_TOKEN": "github-token"},
        clear=True,
    ):
        status, code = auth.status()

    assert code == 1
    assert status["state"] == "missing"
    assert status["github_token"] == "configured"
    assert status["ghcr_token"] == "missing"
