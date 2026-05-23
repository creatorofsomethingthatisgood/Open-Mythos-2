"""
UI Package - Terminal and Web interfaces
"""

from .terminal_ui import TerminalUI, run_terminal_ui

try:
    from .web_ui import WebUI, run_web_ui
    __all__ = ['TerminalUI', 'run_terminal_ui', 'WebUI', 'run_web_ui']
except (ImportError, NameError):
    __all__ = ['TerminalUI', 'run_terminal_ui']
