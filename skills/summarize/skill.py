"""
Summarize skill - condense text and conversations.
"""


def run(args: str, context: dict) -> str:
    """Summarize the given text or recent conversation context."""
    text = _get_text(args, context)
    if not text:
        return "No text to summarize. Provide text or have a conversation first."
    words = text.split()
    if len(words) < 20:
        return f"Text is already short ({len(words)} words): {text}"
    sentences = [s.strip() for s in text.replace("!", ".").replace("?", ".").split(".") if s.strip()]
    if not sentences:
        return text[:200]
    # Extract key sentences (first, last, and longest middle ones)
    key = []
    if sentences:
        key.append(sentences[0])
    if len(sentences) > 2:
        mid = sorted(sentences[1:-1], key=len, reverse=True)[:3]
        key.extend(mid)
    if len(sentences) > 1:
        key.append(sentences[-1])
    # Deduplicate while preserving order
    seen = set()
    unique = []
    for s in key:
        if s not in seen:
            seen.add(s)
            unique.append(s)
    summary = ". ".join(unique) + "."
    return f"[Summary] {summary}"


def bullets(args: str, context: dict) -> str:
    """Produce a bullet-point summary."""
    text = _get_text(args, context)
    if not text:
        return "No text to summarize."
    sentences = [s.strip() for s in text.replace("!", ".").replace("?", ".").split(".") if s.strip()]
    points = sentences[:8]  # cap at 8 bullets
    lines = [f"  - {p}" for p in points]
    return "Bullet summary:\n" + "\n".join(lines)


def tldr(args: str, context: dict) -> str:
    """One-line TLDR summary."""
    text = _get_text(args, context)
    if not text:
        return "No text to summarize."
    sentences = [s.strip() for s in text.replace("!", ".").replace("?", ".").split(".") if s.strip()]
    if sentences:
        return f"TLDR: {sentences[0]}"
    return f"TLDR: {text[:100]}"


def _get_text(args: str, context: dict) -> str:
    """Get text from args or conversation context."""
    if args.strip():
        return args.strip()
    messages = context.get("messages", [])
    if messages:
        parts = []
        for msg in messages[-10:]:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            parts.append(f"[{role}] {content}")
        return "\n".join(parts)
    return ""
