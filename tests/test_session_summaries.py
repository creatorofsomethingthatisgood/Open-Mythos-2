"""Tests for the Session Summaries feature."""
import json
import os
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from engine.session_summaries import SessionSummaries, _DEFAULT_SUMMARY


@pytest.fixture
def tmp_dir(monkeypatch):
    """Point session summaries at a temp directory."""
    with tempfile.TemporaryDirectory() as d:
        monkeypatch.setenv("MYTHOS_HOME", d)
        yield d


@pytest.fixture
def ss(tmp_dir):
    return SessionSummaries({"session_summaries": {"enabled": True, "auto_on_exit": True, "max_summaries": 50}})


def _basic_messages():
    return [
        {"role": "user", "content": "How do I debug a Python memory leak?"},
        {"role": "assistant", "content": "Use tracemalloc and objgraph. Wrote memory_debug.py"},
        {"role": "user", "content": "Thanks, also help me fix the Dockerfile"},
        {"role": "assistant", "content": "Updated Dockerfile with multi-stage build. Wrote Dockerfile"},
    ]


class TestHeuristicExtraction:
    def test_basic_summary(self, ss):
        messages = _basic_messages()
        summary = ss.generate_summary(messages, session_start_time=1000.0, model_name="qwen2.5")
        assert summary is not None
        assert "one_line" in summary
        assert summary["code_written"] is True
        assert len(summary["files_modified"]) >= 1
        assert summary["turn_count"] == 4
        assert summary["model"] == "qwen2.5"

    def test_too_few_messages_returns_none(self, ss):
        assert ss.generate_summary([{"role": "user", "content": "hi"}]) is None
        assert ss.generate_summary([]) is None

    def test_topics_detected(self, ss):
        messages = [
            {"role": "user", "content": "Help me debug my Python API server"},
            {"role": "assistant", "content": "Let's look at the error traceback."},
        ]
        summary = ss.generate_summary(messages)
        assert summary is not None
        # Should detect at least 'python' and 'api' as topics
        assert len(summary["topics"]) >= 1

    def test_decisions_detected(self, ss):
        messages = [
            {"role": "user", "content": "Should I use FastAPI or Flask?"},
            {"role": "assistant", "content": "I decided: FastAPI for async support and auto-docs."},
        ]
        summary = ss.generate_summary(messages)
        assert summary is not None
        assert len(summary["decisions"]) >= 1

    def test_no_messages(self, ss):
        assert ss.generate_summary([]) is None

    def test_system_messages_filtered(self, ss):
        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Hello"},
        ]
        assert ss.generate_summary(messages) is None  # Only 1 user msg, 0 assistant


class TestPersistence:
    def test_save_and_load(self, ss, tmp_dir):
        messages = _basic_messages()
        summary = ss.generate_summary(messages, session_start_time=1000.0)
        sid = ss.save_summary(summary)
        loaded = ss.load_summary(sid)
        assert loaded is not None
        assert loaded["session_id"] == sid
        assert loaded["one_line"] == summary["one_line"]

    def test_list_summaries(self, ss):
        messages = _basic_messages()
        for _ in range(3):
            summary = ss.generate_summary(messages, session_start_time=1000.0)
            ss.save_summary(summary)
        listings = ss.list_summaries(limit=10)
        assert len(listings) >= 3

    def test_delete_summary(self, ss):
        messages = _basic_messages()
        summary = ss.generate_summary(messages)
        sid = ss.save_summary(summary)
        assert ss.delete_summary(sid) is True
        assert ss.load_summary(sid) is None

    def test_clear_all(self, ss):
        messages = _basic_messages()
        for _ in range(5):
            summary = ss.generate_summary(messages)
            ss.save_summary(summary)
        count = ss.clear_all()
        assert count == 5
        assert ss.list_summaries(limit=100) == []

    def test_load_nonexistent(self, ss):
        assert ss.load_summary("s_nonexistent") is None

    def test_delete_nonexistent(self, ss):
        assert ss.delete_summary("s_nonexistent") is False


class TestFormatting:
    def test_format_detail(self, ss):
        messages = _basic_messages()
        summary = ss.generate_summary(messages, session_start_time=1000.0, model_name="qwen2.5")
        text = ss.format_summary_detail(summary)
        assert "Session Summary" in text
        assert "qwen2.5" in text

    def test_format_list_empty(self, ss):
        text = ss.format_sessions_list([])
        assert "No session summaries yet" in text

    def test_format_list_with_items(self, ss):
        messages = _basic_messages()
        summary = ss.generate_summary(messages)
        ss.save_summary(summary)
        listings = ss.list_summaries(limit=10)
        text = ss.format_sessions_list(listings)
        assert "Session Summaries" in text


class TestConfig:
    def test_enabled_by_default(self):
        ss = SessionSummaries({})
        assert ss.enabled is True

    def test_bool_config(self):
        ss = SessionSummaries({"session_summaries": False})
        assert ss.enabled is False

    def test_disabled_config(self):
        ss = SessionSummaries({"session_summaries": {"enabled": False}})
        assert ss.enabled is False

    def test_max_summaries(self):
        ss = SessionSummaries({"session_summaries": {"max_summaries": 10}})
        assert ss.max_summaries == 10


class TestPruning:
    def test_prune_old_summaries(self, monkeypatch):
        with tempfile.TemporaryDirectory() as d:
            monkeypatch.setenv("MYTHOS_HOME", d)
            ss = SessionSummaries({"session_summaries": {"enabled": True, "max_summaries": 2}})
            messages = _basic_messages()
            for i in range(5):
                summary = ss.generate_summary(messages)
                summary["session_id"] = f"s_test_{i}_{int(time.time()*1000)}"
                ss.save_summary(summary)
            listings = ss.list_summaries(limit=100)
            assert len(listings) <= 2
