"""LLM + RAG deep security audit for a single codebase path."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from mythos_cli.config_store import PROMPTS_DIR, llm_config_path

logger = logging.getLogger(__name__)

DEEP_USER_PROMPT = """Perform a security audit of this codebase. Use the retrieved code context.

Prioritize:
1. Authentication, authorization, IDOR
2. Injection and SSRF
3. Secrets, webhooks, unsafe defaults
4. Business-logic flaws (OTP, payments, rate limits)

List concrete findings with Severity, Location, Issue, Impact, Fix.
End with a short executive summary."""


def run_deep_audit(target: Path, temperature: float = 0.2, max_tokens: int = 4096) -> str:
    """
    Index target directory, retrieve relevant chunks, run local LLM audit.

    Requires model downloaded (mythos model download).
    """
    config = llm_config_path()
    if not config.exists():
        raise RuntimeError("Run `mythos init` first.")

    from engine.rag import RAGPipeline
    from engine.inference import InferenceEngine

    target = target.resolve()
    rag = RAGPipeline(str(config))
    if not getattr(rag, "available", True):
        return "RAG dependencies not installed. Install chromadb + sentence-transformers for deep scanning."
    rag.index_directory(path=str(target))

    stats = rag.get_stats()
    if stats["total_chunks"] == 0:
        return "No indexable source files found for deep audit."

    rag_context = rag.get_context(
        "authentication authorization webhook API key SQL injection SSRF secrets",
        top_k=8,
    )

    prompt_path = PROMPTS_DIR / "security_audit.txt"
    if prompt_path.exists():
        system_prompt = prompt_path.read_text(encoding="utf-8")
    else:
        system_prompt = "You are a senior application security engineer."

    system_prompt = (
        f"{system_prompt}\n\n"
        f"CODEBASE: {target}\n\n"
        f"RETRIEVED CONTEXT:\n{rag_context}"
    )

    engine = InferenceEngine(str(config))
    messages = [{"role": "user", "content": DEEP_USER_PROMPT}]
    response = engine.chat(
        messages,
        system_prompt=system_prompt,
        temperature=temperature,
        max_tokens=max_tokens,
        stream=False,
    )
    return response
