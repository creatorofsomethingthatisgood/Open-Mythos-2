"""Print fix results for CLI and chat."""

from __future__ import annotations

from typing import List

from mythos_cli.auto_fix import FixResult


def print_fix_results(fixes: List[FixResult], *, dry_run: bool) -> int:
    applied = [f for f in fixes if f.status in ("applied", "pending")]
    skipped = [f for f in fixes if f.status == "skipped"]

    if not fixes:
        print("No fixable findings (secrets and logic issues need manual review).")
        return 0

    mode = "Would apply" if dry_run else "Applied"
    print(f"\n=== Auto-fix ({mode}) ===\n")
    for f in applied:
        if f.status != "applied" and f.status != "pending":
            continue
        label = "pending" if dry_run else "applied"
        print(f"  [{label}] {f.path}:{f.line} ({f.rule_id}) — {f.detail}")
        if f.before and f.after:
            print(f"    - {f.before}")
            print(f"    + {f.after}")

    if skipped:
        print(f"\n  Skipped {len(skipped)} finding(s) (no safe auto-fix).")
        for f in skipped[:10]:
            print(f"    {f.path}:{f.line} ({f.rule_id}) — {f.detail}")
        if len(skipped) > 10:
            print(f"    ... and {len(skipped) - 10} more")

    if dry_run and applied:
        print("\nRe-run with --apply to write line-level fixes (use git; no .bak files).")
    elif not dry_run and applied:
        print("\nChanges written — review with git diff.")

    return len(applied)
