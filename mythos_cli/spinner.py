"""Animated thinking spinner with cycling unicode glyphs, like Claude Code.

Used by the mythos CLI to show a live-updating spinner while the model
is generating a response. Cycles through decorative unicode star/symbol
characters with the red-orange #EA580C theme.
"""

import threading
import sys

try:
    from rich.live import Live
    _RICH_AVAILABLE = True
except ImportError:
    _RICH_AVAILABLE = False

# Unicode star/symbol glyphs that rotate during thinking
GLYPHS = [
    "\u2736",  # ✶
    "\u2737",  # ✷
    "\u2738",  # ✸
    "\u2739",  # ✹
    "\u273A",  # ✺
    "\u274B",  # ❋
    "\u274A",  # ❊
    "\u2747",  # ❇
    "\u2748",  # ❈
    "\u2749",  # ❉
    "\u2726",  # ✦
    "\u2727",  # ✧
    "\u22C6",  # ⋆
    "\u2042",  # ⁂
    "\u2734",  # ✴
    "\u2735",  # ✵
    "\u2731",  # ✱
    "\u2732",  # ✲
    "\u2733",  # ✳
    "\u2743",  # ❃
    "\u2744",  # ❄
    "\u2745",  # ❅
    "\u2746",  # ❆
    "\u2605",  # ★
]

COLORS = ["#EA580C", "#F97316", "#FB923C", "#EF4444", "#F97316", "#EA580C"]


class ThinkingSpinner:
    """Animated spinner cycling through unicode star glyphs."""

    def __init__(self) -> None:
        self._idx = 0
        self._stop = threading.Event()
        self._thread = None
        self._live = None
        self._label = "Thinking"
        self._console = None

    def start(self, console=None, label: str = "Thinking") -> None:
        self._label = label
        self._console = console
        self._stop.clear()
        if _RICH_AVAILABLE and console is not None:
            self._live = Live("", console=console, transient=True, refresh_per_second=8)
            self._live.__enter__()
        self._thread = threading.Thread(target=self._spin, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=0.5)
        if self._live:
            self._live.__exit__(None, None, None)
            self._live = None
        elif self._console:
            self._console.print("\r", end="")

    def _frame_text(self) -> str:
        glyph = GLYPHS[self._idx % len(GLYPHS)]
        color = COLORS[self._idx % len(COLORS)]
        return f"[{color}]{glyph}[/{color}] [dim]{self._label}...[/dim]"

    def _spin(self) -> None:
        while not self._stop.is_set():
            if self._live:
                self._live.update(self._frame_text())
            elif self._console:
                frame = self._frame_text()
                self._console.print(f"\r{frame}", end="", highlight=False)
            else:
                # Fallback: plain terminal
                glyph = GLYPHS[self._idx % len(GLYPHS)]
                sys.stdout.write(f"\r{glyph} {self._label}...")
                sys.stdout.flush()
            self._idx += 1
            self._stop.wait(0.12)
