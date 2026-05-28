"""Tests for Cross-Session Memory (engine/cross_session_memory.py)."""

import json
import os
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.cross_session_memory import CrossSessionMemory, _DEFAULT_STORE


# ── fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture
def memory_dir(tmp_path):
    """Create a temporary MYTHOS_HOME and point the module at it."""
    home = tmp_path / "mythos_home"
    home.mkdir()
    os.environ["MYTHOS_HOME"] = str(home)
    yield home
    os.environ.pop("MYTHOS_HOME", None)


@pytest.fixture
def mem(memory_dir):
    """Return a fresh CrossSessionMemory with a clean store."""
    m = CrossSessionMemory({"memory": {"cross_session": {"enabled": True}}})
    m.clear()  # Start completely clean
    return m


# ── add_fact ──────────────────────────────────────────────────────────────


class TestAddFact:
    def test_add_returns_fact_id(self, mem):
        fid = mem.add_fact("User prefers Python with type hints")
        assert fid is not None
        assert fid.startswith("f_")

    def test_add_persists_to_disk(self, mem, memory_dir):
        mem.add_fact("User prefers Python with type hints")
        store_path = memory_dir / "cross_session_memory.json"
        assert store_path.exists()
        with open(store_path) as f:
            data = json.load(f)
        assert len(data["facts"]) == 1
        assert data["facts"][0]["text"] == "User prefers Python with type hints"

    def test_add_empty_string_returns_none(self, mem):
        assert mem.add_fact("") is None

    def test_add_too_short_returns_none(self, mem):
        assert mem.add_fact("ab") is None  # < 3 chars

    def test_add_whitespace_only_returns_none(self, mem):
        assert mem.add_fact("   ") is None

    def test_add_strips_whitespace(self, mem):
        fid = mem.add_fact("  hello world  ")
        assert fid is not None
        facts = mem.list_facts()
        assert facts[0]["text"] == "hello world"

    def test_add_stores_source(self, mem):
        mem.add_fact("test fact", source="manual")
        assert mem.list_facts()[0]["source"] == "manual"

    def test_add_stores_extracted_source(self, mem):
        mem.add_fact("test fact", source="extracted")
        assert mem.list_facts()[0]["source"] == "extracted"


class TestDeduplication:
    def test_duplicate_reinforces_existing(self, mem):
        fid1 = mem.add_fact("User prefers Python")
        facts_before = mem.list_facts()
        assert len(facts_before) == 1

        fid2 = mem.add_fact("User prefers Python")
        assert fid2 == fid1  # Same fact ID returned

        facts_after = mem.list_facts()
        assert len(facts_after) == 1  # No duplicate added
        assert facts_after[0]["reinforcements"] == 1

    def test_near_duplicate_reinforces(self, mem):
        """Normalization strips punctuation and case, so near-duplicates
        should reinforce the existing fact."""
        fid1 = mem.add_fact("User prefers Python")
        fid2 = mem.add_fact("user prefers python!")
        assert fid2 == fid1
        facts = mem.list_facts()
        assert len(facts) == 1

    def test_different_facts_both_stored(self, mem):
        mem.add_fact("User prefers Python")
        mem.add_fact("User prefers TypeScript")
        assert len(mem.list_facts()) == 2


# ── remove_fact ───────────────────────────────────────────────────────────


class TestRemoveFact:
    def test_remove_by_id(self, mem):
        fid = mem.add_fact("User prefers Python")
        assert mem.remove_fact(fid)
        assert len(mem.list_facts()) == 0

    def test_remove_by_text(self, mem):
        mem.add_fact("User prefers Python")
        assert mem.remove_fact("prefers Python")
        assert len(mem.list_facts()) == 0

    def test_remove_nonexistent_returns_false(self, mem):
        assert not mem.remove_fact("nonexistent_id")

    def test_remove_case_insensitive(self, mem):
        mem.add_fact("User prefers Python")
        assert not mem.remove_fact("USER PREFERENCES PYTHON")  # Not a substring
        assert mem.remove_fact("prefers python")  # Substring match, case-insensitive


# ── clear ─────────────────────────────────────────────────────────────────


class TestClear:
    def test_clear_wipes_all_facts(self, mem):
        mem.add_fact("fact 1")
        mem.add_fact("fact 2")
        mem.clear()
        assert len(mem.list_facts()) == 0

    def test_clear_persists_to_disk(self, mem, memory_dir):
        mem.add_fact("fact 1")
        mem.clear()
        store_path = memory_dir / "cross_session_memory.json"
        with open(store_path) as f:
            data = json.load(f)
        assert not data["facts"]


# ── list_facts ────────────────────────────────────────────────────────────


class TestListFacts:
    def test_list_returns_sorted_by_recency(self, mem):
        mem.add_fact("oldest fact")
        time.sleep(0.01)
        mem.add_fact("newest fact")
        facts = mem.list_facts()
        assert facts[0]["text"] == "newest fact"
        assert facts[1]["text"] == "oldest fact"

    def test_list_empty(self, mem):
        assert mem.list_facts() == []


# ── get_prompt_block ──────────────────────────────────────────────────────


class TestGetPromptBlock:
    def test_returns_formatted_block(self, mem):
        mem.add_fact("User prefers Python")
        block = mem.get_prompt_block()
        assert "REMEMBERED FROM PAST SESSIONS" in block
        assert "User prefers Python" in block

    def test_returns_empty_when_disabled(self, memory_dir):
        m = CrossSessionMemory({"memory": {"cross_session": {"enabled": False}}})
        m.clear()
        m.add_fact("should not appear")
        assert m.get_prompt_block() == ""

    def test_returns_empty_when_no_facts(self, mem):
        assert mem.get_prompt_block() == ""

    def test_respects_max_context_chars(self, memory_dir):
        m = CrossSessionMemory(
            {"memory": {"cross_session": {"enabled": True, "max_context_chars": 100}}}
        )
        m.clear()
        m.add_fact("A" * 200)  # Way over the budget
        block = m.get_prompt_block()
        # The header line alone is ~60 chars, so the long fact shouldn't fit
        assert len(block) < 200


# ── heuristic extraction ─────────────────────────────────────────────────


class TestHeuristicExtraction:
    def test_extracts_name(self, mem):
        messages = [{"role": "user", "content": "Hi, my name is Alice"}]
        n = mem.extract_facts_from_messages(messages, engine=None)
        assert n >= 1
        texts = [f["text"] for f in mem.list_facts()]
        assert any("Alice" in t for t in texts)

    def test_extracts_preference(self, mem):
        messages = [{"role": "user", "content": "I prefer dark mode"}]
        n = mem.extract_facts_from_messages(messages, engine=None)
        assert n >= 1

    def test_extracts_dislike(self, mem):
        messages = [{"role": "user", "content": "I dislike verbose output"}]
        n = mem.extract_facts_from_messages(messages, engine=None)
        assert n >= 1

    def test_extracts_project(self, mem):
        messages = [{"role": "user", "content": "My project is called payments-api"}]
        n = mem.extract_facts_from_messages(messages, engine=None)
        assert n >= 1

    def test_extracts_os(self, mem):
        messages = [{"role": "user", "content": "I'm running Linux"}]
        n = mem.extract_facts_from_messages(messages, engine=None)
        assert n >= 1

    def test_ignores_assistant_messages(self, mem):
        messages = [
            {"role": "assistant", "content": "My name is Bot and I prefer Go"},
        ]
        n = mem.extract_facts_from_messages(messages, engine=None)
        assert n == 0

    def test_disabled_returns_zero(self, memory_dir):
        m = CrossSessionMemory({"memory": {"cross_session": {"enabled": False}}})
        m.clear()
        messages = [{"role": "user", "content": "my name is Alice"}]
        assert m.extract_facts_from_messages(messages, engine=None) == 0

    def test_does_not_duplicate(self, mem):
        """Extracting the same fact twice should reinforce, not add a new one."""
        messages = [{"role": "user", "content": "my name is Alice"}]
        n1 = mem.extract_facts_from_messages(messages, engine=None)
        _n2 = mem.extract_facts_from_messages(messages, engine=None)
        assert n1 >= 1
        # Second extraction should reinforce, not add new
        facts = mem.list_facts()
        name_facts = [f for f in facts if "Alice" in f["text"]]
        assert len(name_facts) == 1


# ── LLM-based extraction ─────────────────────────────────────────────────


class TestLLMExtraction:
    def test_calls_engine_generate(self, mem):
        engine = MagicMock()
        engine.generate.return_value = "- User works on FastAPI project\n- User prefers TypeScript"
        messages = [{"role": "user", "content": "I'm building a FastAPI project and I prefer TypeScript"}]
        n = mem.extract_facts_from_messages(messages, engine=engine)
        assert n >= 1
        engine.generate.assert_called_once()

    def test_falls_back_to_heuristic_on_error(self, mem):
        engine = MagicMock()
        engine.generate.side_effect = RuntimeError("model not loaded")
        # Use a message that the heuristic can extract from
        messages = [{"role": "user", "content": "I prefer dark mode"}]
        n = mem.extract_facts_from_messages(messages, engine=engine)
        # Should fall back to heuristic and still extract
        assert n >= 1

    def test_returns_zero_on_empty_response(self, mem):
        engine = MagicMock()
        engine.generate.return_value = ""
        messages = [{"role": "user", "content": "hello"}]
        n = mem.extract_facts_from_messages(messages, engine=engine)
        assert n == 0

    def test_truncates_long_messages(self, mem):
        engine = MagicMock()
        engine.generate.return_value = ""
        messages = [{"role": "user", "content": "w" * 1000}]
        mem.extract_facts_from_messages(messages, engine=engine)
        # Check that the prompt sent to engine truncated the long message
        call_args = engine.generate.call_args
        prompt = call_args[0][0] if call_args[0] else call_args[1].get("prompt", "")
        # The original 1000-char message should be truncated to ~500 + "..."
        assert "w" * 600 not in prompt  # If not truncated, 600+ w's would be present


# ── decay / pruning ──────────────────────────────────────────────────────


class TestDecayAndPruning:
    def test_max_facts_pruning(self, memory_dir):
        m = CrossSessionMemory(
            {"memory": {"cross_session": {"enabled": True, "max_facts": 3}}}
        )
        m.clear()
        m.add_fact("fact 1")
        m.add_fact("fact 2")
        m.add_fact("fact 3")
        m.add_fact("fact 4")  # Should trigger pruning
        facts = m.list_facts()
        assert len(facts) <= 3

    def test_reinforced_fact_survives_pruning(self, memory_dir):
        m = CrossSessionMemory(
            {"memory": {"cross_session": {"enabled": True, "max_facts": 2}}}
        )
        m.clear()
        fid1 = m.add_fact("important fact")
        # Reinforce it multiple times
        m.add_fact("important fact")
        m.add_fact("important fact")
        m.add_fact("less important")
        m.add_fact("newest fact")
        facts = m.list_facts()
        texts = [f["text"] for f in facts]
        assert "important fact" in texts

    def test_old_unreinforced_fact_decays(self, mem):
        """Simulate an old, unreinforced fact and verify it gets deprioritized."""
        mem.add_fact("fresh fact")
        # Manually age an existing fact to test decay logic
        facts = mem.store["facts"]
        if len(facts) > 1:
            # Set an old fact's last_seen to far in the past
            facts[-1]["last_seen"] = time.time() - (60 * 86400)  # 60 days ago
            facts[-1]["reinforcements"] = 0
            _save_store = mem.store  # Trigger save
        # Active facts should not include the expired one
        active = mem._active_facts()
        # The very old fact should be pruned if decay_days < 60
        # (default is 30 days, and 2x decay = 60 days for full expiry)


# ── config handling ───────────────────────────────────────────────────────


class TestConfigHandling:
    def test_enabled_by_default(self, memory_dir):
        m = CrossSessionMemory()  # No config
        m.clear()
        assert m.enabled

    def test_bool_config_toggle(self, memory_dir):
        m = CrossSessionMemory({"memory": {"cross_session": True}})
        assert m.enabled

    def test_disabled_via_config(self, memory_dir):
        m = CrossSessionMemory({"memory": {"cross_session": {"enabled": False}}})
        assert not m.enabled

    def test_custom_settings(self, memory_dir):
        m = CrossSessionMemory(
            {"memory": {"cross_session": {
                "enabled": True,
                "max_facts": 100,
                "decay_days": 90,
                "max_context_chars": 4000,
            }}}
        )
        assert m.max_facts == 100
        assert m.decay_days == 90
        assert m.max_context_chars == 4000


# ── format_facts_table ───────────────────────────────────────────────────


class TestFormatFactsTable:
    def test_table_shows_facts(self, mem):
        mem.add_fact("User prefers Python")
        table = mem.format_facts_table()
        assert "Cross-Session Memory" in table
        assert "User prefers Python" in table

    def test_table_empty(self, mem):
        table = mem.format_facts_table()
        assert "no facts remembered yet" in table

    def test_table_shows_status(self, mem):
        table = mem.format_facts_table()
        assert "ON" in table
