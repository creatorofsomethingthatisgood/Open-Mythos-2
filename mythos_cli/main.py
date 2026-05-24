#!/usr/bin/env python3
"""
Mythos — your local AI assistant and security scanner.

    mythos              # launch chat (like `claude`)
    mythos chat         # same thing
    mythos web          # web UI
    mythos scan         # security scan
    mythos init         # first-time setup
    mythos path add .   # register a codebase for scanning
    mythos status       # show config / model status
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from mythos_cli import __version__
from mythos_cli.config_store import (
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
    init_config(quiet=False)
    return 0


def _cmd_path_add(args: argparse.Namespace) -> int:
    ensure_initialized()
    entry = add_scan_path(args.directory, label=args.label)
    print(f"✓ Added scan path: {entry['label']}")
    print(f"  {entry['path']}")
    print("\nRun: mythos scan")
    return 0


def _cmd_path_list(_args: argparse.Namespace) -> int:
    ensure_initialized()
    paths = list_scan_paths()
    if not paths:
        print("No paths configured. Add one:")
        print("  mythos path add /path/to/code")
        return 0
    print("Registered scan paths:\n")
    for i, entry in enumerate(paths, 1):
        print(f"  {i}. [{entry.get('id', '?')}] {entry.get('label', '')}")
        print(f"     {entry['path']}")
    return 0


def _cmd_path_remove(args: argparse.Namespace) -> int:
    ensure_initialized()
    if remove_scan_path(args.target):
        print(f"✓ Removed: {args.target}")
        return 0
    print(f"Not found: {args.target}", file=sys.stderr)
    return 1


def _cmd_scan(args: argparse.Namespace) -> int:
    ensure_initialized()
    if args.verbose:
        logging.getLogger().setLevel(logging.INFO)

    try:
        findings, roots, deep_report = run_scan(
            path_arg=args.path,
            deep=args.deep,
            min_severity=args.severity,
        )
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        if args.deep:
            print(
                f"Deep scan failed: {e}\n"
                "Ensure the model is installed: mythos model download",
                file=sys.stderr,
            )
        else:
            print(f"Scan failed: {e}", file=sys.stderr)
        return 1

    if args.format == "json":
        return print_json(findings, roots, deep_report)

    if args.verbose and findings:
        print_verbose_findings(findings)

    return print_summary(findings, roots, deep_report)


def _cmd_fix(args: argparse.Namespace) -> int:
    ensure_initialized()
    dry_run = not args.apply

    try:
        findings, roots, fixes = run_fix(
            path_arg=args.path,
            dry_run=dry_run,
            min_severity=args.severity,
        )
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Fix failed: {e}", file=sys.stderr)
        return 1

    print_fix_results(fixes, dry_run=dry_run)

    if findings:
        from mythos_cli.output import print_summary

        print("\n--- Remaining findings after fix ---")
        return print_summary(findings, roots, None)

    print("\nNo remaining static findings at configured severity.")
    return 0


def _cmd_explore(args: argparse.Namespace) -> int:
    ensure_initialized()
    from engine.rag import RAGPipeline

    config = llm_config_path()
    if not config.exists():
        print("Run `mythos init` first.", file=sys.stderr)
        return 1

    rag = RAGPipeline(str(config))
    summary = rag.explore_directory(args.path)
    print(f"\nDirectory: {summary['directory']}")
    if not summary.get("exists"):
        print("Directory does not exist.")
        return 1
    print(f"Indexable files: {summary['file_count']}")
    print(f"Total size: {summary['total_bytes']} bytes")
    if summary.get("sample_files"):
        print("\nSample files:")
        for rel in summary["sample_files"][:15]:
            print(f"  {rel}")
    return 0


def _cmd_model_download(_args: argparse.Namespace) -> int:
    ensure_initialized()
    from engine.model_manager import ModelManager

    config = llm_config_path()
    print("Downloading default security audit model (~4.5 GB)...")
    manager = ModelManager(str(config))
    path = manager.download_default()
    print(f"✓ Model ready: {path}")
    return 0


def _cmd_status(_args: argparse.Namespace) -> int:
    home = mythos_home()
    cfg = user_config_path()
    llm = llm_config_path()
    paths = list_scan_paths() if cfg.exists() else []

    print("Mythos status\n")
    print(f"  Version:      {__version__}")
    print(f"  Config home:  {home}")
    print(f"  User config:  {'yes' if cfg.exists() else 'no — run mythos init'}")
    print(f"  LLM config:   {'yes' if llm.exists() else 'no'}")
    print(f"  Scan paths:   {len(paths)}")
    for entry in paths:
        print(f"   - {entry.get('label')}: {entry['path']}")

    model_dir = models_hint_dir()
    gguf = list(model_dir.glob("*.gguf")) if model_dir.exists() else []
    print(f"  Models:       {len(gguf)} in {model_dir}")
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
  mythos init             First-time setup
  mythos path add ~/src   Register a codebase
  mythos scan             Instant static analysis
  mythos scan --deep      AI-powered audit (needs model)
  mythos fix --path .     Auto-fix safe patterns (dry-run; use --apply)

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
        print("\nInterrupted.")
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        logging.getLogger().exception("fatal error")
        return 1


if __name__ == "__main__":
    sys.exit(main())
