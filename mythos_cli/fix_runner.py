"""Scan and apply automatic security fixes."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Tuple

from mythos_cli.auto_fix import FixResult, apply_fixes_to_tree
from mythos_cli.config_store import load_user_config, resolve_targets
from mythos_cli.scan_runner import run_scan
from mythos_cli.static_scanner import Finding, scan_directory


def run_fix(
    path_arg: Optional[str] = None,
    *,
    dry_run: bool = True,
    min_severity: Optional[str] = None,
) -> Tuple[List[Finding], List[str], List[FixResult]]:
    """
    Static scan + deterministic auto-fix.

    Returns:
        (remaining_findings, scanned_roots, fix_results)
    """
    user_cfg = load_user_config()
    sec = user_cfg.get("security", {})
    scan_cfg = user_cfg.get("scan", {})
    min_sev = (min_severity or sec.get("min_severity", "low")).lower()

    targets = resolve_targets(path_arg, user_cfg)
    all_findings: List[Finding] = []
    all_fixes: List[FixResult] = []
    roots: List[str] = []

    for target in targets:
        findings = scan_directory(
            target,
            exclude_dirs=scan_cfg.get("exclude_dirs"),
            max_file_bytes=int(scan_cfg.get("max_file_bytes", 2_097_152)),
            min_severity=min_sev,
        )
        fix_results = apply_fixes_to_tree(target, findings, dry_run=dry_run)
        all_fixes.extend(fix_results)
        roots.append(str(target))

        # Re-scan to report what remains after apply
        if not dry_run:
            findings = scan_directory(
                target,
                exclude_dirs=scan_cfg.get("exclude_dirs"),
                max_file_bytes=int(scan_cfg.get("max_file_bytes", 2_097_152)),
                min_severity=min_sev,
            )
        all_findings.extend(findings)

    return all_findings, roots, all_fixes


def run_fix_on_path(
    target: Path,
    *,
    dry_run: bool = True,
) -> Tuple[List[Finding], List[FixResult]]:
    """Fix a single file or directory (used from chat /fix)."""
    target = target.resolve()
    if target.is_file():
        from mythos_cli.auto_fix import apply_fixes_to_file
        from mythos_cli.static_scanner import scan_file

        findings = scan_file(target, target.parent)
        fixes = apply_fixes_to_file(target, findings, dry_run=dry_run)
        if not dry_run:
            findings = scan_file(target, target.parent)
        return findings, fixes

    findings = scan_directory(target)
    fixes = apply_fixes_to_tree(target, findings, dry_run=dry_run)
    if not dry_run:
        findings = scan_directory(target)
    return findings, fixes
