"""Tests for progress callbacks."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.progress import emit_progress


def test_emit_progress_calls_callback():
    seen: list[str] = []
    emit_progress("hello", lambda m: seen.append(m))
    assert seen == ["hello"]


def test_emit_progress_no_callback():
    emit_progress("ignored", None)
