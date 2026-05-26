"""Progressive operation log (bitácora) for fix/rewrite workflows."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, List, Optional

from engine.progress import ProgressCallback

BitacoraUpdateCallback = Callable[["Bitacora"], None]


@dataclass
class BitacoraEntry:
    time: str
    kind: str
    message: str


def classify_bitacora_message(message: str) -> str:
    lower = message.lower()
    if message.startswith("  •"):
        return "rationale"
    if message.startswith("Wrote") or "writing " in lower or "wrote full file" in lower:
        return "write"
    if message.startswith("Failed") or "cannot read" in lower:
        return "error"
    if message.startswith("Skip") or "skipped" in lower or "not confirmed" in lower:
        return "warn"
    if "scan" in lower:
        return "scan"
    return "info"


@dataclass
class Bitacora:
    """Append-only journal updated as fix/rewrite steps run."""

    entries: List[BitacoraEntry] = field(default_factory=list)
    on_update: Optional[BitacoraUpdateCallback] = field(default=None, repr=False, compare=False)
    _stream_chars: int = field(default=0, init=False, repr=False)

    def log(self, message: str, *, kind: Optional[str] = None) -> None:
        message = message.strip()
        if not message:
            return
        entry = BitacoraEntry(
            time=datetime.now().strftime("%H:%M:%S"),
            kind=kind or classify_bitacora_message(message),
            message=message,
        )
        self.entries.append(entry)
        if self.on_update is not None:
            self.on_update(self)

    def log_stream_chunk(self, chunk: str, *, every_chars: int = 400) -> None:
        if not chunk:
            return
        self._stream_chars += len(chunk)
        if self._stream_chars == len(chunk) or self._stream_chars % every_chars < len(chunk):
            self.log(
                f"Model output streaming… ({self._stream_chars:,} chars received)",
                kind="stream",
            )

    def reset_stream_counter(self) -> None:
        self._stream_chars = 0

    def as_progress_callback(self) -> ProgressCallback:
        def _cb(message: str) -> None:
            self.log(message)
        return _cb

    def render_plain(self, *, max_lines: int = 40) -> str:
        lines = self._format_lines(max_lines=max_lines)
        return "\n".join(lines) if lines else "(empty)"

    def render_rich(self, *, max_lines: int = 22):
        """Build a Renderable for the bitácora Panel body.

        Entries whose `kind` is "stream" represent the model's thinking
        state (token streaming during generation). They are rendered
        center-aligned in the panel, without the `HH:MM:SS` timestamp
        prefix, to set them apart from operational log lines. Everything
        else stays left-aligned in the familiar `HH:MM:SS  message` form.

        Returns a `rich.console.Group` so the Panel content can mix
        alignment per line; the previous markup-string version forced a
        single justification for the whole block.
        """
        # Lazy import: keep bitácora usable in headless / library contexts
        # where `rich` is not installed; the renderable path is only
        # exercised by terminal_bitacora.py, which already requires rich.
        from rich.align import Align
        from rich.console import Group
        from rich.text import Text

        style_map = {
            "write": "bold green",
            "error": "bold red",
            "warn": "yellow",
            "scan": "cyan",
            "rationale": "dim",
            "stream": "dim italic",
            "info": "white",
        }

        renderables: List = []

        if len(self.entries) > max_lines:
            renderables.append(
                Text(
                    f"… {len(self.entries) - max_lines} earlier entries",
                    style="dim",
                )
            )

        for entry in self.entries[-max_lines:]:
            style = style_map.get(entry.kind, "white")
            if entry.kind == "stream":
                # Thinking state — centered, drop the timestamp clutter.
                renderables.append(
                    Align.center(Text(entry.message, style=style))
                )
            else:
                renderables.append(
                    Text.assemble(
                        (entry.time + "  ", "dim"),
                        (entry.message, style),
                    )
                )

        if not renderables:
            renderables.append(Text("Waiting for events…", style="dim"))

        return Group(*renderables)

    def _format_lines(self, *, max_lines: int) -> List[str]:
        visible = self.entries[-max_lines:]
        lines = [f"{e.time}  {e.message}" for e in visible]
        if len(self.entries) > max_lines:
            lines.insert(0, f"… {len(self.entries) - max_lines} earlier entries")
        return lines
