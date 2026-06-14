"""
User configuration under ~/.config/mythos (or MYTHOS_HOME).
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LLM_CONFIG = PACKAGE_ROOT / "config.yaml"
PROMPTS_DIR = PACKAGE_ROOT / "prompts"
DEFAULT_PROMPT_FILE = PROMPTS_DIR / "open-2.txt"


def mythos_home() -> Path:
    return Path(os.environ.get("MYTHOS_HOME", Path.home() / ".config" / "mythos")).expanduser()


def user_config_path() -> Path:
    return mythos_home() / "config.yaml"


def llm_config_path() -> Path:
    """Full Mythos LLM + RAG settings (copied on init)."""
    return mythos_home() / "mythos.yaml"


def chroma_root() -> Path:
    return mythos_home() / "chroma_db"


def models_hint_dir() -> Path:
 return mythos_home() / "models"


def cross_session_memory_path() -> Path:
 """Directory for cross-session memory facts (JSON store)."""
 return mythos_home() / "memory"


def _default_user_config() -> Dict[str, Any]:
    return {
        "version": 1,
        "scan_paths": [],
        "security": {
            "min_severity": "low",
            "static_enabled": True,
            "deep_temperature": 0.2,
            "deep_max_tokens": 4096,
        },
        "scan": {
            "max_file_bytes": 2_097_152,
            "exclude_dirs": [
                ".git", "node_modules", "__pycache__", ".pytest_cache",
                "venv", ".venv", "dist", "build", ".next", "coverage",
                "chroma_db", "models", ".mypy_cache", "target", "vendor",
                ".cache", "conversations", "benchmarks", "lora", "install-pip",
            ],
        },
    }


def load_user_config() -> Dict[str, Any]:
    path = user_config_path()
    if not path.exists():
        return _default_user_config()
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    merged = _default_user_config()
    merged.update({k: v for k, v in data.items() if k != "scan_paths"})
    if "security" in data:
        merged["security"].update(data["security"])
    if "scan" in data:
        merged["scan"].update(data["scan"])
    merged["scan_paths"] = data.get("scan_paths", [])
    return merged


def save_user_config(config: Dict[str, Any]) -> Path:
    mythos_home().mkdir(parents=True, exist_ok=True)
    path = user_config_path()
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(config, f, default_flow_style=False, sort_keys=False)
    return path


def ensure_initialized() -> Dict[str, Any]:
    """Load config; create defaults if missing."""
    if user_config_path().exists():
        return load_user_config()
    return init_config(quiet=True)


def init_config(quiet: bool = False) -> Dict[str, Any]:
    home = mythos_home()
    home.mkdir(parents=True, exist_ok=True)
    models_hint_dir().mkdir(parents=True, exist_ok=True)

    user_cfg = _default_user_config()
    save_user_config(user_cfg)

    llm_dest = llm_config_path()
    if DEFAULT_LLM_CONFIG.exists() and not llm_dest.exists():
        shutil.copy2(DEFAULT_LLM_CONFIG, llm_dest)
        _patch_llm_config_for_user(llm_dest)

    if not quiet:
        print(f"✓ Config directory: {home}")
        print(f"✓ User config:      {user_config_path()}")
        print(f"✓ LLM config:       {llm_dest}")
        print(f"✓ Models directory: {models_hint_dir()}/")
        print()
        print("Next steps:")
        print("  mythos path add ~/your/project")
        print("  mythos scan                    # instant static findings")
        print("  mythos model download          # for AI deep scans")
        print("  mythos scan --deep")

    return user_cfg


def _patch_llm_config_for_user(llm_path: Path) -> None:
    """Point models, cache, and data dirs to ~/.config/mythos (shared across clones)."""
    with open(llm_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}

    home = mythos_home()
    model = cfg.setdefault("model", {})
    name = model.get("filename", "Qwen2.5-7B-Instruct-Q4_K_M.gguf")
    model["path"] = str(models_hint_dir() / name)

    rag = cfg.setdefault("rag", {})
    rag["persist_dir"] = str(chroma_root())
    rag["hf_cache_dir"] = str(home / "cache" / "huggingface")
    rag["docs_dir"] = str(home / "rag_docs")
    rag["enabled"] = rag.get("enabled", False)

    mem = cfg.setdefault("memory", {})
    mem["conversations_dir"] = str(home / "conversations")
    cs = mem.setdefault("cross_session", {})
    cs.setdefault("data_dir", str(cross_session_memory_path()))

    sys_cfg = cfg.setdefault("system", {})
    default_prompt = DEFAULT_PROMPT_FILE if DEFAULT_PROMPT_FILE.exists() else PROMPTS_DIR / "default.txt"
    if default_prompt.exists():
        sys_cfg["prompt_file"] = str(default_prompt)

    log_cfg = cfg.setdefault("logging", {})
    log_cfg["file"] = str(home / "mythos.log")

    from engine.chat_config import merge_chat_defaults

    cfg = merge_chat_defaults(cfg)

    with open(llm_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f, default_flow_style=False, sort_keys=False)


def ensure_chat_edit_config() -> None:
    """Ensure ~/.config/mythos/mythos.yaml has unlimited chat limits and enough max_tokens."""
    llm = llm_config_path()
    if not llm.exists():
        return
    with open(llm, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    from engine.chat_config import merge_chat_defaults

    merged = merge_chat_defaults(cfg)
    gen = merged.setdefault("generation", {})
    model_cfg = merged.setdefault("model", {})
    
    # Check if we actually need to write changes by looking at the ORIGINAL config
    # We must do this BEFORE we potentially modify merged and affect its references
    orig_gen = cfg.get("generation") if isinstance(cfg.get("generation"), dict) else {}
    orig_model = cfg.get("model") if isinstance(cfg.get("model"), dict) else {}
    current_max = int(orig_gen.get("max_tokens", 2048))
    current_ctx = int(orig_model.get("context_length", 4096))

    if int(gen.get("max_tokens", 2048)) < 8192:
        gen["max_tokens"] = 8192
    
    # Ensure context_length is at least as large as max_tokens to prevent startup errors
    if int(model_cfg.get("context_length", 4096)) < int(gen["max_tokens"]):
        model_cfg["context_length"] = int(gen["max_tokens"])

    old_chat = cfg.get("chat") if isinstance(cfg.get("chat"), dict) else {}
    old_fix = old_chat.get("fix") if isinstance(old_chat.get("fix"), dict) else {}
    old_lf = old_chat.get("local_files") if isinstance(old_chat.get("local_files"), dict) else {}
    limits_need_upgrade = (
        int(old_fix.get("max_rewrite_files", 5) or 0) > 0
        or int(old_lf.get("max_files", 10) or 0) > 0
        or int(old_lf.get("max_dir_sample_files", 5) or 0) > 0
    )
    old_pf = str(cfg.get("system", {}).get("prompt_file", "")).lower()
    prompt_should_upgrade = any(
        x in old_pf for x in ("security_audit", "default.txt", "default")
    ) and "security_fix" not in old_pf
    if prompt_should_upgrade and DEFAULT_PROMPT_FILE.exists():
        merged.setdefault("system", {})["prompt_file"] = str(DEFAULT_PROMPT_FILE)
    
    need_write = (
        not isinstance(cfg.get("chat"), dict)
        or limits_need_upgrade
        or prompt_should_upgrade
        or current_max < 8192
        or current_ctx < 8192
    )
    if need_write:
        with open(llm, "w", encoding="utf-8") as f:
            yaml.safe_dump(merged, f, default_flow_style=False, sort_keys=False)


def migrate_repo_models_to_user_home() -> None:
    """Link or reuse GGUF files from a repo checkout into ~/.config/mythos/models."""
    dest_dir = models_hint_dir()
    dest_dir.mkdir(parents=True, exist_ok=True)
    repo_models = PACKAGE_ROOT / "models"
    if not repo_models.is_dir():
        return
    for src in repo_models.glob("*.gguf"):
        target = dest_dir / src.name
        if target.exists():
            continue
        try:
            target.symlink_to(src.resolve())
        except OSError:
            pass


def resolve_chat_config(explicit: Optional[str] = None) -> Path:
    """Config file for chat/web: user home first, then repo config.yaml."""
    if explicit and explicit != "config.yaml":
        return Path(explicit).expanduser().resolve()

    ensure_initialized()
    migrate_repo_models_to_user_home()
    user_llm = llm_config_path()
    if user_llm.exists():
        return user_llm

    repo_cfg = PACKAGE_ROOT / "config.yaml"
    if repo_cfg.exists():
        return repo_cfg.resolve()

    return user_llm


def list_scan_paths(config: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    cfg = config or load_user_config()
    return list(cfg.get("scan_paths") or [])


def add_scan_path(
    directory: str,
    label: Optional[str] = None,
    config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    cfg = config or load_user_config()
    resolved = Path(directory).expanduser().resolve()
    if not resolved.is_dir():
        raise FileNotFoundError(f"Not a directory: {resolved}")

    paths: List[Dict[str, Any]] = cfg.setdefault("scan_paths", [])
    for entry in paths:
        if Path(entry["path"]).resolve() == resolved:
            if label:
                entry["label"] = label
            save_user_config(cfg)
            return entry

    entry = {
        "id": resolved.name[:32] or "project",
        "path": str(resolved),
        "label": label or resolved.name,
    }
    paths.append(entry)
    save_user_config(cfg)
    return entry


def remove_scan_path(target: str, config: Optional[Dict[str, Any]] = None) -> bool:
    cfg = config or load_user_config()
    paths: List[Dict[str, Any]] = cfg.get("scan_paths") or []
    target_path = Path(target).expanduser().resolve()
    new_paths = []
    removed = False
    for entry in paths:
        ep = Path(entry["path"]).resolve()
        if entry.get("id") == target or ep == target_path:
            removed = True
            continue
        new_paths.append(entry)
    if removed:
        cfg["scan_paths"] = new_paths
        save_user_config(cfg)
    return removed


def resolve_targets(
    path_arg: Optional[str] = None,
    config: Optional[Dict[str, Any]] = None,
) -> List[Path]:
    if path_arg:
        p = Path(path_arg).expanduser().resolve()
        if not p.is_dir():
            raise FileNotFoundError(f"Not a directory: {p}")
        return [p]

    entries = list_scan_paths(config)
    if not entries:
        raise RuntimeError(
            "No scan paths configured. Add one with:\n"
            "  mythos path add /path/to/your/code"
        )
    return [Path(e["path"]).resolve() for e in entries]
