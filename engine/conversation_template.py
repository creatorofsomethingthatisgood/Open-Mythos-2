"""Conversation Template Manager

Manages reusable conversation templates that bundle a system prompt,
generation parameters, initial context messages, and RAG settings.
Templates let users save and restore session setups for common workflows
(coding, creative writing, security audits, etc.).

Templates are stored as JSON files in ~/.config/mythos/templates/.
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── constants ──────────────────────────────────────────────────────────

_TEMPLATES_DIR = "templates"

_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]{1,50}$")

_DEFAULT_GENERATION_PARAMS: Dict[str, Any] = {
    "temperature": 0.7,
    "top_p": 0.9,
    "top_k": 40,
    "repeat_penalty": 1.1,
    "max_tokens": 2048,
}


# ── helpers ────────────────────────────────────────────────────────────


def _mythos_home() -> Path:
    """Return the Mythos home directory.

    Checks MYTHOS_HOME env var first, falls back to ~/.config/mythos.
    """
    return Path(
        os.environ.get("MYTHOS_HOME", Path.home() / ".config" / "mythos")
    )


def _templates_dir() -> Path:
    """Return (and create) the templates directory."""
    d = _mythos_home() / _TEMPLATES_DIR
    d.mkdir(parents=True, exist_ok=True)
    return d


def _validate_name(name: str) -> bool:
    """Check that a template name is safe and within length limits.

    Args:
        name: Template name to validate.

    Returns:
        True if the name is valid (alphanumeric, dash, underscore, max 50 chars).
    """
    return bool(_NAME_RE.match(name))


# ── manager ────────────────────────────────────────────────────────────


class ConversationTemplateManager:
    """Create, save, load, and delete conversation templates.

    Each template captures a full session setup: system prompt file,
    generation parameters, seed messages, RAG toggle, and metadata.

    Args:
        config: Project configuration dict (loaded from config.yaml).
    """

    def __init__(self, config: dict) -> None:
        self.config = config
        self._templates_dir = _templates_dir()

    # ── public API ─────────────────────────────────────────────────────

    def save_template(self, template: dict) -> str:
        """Save a template to disk as JSON.

        Args:
            template: Template dict with keys matching the template
                structure (name, system_prompt_file, generation_params,
                initial_messages, rag_enabled, tags, created_at,
                description).

        Returns:
            The template name.

        Raises:
            ValueError: If the template name is invalid.
        """
        name = template.get("name", "")
        if not _validate_name(name):
            raise ValueError(
                f"Invalid template name: {name!r}. "
                "Use alphanumeric characters, dashes, or underscores (max 50 chars)."
            )

        path = self._templates_dir / f"{name}.json"
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(template, f, indent=2, ensure_ascii=False)
            logger.debug("Saved template %s to %s", name, path)
        except OSError as exc:
            logger.error("Failed to save template %s: %s", name, exc)
            raise

        return name

    def load_template(self, name: str) -> Optional[dict]:
        """Load a template from disk.

        Args:
            name: Template name to load.

        Returns:
            Template dict, or None if the template does not exist.

        Raises:
            ValueError: If the template name is invalid.
        """
        if not _validate_name(name):
            raise ValueError(
                f"Invalid template name: {name!r}. "
                "Use alphanumeric characters, dashes, or underscores (max 50 chars)."
            )

        path = self._templates_dir / f"{name}.json"
        if not path.exists():
            logger.debug("Template %s not found at %s", name, path)
            return None

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to load template %s: %s", name, exc)
            return None

    def list_templates(self) -> List[dict]:
        """List all saved templates with summary metadata.

        Returns:
            List of dicts, each containing name, description,
            created_at, and tags.
        """
        summaries: List[dict] = []
        for path in sorted(self._templates_dir.glob("*.json")):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                summaries.append(
                    {
                        "name": data.get("name", path.stem),
                        "description": data.get("description", ""),
                        "created_at": data.get("created_at", ""),
                        "tags": data.get("tags", []),
                    }
                )
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("Skipping malformed template %s: %s", path, exc)
        return summaries

    def delete_template(self, name: str) -> bool:
        """Delete a template from disk.

        Args:
            name: Template name to delete.

        Returns:
            True if the template was deleted, False if it did not exist.

        Raises:
            ValueError: If the template name is invalid.
        """
        if not _validate_name(name):
            raise ValueError(
                f"Invalid template name: {name!r}. "
                "Use alphanumeric characters, dashes, or underscores (max 50 chars)."
            )

        path = self._templates_dir / f"{name}.json"
        if not path.exists():
            logger.debug("Template %s not found for deletion", name)
            return False

        try:
            path.unlink()
            logger.debug("Deleted template %s", name)
            return True
        except OSError as exc:
            logger.error("Failed to delete template %s: %s", name, exc)
            return False

    def create_from_session(self, name: str, session_state: dict) -> dict:
        """Create a template from the current session state.

        Builds a template dict using the active session's system prompt
        file and generation parameters. Initial messages are left empty
        for the user to fill in later.

        Args:
            name: Name for the new template.
            session_state: Dict with keys system_prompt_file,
                generation_params, rag_enabled from the active session.

        Returns:
            The newly created template dict.

        Raises:
            ValueError: If the template name is invalid.
        """
        if not _validate_name(name):
            raise ValueError(
                f"Invalid template name: {name!r}. "
                "Use alphanumeric characters, dashes, or underscores (max 50 chars)."
            )

        generation_params = dict(_DEFAULT_GENERATION_PARAMS)
        generation_params.update(session_state.get("generation_params", {}))

        template: Dict[str, Any] = {
            "name": name,
            "system_prompt_file": session_state.get("system_prompt_file", "prompts/default.txt"),
            "generation_params": generation_params,
            "initial_messages": [],
            "rag_enabled": session_state.get("rag_enabled", False),
            "tags": [],
            "created_at": datetime.now(timezone.utc).isoformat(),
            "description": "",
        }

        return template
