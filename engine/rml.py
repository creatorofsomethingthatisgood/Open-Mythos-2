"""
Reinforcement Machine Learning (RML) — feedback-driven self-improvement loop.

Tracks which assistant responses the user accepts, edits, or rejects.
Accumulates preference signals across sessions and uses them to:
  1. Adjust generation parameters (temperature, top_p) toward preferred style.
  2. Inject learned style/constraint hints into the system prompt.
  3. Surface a /rml stats dashboard so the user can see what RML learned.

Signal sources (collected automatically during chat):
  - explicit:  /rml good  /rml bad   (strong signal, ±2)
  - implicit:  user follows up with "yes", "thanks", "perfect" (+1)
               user follows up with "no", "wrong", "try again" (−1)
  - edit:      user rewrites the response or writes a MYTHOS_PATCH after the
               model failed to produce one (−1 per rewrite)
  - skip:      user interrupts generation (Ctrl+C) (−0.5)
  - length:    very long answers on short questions get a slight penalty

Preferences are persisted to  ~/.config/mythos/rml_preferences.json
so they survive across sessions.
"""

from __future__ import annotations

import json
import logging
import math
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from engine.chat_config import merge_chat_defaults

logger = logging.getLogger(__name__)

# ── signal constants ───────────────────────────────────────────────────

SIGNAL_EXPLICIT_GOOD = 2.0
SIGNAL_EXPLICIT_BAD = -2.0
SIGNAL_IMPLICIT_POSITIVE = 1.0
SIGNAL_IMPLICIT_NEGATIVE = -1.0
SIGNAL_EDIT_PENALTY = -1.0
SIGNAL_INTERRUPT_PENALTY = -0.5

IMPLICIT_POSITIVE_RE = re.compile(
    r"^(thanks|thank you|perfect|great|exactly|spot on|works|awesome|helpful|that works|that helped|you got it|spot on)\s*[!.?]*\s*$",
    re.IGNORECASE,
)
IMPLICIT_NEGATIVE_RE = re.compile(
    r"^(no|wrong|bad|incorrect|try again|not right|not what|mistake|useless|terrible|that.s wrong|that.s not right|that.s incorrect)\s*[!.?]*\s*$",
    re.IGNORECASE,
)
# Mid-sentence patterns — only match if clearly about the previous response
IMPLICIT_POSITIVE_MID = re.compile(
    r"\b(that.s (correct|right|perfect|great|exactly (right|what))|you.re (right|correct)|good answer|nice answer)\b",
    re.IGNORECASE,
)
IMPLICIT_NEGATIVE_MID = re.compile(
    r"\b(that.s (wrong|incorrect|not right)|you're (wrong|incorrect)|bad answer|wrong answer)\b",
    re.IGNORECASE,
)

# ── preference store ───────────────────────────────────────────────────

_DEFAULT_PREFS: Dict[str, Any] = {
    "version": 1,
    "total_signals": 0,
    "cumulative_score": 0.0,
    "accept_count": 0,
    "reject_count": 0,
    "skip_count": 0,
    "edit_count": 0,
    "category_scores": {
        "accuracy": 0.0,
        "completeness": 0.0,
        "clarity": 0.0,
        "code_quality": 0.0,
        "security": 0.0,
        "conciseness": 0.0,
    },
    "learned_hints": [],
    "param_adjustments": {
        "temperature_offset": 0.0,
        "top_p_offset": 0.0,
        "repeat_penalty_offset": 0.0,
    },
    "history": [],  # last N signal entries for debugging
    "created_at": None,
    "updated_at": None,
}

_MAX_HISTORY = 200


def _prefs_path() -> Path:
    """Return the path to the RML preferences file."""
    home = Path(os.environ.get("MYTHOS_HOME", Path.home() / ".config" / "mythos"))
    return home / "rml_preferences.json"


def _load_prefs() -> Dict[str, Any]:
    """Load preferences from disk, or return defaults."""
    p = _prefs_path()
    if p.exists():
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            # Merge in any new keys from defaults
            merged = dict(_DEFAULT_PREFS)
            merged.update(data)
            for k, v in _DEFAULT_PREFS.items():
                if k not in merged:
                    merged[k] = v if not isinstance(v, dict) else dict(v)
            if "category_scores" in merged and "category_scores" in _DEFAULT_PREFS:
                for k2, v2 in _DEFAULT_PREFS["category_scores"].items():
                    merged["category_scores"].setdefault(k2, v2)
            if "param_adjustments" in merged and "param_adjustments" in _DEFAULT_PREFS:
                for k2, v2 in _DEFAULT_PREFS["param_adjustments"].items():
                    merged["param_adjustments"].setdefault(k2, v2)
            return merged
        except Exception as exc:
            logger.warning("RML prefs load failed (%s); starting fresh", exc)
    prefs = dict(_DEFAULT_PREFS)
    prefs["category_scores"] = dict(_DEFAULT_PREFS["category_scores"])
    prefs["param_adjustments"] = dict(_DEFAULT_PREFS["param_adjustments"])
    prefs["learned_hints"] = []
    prefs["history"] = []
    return prefs


def _save_prefs(prefs: Dict[str, Any]) -> None:
    """Persist preferences to disk."""
    p = _prefs_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    prefs["updated_at"] = time.time()
    if prefs.get("created_at") is None:
        prefs["created_at"] = prefs["updated_at"]
    # Trim history
    if len(prefs.get("history", [])) > _MAX_HISTORY:
        prefs["history"] = prefs["history"][-_MAX_HISTORY:]
    try:
        with open(p, "w", encoding="utf-8") as f:
            json.dump(prefs, f, indent=2, ensure_ascii=False)
    except OSError as exc:
        logger.error("RML prefs save failed: %s", exc)


# ── RML engine ─────────────────────────────────────────────────────────

class RMLEngine:
    """
    Reinforcement Machine Learning engine.

    Collects preference signals and adapts the model's behaviour over time.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.prefs = _load_prefs()
        self._session_signals: List[Dict[str, Any]] = []
        rml_cfg = self.config.get("rml", {})
        self.enabled = rml_cfg.get("enabled", False)
        self.learning_rate = float(rml_cfg.get("learning_rate", 0.05))
        self.max_param_offset = float(rml_cfg.get("max_param_offset", 0.3))
        self.hint_threshold = float(rml_cfg.get("hint_threshold", 3.0))

    # ── signal recording ───────────────────────────────────────────────

    def record_signal(
        self,
        signal: float,
        *,
        source: str = "manual",
        category: str = "accuracy",
        detail: str = "",
    ) -> None:
        """
        Record a preference signal.

        Args:
            signal: numeric value (positive = good, negative = bad).
            source: 'explicit_good', 'explicit_bad', 'implicit_pos',
                    'implicit_neg', 'edit', 'interrupt', 'manual'.
            category: which quality dimension this signal targets.
            detail: free-text note stored in history.
        """
        if not self.enabled:
            return

        entry = {
            "signal": signal,
            "source": source,
            "category": category,
            "detail": detail,
            "ts": time.time(),
        }
        self._session_signals.append(entry)

        # Update cumulative stats
        self.prefs["total_signals"] += 1
        self.prefs["cumulative_score"] += signal

        if signal > 0:
            self.prefs["accept_count"] += 1
        elif signal < 0:
            self.prefs["reject_count"] += 1

        if source == "edit":
            self.prefs["edit_count"] += 1
        elif source == "interrupt":
            self.prefs["skip_count"] += 1

        # Category scores use exponential moving average
        if category in self.prefs.get("category_scores", {}):
            old = self.prefs["category_scores"][category]
            alpha = min(self.learning_rate, 0.5)
            self.prefs["category_scores"][category] = old * (1 - alpha) + signal * alpha

        # History
        self.prefs.setdefault("history", []).append(entry)

        # Recompute param adjustments and hints
        self._update_param_adjustments()
        self._update_learned_hints(category, signal)

        _save_prefs(self.prefs)
        logger.debug("RML signal: %.2f [%s/%s] %s", signal, source, category, detail)

    def record_explicit(self, good: bool, category: str = "accuracy", detail: str = "") -> None:
        """Record an explicit /rml good or /rml bad signal."""
        if good:
            self.record_signal(SIGNAL_EXPLICIT_GOOD, source="explicit_good",
                               category=category, detail=detail)
        else:
            self.record_signal(SIGNAL_EXPLICIT_BAD, source="explicit_bad",
                               category=category, detail=detail)

    # Keyword-to-category heuristics for implicit signals
    _NEGATIVE_CATEGORY_HINTS = {
        "too long": "conciseness",
        "too verbose": "conciseness",
        "too short": "completeness",
        "incomplete": "completeness",
        "missing": "completeness",
        "wrong code": "code_quality",
        "bad code": "code_quality",
        "doesn't work": "code_quality",
        "does not work": "code_quality",
        "doesn't run": "code_quality",
        "insecure": "security",
        "vulnerable": "security",
        "unsafe": "security",
        "unclear": "clarity",
        "confusing": "clarity",
        "inaccurate": "accuracy",
        "wrong fact": "accuracy",
        "incorrect": "accuracy",
        "mistake": "accuracy",
    }

    def _infer_implicit_category(self, text: str, fallback: str = "accuracy") -> str:
        """Guess the feedback category from the user's phrasing."""
        lower = text.lower()
        for phrase, cat in self._NEGATIVE_CATEGORY_HINTS.items():
            if phrase in lower:
                return cat
        return fallback

    def record_implicit(self, text: str) -> Optional[str]:
        """
        Scan a user follow-up for implicit positive/negative signals.

        Uses two-tier matching:
          1. Full-match regex (standalone feedback like "thanks!", "wrong.")
          2. Mid-sentence regex (explicit evaluation like "that's correct")

        Returns 'positive', 'negative', or None.
        """
        if not self.enabled:
            return None

        # Short messages are likely pure feedback; longer ones might be questions
        # that coincidentally contain feedback words. Use stricter matching for those.
        is_short = len(text.strip()) < 40

        positive_hit = False
        negative_hit = False

        if is_short:
            # Standalone feedback: "thanks", "wrong", "perfect!", etc.
            positive_hit = bool(IMPLICIT_POSITIVE_RE.match(text))
            negative_hit = bool(IMPLICIT_NEGATIVE_RE.match(text))
        else:
            # Longer messages: only match if clearly evaluating the response
            positive_hit = bool(IMPLICIT_POSITIVE_MID.search(text))
            negative_hit = bool(IMPLICIT_NEGATIVE_MID.search(text))

        if positive_hit:
            # Avoid double-counting if mixed signals
            if negative_hit:
                return None
            cat = self._infer_implicit_category(text, fallback="accuracy")
            self.record_signal(SIGNAL_IMPLICIT_POSITIVE, source="implicit_pos",
                               category=cat, detail=text[:80])
            return "positive"
        if negative_hit:
            cat = self._infer_implicit_category(text, fallback="accuracy")
            self.record_signal(SIGNAL_IMPLICIT_NEGATIVE, source="implicit_neg",
                               category=cat, detail=text[:80])
            return "negative"
        return None

    def record_edit(self, detail: str = "user rewrite") -> None:
        """Record that the user edited/rewrote the assistant's output."""
        self.record_signal(SIGNAL_EDIT_PENALTY, source="edit",
                           category="code_quality", detail=detail)

    def record_interrupt(self) -> None:
        """Record that the user interrupted generation (Ctrl+C)."""
        self.record_signal(SIGNAL_INTERRUPT_PENALTY, source="interrupt",
                           category="conciseness", detail="generation interrupted")

    # ── parameter adaptation ────────────────────────────────────────────

    def _update_param_adjustments(self) -> None:
        """
        Adjust generation parameter offsets based on cumulative signals.

        Logic:
          - If accept_rate is high and edits are low → the model is doing well;
            nudge temperature *up* slightly (more creative/confident).
          - If rejections/edits are high → nudge temperature *down* (more
            conservative/precise).
          - top_p follows a similar but dampened pattern.
          - repeat_penalty goes up slightly when the model gets verbose/repetitive.
        """
        total = self.prefs["accept_count"] + self.prefs["reject_count"]
        if total == 0:
            return

        accept_rate = self.prefs["accept_count"] / total
        edit_ratio = self.prefs["edit_count"] / max(total, 1)

        # Temperature: shift toward conservative when rejections/edits are high
        lr = self.learning_rate
        cap = self.max_param_offset

        # Target offset: positive means "be more creative", negative means "be more precise"
        temp_target = (accept_rate - 0.5) * 2 * cap  # range [-cap, +cap]
        # Edits push toward precision (lower temp)
        temp_target -= edit_ratio * cap * 0.5

        # Smooth toward target
        cur = self.prefs["param_adjustments"]["temperature_offset"]
        new = cur + lr * (temp_target - cur)
        new = max(-cap, min(cap, new))
        self.prefs["param_adjustments"]["temperature_offset"] = round(new, 4)

        # top_p: similar but half the magnitude
        tpp_target = temp_target * 0.5
        cur_tp = self.prefs["param_adjustments"]["top_p_offset"]
        new_tp = cur_tp + lr * (tpp_target - cur_tp)
        new_tp = max(-cap * 0.5, min(cap * 0.5, new_tp))
        self.prefs["param_adjustments"]["top_p_offset"] = round(new_tp, 4)

        # repeat_penalty: slight increase when model is verbose (many skips/interrupts)
        skip_ratio = self.prefs["skip_count"] / max(total, 1)
        rp_target = skip_ratio * 0.15  # small nudge
        cur_rp = self.prefs["param_adjustments"]["repeat_penalty_offset"]
        new_rp = cur_rp + lr * (rp_target - cur_rp)
        new_rp = max(-0.2, min(0.2, new_rp))
        self.prefs["param_adjustments"]["repeat_penalty_offset"] = round(new_rp, 4)

    # ── learned hints ───────────────────────────────────────────────────

    def _update_learned_hints(self, category: str, signal: float) -> None:
        """
        When a category accumulates enough negative signal, add a concrete
        hint to learned_hints that gets injected into the system prompt.
        """
        hints = self.prefs.setdefault("learned_hints", [])
        score = self.prefs["category_scores"].get(category, 0.0)
        threshold = -self.hint_threshold

        # Only add hints for categories with sustained negative signal
        if score > threshold:
            # If the category recovered, remove old hints for it
            hints[:] = [h for h in hints if h["category"] != category]
            return

        # Check if we already have a hint for this category
        existing = [h for h in hints if h["category"] == category]
        if existing:
            # Update strength
            existing[0]["strength"] = min(abs(score), 10.0)
            existing[0]["updated_at"] = time.time()
            return

        hint_text = self._category_hint_text(category, score)
        if hint_text:
            hints.append({
                "category": category,
                "hint": hint_text,
                "strength": min(abs(score), 10.0),
                "created_at": time.time(),
                "updated_at": time.time(),
            })

    @staticmethod
    def _category_hint_text(category: str, score: float) -> Optional[str]:
        """Map a negative category score to a concrete prompt hint."""
        mapping = {
            "accuracy": (
                "Prioritize accuracy over creativity. Double-check facts before stating them. "
                "If unsure, say so explicitly."
            ),
            "completeness": (
                "Be thorough and complete. Address all parts of the question. "
                "Do not skip steps or leave out edge cases."
            ),
            "clarity": (
                "Write clearly and structure your response. Use headers, bullet points, "
                "and short paragraphs. Avoid jargon without explanation."
            ),
            "code_quality": (
                "Write production-quality code: well-named variables, type hints, docstrings, "
                "and error handling. No shortcuts or placeholder comments."
            ),
            "security": (
                "Apply security best practices: input validation, parameterized queries, "
                "no hardcoded secrets, proper error messages (no stack traces to users)."
            ),
            "conciseness": (
                "Be concise. Avoid unnecessary preamble or repetition. "
                "Get to the answer quickly; elaborate only when asked."
            ),
        }
        return mapping.get(category)

    def get_learned_hints_text(self) -> str:
        """Return a formatted block of all active learned hints for the system prompt."""
        hints = self.prefs.get("learned_hints", [])
        if not hints:
            return ""
        lines = ["\n[RML LEARNED PREFERENCES — adapt your style to match:]"]
        for h in sorted(hints, key=lambda x: -x.get("strength", 0)):
            lines.append(f"  - {h['hint']}")
        return "\n".join(lines) + "\n"

    # ── generation parameter overrides ──────────────────────────────────

    def adjusted_generation_params(self, gen_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Return a copy of gen_config with RML offsets applied.

        Called by the chat loop before generation.
        """
        if not self.enabled:
            return dict(gen_config)

        adj = self.prefs.get("param_adjustments", {})
        out = dict(gen_config)

        # Temperature
        base_temp = float(out.get("temperature", 0.7))
        out["temperature"] = max(0.0, min(2.0, base_temp + adj.get("temperature_offset", 0.0)))

        # Top-p
        base_top_p = float(out.get("top_p", 0.9))
        out["top_p"] = max(0.1, min(1.0, base_top_p + adj.get("top_p_offset", 0.0)))

        # Repeat penalty
        base_rp = float(out.get("repeat_penalty", 1.1))
        out["repeat_penalty"] = max(1.0, min(1.5, base_rp + adj.get("repeat_penalty_offset", 0.0)))

        return out

    # ── stats / reset ───────────────────────────────────────────────────

    def get_stats(self) -> Dict[str, Any]:
        """Return a dict of RML statistics for display."""
        p = self.prefs
        total = p["accept_count"] + p["reject_count"]
        accept_rate = (p["accept_count"] / total * 100) if total > 0 else 0.0
        return {
            "enabled": self.enabled,
            "total_signals": p["total_signals"],
            "cumulative_score": round(p["cumulative_score"], 2),
            "accept_count": p["accept_count"],
            "reject_count": p["reject_count"],
            "edit_count": p["edit_count"],
            "skip_count": p["skip_count"],
            "accept_rate": round(accept_rate, 1),
            "category_scores": {k: round(v, 3) for k, v in p.get("category_scores", {}).items()},
            "param_adjustments": {k: round(v, 4) for k, v in p.get("param_adjustments", {}).items()},
            "active_hints": len(p.get("learned_hints", [])),
            "session_signals": len(self._session_signals),
        }

    def reset(self) -> None:
        """Wipe all learned preferences and start fresh."""
        self.prefs = dict(_DEFAULT_PREFS)
        self.prefs["category_scores"] = dict(_DEFAULT_PREFS["category_scores"])
        self.prefs["param_adjustments"] = dict(_DEFAULT_PREFS["param_adjustments"])
        self.prefs["learned_hints"] = []
        self.prefs["history"] = []
        self._session_signals = []
        _save_prefs(self.prefs)
        logger.info("RML preferences reset")

    def toggle(self, enabled: Optional[bool] = None) -> bool:
        """Enable or disable RML. Returns the new state."""
        if enabled is not None:
            self.enabled = enabled
        else:
            self.enabled = not self.enabled
        return self.enabled

    def format_stats_table(self) -> str:
        """Format stats for terminal display."""
        s = self.get_stats()
        lines = [
            "╔══════════════════════════════════════════════════╗",
            "║           RML — Reinforcement ML Stats           ║",
            "╚══════════════════════════════════════════════════╝",
            "",
            f"  Status:         {'ON' if s['enabled'] else 'OFF'}",
            f"  Total signals:  {s['total_signals']}",
            f"  Score:          {s['cumulative_score']:+.2f}",
            f"  Accept rate:    {s['accept_rate']:.1f}%",
            f"  Accepts:        {s['accept_count']}",
            f"  Rejects:        {s['reject_count']}",
            f"  Edits:          {s['edit_count']}",
            f"  Interrupts:     {s['skip_count']}",
            "",
            "  Category scores (negative = needs improvement):",
        ]
        for cat, score in s["category_scores"].items():
            bar_len = int(min(abs(score), 5) * 4)
            if score >= 0:
                bar = "+" * bar_len
                marker = " "
            else:
                bar = "-" * bar_len
                marker = "!"
            lines.append(f"    {cat:16s} {score:+6.2f}  {marker}{bar}")

        lines.append("")
        lines.append("  Parameter adjustments:")
        for param, val in s["param_adjustments"].items():
            lines.append(f"    {param:26s} {val:+.4f}")
        lines.append(f"    Active hints:             {s['active_hints']}")
        lines.append(f"    Session signals:          {s['session_signals']}")
        lines.append("")
        return "\n".join(lines)
