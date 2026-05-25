"""
Print fix results for CLI and chat — with colorful git-style diff output.

Removed lines are shown in **red** with a ``-`` prefix.
Added   lines are shown in **green** with a ``+`` prefix.
"""

from __future__ import annotations

from typing import List

from mythos_cli.auto_fix import FixResult
from mythos_cli.console import console, STYLE_OK, STYLE_WARN, STYLE_ERR, STYLE_DIM


def print_fix_results(fixes: List[FixResult], *, dry_run: bool) -> int:
    from rich.panel import Panel
    from rich.table import Table

    applied = [f for f in fixes if f.status in ("applied", "pending")]
    skipped = [f for f in fixes if f.status == "skipped"]

    if not fixes:
        console.print("[yellow]No fixable findings[/yellow] "
                      "(secrets and logic issues need manual review).")
        return 0

    mode = "PREVIEW (dry-run)" if dry_run else "APPLIED"
    title_style = "bold yellow" if dry_run else STYLE_OK
    console.print()
    console.print(Panel.fit(
        f"[{title_style}]Auto-fix — {mode}[/{title_style}]",
        border_style="yellow" if dry_run else "green",
    ))

    # ── Applied / pending fixes with diff ────────────────────────────────
    if applied:
        table = Table(show_header=True, header_style="bold", box=None, padding=(0, 1))
        table.add_column("Status", width=8)
        table.add_column("Location", min_width=28)
        table.add_column("Fix", min_width=20)
        table.add_column("Diff", min_width=30)

        for f in applied:
            if f.status not in ("applied", "pending"):
                continue
            label = f"[yellow]pending[/yellow]" if dry_run else STYLE_OK
            loc = f"[bold]{f.path}:{f.line}[/bold]  [dim]({f.rule_id})[/dim]"
            diff_lines = _build_diff(f.before, f.after)
            table.add_row(
                label,
                loc,
                f.detail,
                "\n".join(diff_lines) if diff_lines else "[dim]—[/dim]",
            )
        console.print(table)
        console.print()

    # ── Skipped findings ─────────────────────────────────────────────────
    if skipped:
        console.print(f"[{STYLE_WARN}]Skipped {len(skipped)} finding(s)[/] "
                      "(no safe auto-fix):")
        for f in skipped[:10]:
            console.print(f"  [dim]{f.path}:{f.line} ({f.rule_id})[/] — {f.detail}")
        if len(skipped) > 10:
            console.print(f"  [dim]... and {len(skipped) - 10} more[/dim]")
        console.print()

    # ── Next-step hints ──────────────────────────────────────────────────
    if dry_run and applied:
        console.print(Panel.fit(
            "[yellow]Re-run with [bold]--apply[/bold] to write line-level fixes "
            "(use git; no .bak files).[/yellow]",
            border_style="yellow",
        ))
    elif not dry_run and applied:
        console.print(Panel.fit(
            "[green]Changes written — review with [bold]git diff[/bold].[/green]",
            border_style="green",
        ))

    return len(applied)


def _build_diff(before: str, after: str) -> list[str]:
    """Return coloured diff lines (red ``-`` / green ``+``) for a changed line."""
    lines: list[str] = []
    if before:
        lines.append(f"[red]- {before}[/red]")
    if after:
        lines.append(f"[green]+ {after}[/green]")
    return lines
