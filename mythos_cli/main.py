#!/usr/bin/env python3
"""
Mythos — your local AI assistant and security scanner.

 mythos # launch chat (like `claude`)
 mythos chat # same thing
 mythos web # web UI
 mythos scan # security scan
 mythos init # first-time setup
 mythos path add . # register a codebase for scanning
 mythos status # show config / model status
 mythos update # pull latest version from GitHub
"""

from __future__ import annotations

import argparse
import logging
import shutil
import sys
from pathlib import Path

from mythos_cli import __version__
from mythos_cli.config_store import (
    PACKAGE_ROOT,
    _patch_llm_config_for_user,
    add_scan_path,
    ensure_initialized,
    init_config,
    list_scan_paths,
    llm_config_path,
    load_user_config,
    models_hint_dir,
    mythos_home,
    remove_scan_path,
    user_config_path,
)
from mythos_cli.output import print_json, print_summary, print_verbose_findings
from mythos_cli.scan_runner import run_scan
from mythos_cli.fix_runner import run_fix
from mythos_cli.fix_output import print_fix_results

logging.basicConfig(
    level=logging.WARNING,
    format="%(levelname)s: %(message)s",
)


# ── chat / web ──────────────────────────────────────────────────────────

def _cmd_chat(args: argparse.Namespace) -> int:
    from mythos_cli.chat import launch_chat
    launch_chat(
        config_path=args.config if args.config != "config.yaml" else None,
        verbose=args.verbose,
    )
    return 0


def _cmd_web(args: argparse.Namespace) -> int:
    from mythos_cli.chat import launch_web
    launch_web(
        config_path=args.config if args.config != "config.yaml" else None,
        port=args.port,
        share=args.share,
    )
    return 0


# ── security scanner ────────────────────────────────────────────────────

def _cmd_init(_args: argparse.Namespace) -> int:
    from mythos_cli.console import console, STYLE_OK
    from mythos_cli.suggest import after_init, show_suggestions

    init_config(quiet=False)
    console.print(f"\n[{STYLE_OK}]✓ Mythos is ready![/]")
    show_suggestions(after_init())
    return 0


def _get_console():
    """Lazy import of the shared console for use in exception handlers."""
    from mythos_cli.console import console
    return console


def _cmd_path_add(args: argparse.Namespace) -> int:
    from mythos_cli.console import console, STYLE_OK, STYLE_INFO
    from mythos_cli.suggest import after_path_add, show_suggestions
    from rich.panel import Panel

    ensure_initialized()
    entry = add_scan_path(args.directory, label=args.label)
    console.print()
    console.print(Panel.fit(
        f"[{STYLE_OK}]✓ Path registered[/{STYLE_OK}]\n"
        f"  [{STYLE_INFO}]{entry['label']}[/{STYLE_INFO}]\n"
        f"  [dim]{entry['path']}[/dim]",
        border_style="green",
    ))
    show_suggestions(after_path_add(entry['label']))
    return 0


def _cmd_path_list(_args: argparse.Namespace) -> int:
    from mythos_cli.console import console, STYLE_WARN, STYLE_INFO
    from mythos_cli.suggest import after_path_list, show_suggestions

    ensure_initialized()
    paths = list_scan_paths()
    if not paths:
        console.print(f"[{STYLE_WARN}]No paths configured.[/{STYLE_WARN}]")
        show_suggestions(after_path_list(0))
        return 0
    console.print(f"\n[{STYLE_INFO}]{len(paths)} registered path(s):[/{STYLE_INFO}]\n")
    for i, entry in enumerate(paths, 1):
        console.print(f"  {i}. [bold]{entry.get('label', '')}[/bold] [dim]({entry.get('id', '?')})[/dim]")
        console.print(f"     [dim]{entry['path']}[/dim]")
    show_suggestions(after_path_list(len(paths)))
    return 0


def _cmd_path_remove(args: argparse.Namespace) -> int:
    from mythos_cli.console import console, STYLE_OK, STYLE_ERR
    from mythos_cli.suggest import after_path_removed, show_suggestions, on_error

    ensure_initialized()
    if remove_scan_path(args.target):
        console.print(f"[{STYLE_OK}]✓ Removed:[/] {args.target}")
        show_suggestions(after_path_removed())
        return 0
    console.print(f"[{STYLE_ERR}]Not found:[/] {args.target}")
    show_suggestions(on_error("path remove"))
    return 1


def _cmd_scan(args: argparse.Namespace) -> int:
    from mythos_cli.console import console
    from mythos_cli.spinner import spinner
    from mythos_cli.suggest import after_scan, show_suggestions, on_error

    ensure_initialized()
    if args.verbose:
        logging.getLogger().setLevel(logging.INFO)

    scan_label = (
        "Running deep AI audit (this may take a minute)..."
        if args.deep
        else "Scanning files for security issues..."
    )

    with spinner(scan_label):
        try:
            findings, roots, deep_report = run_scan(
                path_arg=args.path,
                deep=args.deep,
                min_severity=args.severity,
            )
        except FileNotFoundError as e:
            console = _get_console()
            console.print(f"[bold red]Error:[/bold red] {e}")
            show_suggestions(on_error("scan"))
            return 1
        except RuntimeError as e:
            console = _get_console()
            console.print(f"[bold red]Error:[/bold red] {e}")
            show_suggestions(on_error("scan"))
            return 1
        except Exception as e:
            console = _get_console()
            if args.deep:
                console.print(
                    f"[bold red]Deep scan failed:[/bold red] {e}\n"
                    "[yellow]Ensure the model is installed:[/yellow] "
                    "[bold]mythos model download[/bold]"
                )
            else:
                console.print(f"[bold red]Scan failed:[/bold red] {e}")
            show_suggestions(on_error("scan"))
            return 1

    if args.format == "json":
        return print_json(findings, roots, deep_report)

    if args.verbose and findings:
        print_verbose_findings(findings)

    rc = print_summary(findings, roots, deep_report)
    has_critical_high = any(f.severity in ("critical", "high") for f in findings)
    show_suggestions(after_scan(len(findings), has_critical_high))
    return rc


def _cmd_fix(args: argparse.Namespace) -> int:
    from mythos_cli.console import console
    from mythos_cli.spinner import spinner
    from mythos_cli.suggest import after_fix, show_suggestions, on_error

    ensure_initialized()
    dry_run = not args.apply

    with spinner("Scanning for auto-fixable patterns..."):
        try:
            findings, roots, fixes = run_fix(
                path_arg=args.path,
                dry_run=dry_run,
                min_severity=args.severity,
            )
        except FileNotFoundError as e:
            console.print(f"[bold red]Error:[/bold red] {e}")
            show_suggestions(on_error("fix"))
            return 1
        except Exception as e:
            console.print(f"[bold red]Fix failed:[/bold red] {e}")
            show_suggestions(on_error("fix"))
            return 1

    applied_count = print_fix_results(fixes, dry_run=dry_run)

    if findings:
        from mythos_cli.output import print_summary

        console.print(f"\n[bold yellow]Remaining findings after fix:[/bold yellow]")
        rc = print_summary(findings, roots, None)
    else:
        console.print(f"\n[green]✓ No remaining static findings at configured severity.[/green]")
        rc = 0

    show_suggestions(after_fix(applied_count, dry_run))
    return rc


def _cmd_explore(args: argparse.Namespace) -> int:
    from mythos_cli.console import console, STYLE_ERR, STYLE_INFO, STYLE_DIM
    from mythos_cli.suggest import after_explore, show_suggestions

    ensure_initialized()
    from engine.rag import RAGPipeline

    config = llm_config_path()
    if not config.exists():
        console.print(f"[{STYLE_ERR}]Run [bold]mythos init[/bold] first.[/{STYLE_ERR}]")
        return 1

    rag = RAGPipeline(str(config))
    summary = rag.explore_directory(args.path)
    console.print(f"\n[{STYLE_INFO}]Directory:[/] [bold]{summary['directory']}[/bold]")
    if not summary.get("exists"):
        console.print(f"[{STYLE_ERR}]Directory does not exist.[/{STYLE_ERR}]")
        return 1
    console.print(f"  [bold]Indexable files:[/] {summary['file_count']}")
    console.print(f"  [bold]Total size:[/] {summary['total_bytes']} bytes")
    if summary.get("sample_files"):
        console.print(f"\n[{STYLE_INFO}]Sample files:[/{STYLE_INFO}]")
        for rel in summary["sample_files"][:15]:
            console.print(f"  [{STYLE_DIM}]{rel}[/{STYLE_DIM}]")
    show_suggestions(after_explore())
    return 0


def _cmd_model_download(_args: argparse.Namespace) -> int:
    from mythos_cli.console import console, STYLE_OK, STYLE_WARN
    from mythos_cli.suggest import after_model_download, show_suggestions

    ensure_initialized()
    from engine.model_manager import ModelManager

    config = llm_config_path()
    console.print(f"[{STYLE_WARN}]Downloading default security audit model (~4.5 GB)...[/{STYLE_WARN}]")
    console.print("[dim]This may take a while depending on your internet speed.[/dim]")
    manager = ModelManager(str(config))
    path = manager.download_default()
    console.print(f"\n[{STYLE_OK}]✓ Model ready:[/] [dim]{path}[/dim]")
    show_suggestions(after_model_download())
    return 0


def _cmd_status(_args: argparse.Namespace) -> int:
    from mythos_cli.console import console, STYLE_OK, STYLE_WARN, STYLE_DIM, STYLE_ERR
    from mythos_cli.suggest import after_status, show_suggestions
    from rich.table import Table
    from rich.panel import Panel

    home = mythos_home()
    cfg = user_config_path()
    llm = llm_config_path()
    paths = list_scan_paths() if cfg.exists() else []

    console.print()
    console.print(Panel.fit(
        "[bold cyan]╔══ Mythos ══╗[/bold cyan]",
        border_style="cyan",
    ))
    console.print()

    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Key", style="bold cyan", min_width=16)
    table.add_column("Value", min_width=48)

    table.add_row("Version", f"[bold]{__version__}[/bold]")
    table.add_row("Config home", f"[dim]{home}[/dim]")
    table.add_row(
        "User config",
        f"[{STYLE_OK}]ready ✓[/{STYLE_OK}]" if cfg.exists()
        else f"[{STYLE_WARN}]not initialized[/{STYLE_WARN}] — run [bold]mythos init[/bold]",
    )
    table.add_row(
        "LLM config",
        f"[{STYLE_OK}]ready ✓[/{STYLE_OK}]" if llm.exists() else f"[{STYLE_WARN}]missing[/{STYLE_WARN}]",
    )
    table.add_row(
        "Scan paths",
        f"[bold]{len(paths)}[/bold] registered",
    )
    for entry in paths:
        table.add_row("", f"  [dim]- {entry.get('label')}: {entry['path']}[/dim]")

    model_dir = models_hint_dir()
    gguf = list(model_dir.glob("*.gguf")) if model_dir.exists() else []
    model_status = (
        f"[{STYLE_OK}]{len(gguf)} model(s) ✓[/{STYLE_OK}] in [dim]{model_dir}[/dim]"
        if gguf
        else f"[{STYLE_WARN}]No models found[/{STYLE_WARN}] — run [bold]mythos model download[/bold]"
    )
    table.add_row("Models", model_status)

    console.print(table)
    show_suggestions(after_status())
    return 0


def _cmd_update(_args: argparse.Namespace) -> int:
    """Pull latest Mythos from GitHub while preserving user settings and dependencies."""
    import json
    import subprocess
    import tempfile

    from mythos_cli.console import console, STYLE_OK, STYLE_WARN, STYLE_ERR, STYLE_DIM, STYLE_INFO
    from rich.panel import Panel

    PACKAGE_DIR = str(PACKAGE_ROOT)

    # ── 1. Snapshot current version ──────────────────────────────────────
    old_version = __version__
    console.print(f"\n[{STYLE_INFO}]Mythos Update[/{STYLE_INFO}]")
    console.print(f"  Current version: [bold]{old_version}[/bold]")

    # ── 2. Backup user data from ~/.config/mythos ────────────────────────
    home = mythos_home()
    backup_dir = Path(tempfile.mkdtemp(prefix="mythos_update_"))

    user_files_to_backup = [
        "config.yaml",
        "mythos.yaml",
        "rml_preferences.json",
    ]

    backed_up = []
    for fname in user_files_to_backup:
        src = home / fname
        if src.exists():
            shutil.copy2(src, backup_dir / fname)
            backed_up.append(fname)

    # Also backup conversations dir if it has content
    conv_src = home / "conversations"
    conv_backup = backup_dir / "conversations"
    if conv_src.is_dir() and any(conv_src.iterdir()):
        shutil.copytree(conv_src, conv_backup, dirs_exist_ok=True)
        backed_up.append("conversations/")

    if backed_up:
        console.print(f"  [{STYLE_DIM}]Backed up:[/] {', '.join(backed_up)}")

    # ── 3. Git pull ─────────────────────────────────────────────────────
    console.print(f"  [{STYLE_WARN}]Fetching latest version from GitHub...[/{STYLE_WARN}]")

    try:
        # Stash any uncommitted local changes
        result = subprocess.run(
            ["git", "stash", "--include-untracked"],
            cwd=PACKAGE_DIR,
            capture_output=True,
            text=True,
            timeout=30,
        )
        stash_happened = "No local changes" not in (result.stdout or "")

        # Pull latest
        result = subprocess.run(
            ["git", "pull", "--ff-only", "origin", "main"],
            cwd=PACKAGE_DIR,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            # Restore stash if pull failed
            if stash_happened:
                subprocess.run(
                    ["git", "stash", "pop"],
                    cwd=PACKAGE_DIR,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
            console.print(f"  [{STYLE_ERR}]Update failed:[/] {result.stderr.strip() or result.stdout.strip()}")
            console.print(f"  [{STYLE_WARN}]Resolve git conflicts manually, then re-run:[/] [bold]mythos update[/bold]")
            return 1

        # Pop stash if we stashed
        if stash_happened:
            subprocess.run(
                ["git", "stash", "pop"],
                cwd=PACKAGE_DIR,
                capture_output=True,
                text=True,
                timeout=30,
            )

    except FileNotFoundError:
        console.print(f"  [{STYLE_ERR}]Error: git not found. Install git or update manually.[/{STYLE_ERR}]")
        return 1
    except subprocess.TimeoutExpired:
        console.print(f"  [{STYLE_ERR}]Error: git pull timed out. Check your network.[/{STYLE_ERR}]")
        return 1

    # ── 4. Read new version ─────────────────────────────────────────────
    # Reload __version__ from the updated __init__.py
    try:
        init_path = PACKAGE_ROOT / "mythos_cli" / "__init__.py"
        with open(init_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("__version__"):
                    new_version = line.split("=")[1].strip().strip('"').strip("'")
                    break
            else:
                new_version = old_version
    except Exception:
        new_version = old_version

    # ── 5. Restore user settings ────────────────────────────────────────
    home.mkdir(parents=True, exist_ok=True)

    restored = []
    for fname in user_files_to_backup:
        src = backup_dir / fname
        dst = home / fname
        if src.exists():
            shutil.copy2(src, dst)
            restored.append(fname)

    # Restore conversations
    if conv_backup.is_dir():
        shutil.copytree(conv_backup, conv_src, dirs_exist_ok=True)
        restored.append("conversations/")

    if restored:
        console.print(f"  [{STYLE_DIM}]Restored:[/] {', '.join(restored)}")

    # Clean up temp dir
    shutil.rmtree(backup_dir, ignore_errors=True)

    # ── 6. Re-run init (merges new defaults, preserves user values) ─────
    ensure_initialized()
    # Patch LLM config with user paths (models dir, HF cache, etc.)
    llm = llm_config_path()
    if llm.exists():
        _patch_llm_config_for_user(llm)

    # ── 7. Reinstall Python deps (pip skips already-satisfied) ──────────
    console.print(f"  [{STYLE_DIM}]Updating Python dependencies...[/{STYLE_DIM}]")
    venv_python = PACKAGE_ROOT / "venv" / "bin" / "python3"
    if venv_python.exists():
        try:
            result = subprocess.run(
                [str(venv_python), "-m", "pip", "install", "-e", ".[web]", "--quiet"],
                cwd=PACKAGE_DIR,
                capture_output=True,
                text=True,
                timeout=300,
            )
            if result.returncode == 0:
                console.print(f"  [{STYLE_DIM}]Dependencies up to date[/{STYLE_DIM}]")
            else:
                console.print(f"  [{STYLE_WARN}]Warning:[/] some deps may need manual install: {result.stderr.strip()}")
        except subprocess.TimeoutExpired:
            console.print(f"  [{STYLE_WARN}]Warning:[/] pip install timed out. Run: ./venv/bin/pip install -e .")
    else:
        console.print(f"  [{STYLE_WARN}]Warning: venv not found. Run setup.sh first.[/{STYLE_WARN}]")

    # ── 8. Done ─────────────────────────────────────────────────────────
    console.print()
    if new_version != old_version:
        console.print(Panel.fit(
            f"[{STYLE_OK}]Updated: [bold]{old_version}[/bold] → [bold]{new_version}[/bold][/{STYLE_OK}]",
            border_style="green",
        ))
    else:
        console.print(Panel.fit(
            f"[{STYLE_OK}]Already on version [bold]{new_version}[/bold] (no version change)[/{STYLE_OK}]",
            border_style="green",
        ))

    console.print(f"  [{STYLE_DIM}]Update complete. Your settings and models are preserved.[/{STYLE_DIM}]")

    from mythos_cli.suggest import after_update, show_suggestions
    show_suggestions(after_update(new_version != old_version))
    return 0


# ── argument parser ─────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mythos",
        description="Mythos — local AI chat + security scanner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Quick start:
  mythos                  Launch chat (like `claude`)
  mythos chat             Same as above
  mythos web              Web UI on http://localhost:7860

Security scanning:
 mythos init First-time setup
 mythos path add ~/src Register a codebase
 mythos scan Instant static analysis
 mythos scan --deep AI-powered audit (needs model)
 mythos fix --path . Auto-fix safe patterns (dry-run; use --apply)

Updates:
 mythos update Pull latest version (preserves settings & models)

Examples:
  mythos                  # start chatting from any directory
  mythos chat --config ~/myconfig.yaml
  mythos web --port 8080 --share
  mythos scan --deep --path ~/src/my-api
""",
    )
    parser.add_argument(
        "--version", action="version", version=f"mythos {__version__}"
    )

    sub = parser.add_subparsers(dest="command")

    # ── chat (default when no subcommand) ───────────────────────────────
    p_chat = sub.add_parser("chat", help="Launch terminal chat interface (default)")
    p_chat.add_argument("--config", default="config.yaml", help="Config file path")
    p_chat.add_argument("--verbose", action="store_true", help="Debug logging")
    p_chat.set_defaults(func=_cmd_chat)

    # ── web ─────────────────────────────────────────────────────────────
    p_web = sub.add_parser("web", help="Launch web UI (Gradio)")
    p_web.add_argument("--config", default="config.yaml", help="Config file path")
    p_web.add_argument("--port", type=int, default=7860, help="Port (default 7860)")
    p_web.add_argument("--share", action="store_true", help="Public Gradio link")
    p_web.set_defaults(func=_cmd_web)

    # ── init ────────────────────────────────────────────────────────────
    p_init = sub.add_parser("init", help="Create ~/.config/mythos and defaults")
    p_init.set_defaults(func=_cmd_init)

    # ── path ────────────────────────────────────────────────────────────
    p_add = sub.add_parser("path", help="Manage registered codebase folders")
    path_sub = p_add.add_subparsers(dest="path_cmd", required=True)

    pa = path_sub.add_parser("add", help="Register a folder to scan")
    pa.add_argument("directory", help="Path to source tree")
    pa.add_argument("--label", "-l", help="Friendly name")
    pa.set_defaults(func=_cmd_path_add)

    pl = path_sub.add_parser("list", aliases=["ls"], help="List registered folders")
    pl.set_defaults(func=_cmd_path_list)

    pr = path_sub.add_parser("remove", aliases=["rm"], help="Remove a registered folder")
    pr.add_argument("target", help="Path or id to remove")
    pr.set_defaults(func=_cmd_path_remove)

    # ── scan ────────────────────────────────────────────────────────────
    ps = sub.add_parser("scan", help="Run security scan on registered paths")
    ps.add_argument("--path", "-p", help="Scan one path (overrides registered list)")
    ps.add_argument(
        "--deep", action="store_true",
        help="AI-powered audit via local LLM (slower; needs model)",
    )
    ps.add_argument(
        "--severity",
        choices=["critical", "high", "medium", "low", "info"],
        default=None,
        help="Minimum severity to report",
    )
    ps.add_argument("--format", choices=["table", "json"], default="table")
    ps.add_argument("--verbose", "-v", action="store_true", help="Show snippets and fixes")
    ps.set_defaults(func=_cmd_scan)

    # ── fix ─────────────────────────────────────────────────────────────
    pf = sub.add_parser(
        "fix",
        help="Auto-fix safe static findings (yaml.safe_load, TLS verify, etc.)",
    )
    pf.add_argument("--path", "-p", help="Fix one path (file or directory)")
    pf.add_argument(
        "--apply",
        action="store_true",
        help="Write line-level fixes to disk (use git; no .bak files)",
    )
    pf.add_argument(
        "--severity",
        choices=["critical", "high", "medium", "low", "info"],
        default=None,
        help="Minimum severity to consider",
    )
    pf.set_defaults(func=_cmd_fix)

    # ── explore ─────────────────────────────────────────────────────────
    pe = sub.add_parser("explore", help="Preview indexable files under a path")
    pe.add_argument("path", help="Directory to inspect")
    pe.set_defaults(func=_cmd_explore)

    # ── model ───────────────────────────────────────────────────────────
    pm = sub.add_parser("model", help="Local LLM model management")
    model_sub = pm.add_subparsers(dest="model_cmd", required=True)
    md = model_sub.add_parser("download", help="Download default GGUF model")
    md.set_defaults(func=_cmd_model_download)

    # ── status ──────────────────────────────────────────────────────────
    st = sub.add_parser("status", help="Show configuration and model status")
    st.set_defaults(func=_cmd_status)

    # ── update ──────────────────────────────────────────────────────────
    up = sub.add_parser("update", help="Pull latest Mythos from GitHub (preserves settings)")
    up.set_defaults(func=_cmd_update)

    return parser


def cli_main() -> None:
    """Entry point registered in pyproject.toml."""
    sys.exit(main())


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()

    # If called with no arguments at all, default to chat
    # (like `claude` — just type the name and you're in)
    if argv is None and len(sys.argv) == 1:
        args = parser.parse_args(["chat"])
    else:
        args = parser.parse_args(argv)

    if not hasattr(args, "func"):
        # No subcommand matched — default to chat
        args = parser.parse_args(["chat"])

    try:
        return args.func(args)
    except KeyboardInterrupt:
        from mythos_cli.console import console
        console.print("\n[bold yellow]Interrupted.[/bold yellow]")
        return 0
    except Exception as e:
        from mythos_cli.console import console
        console.print(f"\n[bold red]Error:[/bold red] {e}")
        logging.getLogger().exception("fatal error")
        return 1


if __name__ == "__main__":
    sys.exit(main())
