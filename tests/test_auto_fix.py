"""Tests for deterministic security auto-fixes."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mythos_cli.auto_fix import apply_fixes_to_file


def _finding(rule_id, path, line, title="t"):
    from mythos_cli.static_scanner import Finding

    return Finding(
        severity="high",
        rule_id=rule_id,
        title=title,
        path=path,
        line=line,
        snippet="",
        recommendation="",
        scan_root=".",
    )


def test_fix_yaml_load(tmp_path):
    sample = tmp_path / "app.py"
    sample.write_text("import yaml\ndata = yaml.load(stream)\n", encoding="utf-8")
    findings = [_finding("SEC008", str(sample), 2)]
    results = apply_fixes_to_file(sample, findings, dry_run=False)
    assert any(r.status == "applied" for r in results)
    assert "safe_load" in sample.read_text(encoding="utf-8")


def test_skips_secrets(tmp_path):
    sample = tmp_path / "app.py"
    sample.write_text('password = "secret123"\n', encoding="utf-8")
    findings = [_finding("SEC003", str(sample), 1)]
    results = apply_fixes_to_file(sample, findings, dry_run=False)
    assert all(r.status == "skipped" for r in results)
    assert "secret123" in sample.read_text(encoding="utf-8")
