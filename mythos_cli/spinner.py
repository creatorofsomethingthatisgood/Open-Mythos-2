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
 "\u2736", # 
 "\u2737", # 
 "\u2738", # 
 "\u2739", # 
 "\u273A", # 
 "\u274B", # 
 "\u274A", # 
 "\u2747", # 
 "\u2748", # 
 "\u2749", # 
 "\u2726", # 
 "\u2727", # 
 "\u22C6", # ⋆
 "\u2042", # ⁂
 "\u2734", # 
 "\u2735", # 
 "\u2731", # 
 "\u2732", # 
 "\u2733", # 
 "\u2743", # 
 "\u2744", # 
 "\u2745", # 
 "\u2746", # 
 "\u2605", # 
]

COLORS = ["#EA580C", "#F97316", "#FB923C", "#EF4444", "#F97316", "#EA580C"]

# Moon-phase glyphs (toggle with M key while thinking)
MOON_GLYPHS = ["\u25D0", "\u25D1", "\u25D2", "\u25D3"]

# Rotating labels when using default "Thinking" label
LABELS = [
    "Thinking", "Reasoning", "Pondering", "Analyzing",
    "Musing", "Deliberating", "Contemplating", "Processing",
    "Reflecting", "Calculating",
]


class ThinkingSpinner:
    """Animated spinner cycling through unicode star glyphs."""

    def __init__(self) -> None:
        self._idx = 0
        self._stop = threading.Event()
        self._thread = None
        self._live = None
        self._label = "Thinking"
        self._console = None
        self._moon = False
        self._listener = None

    def start(self, console=None, label: str = "Thinking") -> None:
        # Ensure previous listener is fully stopped and terminal is restored
        # before we capture settings again in a new _start_listener().
        if self._listener and self._listener.is_alive():
            self._stop.set()
            self._listener.join(timeout=1.0)
            self._stop.clear()
        self._label = label
        self._console = console
        self._moon = False
        self._stop.clear()
        if _RICH_AVAILABLE and console is not None:
            self._live = Live("", console=console, transient=True, refresh_per_second=8)
            self._live.__enter__()
        self._thread = threading.Thread(target=self._spin, daemon=True)
        self._thread.start()
        self._start_listener()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=0.5)
        # Join listener first so terminal settings are restored before
        # the main thread touches stdin again (e.g. for Prompt input).
        if self._listener:
            self._listener.join(timeout=1.0)
            self._listener = None
        if self._live:
            self._live.__exit__(None, None, None)
            self._live = None
        elif self._console:
            self._console.print("\r", end="")

    def _frame_text(self) -> str:
        glyphs = MOON_GLYPHS if self._moon else GLYPHS
        glyph = glyphs[self._idx % len(glyphs)]
        color = COLORS[self._idx % len(COLORS)]
        label = LABELS[self._idx % len(LABELS)] if self._label == "Thinking" else self._label
        return f"[{color}]{glyph}[/{color}] [dim]{label}...[/dim]"

    def _spin(self) -> None:
        while not self._stop.is_set():
            if self._live:
                self._live.update(self._frame_text())
            elif self._console:
                frame = self._frame_text()
                self._console.print(f"\r{frame}", end="", highlight=False)
            else:
                # Fallback: plain terminal
                glyphs = MOON_GLYPHS if self._moon else GLYPHS
                glyph = glyphs[self._idx % len(glyphs)]
                label = LABELS[self._idx % len(LABELS)] if self._label == "Thinking" else self._label
                sys.stdout.write(f"\r{glyph} {label}...")
                sys.stdout.flush()
            self._idx += 1
            self._stop.wait(0.12)

    def _start_listener(self) -> None:
        """Spawn a daemon thread listening for 'm' keypress to toggle moon mode."""
        try:
            import tty
            import termios
            import select
        except ImportError:
            return
        if not sys.stdin.isatty():
            return

        def _listen():
            fd = sys.stdin.fileno()
            old_settings = None
            try:
                old_settings = termios.tcgetattr(fd)
                tty.setcbreak(fd)
                while not self._stop.is_set():
                    ready, _, _ = select.select([sys.stdin], [], [], 0.1)
                    if ready:
                        ch = sys.stdin.read(1)
                        if ch.lower() == "m":
                            self._moon = not self._moon
            except (termios.error, OSError, ValueError):
                pass
            finally:
                if old_settings is not None:
                    try:
                        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
                    except (termios.error, OSError):
                        pass

        self._listener = threading.Thread(target=_listen, daemon=True)
        self._listener.start()
