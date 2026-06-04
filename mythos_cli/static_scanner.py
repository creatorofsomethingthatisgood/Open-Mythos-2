"""
Fast static security pattern scanner -- runs in seconds, no model required.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}

SCAN_EXTENSIONS = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".go", ".java", ".rb", ".php",
    ".cs", ".rs", ".swift", ".kt", ".scala", ".sql", ".sh", ".bash",
    ".yaml", ".yml", ".json", ".toml", ".env", ".cfg", ".ini",
    ".html", ".vue", ".svelte", ".graphql", ".prisma",
}

# (rule_id, severity, title, pattern, recommendation)
RULES: List[Tuple[str, str, str, re.Pattern, str]] = [
    (
        "SEC001",
        "critical",
        "Possible private key in source",
        re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
        "Remove the key from the repo; rotate credentials; use a secrets manager.",
    ),
    (
        "SEC002",
        "critical",
        "AWS access key pattern",
        re.compile(r"AKIA[0-9A-Z]{16}"),
        "Revoke the key in AWS IAM; never commit cloud credentials.",
    ),
    (
        "SEC003",
        "high",
        "Hardcoded password assignment",
        re.compile(
            r"""(?i)(password|passwd|pwd)\s*=\s*['"][^'"]{4,}['"]""",
        ),
        "Use environment variables or a vault; avoid literals in code.",
    ),
    (
        "SEC004",
        "high",
        "Generic API / secret key assignment",
        re.compile(
            r"""(?i)(api[_-]?key|secret[_-]?key|auth[_-]?token)\s*=\s*['"][^'"]{8,}['"]""",
        ),
        "Load secrets from secure configuration at runtime.",
    ),
    (
        "SEC005",
        "high",
        "JWT secret in source",
        re.compile(r"""(?i)jwt[_-]?secret\s*=\s*['"][^'"]+['"]"""),
        "Store signing secrets outside the codebase.",
    ),
    (
        "SEC006",
        "high",
        "Dangerous code execution",
        re.compile(r"\beval\s*\(|\bexec\s*\("),
        "Avoid dynamic execution; validate and parse structured input instead.",
    ),
    (
        "SEC007",
        "high",
        "Shell invocation with shell=True",
        re.compile(r"subprocess\.(call|run|Popen)\([^)]*shell\s*=\s*True"),
        "Use argument lists and shell=False to prevent command injection.",
    ),
    (
        "SEC008",
        "high",
        "Unsafe deserialization",
        re.compile(r"\bpickle\.loads?\s*\(|\byaml\.load\s*\([^)]*\)"),
        "Use yaml.safe_load; never unpickle untrusted data.",
    ),
    (
        "SEC009",
        "medium",
        "SQL string concatenation in query",
        re.compile(
            r"""(?i)(?:execute|executemany|rawQuery|query)\s*\(\s*"""
            r"""(?:f['"]|['"][^'"]*(?:SELECT|INSERT|UPDATE|DELETE)[^'"]*['"]\s*\+)""",
        ),
        "Use parameterized queries / prepared statements.",
    ),
    (
        "SEC010",
        "medium",
        "TLS verification disabled",
        re.compile(
            r"(?i)verify\s*=\s*False|VERIFY_SSL\s*=\s*False|rejectUnauthorized\s*:\s*false",
        ),
        "Enable certificate verification in production.",
    ),
    (
        "SEC011",
        "medium",
        "Permissive CORS",
        re.compile(r"""(?i)Access-Control-Allow-Origin['"]?\s*[:=]\s*['"]\*['"]"""),
        "Restrict origins to trusted domains.",
    ),
    (
        "SEC012",
        "medium",
        "Debug mode enabled",
        re.compile(r"""(?i)(DEBUG|FLASK_DEBUG|NODE_ENV)\s*[=:]\s*(true|1|development)"""),
        "Disable debug in production deployments.",
    ),
    (
        "SEC013",
        "medium",
        "Webhook without auth hint",
        re.compile(r"""(?i)@(?:app|router)\.(?:post|get)\s*\(\s*['"][^'"]*webhook[^'"]*['"]"""),
        "Verify webhook signatures (HMAC) and reject replayed requests.",
    ),
    (
        "SEC014",
        "low",
        "Potential secret in log output",
        re.compile(r"""(?i)(logger|console)\.(log|info|debug|error)\([^)]*(?:password|token|secret)"""),
        "Redact sensitive values before logging.",
    ),
    (
        "SEC015",
        "info",
        "Environment file in tree",
        re.compile(r"^\.env$"),
        "Ensure .env is gitignored; never commit production secrets.",
    ),
]


@dataclass
class Finding:
    severity: str
    rule_id: str
    title: str
    path: str
    line: int
    snippet: str
    recommendation: str
    scan_root: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _should_skip_dir(name: str, exclude: set) -> bool:
    return name in exclude or name.startswith(".") and name not in (".env.example",)


def iter_source_files(
    root: Path,
    exclude_dirs: List[str],
    max_file_bytes: int,
) -> Iterator[Path]:
    exclude = set(exclude_dirs)
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(p in exclude for p in path.parts):
            continue
        if path.name == ".env":
            yield path
            continue
        if path.suffix.lower() not in SCAN_EXTENSIONS and path.name != ".env":
            continue
        try:
            if path.stat().st_size > max_file_bytes:
                continue
        except OSError:
            continue
        yield path


def scan_file(
    filepath: Path,
    scan_root: Path,
    rules: Optional[List[Tuple[str, str, str, re.Pattern, str]]] = None,
) -> List[Finding]:
    findings: List[Finding] = []
    rules = rules or RULES

    if filepath.name == ".env":
        findings.append(
            Finding(
                severity="high",
                rule_id="SEC016",
                title=".env file present in project",
                path=str(filepath.relative_to(scan_root)),
                line=1,
                snippet=".env",
                recommendation="Confirm it is not committed; use .env.example for templates only.",
                scan_root=str(scan_root),
            )
        )
        return findings

    try:
        text = filepath.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return findings

    rel = str(filepath.relative_to(scan_root))
    lines = text.splitlines()

    for lineno, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        for rule_id, severity, title, pattern, recommendation in rules:
            if rule_id == "SEC015":
                continue
            if pattern.search(line):
                snippet = line.strip()[:120]
                findings.append(
                    Finding(
                        severity=severity,
                        rule_id=rule_id,
                        title=title,
                        path=rel,
                        line=lineno,
                        snippet=snippet,
                        recommendation=recommendation,
                        scan_root=str(scan_root),
                    )
                )
    return findings


def scan_directory(
    root: Path,
    exclude_dirs: Optional[List[str]] = None,
    max_file_bytes: int = 2_097_152,
    min_severity: str = "low",
) -> List[Finding]:
    """Scan a directory tree and return all findings."""
    cfg_exclude = exclude_dirs or [
        ".git", "node_modules", "__pycache__", "venv", ".venv",
        "dist", "build", ".next", "coverage", "chroma_db", "models",
    ]
    min_rank = SEVERITY_ORDER.get(min_severity.lower(), 3)

    all_findings: List[Finding] = []
    for filepath in iter_source_files(root, cfg_exclude, max_file_bytes):
        for finding in scan_file(filepath, root):
            if SEVERITY_ORDER.get(finding.severity, 99) <= min_rank:
                all_findings.append(finding)

    all_findings.sort(
        key=lambda f: (SEVERITY_ORDER.get(f.severity, 99), f.path, f.line)
    )
    return all_findings
