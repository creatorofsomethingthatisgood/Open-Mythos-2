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
    print(f"  Version: {__version__}")
    print(f"  Config home: {home}")
    print(f"  User config: {'yes' if cfg.exists() else 'no — run mythos init'}")
    print(f"  LLM config: {'yes' if llm.exists() else 'no'}")
    print(f"  Scan paths: {len(paths)}")
    for entry in paths:
        print(f"   - {entry.get('label')}: {entry['path']}")

    model_dir = models_hint_dir()
    gguf = list(model_dir.glob("*.gguf")) if model_dir.exists() else []
    print(f"  Models: {len(gguf)} in {model_dir}")
    return 0


def _cmd_update(_args: argparse.Namespace) -> int:
    """Pull latest Mythos from GitHub while preserving user settings and dependencies."""
    import json
    import subprocess
    import tempfile

    PACKAGE_DIR = str(PACKAGE_ROOT)

    # ── 1. Snapshot current version ──────────────────────────────────────
    old_version = __version__
    print(f"  Current version: {old_version}")

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
        print(f"  Backed up: {', '.join(backed_up)}")

    # ── 3. Git pull ─────────────────────────────────────────────────────
    print("  Fetching latest version from GitHub...")

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
            print(f"  Update failed: {result.stderr.strip() or result.stdout.strip()}", file=sys.stderr)
            print("  Resolve git conflicts manually, then re-run: mythos update", file=sys.stderr)
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
        print("  Error: git not found. Install git or update manually.", file=sys.stderr)
        return 1
    except subprocess.TimeoutExpired:
        print("  Error: git pull timed out. Check your network.", file=sys.stderr)
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
        print(f"  Restored: {', '.join(restored)}")

    # Clean up temp dir
    shutil.rmtree(backup_dir, ignore_errors=True)

    # ── 6. Re-run init (merges new defaults, preserves user values) ─────
    ensure_initialized()
    # Patch LLM config with user paths (models dir, HF cache, etc.)
    llm = llm_config_path()
    if llm.exists():
        _patch_llm_config_for_user(llm)

    # ── 7. Reinstall Python deps (pip skips already-satisfied) ──────────
    print("  Updating Python dependencies (skips already installed)...")
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
                print("  Dependencies up to date")
            else:
                print(f"  Warning: some deps may need manual install: {result.stderr.strip()}", file=sys.stderr)
        except subprocess.TimeoutExpired:
            print("  Warning: pip install timed out. Run manually: ./venv/bin/pip install -e .", file=sys.stderr)
    else:
        print("  Warning: venv not found. Run setup.sh first.", file=sys.stderr)

    # ── 8. Done ─────────────────────────────────────────────────────────
    if new_version != old_version:
        print(f"\n  Updated: {old_version} -> {new_version}")
    else:
        print(f"\n  Already on version {new_version} (no version change)")

    print("  Update complete. Your settings and models are preserved.")
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
        print("\nInterrupted.")
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        logging.getLogger().exception("fatal error")
        return 1


if __name__ == "__main__":
    sys.exit(main())
