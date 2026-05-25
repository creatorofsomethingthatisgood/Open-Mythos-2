"""
Contextual "next step" suggestions — shown after commands to guide the user.

These mimic the helpful hints that Claude Code, Cline, and other polished
CLI tools show after operations.
"""

from __future__ import annotations

from typing import List, Optional

from rich.panel import Panel
from rich.table import Table

from mythos_cli.console import console, STYLE_DIM, STYLE_INFO


def show_suggestions(suggestions: List[str], title: str = "Next steps") -> None:
    """Render a set of hints in a compact panel."""
    if not suggestions:
        return
    table = Table.grid(padding=(0, 1))
    for s in suggestions:
        table.add_row(f"  [{STYLE_INFO}]→[/] [{STYLE_DIM}]{s}[/{STYLE_DIM}]")
    console.print()
    console.print(Panel.fit(
        table,
        title=f"[bold]{title}[/bold]",
        border_style="dim",
        padding=(0, 1),
    ))


# ── Per-command suggestion factories ──────────────────────────────────────

def after_init() -> List[str]:
    return [
        "Register a codebase: [bold]mythos path add ~/your/project[/bold]",
        "Run a quick scan:   [bold]mythos scan[/bold]",
        "Start the chat:     [bold]mythos chat[/bold] (or just [bold]mythos[/bold])",
    ]


def after_path_add(label: str) -> List[str]:
    return [
        "Scan it now:        [bold]mythos scan[/bold]",
        "Add another path:   [bold]mythos path add ~/other/project[/bold]",
        "List all paths:     [bold]mythos path list[/bold]",
    ]


def after_path_list(count: int) -> List[str]:
    if count == 0:
        return [
            "Add your first path: [bold]mythos path add ~/your/project[/bold]",
        ]
    return [
        "Scan all paths:      [bold]mythos scan[/bold]",
        "Remove a path:       [bold]mythos path remove <path-or-id>[/bold]",
    ]


def after_path_removed() -> List[str]:
    return [
        "List remaining paths: [bold]mythos path list[/bold]",
        "Add a new path:       [bold]mythos path add ~/other/project[/bold]",
    ]


def after_scan(
    finding_count: int,
    has_critical_or_high: bool,
) -> List[str]:
    tips: List[str] = []
    if finding_count == 0:
        tips.append("Run deep AI audit:  [bold]mythos scan --deep[/bold] (needs a model)")
        tips.append("Auto-fix safe issues: [bold]mythos fix --path .[/bold] (preview)")
    elif has_critical_or_high:
        tips.append("Auto-fix safe patterns: [bold]mythos fix --apply --path .[/bold]")
        tips.append("Review findings:        [bold]mythos scan --verbose[/bold]")
        tips.append("For full rewrite:       [bold]mythos chat[/bold] then use /fix or /rewrite")
    else:
        tips.append("Auto-fix low-hanging fruit: [bold]mythos fix --apply --path .[/bold]")
        tips.append("Deep AI audit:              [bold]mythos scan --deep --path .[/bold]")
    return tips


def after_fix(applied_count: int, dry_run: bool) -> List[str]:
    if dry_run and applied_count > 0:
        return [
            "Apply fixes:         [bold]mythos fix --apply --path .[/bold]",
            "Review with git:     [bold]git diff[/bold]",
        ]
    if applied_count > 0:
        return [
            "Review changes:      [bold]git diff[/bold]",
            "Re-scan to verify:   [bold]mythos scan --path .[/bold]",
        ]
    return [
        "Try deep AI audit:    [bold]mythos scan --deep --path .[/bold]",
    ]


def after_model_download() -> List[str]:
    return [
        "Run a deep AI scan:   [bold]mythos scan --deep --path .[/bold]",
        "Check model status:   [bold]mythos status[/bold]",
    ]


def after_update(updated: bool) -> List[str]:
    if updated:
        return [
            "Check new features:  [bold]mythos --help[/bold]",
            "Start chatting:      [bold]mythos[/bold]",
        ]
    return [
        "You are up to date!",
        "Start chatting:       [bold]mythos[/bold]",
    ]


def after_status() -> List[str]:
    return [
        "Run a scan:           [bold]mythos scan[/bold]",
        "Init if missing:      [bold]mythos init[/bold]",
        "Download a model:     [bold]mythos model download[/bold]",
    ]


def after_explore() -> List[str]:
    return [
        "Index documents:      Configure RAG in config.yaml",
        "Then use:             [bold]mythos chat[/bold] with /rag on",
    ]


def after_reset() -> List[str]:
    return [
        "Register a codebase: [bold]mythos path add ~/your/project[/bold]",
        "Run a scan:          [bold]mythos scan[/bold]",
        "Start chatting:      [bold]mythos chat[/bold] (or just [bold]mythos[/bold])",
    ]


def after_factory_reset() -> List[str]:
    return [
        "Run setup:           [bold]bash setup.sh[/bold]",
        "Then init:           [bold]mythos init[/bold]",
        "Download a model:    [bold]mythos model download[/bold]",
    ]


def on_error(command: str) -> List[str]:
    """Suggestions shown after a command fails."""
    return [
        f"Run [bold]mythos {command} --help[/bold] for usage info",
        "Check your config:   [bold]mythos status[/bold]",
        "Re-run init:         [bold]mythos init[/bold]",
    ]
