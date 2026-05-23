"""Orchestrate static and deep scans across configured paths."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Optional, Tuple

from mythos_cli.config_store import load_user_config, resolve_targets
from mythos_cli.static_scanner import Finding, scan_directory

logger = logging.getLogger(__name__)


def run_scan(
    path_arg: Optional[str] = None,
    deep: bool = False,
    min_severity: Optional[str] = None,
) -> Tuple[List[Finding], List[str], Optional[str]]:
    """
    Run security scan on one or all configured paths.

    Returns:
        (findings, scanned_roots, deep_report_or_none)
    """
    user_cfg = load_user_config()
    sec = user_cfg.get("security", {})
    scan_cfg = user_cfg.get("scan", {})
    min_sev = (min_severity or sec.get("min_severity", "low")).lower()

    targets = resolve_targets(path_arg, user_cfg)
    all_findings: List[Finding] = []
    roots: List[str] = []

    for target in targets:
        logger.info("Static scan: %s", target)
        findings = scan_directory(
            target,
            exclude_dirs=scan_cfg.get("exclude_dirs"),
            max_file_bytes=int(scan_cfg.get("max_file_bytes", 2_097_152)),
            min_severity=min_sev,
        )
        all_findings.extend(findings)
        roots.append(str(target))

    deep_report: Optional[str] = None
    if deep:
        if len(targets) != 1 and not path_arg:
            raise RuntimeError(
                "Deep AI scan supports one path at a time. Use:\n"
                "  mythos scan --deep --path /your/project"
            )
        from mythos_cli.deep_scanner import run_deep_audit

        deep_report = run_deep_audit(
            targets[0],
            temperature=float(sec.get("deep_temperature", 0.2)),
            max_tokens=int(sec.get("deep_max_tokens", 4096)),
        )

    return all_findings, roots, deep_report
