"""
UI Package - Terminal and Web interfaces
"""

from .terminal_ui import TerminalUI, run_terminal_ui

try:
    from .web_ui import WebUI, run_web_ui
except ImportError:
    pass

__all__ = ['TerminalUI', 'run_terminal_ui']
