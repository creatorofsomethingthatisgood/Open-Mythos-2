"""
Mythos Chat Launcher — starts the terminal (or web) chat interface.

Uses ~/.config/mythos for models and caches so a new clone does not re-download.
Run via ./mythos (repo wrapper) or venv/bin/mythos after setup.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from mythos_cli.config_store import (
    mythos_home,
    resolve_chat_config,
)

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _prepare_runtime_dirs(config_path: Path) -> None:
    """Ensure directories referenced by config exist."""
    home = mythos_home()
    for d in (
        home / "models",
        home / "conversations",
        home / "cache" / "huggingface",
        home / "rag_docs",
        home / "chroma_db",
        _PROJECT_ROOT / "models",
        _PROJECT_ROOT / "conversations",
    ):
        d.mkdir(parents=True, exist_ok=True)


def _setup_import_path() -> None:
    root_str = str(_PROJECT_ROOT)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)


def launch_chat(config_path: str | None = None, verbose: bool = False) -> None:
    """Launch the Mythos terminal chat interface."""
    _setup_import_path()
    cfg_path = resolve_chat_config(config_path)
    _prepare_runtime_dirs(cfg_path)

    os.environ["MYTHOS_CONFIG"] = str(cfg_path)
    os.environ["MYTHOS_PROJECT_ROOT"] = str(_PROJECT_ROOT)
    os.environ.setdefault("OLDPWD", os.getcwd())

    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    from ui.terminal_ui import run_terminal_ui

    run_terminal_ui(str(cfg_path))


def launch_web(
    config_path: str | None = None,
    port: int = 7860,
    share: bool = False,
) -> None:
    """Launch the Mythos web UI."""
    _setup_import_path()
    cfg_path = resolve_chat_config(config_path)
    _prepare_runtime_dirs(cfg_path)

    os.environ["MYTHOS_CONFIG"] = str(cfg_path)
    os.environ["MYTHOS_PROJECT_ROOT"] = str(_PROJECT_ROOT)

    from ui.web_ui import run_web_ui

    run_web_ui(str(cfg_path), share=share, port=port)
