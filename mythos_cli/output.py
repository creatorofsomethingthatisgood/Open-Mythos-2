"""Format scan results for terminal and CI."""

from __future__ import annotations

import json
from collections import Counter
from typing import List, Optional

from mythos_cli.console import console
from mythos_cli.static_scanner import Finding, SEVERITY_ORDER

try:
    from rich.table import Table
    from rich.panel import Panel
    from rich import box

    RICH = True
except ImportError:
    RICH = False


SEVERITY_STYLE = {
    "critical": "bold red",
    "high": "red",
    "medium": "yellow",
    "low": "blue",
    "info": "dim",
}


def print_summary(findings: List[Finding], roots: List[str], deep_report: Optional[str] = None) -> int:
    """Print human-readable report. Returns exit code (1 if critical/high)."""
    counts = Counter(f.severity for f in findings)

    if RICH:
        return _print_rich(findings, roots, counts, deep_report)
    return _print_plain(findings, roots, counts, deep_report)


def _print_plain(
    findings: List[Finding],
    roots: List[str],
    counts: Counter,
    deep_report: Optional[str],
) -> int:
    from mythos_cli.console import STYLE_ERR, STYLE_OK, STYLE_DIM

    console.print("\n[bold #EA580C]╔══ Mythos Security Scan ══╗[/bold #EA580C]")
    console.print()
    for root in roots:
        console.print(f"  [dim]Scanned:[/dim] {root}")
    console.print()
    console.print(
        f"  [bold red]Critical:[/bold red] {counts.get('critical', 0)}  "
        f"[red]High:[/red] {counts.get('high', 0)}  "
        f"[yellow]Medium:[/yellow] {counts.get('medium', 0)}  "
        f"[blue]Low:[/blue] {counts.get('low', 0)}  "
        f"[dim]Info:[/dim] {counts.get('info', 0)}"
    )
    console.print()

    for f in findings:
        style = SEVERITY_STYLE.get(f.severity, "")
        console.print(f"[{style}][{f.severity.upper()}][/{style}] "
                      f"[bold]{f.rule_id}[/bold] {f.path}:{f.line}")
        console.print(f"  {f.title}")
        console.print(f"  [{STYLE_DIM}]{f.snippet}[/{STYLE_DIM}]")
        console.print(f"  → {f.recommendation}\n")

    if deep_report:
        console.print("\n[bold #F97316]── AI Deep Audit ──[/bold #F97316]\n")
        console.print(deep_report)

    if counts.get("critical") or counts.get("high"):
        console.print(f"\n[{STYLE_ERR}]Failed: critical or high severity findings present.[/{STYLE_ERR}]")
        return 1
    return 0


def _print_rich(
    findings: List[Finding],
    roots: List[str],
    counts: Counter,
    deep_report: Optional[str],
) -> int:
    console.print()
    console.print(
        Panel.fit(
            "[bold #EA580C]Mythos Sentinel[/bold #EA580C] — security scan results",
            border_style="#EA580C",
        )
    )
    for root in roots:
        console.print(f"  [dim]Scanned[/dim] {root}")
    console.print()

    summary = Table.grid(padding=(0, 2))
    for sev in ("critical", "high", "medium", "low", "info"):
        n = counts.get(sev, 0)
        style = SEVERITY_STYLE.get(sev, "")
        summary.add_row(f"[{style}]{sev.capitalize()}[/{style}]", str(n))
    console.print(summary)
    console.print()

    if not findings:
        console.print("[green]No issues matched your severity filter.[/green]")
    else:
        table = Table(box=box.SIMPLE_HEAD, show_lines=False, pad_edge=False)
        table.add_column("Sev", style="bold", width=8)
        table.add_column("Rule", width=7)
        table.add_column("Location", min_width=28)
        table.add_column("Issue", min_width=24)

        for f in findings:
            style = SEVERITY_STYLE.get(f.severity, "")
            loc = f"{f.path}:{f.line}"
            table.add_row(
                f"[{style}]{f.severity}[/{style}]",
                f.rule_id,
                loc,
                f.title,
            )
        console.print(table)
        console.print()
        console.print("[dim]Run with --verbose for snippets and remediation text[/dim]")

    if deep_report:
        console.print()
        console.print(Panel(deep_report, title="AI Deep Audit", border_style="#F97316"))

    if counts.get("critical") or counts.get("high"):
        console.print("\n[bold red]Failed:[/bold red] critical or high severity findings present.")
        return 1
    console.print("\n[green]Passed[/green] (no critical/high static findings).")
    return 0


def print_verbose_findings(findings: List[Finding]) -> None:
    if not RICH:
        for f in findings:
            print(f"\n{f.rule_id} @ {f.path}:{f.line}\n  {f.snippet}\n  → {f.recommendation}")
        return
    for f in findings:
        style = SEVERITY_STYLE.get(f.severity, "")
        console.print(
            f"\n[{style}]{f.severity.upper()}[/{style}] [bold]{f.rule_id}[/bold] "
            f"{f.path}:{f.line} — {f.title}"
        )
        console.print(f"  [dim]{f.snippet}[/dim]")
        console.print(f"  → {f.recommendation}")


def print_json(findings: List[Finding], roots: List[str], deep_report: Optional[str] = None) -> int:
    payload = {
        "scanned_roots": roots,
        "finding_count": len(findings),
        "by_severity": dict(Counter(f.severity for f in findings)),
        "findings": [f.to_dict() for f in findings],
        "deep_audit": deep_report,
    }
    print(json.dumps(payload, indent=2))
    counts = payload["by_severity"]
    if counts.get("critical") or counts.get("high"):
        return 1
    return 0
