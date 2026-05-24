"""Tests for finding rationale progress lines."""

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.chat_fix import format_finding_rationale


def test_format_finding_rationale_empty():
    assert format_finding_rationale([]) == [
        "  • No static findings — applying general security hardening"
    ]


def test_format_finding_rationale_truncates():
    findings = [
        SimpleNamespace(severity="high", line=i, title=f"Issue {i}", recommendation="fix")
        for i in range(1, 10)
    ]
    lines = format_finding_rationale(findings, max_items=3)
    assert len(lines) == 4
    assert "… and 6 more" in lines[-1]
