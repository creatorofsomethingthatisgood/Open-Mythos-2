"""
Session Summaries — "Mythos Remembers Your Sessions"

Generates structured digests of chat sessions so the user can quickly recall
what they worked on across sessions: topics covered, decisions made, code
written, and files modified.

Summaries are persisted to ~/.config/mythos/session_summaries/
as individual JSON files. They can be browsed with /sessions and
generated on-demand with /summary.

Extraction: uses the local LLM to produce a structured summary from the
conversation transcript. Falls back to a heuristic approach if the engine
is unavailable.
"""

from __future__ import annotations

import itertools
import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── defaults ────────────────────────────────────────────────────────────

_DEFAULT_SUMMARY: Dict[str, Any] = {
    "version": 1,
    "session_id": None,
    "created_at": None,
    "topics": [],
    "decisions": [],
    "files_modified": [],
    "code_written": False,
    "key_insights": [],
    "one_line": "",
    "duration_seconds": 0,
    "turn_count": 0,
    "model": "",
}

_MAX_SUMMARIES = 200
_SUMMARY_DIR = "session_summaries"

# ── persistence ─────────────────────────────────────────────────────────


def _summaries_dir() -> Path:
    """Return the directory for session summary files."""
    home = Path(os.environ.get("MYTHOS_HOME", Path.home() / ".config" / "mythos"))
    d = home / _SUMMARY_DIR
    d.mkdir(parents=True, exist_ok=True)
    return d


def _summary_path(session_id: str) -> Path:
    """Return the path for a specific session summary file."""
    return _summaries_dir() / f"{session_id}.json"


_id_counter = itertools.count()


def _generate_session_id() -> str:
    """Generate a unique session ID. Nanosecond timestamp plus a process-local
    counter so back-to-back calls within the same tick never collide."""
    return f"s_{time.time_ns()}_{next(_id_counter)}"


# ── engine ──────────────────────────────────────────────────────────────


class SessionSummaries:
    """
    Manages structured session summaries.

    Each summary captures what happened in a chat session:
    - topics: main topics discussed
    - decisions: decisions or conclusions reached
    - files_modified: files that were modified during the session
    - code_written: whether any code was produced
    - key_insights: notable insights or findings
    - one_line: a single-line summary for quick browsing
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        ss_cfg = self.config.get("session_summaries", {})
        if isinstance(ss_cfg, bool):
            self.enabled = ss_cfg
            self.auto_on_exit = True
            self.max_summaries = _MAX_SUMMARIES
        else:
            self.enabled = ss_cfg.get("enabled", True)
            self.auto_on_exit = ss_cfg.get("auto_on_exit", True)
            self.max_summaries = int(ss_cfg.get("max_summaries", _MAX_SUMMARIES))

    # ── summary generation ───────────────────────────────────────────

    def generate_summary(
        self,
        messages: List[Dict[str, str]],
        engine: Any = None,
        *,
        session_start_time: Optional[float] = None,
        model_name: str = "",
    ) -> Optional[Dict[str, Any]]:
        """
        Generate a structured summary from a conversation.

        If an InferenceEngine is provided, uses the local LLM.
        Otherwise falls back to heuristic extraction.

        Args:
            messages: List of message dicts with 'role' and 'content'.
            engine: Optional InferenceEngine for LLM-based extraction.
            session_start_time: Epoch timestamp when the session started.
            model_name: Name of the model used in this session.

        Returns:
            A summary dict, or None if the conversation is too short.
        """
        if not messages:
            return None

        # Only user+assistant messages count
        conversation_msgs = [
            m for m in messages if m.get("role") in ("user", "assistant")
        ]
        if len(conversation_msgs) < 2:
            return None

        if engine is not None:
            summary = self._extract_with_llm(messages, engine)
        else:
            summary = self._extract_heuristic(messages)

        if summary is None:
            return None

        # Enrich with metadata
        summary["session_id"] = _generate_session_id()
        summary["created_at"] = time.time()
        summary["turn_count"] = len(conversation_msgs)
        summary["model"] = model_name
        if session_start_time:
            summary["duration_seconds"] = round(
                time.time() - session_start_time, 1
            )

        return summary

    def _extract_with_llm(
        self,
        messages: List[Dict[str, str]],
        engine: Any,
    ) -> Optional[Dict[str, Any]]:
        """
        Use the local LLM to extract a structured session summary.
        """
        transcript_parts = []
        for msg in messages[-40:]:  # Last 40 messages max
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if len(content) > 400:
                content = content[:400] + "..."
            if role in ("user", "assistant"):
                transcript_parts.append(f"{role.upper()}: {content}")

        transcript = "\n".join(transcript_parts)
        if len(transcript) < 80:
            return None

        extraction_prompt = (
            "Below is a conversation between a user and an AI assistant. "
            "Produce a structured summary of this session.\n\n"
            "Respond in this EXACT JSON format (no markdown, no backticks):\n"
            "{\n"
            '  "one_line": "a single sentence summarizing the session",\n'
            '  "topics": ["topic1", "topic2"],\n'
            '  "decisions": ["decision or conclusion reached"],\n'
            '  "files_modified": ["file paths mentioned as modified"],\n'
            '  "code_written": true_or_false,\n'
            '  "key_insights": ["notable insights or findings"]\n'
            "}\n\n"
            "Rules:\n"
            "- one_line must be under 100 characters\n"
            "- topics: 1-5 main subjects discussed\n"
            "- decisions: conclusions, choices, or resolutions reached\n"
            "- files_modified: only files that were actually rewritten or patched\n"
            "- code_written: true if the assistant wrote any code\n"
            "- key_insights: 0-3 notable findings or learnings\n"
            "- Keep all fields concise. Use empty arrays if nothing fits.\n\n"
            f"CONVERSATION:\n{transcript}\n\nSUMMARY:"
        )

        try:
            raw = engine.generate(
                extraction_prompt,
                max_tokens=512,
                temperature=0.1,
                top_p=0.9,
                stream=False,
            )
            if not raw or not raw.strip():
                return self._extract_heuristic(messages)

            # Try to parse JSON from the response
            text = raw.strip()
            # Strip markdown code fences if present
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```\s*$", "", text)
            text = text.strip()

            data = json.loads(text)

            # Validate and normalize
            summary = {
                "one_line": str(data.get("one_line", ""))[:150],
                "topics": [str(t) for t in data.get("topics", [])][:5],
                "decisions": [str(d) for d in data.get("decisions", [])][:5],
                "files_modified": [str(f) for f in data.get("files_modified", [])][:10],
                "code_written": bool(data.get("code_written", False)),
                "key_insights": [str(i) for i in data.get("key_insights", [])][:3],
            }

            if not summary["one_line"]:
                summary["one_line"] = self._heuristic_one_line(messages)

            return summary

        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            logger.warning("LLM session summary parse failed: %s", exc)
            return self._extract_heuristic(messages)
        except Exception as exc:
            logger.warning("LLM session summary generation failed: %s", exc)
            return self._extract_heuristic(messages)

    def _extract_heuristic(
        self,
        messages: List[Dict[str, str]],
    ) -> Dict[str, Any]:
        """
        Heuristic summary extraction — scans messages for key signals.
        """
        topics = set()
        decisions = []
        files_modified = set()
        code_written = False
        user_msgs = []
        assistant_msgs = []

        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role == "user":
                user_msgs.append(content)
            elif role == "assistant":
                assistant_msgs.append(content)

            # Detect file modifications
            for pattern in [
                r"Wrote\s+(\S+\.\w+)",
                r"MYTHOS_PATCH\s+.*?(\S+\.\w+)",
                r"(?:wrote|modified|updated|saved)\s+[`'\"]?(\S+\.\w+)",
            ]:
                for match in re.finditer(pattern, content, re.IGNORECASE):
                    files_modified.add(match.group(1).strip("`'\""))

            # Detect code
            if re.search(r"```\w", content):
                code_written = True
            # "Wrote X.py" or "Created X.py" also implies code
            if re.search(r"\b(?:wrote|created|added|implemented)\s+\S+\.\w+", content, re.IGNORECASE):
                code_written = True

            # Detect decisions/conclusions
            decision_patterns = [
            r"(?:decided|decision|concluded|conclusion|agreed|resolved)\s*[.:]\s*(.{10,80})",
            r"(?:going with|let's use|we'll use|I'll use)\s+(.{5,60})",
            ]
            for pattern in decision_patterns:
                for match in re.finditer(pattern, content, re.IGNORECASE):
                    text = match.group(1).strip().rstrip(".")
                    if text and len(text) > 5:
                        decisions.append(text)

        # Extract topics from user messages (simple keyword extraction)
        topic_keywords = [
            r"\b(?:python|javascript|rust|go|java|typescript|c\+\+)\b",
            r"\b(?:api|database|server|client|frontend|backend)\b",
            r"\b(?:debug|fix|refactor|test|deploy|build|install)\b",
            r"\b(?:security|auth|encryption|vulnerability)\b",
            r"\b(?:docker|kubernetes|aws|gcp|azure)\b",
            r"\b(?:machine learning|neural|model|training|inference)\b",
            r"\b(?:design|architecture|pattern|algorithm)\b",
            r"\b(?:error|bug|crash|exception|traceback)\b",
            r"\b(?:performance|optimize|benchmark|speed)\b",
            r"\b(?:data|pipeline|etl|processing|transform)\b",
        ]
        all_user_text = " ".join(user_msgs).lower()
        for pattern in topic_keywords:
            match = re.search(pattern, all_user_text, re.IGNORECASE)
            if match:
                topics.add(match.group(0).lower())

        # Cap lists
        decisions = decisions[:5]
        files_modified = set(list(files_modified)[:10])

        one_line = self._heuristic_one_line(messages)

        return {
            "one_line": one_line,
            "topics": sorted(topics)[:5],
            "decisions": decisions,
            "files_modified": sorted(files_modified),
            "code_written": code_written,
            "key_insights": [],
        }

    def _heuristic_one_line(self, messages: List[Dict[str, str]]) -> str:
        """Generate a rough one-line summary from messages."""
        user_msgs = [
            m.get("content", "")
            for m in messages
            if m.get("role") == "user"
        ]
        if not user_msgs:
            return "Empty session"

        # Use the first user message as the topic hint
        first = user_msgs[0].strip()
        if len(first) > 90:
            first = first[:87] + "..."
        n_turns = len([m for m in messages if m.get("role") == "user"])
        return f"{first} ({n_turns} turn{'s' if n_turns != 1 else ''})"

    # ── save / load ──────────────────────────────────────────────────

    def save_summary(self, summary: Dict[str, Any]) -> str:
        """
        Save a summary to disk.

        Returns:
            The session_id of the saved summary.
        """
        if not summary.get("session_id"):
            summary["session_id"] = _generate_session_id()
        if not summary.get("created_at"):
            summary["created_at"] = time.time()

        # Fill in defaults for missing fields
        for key, default in _DEFAULT_SUMMARY.items():
            summary.setdefault(key, default)

        path = _summary_path(summary["session_id"])
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(summary, f, indent=2, ensure_ascii=False)
            logger.debug("Session summary saved: %s", summary["session_id"])
        except OSError as exc:
            logger.error("Session summary save failed: %s", exc)

        # Prune old summaries if over limit
        self._prune_old_summaries()

        return summary["session_id"]

    def load_summary(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Load a specific summary by session_id."""
        path = _summary_path(session_id)
        if not path.exists():
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to load summary %s: %s", session_id, exc)
            return None

    def list_summaries(
        self,
        *,
        limit: int = 20,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """
        List summaries, newest first.

        Returns a list of summary dicts (lightweight: id, one_line, created_at,
        topics, turn_count).
        """
        summaries_dir = _summaries_dir()
        all_files = sorted(
            summaries_dir.glob("s_*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )

        results = []
        for f in all_files[offset : offset + limit]:
            try:
                with open(f, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                results.append({
                    "session_id": data.get("session_id", f.stem),
                    "one_line": data.get("one_line", "(no summary)"),
                    "created_at": data.get("created_at", 0),
                    "topics": data.get("topics", []),
                    "turn_count": data.get("turn_count", 0),
                    "code_written": data.get("code_written", False),
                    "duration_seconds": data.get("duration_seconds", 0),
                })
            except (json.JSONDecodeError, OSError):
                continue

        return results

    def delete_summary(self, session_id: str) -> bool:
        """Delete a specific summary."""
        path = _summary_path(session_id)
        if path.exists():
            try:
                path.unlink()
                return True
            except OSError:
                return False
        return False

    def clear_all(self) -> int:
        """Delete all summaries. Returns count deleted."""
        summaries_dir = _summaries_dir()
        count = 0
        for f in summaries_dir.glob("s_*.json"):
            try:
                f.unlink()
                count += 1
            except OSError:
                continue
        return count

    # ── display ──────────────────────────────────────────────────────

    def format_summary_detail(self, summary: Dict[str, Any]) -> str:
        """Format a full summary for terminal display."""
        ts = summary.get("created_at", 0)
        if ts:
            dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            time_str = dt.strftime("%Y-%m-%d %H:%M UTC")
        else:
            time_str = "unknown"

        duration = summary.get("duration_seconds", 0)
        if duration >= 60:
            dur_str = f"{duration / 60:.0f}m {duration % 60:.0f}s"
        elif duration > 0:
            dur_str = f"{duration:.0f}s"
        else:
            dur_str = "N/A"

        lines = [
            "╔══════════════════════════════════════════════════╗",
            "║ Session Summary                                 ║",
            "╚══════════════════════════════════════════════════╝",
            "",
            f"  ID: {summary.get('session_id', '?')}",
            f"  Date: {time_str}",
            f"  Duration: {dur_str}",
            f"  Turns: {summary.get('turn_count', '?')}",
            f"  Model: {summary.get('model', '?')}",
            "",
            f"  Summary: {summary.get('one_line', '(none)')}",
        ]

        topics = summary.get("topics", [])
        if topics:
            lines.append("")
            lines.append("  Topics:")
            for t in topics:
                lines.append(f"    - {t}")

        decisions = summary.get("decisions", [])
        if decisions:
            lines.append("")
            lines.append("  Decisions:")
            for d in decisions:
                lines.append(f"    - {d}")

        files = summary.get("files_modified", [])
        if files:
            lines.append("")
            lines.append("  Files modified:")
            for f in files:
                lines.append(f"    - {f}")

        if summary.get("code_written"):
            lines.append("")
            lines.append("  Code written: yes")

        insights = summary.get("key_insights", [])
        if insights:
            lines.append("")
            lines.append("  Key insights:")
            for i in insights:
                lines.append(f"    - {i}")

        lines.append("")
        return "\n".join(lines)

    def format_sessions_list(
        self,
        summaries: List[Dict[str, Any]],
    ) -> str:
        """Format a list of summaries for terminal display."""
        if not summaries:
            return (
                "╔══════════════════════════════════════════════════╗\n"
                "║ Session Summaries                                ║\n"
                "╚══════════════════════════════════════════════════╝\n"
                "\n"
                "  No session summaries yet.\n"
                "  Use /summary to generate one for this session,\n"
                "  or just exit -- auto-summarize is on by default.\n"
            )

        lines = [
            "╔══════════════════════════════════════════════════╗",
            "║ Session Summaries                                ║",
            "╚══════════════════════════════════════════════════╝",
            "",
        ]

        for i, s in enumerate(summaries, 1):
            ts = s.get("created_at", 0)
            if ts:
                dt = datetime.fromtimestamp(ts, tz=timezone.utc)
                date_str = dt.strftime("%Y-%m-%d %H:%M")
            else:
                date_str = "???"

            one_line = s.get("one_line", "(no summary)")
            if len(one_line) > 60:
                one_line = one_line[:57] + "..."

            turns = s.get("turn_count", "?")
            code_flag = "+" if s.get("code_written") else " "
            topics = s.get("topics", [])
            topic_str = ", ".join(topics[:3]) if topics else ""

            lines.append(
                f"  {i:2d}. [{date_str}] [{code_flag}] {one_line}"
            )
            lines.append(
                f"      {turns} turns | {topic_str}"
            )

        lines.append("")
        lines.append(f"  Showing {len(summaries)} session(s).")
        lines.append("  Use /summary <number> to view details.")
        lines.append("")
        return "\n".join(lines)

    # ── internal helpers ─────────────────────────────────────────────

    def _prune_old_summaries(self) -> None:
        """Remove oldest summaries if over the limit."""
        summaries_dir = _summaries_dir()
        all_files = sorted(
            summaries_dir.glob("s_*.json"),
            key=lambda p: p.stat().st_mtime,
        )
        if len(all_files) > self.max_summaries:
            for f in all_files[: len(all_files) - self.max_summaries]:
                try:
                    f.unlink()
                except OSError:
                    pass
