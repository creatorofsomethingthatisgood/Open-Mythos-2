"""Tests for progressive bitácora journal."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.bitacora import Bitacora, classify_bitacora_message


def test_classify_write():
    assert classify_bitacora_message("Writing /tmp/a.py…") == "write"
    assert classify_bitacora_message("Wrote /tmp/a.py (1,024 bytes)") == "write"


def test_bitacora_updates_on_log():
    seen = 0

    def _on_update(_b: Bitacora) -> None:
        nonlocal seen
        seen += 1

    b = Bitacora(on_update=_on_update)
    b.log("Scanning app…")
    b.log("  • [high] line 1: issue", kind="rationale")
    assert len(b.entries) == 2
    assert seen == 2
    assert "Scanning" in b.render_plain()


def test_stream_counter_logs_periodically():
    b = Bitacora()
    b.log_stream_chunk("x" * 100, every_chars=50)
    b.log_stream_chunk("x" * 100, every_chars=50)
    stream_lines = [e for e in b.entries if e.kind == "stream"]
    assert len(stream_lines) >= 1
