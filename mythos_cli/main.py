#!/usr/bin/env python3
"""
Mythos Sentinel — installable security scanner CLI.

  pip install -e .
  mythos init
  mythos path add ~/projects/api
  mythos scan
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

logging.basicConfig(
    level=logging.WARNING,
    format="%(levelname)s: %(message)s",
)


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
    print(f"Total size:      {summary['total_bytes']} bytes")
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

    print("Mythos Sentinel status\n")
    print(f"  Version:     {__version__}")
    print(f"  Config home: {home}")
    print(f"  User config: {'yes' if cfg.exists() else 'no — run mythos init'}")
    print(f"  LLM config:  {'yes' if llm.exists() else 'no'}")
    print(f"  Scan paths:  {len(paths)}")
    for entry in paths:
        print(f"    - {entry.get('label')}: {entry['path']}")

    model_dir = models_hint_dir()
    gguf = list(model_dir.glob("*.gguf")) if model_dir.exists() else []
    print(f"  Models:      {len(gguf)} in {model_dir}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mythos",
        description="Mythos Sentinel — local security scanner for your codebases",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Quick start:
  mythos init
  mythos path add ~/src/my-api
  mythos scan                 # instant static analysis
  mythos scan --deep --path ~/src/my-api   # AI audit (requires model)

Sell / ship workflow: customers install once, register folders, run `mythos scan` in CI.
        """,
    )
    parser.add_argument("--version", action="version", version=f"mythos {__version__}")

    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="Create ~/.config/mythos and default settings")
    p_init.set_defaults(func=_cmd_init)

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

    ps = sub.add_parser("scan", help="Run security scan on registered paths")
    ps.add_argument("--path", "-p", help="Scan one path (overrides registered list)")
    ps.add_argument(
        "--deep",
        action="store_true",
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

    pe = sub.add_parser("explore", help="Preview indexable files under a path")
    pe.add_argument("path", help="Directory to inspect")
    pe.set_defaults(func=_cmd_explore)

    pm = sub.add_parser("model", help="Local LLM model management")
    model_sub = pm.add_subparsers(dest="model_cmd", required=True)
    md = model_sub.add_parser("download", help="Download default GGUF model")
    md.set_defaults(func=_cmd_model_download)

    st = sub.add_parser("status", help="Show configuration and model status")
    st.set_defaults(func=_cmd_status)

    return parser


def cli_main() -> None:
    sys.exit(main())


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
