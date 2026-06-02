"""
Quick reference skill - lookup common programming patterns and commands.
"""

PYTHON_REF = """\
[Python Quick Reference]

Data types:
  str, int, float, bool, list, dict, tuple, set, None

Common operations:
  len(x)         - length
  type(x)        - type check
  isinstance(x, T) - type check with class
  range(start, stop, step) - number range
  enumerate(iterable) - index + value pairs
  zip(a, b)      - pair elements from iterables

String:
  s.upper(), s.lower(), s.strip()
  s.split(sep), sep.join(list)
  s.startswith(x), s.endswith(x)
  f"value: {var}"  - f-string formatting

List:
  l.append(x), l.extend(iter)
  l.insert(i, x), l.pop([i])
  l.sort(), l.reverse()
  [x for x in l if cond]  - list comprehension

Dict:
  d.keys(), d.values(), d.items()
  d.get(key, default)
  d.setdefault(key, default)
  {k: v for k, v in iter}  - dict comprehension

File I/O:
  with open(path, "r") as f: f.read()
  with open(path, "w") as f: f.write(s)

Error handling:
  try: ... except Exception as e: ...
  finally: ...
  raise ValueError("msg")
"""

GIT_REF = """\
[Git Quick Reference]

Basics:
  git init                  - Initialize repo
  git clone <url>           - Clone remote repo
  git status                - Show working tree status
  git add <file>            - Stage changes
  git add -A                - Stage all changes
  git commit -m "msg"       - Commit staged changes
  git push                  - Push to remote
  git pull                  - Pull and merge from remote

Branching:
  git branch                - List branches
  git branch <name>         - Create branch
  git checkout <branch>     - Switch branch
  git checkout -b <name>    - Create and switch
  git merge <branch>        - Merge branch into current
  git branch -d <name>      - Delete branch

History:
  git log --oneline         - Compact log
  git log --graph           - Branch graph
  git diff                  - Unstaged changes
  git diff --staged         - Staged changes

Undo:
  git checkout -- <file>    - Discard working changes
  git reset HEAD <file>     - Unstage file
  git revert <commit>       - Revert commit (safe)
  git stash                 - Stash changes
  git stash pop             - Apply stashed changes
"""

REGEX_REF = """\
[Regular Expression Quick Reference]

Character classes:
  .        - Any character (except newline)
  \\d       - Digit [0-9]
  \\w       - Word character [a-zA-Z0-9_]
  \\s       - Whitespace
  \\D, \\W, \\S - Negated versions

Quantifiers:
  *        - Zero or more
  +        - One or more
  ?        - Zero or one
  {n}      - Exactly n
  {n,m}    - Between n and m
  {n,}     - n or more

Anchors:
  ^        - Start of string/line
  $        - End of string/line
  \\b       - Word boundary

Groups:
  (abc)    - Capturing group
  (?:abc)  - Non-capturing group
  (?P<name>abc) - Named group
  a|b      - Alternation (OR)

Lookahead/Lookbehind:
  (?=abc)  - Positive lookahead
  (?!abc)  - Negative lookahead
  (?<=abc) - Positive lookbehind
  (?<!abc) - Negative lookbehind

Flags (Python):
  re.IGNORECASE  - Case insensitive
  re.MULTILINE   - ^/$ match line starts/ends
  re.DOTALL      - . matches newline
"""


def run(args: str, context: dict) -> str:
    """Look up a quick reference topic."""
    topic = args.strip().lower()
    if not topic:
        return "Available references: python, git, regex. Usage: /skill quick_ref run <topic>"
    if "python" in topic or "py" in topic:
        return PYTHON_REF
    if "git" in topic:
        return GIT_REF
    if "regex" in topic or "regexp" in topic or "regular" in topic:
        return REGEX_REF
    return f"No reference found for '{topic}'. Available: python, git, regex"


def python_ref(args: str, context: dict) -> str:
    return PYTHON_REF


def git_ref(args: str, context: dict) -> str:
    return GIT_REF


def regex_ref(args: str, context: dict) -> str:
    return REGEX_REF
