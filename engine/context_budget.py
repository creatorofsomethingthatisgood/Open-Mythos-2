"""
Fit chat prompts into the model context window (tokens).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


def count_tokens(engine: Any, text: str) -> int:
    """Count tokens using the loaded llama.cpp model."""
    if not text:
        return 0
    return len(engine.model.tokenize(text.encode("utf-8"), add_bos=False))


def count_chat_prompt_tokens(
    engine: Any,
    messages: List[Dict[str, str]],
    system_prompt: Optional[str],
) -> int:
    prompt = engine.format_chat_prompt(messages, system_prompt)
    return count_tokens(engine, prompt)


def truncate_text(text: str, max_chars: int, suffix: str = "\n\n[... truncated for context limit ...]") -> str:
    if len(text) <= max_chars:
        return text
    keep = max(0, max_chars - len(suffix))
    return text[:keep] + suffix


def fit_chat_context(
    engine: Any,
    messages: List[Dict[str, str]],
    system_prompt: str,
    reserve_tokens: int = 2048,
) -> Tuple[List[Dict[str, str]], str, int]:
    """
    Shrink history and/or system prompt so the request fits in n_ctx.

    Returns:
        (trimmed_messages, trimmed_system_prompt, token_count)
    """
    n_ctx = engine.context_length
    budget = max(512, n_ctx - reserve_tokens)
    msgs = list(messages)
    system = system_prompt or ""

    def tokens() -> int:
        return count_chat_prompt_tokens(engine, msgs, system)

    used = tokens()
    if used <= budget:
        return msgs, system, used

    logger.warning(
        "Prompt %d tokens exceeds budget %d (n_ctx=%d); trimming...",
        used,
        budget,
        n_ctx,
    )

    # 1. Drop oldest conversation turns
    while used > budget and len(msgs) >= 2:
        msgs = msgs[2:]
        used = tokens()

    # 2. Shrink system / RAG block (keep start: instructions + first sources)
    while used > budget and len(system) > 2000:
        system = truncate_text(system, int(len(system) * 0.75))
        used = tokens()

    while used > budget and len(system) > 500:
        system = truncate_text(system, max(500, len(system) - 4000))
        used = tokens()

    # 3. Last resort: only latest user message
    if used > budget and len(msgs) > 1:
        msgs = msgs[-1:]
        used = tokens()

    if used > budget:
        logger.error(
            "Prompt still %d tokens after trimming (budget %d). "
            "Raise model.context_length or lower rag.top_k / rag.max_context_chars.",
            used,
            budget,
        )

    return msgs, system, used
