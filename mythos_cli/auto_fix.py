"""
Deterministic, line-level security fixes for static scanner findings.

Only applies changes with predictable behavior (no LLM). Secrets and logic
flaws are reported but not auto-edited.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

from mythos_cli.static_scanner import Finding

# Rules we will never auto-edit (need human / LLM review)
SKIP_RULES = frozenset({
    "SEC001", "SEC002", "SEC003", "SEC004", "SEC005",  # secrets / keys
    "SEC006",  # eval/exec
    "SEC007",  # shell injection
    "SEC009",  # SQL — needs parameterized queries, not regex
    "SEC013",  # webhooks — design change
    "SEC014",  # logging
    "SEC015", "SEC016",  # .env presence
})


@dataclass
class FixResult:
    rule_id: str
    path: str
    line: int
    status: str  # applied | skipped | unchanged
    detail: str
    before: str = ""
    after: str = ""


def _fix_line(rule_id: str, line: str) -> Tuple[str, Optional[str]]:
    """Return (new_line, detail) or (line, None) if no change."""
    if rule_id == "SEC008":
        if "yaml.load(" in line and "safe_load" not in line:
            new = line.replace("yaml.load(", "yaml.safe_load(")
            return new, "yaml.load → yaml.safe_load"
        return line, None

    if rule_id == "SEC010":
        new = line
        detail_parts: List[str] = []
        for pat, repl in (
            (r"verify\s*=\s*False", "verify=True"),
            (r"VERIFY_SSL\s*=\s*False", "VERIFY_SSL=True"),
            (r"rejectUnauthorized\s*:\s*false", "rejectUnauthorized: true"),
        ):
            if re.search(pat, line, re.IGNORECASE):
                new = re.sub(pat, repl, new, flags=re.IGNORECASE)
                detail_parts.append(repl)
        if detail_parts and new != line:
            return new, "; ".join(detail_parts)
        return line, None

    if rule_id == "SEC011":
        if re.search(r"""Access-Control-Allow-Origin['"]?\s*[:=]\s*['"]\*['"]""", line, re.I):
            new = re.sub(
                r"""(['"])\*(\1)""",
                r"\1https://your-trusted-origin.example\2",
                line,
                count=1,
            )
            return new, "wildcard CORS → placeholder origin (edit domain)"
        return line, None

    if rule_id == "SEC012":
        for pat, repl in (
            (r"(?i)(DEBUG|FLASK_DEBUG)\s*=\s*true", r"\1 = False"),
            (r"(?i)NODE_ENV\s*[:=]\s*['\"]?development['\"]?", "NODE_ENV=production"),
        ):
            if re.search(pat, line):
                new = re.sub(pat, repl, line)
                if new != line:
                    return new, "disabled debug/development flag"
        return line, None

    return line, None


def apply_fixes_to_file(
    filepath: Path,
    findings: List[Finding],
    *,
    dry_run: bool = True,
) -> List[FixResult]:
    """
    Apply deterministic fixes for findings in one file.

    Findings must belong to this file (matching path relative to scan root).
    """
    results: List[FixResult] = []
    rel_name = filepath.name
    applicable = [
        f for f in findings
        if f.rule_id not in SKIP_RULES
        and (f.path == rel_name or str(filepath).endswith(f.path))
    ]
    # Dedupe by line — one fix attempt per line
    by_line: dict[int, Finding] = {}
    for f in applicable:
        if f.line not in by_line:
            by_line[f.line] = f

    if not by_line:
        return results

    try:
        lines = filepath.read_text(encoding="utf-8", errors="ignore").splitlines(keepends=True)
    except OSError as exc:
        return [
            FixResult(
                rule_id="",
                path=str(filepath),
                line=0,
                status="skipped",
                detail=f"Cannot read file: {exc}",
            )
        ]

    changed = False
    for lineno in sorted(by_line.keys()):
        finding = by_line[lineno]
        idx = lineno - 1
        if idx < 0 or idx >= len(lines):
            results.append(
                FixResult(
                    rule_id=finding.rule_id,
                    path=finding.path,
                    line=lineno,
                    status="skipped",
                    detail="Line out of range",
                )
            )
            continue

        old = lines[idx]
        new, detail = _fix_line(finding.rule_id, old.rstrip("\n\r"))
        if not detail or new == old.rstrip("\n\r"):
            results.append(
                FixResult(
                    rule_id=finding.rule_id,
                    path=finding.path,
                    line=lineno,
                    status="skipped",
                    detail="No safe automatic fix for this pattern",
                    before=old.strip(),
                )
            )
            continue

        newline = new
        if old.endswith("\n"):
            newline += "\n"
        elif old.endswith("\r\n"):
            newline += "\r\n"

        results.append(
            FixResult(
                rule_id=finding.rule_id,
                path=finding.path,
                line=lineno,
                status="applied" if not dry_run else "pending",
                detail=detail,
                before=old.strip(),
                after=newline.strip(),
            )
        )
        lines[idx] = newline
        changed = True

    if changed and not dry_run:
        filepath.write_text("".join(lines), encoding="utf-8")

    return results


def apply_fixes_to_tree(
    root: Path,
    findings: List[Finding],
    *,
    dry_run: bool = True,
) -> List[FixResult]:
    """Group findings by file under root and apply fixes."""
    all_results: List[FixResult] = []
    by_file: dict[str, List[Finding]] = {}
    for f in findings:
        by_file.setdefault(f.path, []).append(f)

    for rel, file_findings in by_file.items():
        full = (root / rel).resolve()
        if not full.is_file():
            all_results.append(
                FixResult(
                    rule_id="",
                    path=rel,
                    line=0,
                    status="skipped",
                    detail="File not found under scan root",
                )
            )
            continue
        all_results.extend(
            apply_fixes_to_file(full, file_findings, dry_run=dry_run)
        )
    return all_results
