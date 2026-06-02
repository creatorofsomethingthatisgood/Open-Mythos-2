"""
Code explain skill - explain code snippets in plain language.
"""


def run(args: str, context: dict) -> str:
    """Explain the provided code snippet."""
    code = _get_code(args, context)
    if not code:
        return "No code provided. Paste code after the command or load a file with /file."
    lines = code.strip().split("\n")
    explanation_parts = []
    explanation_parts.append(f"Code analysis ({len(lines)} lines):\n")
    # Detect language hints
    lang = _detect_lang(code)
    if lang:
        explanation_parts.append(f"Language hint: {lang}")
    # High-level structure
    explanation_parts.append("\nStructure overview:")
    indent_levels = set()
    for line in lines:
        if line.strip():
            indent = len(line) - len(line.lstrip())
            indent_levels.add(indent // 4 if indent >= 4 else 0)
    if len(indent_levels) > 1:
        explanation_parts.append(f"  - Contains {len(indent_levels)} indentation levels (nested logic)")
    else:
        explanation_parts.append("  - Flat structure (minimal nesting)")
    # Key constructs
    constructs = _find_constructs(code)
    if constructs:
        explanation_parts.append("\nKey constructs found:")
        for c in constructs:
            explanation_parts.append(f"  - {c}")
    # Line-by-line summary
    explanation_parts.append("\nLine-by-line walkthrough:")
    for i, line in enumerate(lines[:20], 1):
        stripped = line.strip()
        if stripped:
            explanation_parts.append(f"  L{i}: {stripped[:80]}")
    if len(lines) > 20:
        explanation_parts.append(f"  ... ({len(lines) - 20} more lines)")
    return "\n".join(explanation_parts)


def steps(args: str, context: dict) -> str:
    """Break down code execution step by step."""
    code = _get_code(args, context)
    if not code:
        return "No code provided."
    lines = [l.strip() for l in code.strip().split("\n") if l.strip()]
    steps_list = []
    steps_list.append("Execution steps:\n")
    for i, line in enumerate(lines, 1):
        desc = _describe_line(line)
        steps_list.append(f"  {i}. {desc}")
    return "\n".join(steps_list)


def simplify(args: str, context: dict) -> str:
    """Simplify the code in plain English."""
    code = _get_code(args, context)
    if not code:
        return "No code provided."
    lines = [l.strip() for l in code.strip().split("\n") if l.strip()]
    simplified = []
    simplified.append("Plain English version:\n")
    for line in lines:
        s = _line_to_english(line)
        if s:
            simplified.append(f"  - {s}")
    return "\n".join(simplified)


def _get_code(args: str, context: dict) -> str:
    if args.strip():
        return args.strip()
    messages = context.get("messages", [])
    # Find the last message that looks like code
    for msg in reversed(messages):
        content = msg.get("content", "")
        if any(kw in content for kw in ["def ", "class ", "import ", "function ", "var ", "const ", "let ", "if ", "for ", "while "]):
            return content
    return ""


def _detect_lang(code: str) -> str:
    if "def " in code or "import " in code or "class " in code:
        if "fn " in code or "let " in code or "pub " in code:
            return "Rust"
        return "Python"
    if "function " in code or "const " in code or "=>" in code:
        return "JavaScript/TypeScript"
    if "fn " in code or "let " in code or "mut " in code:
        return "Rust"
    if "#include" in code or "int main" in code:
        return "C/C++"
    if "package " in code or "func " in code:
        return "Go"
    return ""


def _find_constructs(code: str) -> list:
    constructs = []
    if "def " in code:
        constructs.append("Function definition(s)")
    if "class " in code:
        constructs.append("Class definition(s)")
    if "if " in code or "if(" in code:
        constructs.append("Conditional logic (if/else)")
    if "for " in code or "while " in code:
        constructs.append("Loop(s)")
    if "try" in code or "except" in code or "catch" in code:
        constructs.append("Error handling")
    if "import " in code or "require(" in code or "#include" in code:
        constructs.append("External dependencies")
    if "return " in code:
        constructs.append("Return value(s)")
    if "async " in code or "await " in code:
        constructs.append("Async operations")
    return constructs


def _describe_line(line: str) -> str:
    if line.startswith("def "):
        return f"Define function: {line[4:].split('(')[0]}"
    if line.startswith("class "):
        return f"Define class: {line[6:].split('(')[0].split(':')[0]}"
    if line.startswith("import "):
        return f"Import module: {line[7:].strip()}"
    if line.startswith("if "):
        return f"Check condition: {line[3:].rstrip(':').strip()}"
    if line.startswith("for "):
        return f"Loop: {line[4:].rstrip(':').strip()}"
    if line.startswith("while "):
        return f"While loop: {line[6:].rstrip(':').strip()}"
    if line.startswith("return "):
        return f"Return: {line[7:].strip()}"
    if line.startswith("print"):
        return f"Output: {line.strip()}"
    if "=" in line and not line.startswith(" ") and not line.startswith("#"):
        return f"Assign: {line.strip()}"
    return line.strip()[:80]


def _line_to_english(line: str) -> str:
    if line.startswith("def "):
        name = line[4:].split("(")[0]
        return f"Create a function called {name}"
    if line.startswith("class "):
        name = line[6:].split("(")[0].split(":")[0]
        return f"Define a class called {name}"
    if line.startswith("if "):
        cond = line[3:].rstrip(":").strip()
        return f"If {cond}, then do the following"
    if line.startswith("for "):
        return f"Repeat for each item: {line[4:].rstrip(':').strip()}"
    if line.startswith("while "):
        return f"Keep doing this while: {line[6:].rstrip(':').strip()}"
    if line.startswith("return "):
        return f"Give back the result: {line[7:].strip()}"
    if line.startswith("import "):
        return f"Bring in the {line[7:].strip()} module"
    if line.startswith("print") or line.startswith("console.log"):
        return f"Display something to the user"
    if line.startswith("#") or line.startswith("//"):
        return ""
    return f"Do: {line.strip()[:60]}"
