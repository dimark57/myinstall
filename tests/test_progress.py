from __future__ import annotations

import io
from unittest.mock import patch

from myinstall.progress import Progress


def test_progress_bar_is_stderr_only_and_finishes() -> None:
    stream = io.StringIO()
    stream.isatty = lambda: True
    with patch("myinstall.progress.sys.stderr", stream):
        bar = Progress("install", 2)
        bar.step("download")
        bar.step("verify")
        bar.finish()

    rendered = stream.getvalue()
    assert "install" in rendered
    assert "2/2" in rendered
    assert rendered.endswith("\n")
