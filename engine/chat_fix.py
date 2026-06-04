"""
Fix vulnerabilities during chat -- detect intent, run auto-fix, guide the LLM,
and optionally apply patches from the assistant reply.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from engine.chat_config import allow_disk_edit, file_limit, merge_chat_defaults
from engine.progress import ProgressCallback, StreamCallback, emit_progress
from engine.local_refs import extract_local_refs, ref_to_path

logger = logging.getLogger(__name__)

FIX_INTENT_RE = re.compile(
    r"\b(fix\w*|patch\w*|remediat\w*|auto-?fix\w*|repair\w*|correct\w*)\b",
    re.IGNORECASE,
)
APPLY_INTENT_RE = re.compile(
    r"\b(apply|write|save|commit)\b",
    re.IGNORECASE,
)
CONFIRM_INTENT_RE = re.compile(
    r"\b(confirm|confirmed|yes|proceed|go ahead|do it)\b",
    re.IGNORECASE,
)
REWRITE_INTENT_RE = re.compile(
    r"\b(rewrite|rewrote|rewriting|overwrite|replace)\b",
    re.IGNORECASE,
)

PATCH_BLOCK_RE = re.compile(
    r"<<<MYTHOS_PATCH\s+path\s*=\s*(?P<path>[^>\n]+)>>>\s*"
    r"(?P<body>.*?)<<<END_PATCH>>>",
    re.DOTALL | re.IGNORECASE,
)
# Model sometimes omits END_PATCH -- grab fenced code after path= line
PATCH_LOOSE_RE = re.compile(
    r"<<<MYTHOS_PATCH\s+path\s*=\s*(?P<path>[^>\n]+)>>>\s*"
    r"(?:```[\w]*\n(?P<body>.*?)```|(?P<raw>[^\n<]+))",
    re.DOTALL | re.IGNORECASE,
)
# Audit/fix replies often use markdown headers + fences instead of <<<MYTHOS_PATCH>>>
MARKDOWN_PATCH_RE = re.compile(
    r"(?:^|\n)#{1,6}\s+(?:MYTHOS_PATCH\s+)?[`']?(?P<path>/[^\s`']+)[`']?\s*\n+"
    r"```[\w]*\s*\n(?P<body>.*?)```",
    re.MULTILINE | re.DOTALL | re.IGNORECASE,
)

MYTHOS_PATCH_FORMAT = """
<<<MYTHOS_PATCH path="/Users/you/your-repo/src/module/file.py">>>
```python
# complete file contents -- use the REAL absolute path from the user message
```
<<<END_PATCH>>>
"""

_PATCH_PLACEHOLDER_MARKERS = (
    "/absolute/path/to/",
    "/absolute/path/",
)

REWRITE_WARNING = (
    "WARNING: Full-file rewrite overwrites entire files on disk. "
    "Mythos does not create .bak backups -- commit or branch with git before continuing."
)

SECURITY_FIX_HINT = """
FIX MODE: Output ONLY MYTHOS_PATCH blocks -- one per changed file.
Each block must contain the COMPLETE file from line 1 to EOF (no snippets, no "..." placeholders).
No git diff, no partial edits, no ### markdown sections.
"""

REWRITE_HINT = """
REWRITE MODE: Reply with ONLY MYTHOS_PATCH block(s). Each block is the entire file.
Every line of the original file must appear (corrected). Partial files are rejected.
"""


def user_wants_rewrite(message: str) -> bool:
    return bool(REWRITE_INTENT_RE.search(message))


def user_wants_fix(message: str) -> bool:
    return bool(FIX_INTENT_RE.search(message)) or user_wants_rewrite(message)


def user_wants_apply(message: str) -> bool:
    return user_wants_fix(message) and (
        bool(APPLY_INTENT_RE.search(message))
        or user_wants_rewrite(message)
        or bool(CONFIRM_INTENT_RE.search(message))
    )


def active_prompt_is_security_audit(config: Optional[Dict[str, Any]] = None) -> bool:
    """True when the configured system prompt is audit-only (no MYTHOS_PATCH)."""
    pf = str((config or {}).get("system", {}).get("prompt_file", "")).lower()
    return "security_audit" in pf


def should_use_fix_system_prompt(
    message: str,
    *,
    rewrite_approved: bool = False,
) -> bool:
    """Use security_fix + MYTHOS_PATCH hints (not audit report format)."""
    return user_wants_fix(message) or rewrite_approved


def build_fix_system_prompt(
    prompt_manager: Any,
    base_prompt: str,
    message: str,
    *,
    rewrite_approved: bool = False,
) -> str:
    """Replace audit-style instructions with security_fix when rewriting."""
    if not should_use_fix_system_prompt(message, rewrite_approved=rewrite_approved):
        return base_prompt
    try:
        fix_prompt = prompt_manager.load_prompt("security_fix")
        return (
            f"{fix_prompt}\n\n{MYTHOS_PATCH_FORMAT}\n"
            f"{SECURITY_FIX_HINT}\n{REWRITE_HINT}"
        )
    except Exception:
        return f"{base_prompt}\n\n{MYTHOS_PATCH_FORMAT}\n{SECURITY_FIX_HINT}"


def user_confirms_rewrite(message: str) -> bool:
    """Short confirmation to proceed with a pending rewrite (e.g. 'yes', 'i confirm')."""
    text = message.strip()
    if not text:
        return False
    if FIX_INTENT_RE.search(message) or REWRITE_INTENT_RE.search(message):
        return False
    return bool(
        CONFIRM_INTENT_RE.search(message)
        or re.match(r"^(yes|y|confirm|i confirm)\.?$", text, re.IGNORECASE)
    )


def _fix_cfg(config: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    return merge_chat_defaults(config or {}).get("chat", {}).get("fix", {})


def format_finding_rationale(
    findings: list,
    *,
    max_items: int = 6,
) -> List[str]:
    """Human-readable lines explaining why a file is being rewritten."""
    if not findings:
        return ["  • No static findings -- applying general security hardening"]
    lines: List[str] = []
    for f in findings[:max_items]:
        rec = getattr(f, "recommendation", "") or ""
        detail = f.title if hasattr(f, "title") else str(f)
        if rec and len(rec) < 120:
            lines.append(f"  • [{f.severity}] line {f.line}: {detail} -- {rec}")
        else:
            lines.append(f"  • [{f.severity}] line {f.line}: {detail}")
    if len(findings) > max_items:
        lines.append(f"  • … and {len(findings) - max_items} more finding(s)")
    return lines


def emit_finding_rationale(
    path: Path,
    findings: list,
    on_progress: Optional[ProgressCallback],
    *,
    max_items: int = 6,
) -> None:
    emit_progress(f"Why {path.name} is being rewritten:", on_progress)
    for line in format_finding_rationale(findings, max_items=max_items):
        emit_progress(line, on_progress)


def format_rewrite_confirm_message(file_paths: List[str]) -> str:
    """Prompt text listing files that would be fully overwritten."""
    if not file_paths:
        return "No files identified for full-file rewrite."
    lines = [
        f"Rewrite {len(file_paths)} file(s) on disk? (complete file replace; use git, no .bak)",
    ]
    preview = 20
    for path in file_paths[:preview]:
        lines.append(f"  • {path}")
    if len(file_paths) > preview:
        lines.append(f"  … and {len(file_paths) - preview} more")
    return "\n".join(lines)


def should_auto_write_patches(
    message: str,
    config: Optional[Dict[str, Any]] = None,
    *,
    rewrite_approved: bool = False,
) -> bool:
    """Write MYTHOS_PATCH blocks to disk only after explicit user approval."""
    if not allow_disk_edit(config or {}):
        return False
    if rewrite_approved:
        return True
    cfg = merge_chat_defaults(config or {}).get("chat", {}).get("fix", {})
    return bool(cfg.get("auto_write_patches", False) and user_wants_apply(message))


def resolve_fix_targets(
    message: str,
    last_targets: Optional[List[Path]] = None,
    extra_refs: Optional[List[str]] = None,
) -> List[Path]:
    refs = extract_local_refs(message)
    for ref in extra_refs or []:
        if ref not in refs:
            refs.append(ref)
    if refs:
        targets: List[Path] = []
        seen: set[str] = set()
        for ref in refs:
            path = ref_to_path(ref)
            try:
                resolved = path.resolve()
            except OSError:
                continue
            key = str(resolved)
            if key in seen or not resolved.exists():
                continue
            seen.add(key)
            targets.append(resolved)
        return targets
    return list(last_targets or [])


def _format_fix_context(
    targets: List[Path],
    fix_results: list,
    findings: list,
    *,
    applied: bool,
) -> str:
    lines = [
        "CHAT AUTO-FIX (ran because the user asked to fix security issues):",
        f"Targets: {', '.join(str(t) for t in targets)}",
        f"Mode: {'scan preview (full-file rewrite uses MYTHOS_PATCH only)' if applied else 'scan preview only'}",
        "",
    ]
    pending = [f for f in fix_results if f.status in ("applied", "pending")]
    skipped = [f for f in fix_results if f.status == "skipped"]
    if pending:
        lines.append("Automatic line fixes:")
        for f in pending:
            lines.append(
                f"  - {f.path}:{f.line} ({f.rule_id}) {f.detail}\n"
                f"    - {f.before}\n    + {f.after}"
            )
    else:
        lines.append("No deterministic auto-fixes matched (see static findings below).")

    if skipped:
        lines.append(f"\nSkipped {len(skipped)} item(s) -- need manual/LLM fix (secrets, eval, SQL, etc.).")

    if findings:
        lines.append(f"\nRemaining static findings after fix ({len(findings)}):")
        for f in findings:
            lines.append(
                f"  - [{f.severity}] {f.path}:{f.line} {f.title} -- {f.recommendation}"
            )

    lines.append(
        "\nExplain remaining issues and output MYTHOS_PATCH blocks for files you rewrite."
    )
    return "\n".join(lines)


def handle_chat_fix(
    message: str,
    config: Optional[Dict[str, Any]] = None,
    *,
    last_targets: Optional[List[Path]] = None,
    extra_refs: Optional[List[str]] = None,
    confirm_apply: Optional[Callable[[str], bool]] = None,
    on_progress: Optional[ProgressCallback] = None,
) -> Tuple[str, List[str], List[Path], bool, List[str]]:
    """
    If the user wants fixes, scan targets and prepare full-file rewrite context.

    Line-level auto-fix is never written to disk here -- only full MYTHOS_PATCH files.

    confirm_apply: callable(prompt) -> bool; when provided, called for every fix
    request to ask whether to rewrite files (recommended). If None, writes only when
    user_wants_apply(message) is True.

    Returns:
        (context, status_notices, targets_touched, rewrite_approved, rewrite_file_paths)
    """
    cfg = merge_chat_defaults(config or {}).get("chat", {}).get("fix", {})
    if not cfg.get("enabled", True):
        return "", [], [], False, []

    if not cfg.get("allow_edit", True):
        return "", ["File edit disabled in config (chat.fix.allow_edit: false)"], [], False, []

    if not user_wants_fix(message):
        return "", [], list(last_targets or []), False, []

    targets = resolve_fix_targets(message, last_targets, extra_refs=extra_refs)
    rewrite_mode = user_wants_rewrite(message)
    emit_progress("Preparing security scan…", on_progress)
    if not targets:
        return (
            "",
            [
                "Fix requested -- add a path (e.g. ~/my-api) or use /file <path> first, "
                "then ask again: fix the vulns"
            ],
            [],
            False,
            [],
        )

    try:
        from mythos_cli.fix_runner import run_fix_on_path
    except ImportError:
        return "", ["Fix unavailable (mythos_cli not installed)"], targets, False, []

    all_findings = []
    all_fixes = []
    notices: List[str] = []
    emit_progress(REWRITE_WARNING, on_progress)
    notices.append(REWRITE_WARNING)

    # Scan only -- chat rewrite uses full-file MYTHOS_PATCH, not line-level edits.
    for target in targets:
        label = target.name if target.is_file() else str(target)
        emit_progress(f"Scanning {label}…", on_progress)
        findings, fixes = run_fix_on_path(target, dry_run=True)
        all_findings.extend(findings)
        all_fixes.extend(fixes)
        emit_progress(
            f"Scan complete: {label} -- {len(findings)} finding(s)",
            on_progress,
        )
        if _fix_cfg(config).get("show_finding_rationale", True) and findings:
            for line in format_finding_rationale(findings, max_items=4):
                emit_progress(line, on_progress)
        notices.append(f"Scanned {target} ({len(findings)} finding(s))")

    emit_progress("Selecting files for full-file rewrite…", on_progress)
    file_paths = _files_to_rewrite(targets, all_findings, config)
    if not file_paths:
        file_paths = resolve_rewrite_file_paths(targets, config)
    if not file_paths:
        for target in targets:
            if target.is_file():
                file_paths.append(str(target.resolve()))
    rewrite_approved = False
    if file_paths:
        emit_progress(
            f"Found {len(file_paths)} file(s) that may need a full rewrite",
            on_progress,
        )
        confirm_text = format_rewrite_confirm_message(file_paths)
        if confirm_apply is not None:
            emit_progress("Waiting for your confirmation to rewrite files…", on_progress)
            rewrite_approved = confirm_apply(confirm_text)
        elif user_wants_apply(message):
            rewrite_approved = True
        if rewrite_approved:
            msg = f"Rewrite approved for {len(file_paths)} file(s)"
            notices.append(msg)
            emit_progress(msg, on_progress)
        else:
            msg = (
                "Rewrite not confirmed -- model may reply with patches; "
                "nothing will be written until you confirm"
            )
            notices.append(msg)
            emit_progress(msg, on_progress)
    elif rewrite_mode:
        msg = "No files matched for rewrite -- check the path"
        notices.append(msg)
        emit_progress(msg, on_progress)

    ctx = _format_fix_context(targets, all_fixes, all_findings, applied=False)
    if file_paths:
        ctx += "\n\nTARGET FILES TO REWRITE (output one full MYTHOS_PATCH per file):\n"
        ctx += "\n".join(f"  - {p}" for p in file_paths)

    return ctx, notices, targets, rewrite_approved, file_paths


def resolve_rewrite_file_paths(
    targets: List[Path],
    config: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """Scan targets and list absolute paths that need a full-file MYTHOS_PATCH rewrite."""
    if not targets:
        return []
    all_findings: list = []
    try:
        from mythos_cli.fix_runner import run_fix_on_path

        for target in targets:
            findings, _ = run_fix_on_path(target.resolve(), dry_run=True)
            all_findings.extend(findings)
    except ImportError:
        pass
    return _files_to_rewrite(targets, all_findings, config)


def _files_to_rewrite(
    targets: List[Path],
    findings: list,
    config: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """Absolute paths the model should emit as full-file MYTHOS_PATCH blocks."""
    cfg = merge_chat_defaults(config or {}).get("chat", {}).get("fix", {})
    max_files = file_limit(cfg.get("max_rewrite_files"), 0)
    paths: List[str] = []

    for target in targets:
        if target.is_file():
            paths.append(str(target.resolve()))
            continue
        seen: set[str] = set()
        for f in findings:
            full = (target / f.path).resolve()
            key = str(full)
            if key in seen or not full.is_file():
                continue
            seen.add(key)
            paths.append(key)
        if not paths:
            continue

    if not paths:
        for target in targets:
            if target.is_file():
                paths.append(str(target.resolve()))
    if max_files is None:
        return paths
    return paths[:max_files]


def rewrite_context_for_targets(
    targets: List[Path],
    config: Optional[Dict[str, Any]] = None,
) -> str:
    """Extra system context listing files that must be rewritten in full."""
    files = _files_to_rewrite(targets, [], config)
    if not files:
        return ""
    return (
        "TARGET FILES TO REWRITE (complete file in MYTHOS_PATCH each):\n"
        + "\n".join(f"  - {p}" for p in files)
    )


def is_placeholder_patch_path(path: Path) -> bool:
    """Reject template paths copied from the prompt instead of real targets."""
    s = str(path).lower()
    return any(marker in s for marker in _PATCH_PLACEHOLDER_MARKERS)


def is_writable_patch_path(path: Path) -> bool:
    if is_placeholder_patch_path(path):
        return False
    if not path.is_absolute():
        return False
    return path.is_file() or path.parent.exists()


def _body_from_patch_match(body: str) -> str:
    body = body.strip()
    fence = re.match(r"^```\w*\n(.*?)```", body, re.DOTALL)
    if fence:
        return fence.group(1).strip()
    return body


def extract_patches_from_response(text: str) -> List[Tuple[Path, str]]:
    """Parse MYTHOS_PATCH blocks from an assistant message."""
    patches: List[Tuple[Path, str]] = []
    seen: set[str] = set()

    for match in PATCH_BLOCK_RE.finditer(text):
        raw_path = match.group("path").strip().strip("\"'")
        body = _body_from_patch_match(match.group("body"))
        path = Path(raw_path).expanduser()
        if not body or raw_path in seen or not is_writable_patch_path(path):
            continue
        seen.add(raw_path)
        patches.append((path, body.rstrip() + "\n"))

    if patches:
        return patches

    for match in PATCH_LOOSE_RE.finditer(text):
        raw_path = match.group("path").strip().strip("\"'")
        if raw_path in seen:
            continue
        body = match.group("body") or match.group("raw") or ""
        body = _body_from_patch_match(body)
        path = Path(raw_path).expanduser()
        if not body or not is_writable_patch_path(path):
            continue
        seen.add(raw_path)
        patches.append((path, body.rstrip() + "\n"))

    if patches:
        return patches

    for match in MARKDOWN_PATCH_RE.finditer(text):
        raw_path = match.group("path").strip().strip("\"'")
        if raw_path in seen:
            continue
        body = _body_from_patch_match(match.group("body"))
        path = Path(raw_path).expanduser()
        if not body or len(body.splitlines()) < 3 or not is_writable_patch_path(path):
            continue
        seen.add(raw_path)
        patches.append((path, body.rstrip() + "\n"))
    return patches


def apply_patches_from_response(
    text: str,
    *,
    confirm: Optional[Callable[[Path], bool]] = None,
    on_progress: Optional[ProgressCallback] = None,
) -> List[str]:
    """
    Write MYTHOS_PATCH blocks from the assistant reply.

    confirm: optional callable(path) -> bool before each write.
    """
    patches = extract_patches_from_response(text)
    if not patches:
        return []

    _cwd = Path.cwd().resolve()
    notices: List[str] = []
    for path, content in patches:
        if is_placeholder_patch_path(path):
            notices.append(f"Skipped placeholder path (use a real file from context): {path}")
            continue
        if not path.is_absolute():
            notices.append(f"Skipped relative path (use absolute): {path}")
            continue
        try:
            path.resolve().relative_to(_cwd)
        except ValueError:
            notices.append(f"Skipped (path outside project): {path}")
            continue
        if not path.parent.exists():
            notices.append(f"Skipped (path not found): {path}")
            continue
        if confirm is not None and not confirm(path):
            notices.append(f"Skipped (declined): {path}")
            emit_progress(f"Skipped (declined): {path}", on_progress)
            continue
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            emit_progress(f"Writing {path}…", on_progress)
            path.write_text(content, encoding="utf-8")
            size = len(content.encode("utf-8"))
            msg = f"Wrote {path} ({size:,} bytes)"
            notices.append(f"Wrote full file: {path}")
            emit_progress(msg, on_progress)
        except OSError as exc:
            notices.append(f"Failed {path}: {exc}")
            emit_progress(f"Failed {path}: {exc}", on_progress)
    return notices


def apply_patches_with_prompt(
    text: str,
    config: Optional[Dict[str, Any]] = None,
    *,
    message: str = "",
    confirm: Optional[Callable[[Path], bool]] = None,
    base_dirs: Optional[List[Path]] = None,
    rewrite_approved: bool = False,
    on_progress: Optional[ProgressCallback] = None,
) -> List[str]:
    """Write full-file MYTHOS_PATCH blocks only when approved."""
    del base_dirs  # paths must be absolute inside MYTHOS_PATCH

    if not allow_disk_edit(config or {}):
        return ["File edit disabled (chat.fix.allow_edit: false)"]

    patches = extract_patches_from_response(text)
    if not patches:
        # Terminal/web run dedicated rewrite after chat when fix mode has no parseable patch.
        return []

    if not should_auto_write_patches(message, config, rewrite_approved=rewrite_approved):
        return [
            f"Found {len(patches)} patch block(s) -- not written (rewrite not confirmed). "
            "Confirm rewrite to write full files to disk."
        ]

    if confirm is not None and not confirm(
        f"Write {len(patches)} full file(s) to disk? (no .bak; use git)"
    ):
        return ["Skipped writing files (declined)"]
    return apply_patches_from_response(text, confirm=None, on_progress=on_progress)


def generate_mythos_patch(
    engine: Any,
    prompt_manager: Any,
    config: Dict[str, Any],
    *,
    file_path: Path,
    source: str,
    finding_text: str,
    max_retries: int = 5,
    on_progress: Optional[ProgressCallback] = None,
    on_stream: Optional[StreamCallback] = None,
) -> Tuple[str, List[str]]:
    """
    Ask the model for a MYTHOS_PATCH-only reply; retry until parseable or attempts exhausted.
    """
    from engine.context_budget import fit_chat_context

    path = file_path.resolve()
    notices: List[str] = []

    try:
        patch_prompt = prompt_manager.load_prompt("mythos_patch_rewrite")
    except Exception:
        patch_prompt = (
            "Output only MYTHOS_PATCH with the full corrected file. "
            + MYTHOS_PATCH_FORMAT
        )

    system_prompt = f"{patch_prompt}\n\n{MYTHOS_PATCH_FORMAT}\n\nAbsolute path: {path}"
    gen_cfg = config.get("generation", {})
    max_tokens = int(gen_cfg.get("max_tokens", 8192))
    temperature = min(0.2, float(gen_cfg.get("temperature", 0.2)))
    reserve = config.get("context", {}).get("reserve_tokens", 2048)

    user_msg = (
        f"Rewrite this file with security fixes.\n"
        f"Absolute path (use exactly in MYTHOS_PATCH): {path}\n\n"
        f"Findings:\n{finding_text}\n\n"
        f"--- CURRENT FILE ---\n{source}\n--- END FILE ---\n\n"
        f"Reply with ONLY one MYTHOS_PATCH block containing the full corrected file."
    )

    response = ""
    total_attempts = max_retries + 1
    for attempt in range(total_attempts):
        retry_note = ""
        if attempt > 0:
            emit_progress(
                f"Retrying {path.name} -- previous reply was not a valid MYTHOS_PATCH "
                f"(attempt {attempt + 1}/{total_attempts})…",
                on_progress,
            )
            retry_note = (
                "\n\nYour previous reply was invalid. "
                f"Output ONLY:\n<<<MYTHOS_PATCH path=\"{path}\">>>\n"
                "```python\n<entire file>\n```\n<<<END_PATCH>>>"
            )
        else:
            emit_progress(
                f"Generating rewritten file: {path.name} "
                f"(attempt 1/{total_attempts})…",
                on_progress,
            )
        messages = [{"role": "user", "content": user_msg + retry_note}]
        msgs, sys_p, _ = fit_chat_context(
            engine, messages, system_prompt, reserve_tokens=reserve
        )
        prompt = engine.format_chat_prompt(msgs, sys_p)
        stream_rewrite = bool(_fix_cfg(config).get("stream_rewrite", False))
        if stream_rewrite and on_stream is not None:
            emit_progress(
                f"Streaming model output for {path.name} (MYTHOS_PATCH)…",
                on_progress,
            )
            chunks: List[str] = []
            for chunk in engine.generate(
                prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                stream=True,
            ):
                chunks.append(chunk)
                on_stream(chunk)
            response = "".join(chunks)
        else:
            emit_progress(
                f"Running model for {path.name} -- this can take a minute…",
                on_progress,
            )
            response = engine.generate(
                prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                stream=False,
            )
        emit_progress(f"Checking MYTHOS_PATCH format for {path.name}…", on_progress)
        patches = extract_patches_from_response(response)
        if patches:
            emit_progress(f"Writing {path.name} to disk…", on_progress)
            written = apply_patches_from_response(
                response, confirm=None, on_progress=on_progress
            )
            notices.extend(written)
            return response, notices

    emit_progress(
        f"Could not produce a valid MYTHOS_PATCH for {path.name} "
        f"after {total_attempts} attempt(s)",
        on_progress,
    )
    notices.append(
        f"Model did not produce MYTHOS_PATCH for {path} after {total_attempts} attempt(s)"
    )
    return response, notices


def run_dedicated_rewrite(
    rewrite_paths: List[str],
    engine: Any,
    prompt_manager: Any,
    config: Dict[str, Any],
    *,
    targets: Optional[List[Path]] = None,
    limit_one: bool = False,
    on_progress: Optional[ProgressCallback] = None,
    on_stream: Optional[StreamCallback] = None,
) -> List[str]:
    """
    Run MYTHOS_PATCH-only generation for each path until written or retries exhausted.
    Rescans targets when no paths were supplied.
    """
    from mythos_cli.static_scanner import scan_file

    paths = list(rewrite_paths)
    if not paths and targets:
        emit_progress("Resolving files to rewrite…", on_progress)
        paths = resolve_rewrite_file_paths(targets, config)
    if limit_one and paths:
        paths = paths[:1]
    if not paths:
        return ["No files to rewrite -- reference a path with /file or in your message"]

    total = len(paths)
    emit_progress(
        f"Starting full-file rewrite ({total} file{'s' if total != 1 else ''})…",
        on_progress,
    )
    notices: List[str] = []
    for index, abs_path in enumerate(paths, start=1):
        path = Path(abs_path)
        if not path.is_file():
            notices.append(f"Skip (not a file): {path}")
            continue
        emit_progress(
            f"File {index}/{total}: {path.name}",
            on_progress,
        )
        try:
            emit_progress(f"Reading {path.name}…", on_progress)
            source = path.read_text(encoding="utf-8", errors="ignore")
        except OSError as exc:
            notices.append(f"Cannot read {path}: {exc}")
            continue

        emit_progress(f"Scanning findings in {path.name}…", on_progress)
        file_findings = scan_file(path, path.parent) if path.parent.exists() else []
        if _fix_cfg(config).get("show_finding_rationale", True):
            emit_finding_rationale(path, file_findings, on_progress)
        finding_text = "\n".join(
            f"- [{f.severity}] line {f.line}: {f.title}"
            for f in file_findings
        ) or "Apply security best practices."

        _, patch_notes = generate_mythos_patch(
            engine,
            prompt_manager,
            config,
            file_path=path,
            source=source,
            finding_text=finding_text,
            on_progress=on_progress,
            on_stream=on_stream,
        )
        notices.extend(patch_notes)

    emit_progress("Full-file rewrite finished.", on_progress)
    return notices


def run_rewrite_files(
    targets: List[Path],
    engine: Any,
    prompt_manager: Any,
    memory: Any,
    config: Dict[str, Any],
    *,
    stream: bool = False,
    single_file: Optional[Path] = None,
    on_progress: Optional[ProgressCallback] = None,
    on_stream: Optional[StreamCallback] = None,
) -> Tuple[str, List[str]]:
    """
    Auto-fix, then MYTHOS_PATCH-only rewrite with retries until written.

    single_file: when set, only rewrite this file (for "rewrite one fix").
    """
    from mythos_cli.fix_runner import run_fix_on_path
    from mythos_cli.static_scanner import scan_file

    del stream, memory  # rewrite path uses non-streaming patch generation

    notices: List[str] = []
    all_responses: List[str] = []

    for target in targets:
        target = target.resolve()
        label = target.name if target.is_file() else str(target)
        emit_progress(f"Scanning {label} for rewrite targets…", on_progress)
        if target.is_dir():
            findings, _ = run_fix_on_path(target, dry_run=True)
            file_list = _files_to_rewrite([target], findings, config)
        else:
            findings = scan_file(target, target.parent)
            _, _ = run_fix_on_path(target, dry_run=True)
            file_list = [str(target)]

        if single_file:
            file_list = [str(single_file.resolve())]

        if not file_list:
            notices.append(f"No files to rewrite under {target}")
            continue

        total = len(file_list)
        for index, abs_path in enumerate(file_list, start=1):
            path = Path(abs_path)
            if not path.is_file():
                continue
            emit_progress(
                f"Rewriting file {index}/{total}: {path.name}",
                on_progress,
            )
            file_findings = scan_file(path, path.parent) if path.parent.exists() else []
            if _fix_cfg(config).get("show_finding_rationale", True):
                emit_finding_rationale(path, file_findings, on_progress)
            finding_text = "\n".join(
                f"- [{f.severity}] line {f.line}: {f.title} -- {f.recommendation}"
                for f in file_findings
            ) or "(apply best-practice security hardening)"

            try:
                emit_progress(f"Reading {path.name}…", on_progress)
                source = path.read_text(encoding="utf-8", errors="ignore")
            except OSError as exc:
                notices.append(f"Cannot read {path}: {exc}")
                continue

            response, patch_notes = generate_mythos_patch(
                engine,
                prompt_manager,
                config,
                file_path=path,
                source=source,
                finding_text=finding_text,
                on_progress=on_progress,
                on_stream=on_stream,
            )
            all_responses.append(response)
            notices.extend(patch_notes)

    emit_progress("Rewrite run finished.", on_progress)
    return "\n\n".join(all_responses), notices
