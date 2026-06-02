"""
Brainstorm skill - generate creative ideas and explore solutions.
"""


def run(args: str, context: dict) -> str:
    """Brainstorm ideas on the given topic."""
    topic = _get_topic(args, context)
    if not topic:
        return "Provide a topic to brainstorm about."
    return (
        f"[Brainstorm Session: {topic}]\n\n"
        f"Let me generate ideas for: {topic}\n\n"
        f"Here are some directions to explore:\n"
        f"  1. What if we approached this from the opposite direction?\n"
        f"  2. What would a child's solution look like?\n"
        f"  3. What would an expert in a completely different field do?\n"
        f"  4. What is the simplest possible version of this?\n"
        f"  5. What would this look like with unlimited resources?\n"
        f"  6. What if we removed the biggest constraint?\n"
        f"  7. What has worked for similar problems in nature?\n"
        f"  8. What would the minimal viable approach be?\n"
        f"  9. How would this work in a different culture or era?\n"
        f"  10. What if we combined this with something unrelated?\n\n"
        f"Use /skill brainstorm ideas <topic> for 10 specific ideas.\n"
        f"Use /skill brainstorm pros_cons <idea> for analysis.\n"
        f"Use /skill brainstorm alternatives <approach> for different approaches."
    )


def ideas(args: str, context: dict) -> str:
    """Generate 10 creative ideas on the topic."""
    topic = _get_topic(args, context)
    if not topic:
        return "Provide a topic for idea generation."
    return (
        f"[10 Ideas for: {topic}]\n\n"
        f"Please generate 10 creative, diverse, and actionable ideas for: {topic}\n\n"
        f"Format each idea as:\n"
        f"  ## Idea N: [Short Title]\n"
        f"  Description: [2-3 sentences]\n"
        f"  Feasibility: [Low/Medium/High]\n"
        f"  Key benefit: [One sentence]\n\n"
        f"Be creative. Mix practical and bold ideas. Think across domains."
    )


def pros_cons(args: str, context: dict) -> str:
    """List pros and cons for a decision or idea."""
    topic = _get_topic(args, context)
    if not topic:
        return "Provide an idea or decision to analyze."
    return (
        f"[Pros & Cons: {topic}]\n\n"
        f"Please analyze the pros and cons of: {topic}\n\n"
        f"Format:\n"
        f"  PROS:\n"
        f"    + [pro 1]\n"
        f"    + [pro 2]\n"
        f"    + [pro 3]\n"
        f"    ...\n\n"
        f"  CONS:\n"
        f"    - [con 1]\n"
        f"    - [con 2]\n"
        f"    - [con 3]\n"
        f"    ...\n\n"
        f"  VERDICT: [Your balanced assessment]\n\n"
        f"Be thorough and balanced. Consider short-term and long-term effects."
    )


def alternatives(args: str, context: dict) -> str:
    """Suggest alternative approaches."""
    topic = _get_topic(args, context)
    if not topic:
        return "Provide an approach to find alternatives for."
    return (
        f"[Alternative Approaches for: {topic}]\n\n"
        f"Please suggest 5 alternative approaches to: {topic}\n\n"
        f"For each alternative:\n"
        f"  ## Approach N: [Name]\n"
        f"  How it works: [brief description]\n"
        f"  Trade-offs vs. original: [key differences]\n"
        f"  When to choose this: [best use case]\n\n"
        f"Range from conservative tweaks to radical rethinks."
    )


def _get_topic(args: str, context: dict) -> str:
    if args.strip():
        return args.strip()
    messages = context.get("messages", [])
    if messages:
        return messages[-1].get("content", "")
    return ""
