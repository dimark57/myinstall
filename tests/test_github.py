from unittest.mock import patch

from myinstall import github


def test_by_tag_preserves_v_prefix_in_github_release_url() -> None:
    payload = b'{"tag_name":"v0.1.63","prerelease":false,"assets":[]}'
    with patch(
        "myinstall.github._request",
        return_value=(200, payload, None),
    ) as request:
        release = github.by_tag("dimark57/mytask", "v0.1.63")

    request.assert_called_once_with(
        "https://api.github.com/repos/dimark57/mytask/releases/tags/v0.1.63"
    )
    assert release.tag == "v0.1.63"
