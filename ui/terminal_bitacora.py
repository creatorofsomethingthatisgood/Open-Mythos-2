"""Live terminal bitácora panel (Rich Live)."""

from __future__ import annotations

from typing import Optional

try:
    from rich.console import Console
    from rich.live import Live
    from rich.panel import Panel
except ImportError:
    Console = None  # type: ignore
    Live = None  # type: ignore
    Panel = None  # type: ignore

from engine.bitacora import Bitacora
from engine.progress import StreamCallback


class TerminalBitacoraSession:
    """Context manager: progressive bitácora panel while fix/rewrite runs."""

    def __init__(self, console: Console):
        self.console = console
        self.bitacora = Bitacora()
        self._live: Optional[Live] = None

    def __enter__(self) -> Bitacora:
        self.bitacora = Bitacora(on_update=self._refresh)
        self.bitacora.log("Bitácora started", kind="info")
        if Live is not None and Panel is not None:
            self._live = Live(
                self._panel(),
                console=self.console,
                refresh_per_second=8,
                transient=False,
            )
            self._live.__enter__()
        return self.bitacora

    def __exit__(self, exc_type, exc, tb) -> None:
        if exc is not None:
            self.bitacora.log(f"Stopped: {exc}", kind="error")
        else:
            self.bitacora.log("Bitácora closed", kind="info")
        if self._live is not None:
            self._live.update(self._panel())
            self._live.__exit__(exc_type, exc, tb)
            self._live = None

    def progress_callback(self):
        return self.bitacora.as_progress_callback()

    def stream_callback(self) -> StreamCallback:
        def _on_chunk(chunk: str) -> None:
            self.bitacora.log_stream_chunk(chunk)
            if self._live is not None:
                self._live.console.print(chunk, end="", style="dim")
            else:
                self.console.print(chunk, end="", style="dim")
        return _on_chunk

    def _panel(self) -> Panel:
        return Panel(
            self.bitacora.render_rich(),
            title="Bitácora",
            border_style="blue",
            subtitle="live",
        )

    def _refresh(self, _bitacora: Bitacora) -> None:
        if self._live is not None:
            self._live.update(self._panel())
