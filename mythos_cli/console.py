"""
Shared Rich Console instance for Mythos CLI — single import point for
colorized terminal output.
"""

from __future__ import annotations

from rich.console import Console

console = Console()

# Shorthand style constants used across the CLI
STYLE_TITLE = "bold cyan"
STYLE_OK = "bold green"
STYLE_WARN = "bold yellow"
STYLE_ERR = "bold red"
STYLE_DIM = "dim"
STYLE_INFO = "cyan"
STYLE_HIGHLIGHT = "bold magenta"
