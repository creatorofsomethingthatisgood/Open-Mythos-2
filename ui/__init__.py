"""
UI Package - Terminal and Web interfaces
"""

from .terminal_ui import TerminalUI, run_terminal_ui

__all__ = ["TerminalUI", "run_terminal_ui", "WebUI", "run_web_ui"]


def __getattr__(name: str):
    if name in ("WebUI", "run_web_ui"):
        from .web_ui import WebUI, run_web_ui
        return WebUI if name == "WebUI" else run_web_ui
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
