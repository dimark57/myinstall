from __future__ import annotations

import os
import sys
from dataclasses import dataclass


_ACTIVE: "Progress | None" = None


@dataclass
class Progress:
    """A stderr-only progress bar for interactive lifecycle commands."""

    label: str
    total: int
    current: int = 0

    def __post_init__(self) -> None:
        global _ACTIVE
        self.enabled = (
            sys.stderr.isatty()
            and os.environ.get("MYINSTALL_NO_PROGRESS") != "1"
        )
        _ACTIVE = self
        if self.enabled:
            self._render()

    def step(self, message: str) -> None:
        self.current = min(self.current + 1, self.total)
        self.message = message
        if self.enabled:
            self._render()

    def finish(self) -> None:
        global _ACTIVE
        if self.enabled:
            self.current = self.total
            self._render()
            sys.stderr.write("\n")
            sys.stderr.flush()
        if _ACTIVE is self:
            _ACTIVE = None

    def _render(self) -> None:
        width = 24
        filled = int(width * self.current / max(self.total, 1))
        bar = "#" * filled + "-" * (width - filled)
        message = getattr(self, "message", self.label)
        sys.stderr.write(
            f"\r{self.label} [{bar}] {self.current}/{self.total} {message}"
        )
        sys.stderr.flush()


def finish_active() -> None:
    if _ACTIVE is not None:
        _ACTIVE.finish()
