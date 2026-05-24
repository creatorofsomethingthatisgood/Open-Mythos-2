"""Optional progress callbacks for long-running fix/rewrite steps."""

from __future__ import annotations

from typing import Callable, Optional

ProgressCallback = Callable[[str], None]
StreamCallback = Callable[[str], None]


def emit_progress(message: str, on_progress: Optional[ProgressCallback] = None) -> None:
    if on_progress is not None:
        on_progress(message)
