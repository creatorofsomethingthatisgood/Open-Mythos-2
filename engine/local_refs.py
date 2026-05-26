"""
Resolve local file/directory references from chat messages for inline context.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import unquote, urlparse

from engine.chat_config import file_limit, merge_chat_defaults

logger = logging.getLogger(__name__)

# Rule IDs whose findings expose a literal secret on the matched line.
SECRET_RULES: Set[str] = {
    "SEC001",  # Private key / PEM block
    "SEC002",  # AWS access key
    "SEC003",  # Hardcoded password
    "SEC004",  # API key / token
    "SEC005",  # JWT secret / signing key
    "SEC014",  # Generic secret assignment
}


def _truncate_text(text: str, max_chars: int) -> str:
    suffix = "\n\n[... truncated for context limit ...]"
    if len(text) <= max_chars:
        return text
    keep = max(0, max_chars - len(suffix))
    return text[:keep] + suffix

FILE_URL_RE = re.compile(r"\bfile://[^\s<>\"'\]`]+", re.IGNORECASE)
# Paths in single or double quotes: '/Users/me/app' or "/Users/me/app"
QUOTED_PATH_RE = re.compile(
    r"""['"](?P<path>(?:~|/|[A-Za-z]:)[^'"]{2,})['"]""",
)
# "in this '/Users/me/project'" or "in '/Users/me/project'"
THIS_QUOTED_PATH_RE = re.compile(
    r"""\b(?:in\s+)?this\s+['"](?P<path>(?:~|/|[A-Za-z]:)[^'"]{2,})['"]""",
    re.IGNORECASE,
)
# Paths after "in" without quotes
IN_PATH_RE = re.compile(
    r"""\bin\s+['"]?(?P<path>(?:~|/)[^\s'"]+)['"]?""",
    re.IGNORECASE,
)
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

# Rules whose findings carry the literal secret on the matched line. We mask
# those lines (and their snippets) before embedding file contents into a
# prompt so secrets are not sent to the model.
SECRET_RULES = frozenset({"SEC001", "SEC002", "SEC003", "SEC004", "SEC005", "SEC014"})

_REDACTED_LINE = "<redacted: secret flagged by static scan>"
_REDACTED_SNIPPET = "<redacted>"


def _redact_secret_lines(
    text: str,
    findings: List[Any],
    line_offset: int = 0,
) -> str:
    """Replace lines flagged by SECRET_RULES with a redaction marker.

    line_offset: lines of header prepended to `text` before the file body
    (finding.line is 1-based against the body, so body-line N maps to
    text-line N + line_offset).
    """
    secret_lines = {
        f.line + line_offset for f in findings
        if getattr(f, "rule_id", "") in SECRET_RULES and getattr(f, "line", 0) > 0
    }
    if not secret_lines:
        return text
    out: List[str] = []
    for idx, line in enumerate(text.splitlines(keepends=True), start=1):
        if idx in secret_lines:
            ending = "\n" if line.endswith(("\n", "\r")) else ""
            out.append(f"{_REDACTED_LINE}{ending}")
        else:
            out.append(line)
    return "".join(out)


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


def _add_ref(refs: List[str], seen: set[str], raw: str) -> None:
    raw = _strip_ref(raw)
    if not raw or raw in seen:
        return
    lower = raw.lower()
    if lower.startswith(("http://", "https://", "ftp://")):
        return
    seen.add(raw)
    refs.append(raw)


def extract_local_refs(text: str) -> List[str]:
    """Find file:// URLs, quoted paths, and absolute paths in a message."""
    seen: set[str] = set()
    refs: List[str] = []

    for match in FILE_URL_RE.finditer(text):
        _add_ref(refs, seen, match.group(0))

    for match in QUOTED_PATH_RE.finditer(text):
        _add_ref(refs, seen, match.group("path"))

    for match in THIS_QUOTED_PATH_RE.finditer(text):
        _add_ref(refs, seen, match.group("path"))

    for match in IN_PATH_RE.finditer(text):
        _add_ref(refs, seen, match.group("path"))

    for match in ABS_PATH_RE.finditer(text):
        _add_ref(refs, seen, match.group("path"))

    return refs


def extract_local_refs_from_messages(messages: List[Dict[str, str]]) -> List[str]:
    """Collect paths mentioned in recent user messages (newest first)."""
    seen: set[str] = set()
    refs: List[str] = []
    for msg in reversed(messages):
        if msg.get("role") != "user":
            continue
        for ref in extract_local_refs(msg.get("content", "")):
            if ref not in seen:
                seen.add(ref)
                refs.append(ref)
    return refs


def _redact_secret_lines(
    text: str, findings: List[Any], line_offset: int = 0
) -> str:
    """Replace lines flagged by secret rules with a redaction placeholder.

    *line_offset* accounts for extra header lines prepended by the caller
    (e.g. the ``--- FILE: … ---`` header from ``_read_file_block`` adds 1).
    """
    # Collect 0-based line indices (in *text*) that must be redacted.
    redact_lines: Set[int] = set()
    for f in findings:
        if f.rule_id in SECRET_RULES:
            # f.line is 1-based in the *original* file; shift by offset
            # to map into the *text* string's line numbering.
            idx = f.line - 1 + line_offset
            redact_lines.add(idx)
            # SEC001 (PEM private key): the BEGIN line is flagged, but the
            # key body and END line also contain secret material.  Redact
            # the full PEM block so the base64 payload doesn't leak.
            if f.rule_id == "SEC001":
                text_lines = text.split("\n")
                i = idx
                while i < len(text_lines):
                    i += 1
                    if i < len(text_lines):
                        redact_lines.add(i)
                    if i < len(text_lines) and "-----END" in text_lines[i]:
                        break

    if not redact_lines:
        return text

    text_lines = text.split("\n")
    for idx in sorted(redact_lines):
        if 0 <= idx < len(text_lines):
            text_lines[idx] = "<redacted: secret flagged by static scan>"
    return "\n".join(text_lines)


def _format_findings(findings: List[Any], limit: int = 40) -> str:
    if not findings:
        return "No static rule matches (run deeper review for logic flaws)."
    lines = ["STATIC SCAN FINDINGS:"]
    for f in findings[:limit]:
        snippet = _REDACTED_SNIPPET if f.rule_id in SECRET_RULES else f.snippet
        lines.append(
            f"- [{f.severity.upper()}] {f.rule_id} {f.path}:{f.line} — {f.title}\n"
            f"  {snippet}\n  Fix: {f.recommendation}"
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
    cfg = merge_chat_defaults(config or {}).get("chat", {}).get("local_files", {})
    if cfg.get("enabled", True) is False:
        return "", []

    max_file_bytes = int(cfg.get("max_file_bytes", 2 * 1024 * 1024))
    max_context_chars = int(cfg.get("max_context_chars", 30000))
    max_files = file_limit(cfg.get("max_files"), 0)
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

    max_dir_samples = file_limit(cfg.get("max_dir_sample_files"), 0)

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
                # Load real source from files with findings so the model does not invent paths
                seen_files: set[str] = set()
                loaded_from_dir = 0
                for f in findings:
                    if max_dir_samples is not None and loaded_from_dir >= max_dir_samples:
                        break
                    fp = (target / f.path).resolve()
                    key = str(fp)
                    if key in seen_files or not fp.is_file():
                        continue
                    seen_files.add(key)
                    if max_files is not None and files_loaded >= max_files:
                        break
                    content, err = _read_file_block(fp, max_file_bytes)
                    if err:
                        continue
                    file_findings = scan_file(fp, target) if scan_file else []
                    # _read_file_block prepends a 1-line "--- FILE: ... ---" header
                    content = _redact_secret_lines(content, file_findings, line_offset=1)
                    blocks.append(content)
                    if scan_file:
                        blocks.append(_format_findings(file_findings))
                    files_loaded += 1
                    loaded_from_dir += 1
                    notices.append(f"Loaded {fp}")
            else:
                notices.append(f"Directory noted (enable static_scan): {target}")
            continue

        if not target.is_file():
            notices.append(f"Not a file or directory: {target}")
            continue

        if max_files is not None and files_loaded >= max_files:
            notices.append(f"File limit ({max_files}) reached; skipped {target}")
            continue

        content, err = _read_file_block(target, max_file_bytes)
        if err:
            notices.append(err)
            continue

        file_findings: List[Any] = []
        if static_scan and scan_file:
            file_findings = scan_file(target, target.parent)
            # _read_file_block prepends a 1-line "--- FILE: ... ---" header
            content = _redact_secret_lines(content, file_findings, line_offset=1)

        section_parts = [content]
        if static_scan and scan_file:
            section_parts.append(_format_findings(file_findings))
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
