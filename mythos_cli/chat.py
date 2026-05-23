"""
Mythos Chat Launcher — starts the terminal (or web) chat interface.

Handles project-root discovery so `mythos` works from any directory.
Strategy: find the project root, then cd into it so all the relative-path
imports in engine/ (config.yaml, prompts/, models/, conversations/, etc.)
resolve correctly. The user's original cwd is preserved via $OLDPWD and
an environment variable so slash-commands like /file still work.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# The project directory is wherever this file's grandparent lives
# (installed via pip install -e .  =>  the repo checkout)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _find_project_root() -> Path:
    """Return the Mythos project root.

    Resolution order:
    1.  MYTHOS_ROOT env var (user override)
    2.  Walk upward from CWD looking for config.yaml + prompts/
    3.  The directory this package was installed from
    """
    # 1. explicit override
    env = os.environ.get("MYTHOS_ROOT")
    if env:
        p = Path(env)
        if p.is_dir():
            return p

    # 2. walk up from cwd — maybe user is inside a subfolder
    cwd = Path.cwd()
    for candidate in [cwd, *cwd.parents]:
        if (candidate / "config.yaml").exists() and (candidate / "prompts").is_dir():
            return candidate

    # 3. fallback: the repo root where this package lives
    return _PROJECT_ROOT


def _prepare_project_dir(root: Path) -> None:
    """Ensure the project directory has the runtime dirs the engine expects."""
    for d in ("conversations", "chroma_db", ".cache/huggingface", "models"):
        (root / d).mkdir(parents=True, exist_ok=True)


def _enter_project_root(root: Path) -> str:
    """cd into the project root so relative paths work.

    Returns the original cwd for restoration if needed.
    Also sets MYTHOS_PROJECT_ROOT and keeps $OLDPWD set.
    """
    original_cwd = os.getcwd()
    os.environ["MYTHOS_PROJECT_ROOT"] = str(root)
    os.environ["OLDPWD"] = original_cwd
    os.chdir(root)
    # Make sure the project root is on sys.path for engine/ and ui/ imports
    root_str = str(root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)
    return original_cwd


def launch_chat(config_path: str | None = None, verbose: bool = False) -> None:
    """Launch the Mythos terminal chat interface."""
    root = _find_project_root()
    _prepare_project_dir(root)
    original_cwd = _enter_project_root(root)

    if config_path and config_path != "config.yaml":
        cfg = config_path
    else:
        cfg = "config.yaml"

    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    from ui.terminal_ui import run_terminal_ui
    run_terminal_ui(cfg)


def launch_web(
    config_path: str | None = None,
    port: int = 7860,
    share: bool = False,
) -> None:
    """Launch the Mythos web UI."""
    root = _find_project_root()
    _prepare_project_dir(root)
    original_cwd = _enter_project_root(root)

    if config_path and config_path != "config.yaml":
        cfg = config_path
    else:
        cfg = "config.yaml"

    from ui.web_ui import run_web_ui
    run_web_ui(cfg, share=share, port=port)
