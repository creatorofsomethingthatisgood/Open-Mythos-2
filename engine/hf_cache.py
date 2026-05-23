"""
Hugging Face cache and logging helpers for RAG embeddings.
Uses a project-local cache to avoid permission errors under ~/.cache.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


def configure_hf_cache(project_root: Path, cache_dir: str = ".cache/huggingface") -> Path:
    """Point HF Hub / transformers at a writable directory inside the project."""
    root = Path(project_root).resolve()
    cache_path = Path(cache_dir)
    if not cache_path.is_absolute():
        cache_path = root / cache_path
    cache_path.mkdir(parents=True, exist_ok=True)
    hub = cache_path / "hub"
    hub.mkdir(parents=True, exist_ok=True)

    os.environ.setdefault("HF_HOME", str(cache_path))
    os.environ.setdefault("HF_HUB_CACHE", str(hub))
    os.environ.setdefault("TRANSFORMERS_CACHE", str(hub))
    os.environ.setdefault("SENTENCE_TRANSFORMERS_HOME", str(cache_path))
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
    return cache_path


def quiet_hf_loggers(level: int = logging.WARNING) -> None:
    """Reduce Hugging Face / HTTP noise during chat startup."""
    for name in (
        "httpx",
        "httpcore",
        "huggingface_hub",
        "sentence_transformers",
        "transformers",
        "filelock",
    ):
        logging.getLogger(name).setLevel(level)


def hf_model_id(model_name: str) -> str:
    """Normalize short names to full Hugging Face repo ids."""
    if "/" in model_name:
        return model_name
    return f"sentence-transformers/{model_name}"


def _snapshot_dir(model_name: str, cache_path: Path) -> Path | None:
    repo_id = hf_model_id(model_name)
    repo_folder = "models--" + repo_id.replace("/", "--")
    snapshots = cache_path / "hub" / repo_folder / "snapshots"
    if not snapshots.is_dir():
        return None
    for d in sorted(snapshots.iterdir(), reverse=True):
        if d.is_dir():
            return d
    return None


def is_hf_model_cached(model_name: str, cache_path: Path) -> bool:
    """True if weights exist in a local hub snapshot (not just config stubs)."""
    snap = _snapshot_dir(model_name, cache_path)
    if snap is None:
        return False
    weight_names = (
        "model.safetensors",
        "pytorch_model.bin",
        "openvino_model.bin",
        "onnx/model.onnx",
    )
    return any((snap / name).is_file() for name in weight_names)


def _hub_repo_path(cache_path: Path, model_name: str) -> Path:
    repo_id = hf_model_id(model_name)
    repo_folder = "models--" + repo_id.replace("/", "--")
    return cache_path / "hub" / repo_folder


def clear_broken_hub_link(model_name: str, cache_path: Path) -> None:
    """Remove symlink to an unusable global cache so we can download locally."""
    target = _hub_repo_path(cache_path, model_name)
    if target.is_symlink() and not is_hf_model_cached(model_name, cache_path):
        target.unlink()
        logger.info("Removed broken HF cache symlink: %s", target)


def bootstrap_embedding_cache_from_user(model_name: str, cache_path: Path) -> bool:
    """
    If weights exist under ~/.cache/huggingface, symlink into the project cache.
    """
    if is_hf_model_cached(model_name, cache_path):
        return True

    legacy_root = Path.home() / ".cache" / "huggingface"
    target = _hub_repo_path(cache_path, model_name)
    target.parent.mkdir(parents=True, exist_ok=True)

    if is_hf_model_cached(model_name, legacy_root) and not target.exists():
        legacy = _hub_repo_path(legacy_root, model_name)
        try:
            target.symlink_to(legacy.resolve())
            logger.info("Using existing Hugging Face cache via symlink: %s", legacy)
        except OSError as e:
            logger.warning("Could not link legacy HF cache (%s): %s", legacy, e)
    return is_hf_model_cached(model_name, cache_path)


def load_sentence_transformer(model_name: str, cache_path: Path, prefer_offline: bool = True):
    """
    Load embedding model from local cache when possible.
    Falls back to a one-time Hub download into the project cache if offline load fails.
    """
    from sentence_transformers import SentenceTransformer

    bootstrap_embedding_cache_from_user(model_name, cache_path)
    model_id = hf_model_id(model_name)

    if prefer_offline and is_hf_model_cached(model_name, cache_path):
        try:
            logger.info("Loading embedding model from local cache: %s", model_id)
            return SentenceTransformer(model_id, local_files_only=True)
        except Exception as exc:
            logger.warning(
                "Offline embedding load failed (%s); downloading into %s",
                exc,
                cache_path,
            )
            clear_broken_hub_link(model_name, cache_path)

    logger.info("Downloading embedding model into project cache: %s", model_id)
    return SentenceTransformer(model_id)
