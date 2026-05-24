"""Default chat / file-edit settings merged into every Mythos config load."""

from __future__ import annotations

import copy
from typing import Any, Dict, Optional

# Defaults for reading and writing user codebases from chat
DEFAULT_CHAT: Dict[str, Any] = {
    "local_files": {
        "enabled": True,
        "static_scan": True,
        "max_files": 0,  # 0 = unlimited files loaded per message
        "max_file_bytes": 2_097_152,
        "max_context_chars": 30_000,
        "max_dir_sample_files": 0,  # 0 = unlimited samples from a directory scan
    },
    "fix": {
        "enabled": True,
        "allow_edit": True,
        "auto_write_patches": False,
        "max_rewrite_files": 0,  # 0 = unlimited files per rewrite/fix run
        "show_finding_rationale": True,  # progress: why each file is being rewritten
        "stream_rewrite": False,  # stream model tokens during dedicated rewrite (noisy)
        "bitacora": True,  # progressive live journal during fix/rewrite (terminal)
    },
}


def file_limit(value: Any, default: int = 0) -> Optional[int]:
    """Return a positive cap, or None when unlimited (0 or negative)."""
    try:
        n = int(value if value is not None else default)
    except (TypeError, ValueError):
        n = default
    return None if n <= 0 else n


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    out = copy.deepcopy(base)
    for key, val in override.items():
        if key in out and isinstance(out[key], dict) and isinstance(val, dict):
            out[key] = _deep_merge(out[key], val)
        else:
            out[key] = val
    return out


def apply_unlimited_chat_limits(chat: Dict[str, Any]) -> Dict[str, Any]:
    """Force unlimited file/fix/rewrite counts (0 = no cap)."""
    out = copy.deepcopy(chat)
    lf = out.setdefault("local_files", {})
    lf["max_files"] = 0
    lf["max_dir_sample_files"] = 0
    fix = out.setdefault("fix", {})
    fix["max_rewrite_files"] = 0
    return out


def merge_chat_defaults(config: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure chat.local_files + chat.fix exist with unlimited edit defaults."""
    cfg = dict(config or {})
    user_chat = cfg.get("chat") if isinstance(cfg.get("chat"), dict) else {}
    cfg["chat"] = apply_unlimited_chat_limits(_deep_merge(DEFAULT_CHAT, user_chat))
    return cfg


def allow_disk_edit(config: Dict[str, Any]) -> bool:
    return bool(
        merge_chat_defaults(config)
        .get("chat", {})
        .get("fix", {})
        .get("allow_edit", True)
    )
