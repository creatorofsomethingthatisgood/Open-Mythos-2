"""
Progress spinner utility for long-running Mythos operations.

Usage::

    with spinner("Scanning files..."):
        time.sleep(2)  # your long operation

    with spinner("Downloading model...") as spin:
        for chunk in download():
            spin.update(f"Downloading... {chunk.percent}%")
"""

from __future__ import annotations

import contextlib
from typing import Iterator, Optional

from rich.progress import (
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
    BarColumn,
    TaskID,
)


@contextlib.contextmanager
def spinner(
    description: str = "Working...",
    transient: bool = True,
) -> Iterator["_SpinnerHandle"]:
    """
    Context manager that shows an animated spinner with a message.

    Args:
        description: Initial message shown next to the spinner.
        transient: Remove the spinner line when done (like ``tqdm``).

    Yields:
        A handle whose ``.update(msg)`` changes the live message.
    """
    progress = Progress(
        SpinnerColumn(spinner_name="dots", style="cyan"),
        TextColumn("[progress.description]{task.description}"),
        TimeElapsedColumn(),
        transient=transient,
    )
    handle = _SpinnerHandle(progress)
    with progress:
        task_id = progress.add_task(description, total=None)
        handle._task_id = task_id
        try:
            yield handle
        finally:
            progress.update(task_id, visible=False)


@contextlib.contextmanager
def progress_bar(
    description: str = "Working...",
    total: int = 100,
    transient: bool = True,
) -> Iterator["_ProgressHandle"]:
    """
    Context manager that shows a determinate progress bar.

    Args:
        description: Label shown above the bar.
        total: Number of steps to completion.
        transient: Remove the bar when done.

    Yields:
        A handle whose ``.advance(steps=1)`` moves the bar and
        ``.update(msg)`` changes the live description.
    """
    progress = Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=None),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        transient=transient,
    )
    handle = _ProgressHandle(progress)
    with progress:
        task_id = progress.add_task(description, total=total)
        handle._task_id = task_id
        yield handle


class _SpinnerHandle:
    """Handle returned by :func:`spinner`."""

    def __init__(self, progress: Progress) -> None:
        self._progress = progress
        self._task_id: TaskID | None = None

    def update(self, description: str) -> None:
        if self._task_id is not None:
            self._progress.update(self._task_id, description=description)


class _ProgressHandle:
    """Handle returned by :func:`progress_bar`."""

    def __init__(self, progress: Progress) -> None:
        self._progress = progress
        self._task_id: TaskID | None = None

    def advance(self, steps: int = 1) -> None:
        if self._task_id is not None:
            self._progress.advance(self._task_id, advance=steps)

    def update(self, description: str) -> None:
        if self._task_id is not None:
            self._progress.update(self._task_id, description=description)
