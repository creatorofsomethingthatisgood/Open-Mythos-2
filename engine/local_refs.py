"""
Resolve local file/directory references from chat messages for inline context.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import unquote, urlparse

logger = logging.getLogger(__name__)


def _truncate_text(text: str, max_chars: int) -> str:
    suffix = "\n\n[... truncated for context limit ...]"
    if len(text) <= max_chars:
        return text
    keep = max(0, max_chars - len(suffix))
    return text[:keep] + suffix

FILE_URL_RE = re.compile(r"\bfile://[^\s<>\"'\]`]+", re.IGNORECASE)
ABS_PATH_RE = re.compile(
    r"""(?:^|[\s(\[{])"""
    r"""(?P<path>"""
    r"""~[a-zA-Z0-9_./\\-]+"""
    r"""|/[a-zA-Z0-9_./\\-]+"""
    r"""|[A-Za-z]:\\[^\s<>\"'\]`]+"""
    r""")""",
    re.MULTILINE,
)

TEXT_EXTENSIONS = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".go", ".java", ".rb", ".php",
    ".cs", ".rs", ".swift", ".kt", ".scala", ".sql", ".sh", ".bash",
    ".yaml", ".yml", ".json", ".toml", ".cfg", ".ini", ".env",
    ".html", ".vue", ".svelte", ".graphql", ".prisma",
    ".md", ".txt", ".csv", ".xml", ".css", ".scss",
}


def _strip_ref(raw: str) -> str:
    return raw.strip().strip(".,;:!?\"'`)")


def ref_to_path(ref: str) -> Path:
    """Turn a file:// URL or filesystem path string into a Path."""
    ref = _strip_ref(ref)
    if ref.lower().startswith("file://"):
        parsed = urlparse(ref)
        path = unquote(parsed.path)
        if parsed.netloc and len(parsed.netloc) == 1:
            path = f"{parsed.netloc}:{path}"
        elif parsed.netloc and parsed.netloc not in ("", "localhost"):
            path = f"/{parsed.netloc}{path}"
        return Path(path).expanduser()
    return Path(ref).expanduser()


def extract_local_refs(text: str) -> List[str]:
    """Find file:// URLs and absolute paths mentioned in a chat message."""
    seen: set[str] = set()
    refs: List[str] = []

    for match in FILE_URL_RE.finditer(text):
        raw = _strip_ref(match.group(0))
        if raw and raw not in seen:
            seen.add(raw)
            refs.append(raw)

    for match in ABS_PATH_RE.finditer(text):
        raw = _strip_ref(match.group("path"))
        lower = raw.lower()
        if lower.startswith(("http://", "https://", "ftp://", "file://")):
            continue
        if not raw or raw in seen:
            continue
        seen.add(raw)
        refs.append(raw)

    return refs


def _format_findings(findings: List[Any], limit: int = 40) -> str:
    if not findings:
        return "No static rule matches (run deeper review for logic flaws)."
    lines = ["STATIC SCAN FINDINGS:"]
    for f in findings[:limit]:
        lines.append(
            f"- [{f.severity.upper()}] {f.rule_id} {f.path}:{f.line} — {f.title}\n"
            f"  {f.snippet}\n  Fix: {f.recommendation}"
        )
    if len(findings) > limit:
        lines.append(f"... and {len(findings) - limit} more findings")
    return "\n".join(lines)


def _read_file_block(path: Path, max_file_bytes: int) -> Tuple[str, Optional[str]]:
    try:
        size = path.stat().st_size
    except OSError as exc:
        return "", f"Cannot read {path}: {exc}"

    if size > max_file_bytes:
        return (
            "",
            f"Skipped {path} ({size} bytes > {max_file_bytes} limit)",
        )

    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError as exc:
        return "", f"Cannot read {path}: {exc}"

    if not text.strip():
        return "", f"Skipped empty file: {path}"

    header = f"--- FILE: {path} ({size} bytes) ---"
    return f"{header}\n{text}", None


def _resolve_targets(refs: List[str]) -> Tuple[List[Path], List[str]]:
    targets: List[Path] = []
    notices: List[str] = []
    seen_paths: set[str] = set()

    for ref in refs:
        path = ref_to_path(ref)
        try:
            resolved = path.resolve()
        except OSError:
            notices.append(f"Invalid path: {ref}")
            continue

        key = str(resolved)
        if key in seen_paths:
            continue
        seen_paths.add(key)

        if not resolved.exists():
            notices.append(f"Not found: {resolved}")
            continue

        targets.append(resolved)

    return targets, notices


def build_local_file_context(
    message: str,
    config: Optional[Dict[str, Any]] = None,
) -> Tuple[str, List[str]]:
    """
    Load local files/dirs referenced in a message and build prompt context.

    Returns:
        (context_block, status_notices)
    """
    cfg = (config or {}).get("chat", {}).get("local_files", {})
    if cfg.get("enabled", True) is False:
        return "", []

    max_file_bytes = int(cfg.get("max_file_bytes", 2 * 1024 * 1024))
    max_context_chars = int(cfg.get("max_context_chars", 30000))
    max_files = int(cfg.get("max_files", 10))
    static_scan = bool(cfg.get("static_scan", True))

    refs = extract_local_refs(message)
    if not refs:
        return "", []

    targets, notices = _resolve_targets(refs)
    if not targets:
        return "", notices

    blocks: List[str] = []
    files_loaded = 0

    try:
        from mythos_cli.static_scanner import scan_directory, scan_file
    except ImportError:
        scan_directory = None  # type: ignore[assignment,misc]
        scan_file = None  # type: ignore[assignment,misc]
        if static_scan:
            notices.append("Static scanner unavailable (mythos_cli not installed)")

    for target in targets:
        if target.is_dir():
            if static_scan and scan_directory:
                findings = scan_directory(
                    target,
                    max_file_bytes=max_file_bytes,
                )
                blocks.append(
                    f"LOCAL DIRECTORY: {target}\n{_format_findings(findings)}"
                )
                notices.append(
                    f"Scanned directory {target} ({len(findings)} finding(s))"
                )
            else:
                notices.append(f"Directory noted (enable static_scan): {target}")
            continue

        if not target.is_file():
            notices.append(f"Not a file or directory: {target}")
            continue

        if files_loaded >= max_files:
            notices.append(f"File limit ({max_files}) reached; skipped {target}")
            continue

        content, err = _read_file_block(target, max_file_bytes)
        if err:
            notices.append(err)
            continue

        section_parts = [content]
        if static_scan and scan_file:
            findings = scan_file(target, target.parent)
            section_parts.append(_format_findings(findings))
        blocks.append("\n\n".join(section_parts))
        files_loaded += 1
        notices.append(f"Loaded {target}")

    if not blocks:
        return "", notices

    context = (
        "LOCAL FILES REFERENCED BY USER (read from disk on this machine):\n\n"
        + "\n\n".join(blocks)
    )
    context = _truncate_text(context, max_context_chars)
    return context, notices


def enrich_system_prompt(
    base_prompt: str,
    message: str,
    config: Optional[Dict[str, Any]] = None,
) -> Tuple[str, List[str]]:
    """Append local file context to a system prompt when paths are detected."""
    local_context, notices = build_local_file_context(message, config)
    if not local_context:
        return base_prompt, notices
    return f"{base_prompt}\n\nADDITIONAL CONTEXT:\n{local_context}", notices
