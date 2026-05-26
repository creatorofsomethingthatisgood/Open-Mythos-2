"""
Cross-Session Memory — "Mythos Remembers"

Persists key facts across chat sessions so Mythos starts each conversation
with knowledge of the user's preferences, projects, and context.

Storage: ~/.config/mythos/cross_session_memory.json
Injection: facts are appended to the system prompt (like RML hints).
Extraction: on /save or session exit, the local LLM scans the conversation
  for durable facts worth remembering.

Decay: facts older than `decay_days` with no reinforcement are faded out
  and eventually pruned.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ── defaults ────────────────────────────────────────────────────────────

_DEFAULT_STORE: Dict[str, Any] = {
    "version": 1,
    "facts": [],
    "created_at": None,
    "updated_at": None,
}

_MAX_FACTS = 50
_DECAY_DAYS = 30
_MAX_CONTEXT_CHARS = 2000

# ── persistence ─────────────────────────────────────────────────────────


def _store_path() -> Path:
    """Return the path to the cross-session memory file."""
    home = Path(os.environ.get("MYTHOS_HOME", Path.home() / ".config" / "mythos"))
    return home / "cross_session_memory.json"


def _load_store() -> Dict[str, Any]:
    """Load the memory store from disk, or return defaults."""
    p = _store_path()
    if p.exists():
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            merged = dict(_DEFAULT_STORE)
            merged.update(data)
            if "facts" not in merged or not isinstance(merged.get("facts"), list):
                merged["facts"] = []
            return merged
        except Exception as exc:
            logger.warning("Cross-session memory load failed (%s); starting fresh", exc)
    store = dict(_DEFAULT_STORE)
    store["facts"] = []
    return store


def _save_store(store: Dict[str, Any]) -> None:
    """Persist the memory store to disk."""
    p = _store_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    store["updated_at"] = time.time()
    if store.get("created_at") is None:
        store["created_at"] = store["updated_at"]
    try:
        with open(p, "w", encoding="utf-8") as f:
            json.dump(store, f, indent=2, ensure_ascii=False)
    except OSError as exc:
        logger.error("Cross-session memory save failed: %s", exc)


# ── engine ──────────────────────────────────────────────────────────────


class CrossSessionMemory:
    """
    Manages persistent facts about the user across chat sessions.

    Facts are short declarative strings like:
      - "User prefers Python with type hints"
      - "Current project: payments-api (FastAPI, PostgreSQL)"
      - "Dislikes verbose explanations"

    They are injected into the system prompt at session start and
    optionally extracted from conversations at session end.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.store = _load_store()
        mem_cfg = self.config.get("memory", {}).get("cross_session", {})
        if isinstance(mem_cfg, bool):
            # Simple toggle: memory.cross_session: true
            self.enabled = mem_cfg
            self.max_facts = _MAX_FACTS
            self.decay_days = _DECAY_DAYS
            self.max_context_chars = _MAX_CONTEXT_CHARS
        else:
            self.enabled = mem_cfg.get("enabled", True)
            self.max_facts = int(mem_cfg.get("max_facts", _MAX_FACTS))
            self.decay_days = int(mem_cfg.get("decay_days", _DECAY_DAYS))
            self.max_context_chars = int(
                mem_cfg.get("max_context_chars", _MAX_CONTEXT_CHARS)
            )

    # ── fact management ───────────────────────────────────────────────

    def add_fact(self, text: str, source: str = "manual") -> Optional[str]:
        """
        Add a fact to the memory store.

        Args:
            text: The fact text (should be a short declarative statement).
            source: 'manual', 'extracted', or 'reinforced'.

        Returns:
            The fact ID, or None if the fact was skipped (duplicate, empty, etc.)
        """
        text = text.strip()
        if not text or len(text) < 3:
            return None

        # Deduplicate: check if we already have a very similar fact
        normalized = self._normalize(text)
        for existing in self.store.get("facts", []):
            if self._normalize(existing.get("text", "")) == normalized:
                # Reinforce the existing fact (touch its timestamp)
                existing["last_seen"] = time.time()
                existing["reinforcements"] = existing.get("reinforcements", 0) + 1
                _save_store(self.store)
                return existing.get("id")

        # Enforce max facts (drop the oldest, least-reinforced first)
        facts = self.store.setdefault("facts", [])
        if len(facts) >= self.max_facts:
            self._prune_facts(n_keep=self.max_facts - 1)

        fact_id = f"f_{int(time.time() * 1000)}"
        now = time.time()
        facts.append(
            {
                "id": fact_id,
                "text": text,
                "source": source,
                "created_at": now,
                "last_seen": now,
                "reinforcements": 0,
            }
        )
        _save_store(self.store)
        logger.debug("Cross-session memory: added fact '%s'", text[:60])
        return fact_id

    def remove_fact(self, fact_id_or_text: str) -> bool:
        """
        Remove a fact by its ID or by matching its text (fuzzy).

        Args:
            fact_id_or_text: Fact ID (e.g. 'f_1234567890') or partial text match.

        Returns:
            True if a fact was removed.
        """
        facts = self.store.get("facts", [])
        original_len = len(facts)

        # Try exact ID match first
        new_facts = [f for f in facts if f.get("id") != fact_id_or_text]
        if len(new_facts) < original_len:
            self.store["facts"] = new_facts
            _save_store(self.store)
            return True

        # Fallback: partial text match (case-insensitive)
        query = fact_id_or_text.lower()
        new_facts = [
            f
            for f in facts
            if query not in f.get("text", "").lower()
        ]
        if len(new_facts) < original_len:
            self.store["facts"] = new_facts
            _save_store(self.store)
            return True

        return False

    def clear(self) -> None:
        """Wipe all cross-session memory facts."""
        self.store = dict(_DEFAULT_STORE)
        self.store["facts"] = []
        _save_store(self.store)
        logger.info("Cross-session memory cleared")

    def list_facts(self) -> List[Dict[str, Any]]:
        """Return all stored facts, sorted by recency."""
        facts = self.store.get("facts", [])
        return sorted(facts, key=lambda f: f.get("last_seen", 0), reverse=True)

    # ── prompt injection ───────────────────────────────────────────────

    def get_prompt_block(self) -> str:
        """
        Build a formatted block of facts for injection into the system prompt.

        Respects max_context_chars. Facts closer to expiry are deprioritized.
        """
        if not self.enabled:
            return ""

        facts = self._active_facts()
        if not facts:
            return ""

        lines = ["\n[REMEMBERED FROM PAST SESSIONS — adapt your behavior to match:]"]
        char_budget = self.max_context_chars - len(lines[0])

        for fact in facts:
            line = f" - {fact['text']}"
            if char_budget - len(line) < 0:
                break
            lines.append(line)
            char_budget -= len(line)

        return "\n".join(lines) + "\n"

    # ── fact extraction from conversation ──────────────────────────────

    def extract_facts_from_messages(
        self,
        messages: List[Dict[str, str]],
        engine: Any = None,
    ) -> int:
        """
        Extract durable facts from a conversation's messages.

        If an InferenceEngine is provided, uses the local LLM to extract
        facts. Otherwise, uses a heuristic approach (keyword-based scanning).

        Args:
            messages: List of message dicts with 'role' and 'content'.
            engine: Optional InferenceEngine for LLM-based extraction.

        Returns:
            Number of new facts extracted.
        """
        if not self.enabled:
            return 0

        if engine is not None:
            return self._extract_with_llm(messages, engine)
        else:
            return self._extract_heuristic(messages)

    def _extract_with_llm(
        self,
        messages: List[Dict[str, str]],
        engine: Any,
    ) -> int:
        """
        Use the local LLM to extract key facts from the conversation.

        Runs a short extraction prompt through the model.
        """
        # Build a condensed transcript (skip very long messages)
        transcript_parts = []
        for msg in messages[-20:]:  # Last 20 messages max
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if len(content) > 500:
                content = content[:500] + "..."
            if role in ("user", "assistant"):
                transcript_parts.append(f"{role.upper()}: {content}")

        transcript = "\n".join(transcript_parts)
        if len(transcript) < 50:
<<<<<<< HEAD
=======
            # Transcript too short to be worth an LLM call, but the heuristic
            # can still pick up self-referential statements like "I prefer X".
>>>>>>> 37e416edbebb16d1430aaff28f9b0e9d7ee0f664
            return self._extract_heuristic(messages)

        extraction_prompt = (
            "Below is a conversation between a user and an AI assistant. "
            "Extract 1-5 key facts about the USER that would be useful to "
            "remember in future sessions. Focus on:\n"
            "- User's name, role, or identity\n"
            "- Projects they work on (names, tech stacks)\n"
            "- Strong preferences (languages, styles, tools)\n"
            "- Important decisions or constraints they mentioned\n"
            "- Context about their environment (OS, frameworks)\n\n"
            "Do NOT extract:\n"
            "- One-off questions or temporary debug details\n"
            "- The assistant's own statements\n"
            "- Things that will be stale soon (version numbers, file paths)\n\n"
            "Output one fact per line, prefixed with '- '. "
            "If nothing is worth remembering, output nothing.\n\n"
            f"CONVERSATION:\n{transcript}\n\nFACTS:"
        )

        try:
            # Use a low temperature for extraction — we want deterministic output
            raw = engine.generate(
                extraction_prompt,
                max_tokens=256,
                temperature=0.1,
                top_p=0.9,
                stream=False,
            )
            if not raw or not raw.strip():
                return 0

            new_count = 0
            for line in raw.strip().splitlines():
                line = line.strip()
                # Strip leading "- " or "* " or numbered "1. "
                line = re.sub(r"^[-*\d]+\.\s*", "", line).strip()
                if line and len(line) >= 5:
                    fact_id = self.add_fact(line, source="extracted")
                    if fact_id is not None:
                        new_count += 1

            return new_count

        except Exception as exc:
            logger.warning("LLM fact extraction failed: %s", exc)
            return self._extract_heuristic(messages)

    def _extract_heuristic(
        self,
        messages: List[Dict[str, str]],
    ) -> int:
        """
        Heuristic fact extraction — scans user messages for self-referential
        statements indicating preferences, identity, or project context.
        """
        patterns = [
            # Name/identity
            (re.compile(r"\bmy name is (\w+)", re.I), "User's name: {0}"),
            (re.compile(r"\bi(?:'m| am) (\w+)(?:\s|$|,)", re.I), None),
            # Preferences
            (re.compile(r"\bi prefer ([^.]+)", re.I), "User prefers {0}"),
            (re.compile(r"\bi (?:like|love|enjoy) ([^.]+)", re.I), "User likes {0}"),
            (re.compile(r"\bi (?:don't like|dislike|hate|avoid) ([^.]+)", re.I),
             "User dislikes {0}"),
            (re.compile(r"\bi (?:always|usually|typically) ([^.]+)", re.I),
             "User habitually {0}"),
            # Projects
            (re.compile(r"\bmy project(?:\s+is|\s+is called)?\s+([^.]+)", re.I),
             "User's project: {0}"),
            (re.compile(r"\b(?:working|building|developing) (?:on|a|an)\s+([^.]+)", re.I),
             "User is working on: {0}"),
            # Tech stack
            (re.compile(r"\bi use ([A-Z][\w\-]+(?:\s*[\+,]\s*[A-Z][\w\-]+)*)", re.I),
             "User uses: {0}"),
            # Environment
            (re.compile(r"\b(?:running|using|on)\s+(Linux|macOS|Windows|Ubuntu|Fedora|Debian|Arch)",
                        re.I),
             "User's OS: {0}"),
        ]

        new_count = 0
        for msg in messages:
            if msg.get("role") != "user":
                continue
            text = msg.get("content", "")
            for pattern, template in patterns:
                match = pattern.search(text)
                if match and template:
                    fact_text = template.format(match.group(1).strip())
                    fact_id = self.add_fact(fact_text, source="extracted")
                    if fact_id is not None:
                        new_count += 1

        return new_count

    # ── internal helpers ───────────────────────────────────────────────

    def _normalize(self, text: str) -> str:
        """Normalize text for dedup comparison (lowercase, strip punctuation)."""
        return re.sub(r"[^a-z0-9\s]", "", text.lower()).strip()

    def _active_facts(self) -> List[Dict[str, Any]]:
        """
        Return facts that haven't decayed, sorted by relevance.

        Decay logic: a fact with no reinforcements that hasn't been seen
        in `decay_days` gets a lower priority. Facts with reinforcements
        get a boost.
        """
        now = time.time()
        decay_seconds = self.decay_days * 86400
        facts = self.store.get("facts", [])

        scored = []
        for f in facts:
            age = now - f.get("last_seen", f.get("created_at", now))
            reinforcements = f.get("reinforcements", 0)

            # Effective age: reinforced facts age slower
            effective_age = age / (1 + reinforcements * 0.5)

            if effective_age > decay_seconds * 2:
                # Fully expired — mark for removal
                continue

            # Score: lower is better (displayed first)
            # Fresh facts with reinforcements are most important
            score = effective_age - (reinforcements * decay_seconds * 0.1)
            scored.append((score, f))

        # Sort by score (lowest = highest priority)
        scored.sort(key=lambda x: x[0])

        # Prune expired facts
        active_ids = {f["id"] for _, f in scored}
        expired = [f for f in facts if f["id"] not in active_ids]
        if expired:
            self.store["facts"] = [f for f in facts if f["id"] in active_ids]
            _save_store(self.store)

        return [f for _, f in scored]

    def _prune_facts(self, n_keep: Optional[int] = None) -> None:
        """
        Remove the least valuable facts to stay within a limit.

        Args:
            n_keep: Number of facts to keep. Defaults to self.max_facts.

        Priority for removal: oldest, fewest reinforcements.
        """
        keep = n_keep if n_keep is not None else self.max_facts
        facts = self.store.get("facts", [])
        if len(facts) <= keep:
            return

        # Sort: oldest + least reinforced first (most expendable)
        facts.sort(
            key=lambda f: (
                f.get("reinforcements", 0),
                -f.get("last_seen", f.get("created_at", 0)),
            )
        )
        # Keep the top `keep` facts (most reinforced + most recent)
        self.store["facts"] = facts[-keep:]
        _save_store(self.store)

    # ── display ────────────────────────────────────────────────────────

    def format_facts_table(self) -> str:
        """Format stored facts for terminal display (like RML stats table)."""
        facts = self.list_facts()
        lines = [
            "╔══════════════════════════════════════════════════╗",
            "║ Cross-Session Memory — Mythos Remembers         ║",
            "╚══════════════════════════════════════════════════╝",
            "",
            f"  Status: {'ON' if self.enabled else 'OFF'}",
            f"  Facts stored: {len(facts)}",
            f"  Max facts: {self.max_facts}",
            f"  Decay: {self.decay_days} days",
            "",
        ]

        if not facts:
            lines.append("  (no facts remembered yet)")
        else:
            for i, f in enumerate(facts, 1):
                age_days = (time.time() - f.get("last_seen", f.get("created_at", 0))) / 86400
                source = f.get("source", "?")
                r = f.get("reinforcements", 0)
                lines.append(f"  {i:2d}. {f['text']}")
                lines.append(f"      [{source} | {age_days:.0f}d ago | x{r}]")

        lines.append("")
        lines.append("  Commands:")
        lines.append("    /memory add <fact>    — manually add a fact")
        lines.append("    /memory forget <text> — remove a fact")
        lines.append("    /memory clear         — wipe all facts")
        lines.append("")
        return "\n".join(lines)
