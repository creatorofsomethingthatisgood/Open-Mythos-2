"""
Agent Mode - Autonomous tool-using loop for Mythos.

Parses tool-call markup from model responses, executes them with
safety guards, and feeds results back into the conversation until
the model signals DONE or max iterations are reached.

Safety:
  - Path traversal guard: all file ops must stay within sandbox_dir
  - Command allowlist + blocklist
  - Confirmation prompts for writes and non-read-only commands
  - Max iterations cap to prevent runaway loops
"""

import logging
import os
import re
import shlex
import subprocess
import difflib
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# -- Markup parsing -----------------------------------------------------------

TOOL_BLOCK_RE = re.compile(
    r"<<<TOOL:(\w+)(?:\s+([^>]*))?>>>\n(.*?)<<<END_TOOL>>>",
    re.DOTALL,
)
TOOL_DONE_RE = re.compile(r"<<<TOOL:DONE>>>(.*?)<<<END_TOOL>>>", re.DOTALL)
TOOL_INLINE_RE = re.compile(
    r"<<<TOOL:(\w+)(?:\s+([^>]*))?>>>", re.DOTALL
)

# -- Safety -------------------------------------------------------------------

BLOCKED_COMMANDS = {
    "rm", "rmdir", "del", "format", "mkfs", "dd", "shred",
    "mv", "chmod", "chown", "chgrp",
    "git push", "git push --force", "git reset --hard",
    "git checkout -- .", "git clean",
    "drop", "truncate", "delete",
    "shutdown", "reboot", "poweroff",
    "kill", "killall", "pkill",
    "pip uninstall", "apt remove", "dnf remove",
    "npm uninstall", "cargo uninstall",
}

ALLOWED_READ_COMMANDS = {
    "ls", "cat", "head", "tail", "wc", "find", "grep", "rg",
    "git status", "git log", "git diff", "git show", "git branch",
    "git remote", "git stash list",
    "python -c", "python3 -c",
    "pytest", "node", "npm test", "npm run", "bun test", "bun run",
    "echo", "pwd", "which", "whoami", "uname", "date",
    "curl", "wget",
    "pip list", "pip show", "pip check",
    "npm list", "cargo check", "cargo test", "cargo build",
    "ast", "mypy", "pylint", "flake8", "ruff",
}

MAX_ITERATIONS = 50


class SafetyTier(Enum):
    """Controls tool access levels for the agent."""
    SAFE = "safe"          # sandbox confined, read + scan only
    ELEVATED = "elevated"  # CWD tree access, write/fix with confirm, port scan ok
    UNLEASHED = "unleashed"  # full filesystem, all tools, confirm destructive only


def _is_path_safe(path: Path, sandbox_dir: Path) -> bool:
    """Return True if resolved path is within sandbox_dir."""
    try:
        resolved = path.resolve()
        sandbox = sandbox_dir.resolve()
        return resolved.is_relative_to(sandbox)
    except Exception:
        return False


def _parse_tool_attrs(attr_str: str) -> Dict[str, str]:
    """Parse key="value" attributes from the tool tag."""
    attrs: Dict[str, str] = {}
    if not attr_str:
        return attrs
    for m in re.finditer(r'(\w+)="([^"]*)"', attr_str):
        attrs[m.group(1)] = m.group(2)
    return attrs


def _is_command_dangerous(cmd: str) -> bool:
    """Check if a command matches the blocklist."""
    stripped = cmd.strip().lower()
    # Extract the base command (first token or basename after /)
    base = stripped.split()[0] if stripped.split() else ""
    base = base.rsplit("/", maxsplit=1)[-1] if "/" in base else base
    for blocked in BLOCKED_COMMANDS:
        if base == blocked or base.startswith(blocked + "-"):
            return True
    return False


def _is_command_readonly(cmd: str) -> bool:
    """Check if a command is in the read-only allowlist."""
    stripped = cmd.strip().lower()
    base = stripped.split()[0] if stripped.split() else ""
    base = base.rsplit("/", maxsplit=1)[-1] if "/" in base else base
    for allowed in ALLOWED_READ_COMMANDS:
        if base == allowed or base.startswith(allowed + "-"):
            return True
    return False


# -- Tool executor ------------------------------------------------------------

class ToolResult:
    """Result from a single tool execution."""

    def __init__(self, tool: str, success: bool, output: str):
        self.tool = tool
        self.success = success
        self.output = output

    def to_message(self) -> str:
        status = "OK" if self.success else "ERROR"
        return f"[{self.tool} {status}]\n{self.output}"


class AgentToolExecutor:
    """Executes parsed tool calls with safety checks."""

    def __init__(
        self,
        sandbox_dir: Path,
        confirm_fn: Optional[Callable[[str], bool]] = None,
        dry_run: bool = False,
        safety_tier: "SafetyTier" = SafetyTier.ELEVATED,
    ):
        self.sandbox_dir = sandbox_dir
        self.confirm_fn = confirm_fn or (lambda _: False)
        self.dry_run = dry_run
        self.safety_tier = safety_tier

    def _resolve(self, raw_path: str) -> Path:
        p = Path(raw_path).expanduser()
        if not p.is_absolute():
            p = self.sandbox_dir / p
        return p

    def execute(self, tool: str, attrs: Dict[str, str], body: str) -> ToolResult:
        dispatch = {
            "READ_FILE": self._read_file,
            "LIST_DIR": self._list_dir,
            "WRITE_FILE": self._write_file,
            "PATCH_FILE": self._patch_file,
            "RUN_COMMAND": self._run_command,
            "SCAN": self._scan,
            "DEEP_SCAN": self._deep_scan,
            "FIX": self._fix,
            "GREP": self._grep,
            "CONTAINER_DETECT": self._container_detect,
            "NETWORK_SCAN": self._network_scan,
            "DONE": lambda a, b: ToolResult("DONE", True, ""),
        }
        handler = dispatch.get(tool)
        if handler is None:
            return ToolResult(tool, False, f"Unknown tool: {tool}")
        return handler(attrs, body)

    # -- individual tools -----------------------------------------------------

    def _read_file(self, attrs: Dict[str, str], _body: str) -> ToolResult:
        raw = attrs.get("path", "")
        if not raw:
            return ToolResult("READ_FILE", False, "Missing path attribute")
        path = self._resolve(raw)
        if self.safety_tier != SafetyTier.UNLEASHED and not _is_path_safe(path, self.sandbox_dir):
            return ToolResult("READ_FILE", False, f"Path outside sandbox: {path}")
        if not path.exists():
            return ToolResult("READ_FILE", False, f"File not found: {path}")
        if path.is_dir():
            return ToolResult("READ_FILE", False, f"Path is a directory: {path}")
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
            lines = content.splitlines()
            if len(lines) > 500:
                truncated = "\n".join(lines[:500])
                truncated += f"\n... ({len(lines) - 500} more lines)"
                return ToolResult("READ_FILE", True, truncated)
            return ToolResult("READ_FILE", True, content)
        except Exception as exc:
            return ToolResult("READ_FILE", False, str(exc))

    def _list_dir(self, attrs: Dict[str, str], _body: str) -> ToolResult:
        raw = attrs.get("path", ".")
        path = self._resolve(raw)
        if self.safety_tier != SafetyTier.UNLEASHED and not _is_path_safe(path, self.sandbox_dir):
            return ToolResult("LIST_DIR", False, f"Path outside sandbox: {path}")
        if not path.exists():
            return ToolResult("LIST_DIR", False, f"Directory not found: {path}")
        if not path.is_dir():
            return ToolResult("LIST_DIR", False, f"Path is not a directory: {path}")
        try:
            entries = sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name))
            lines = []
            for entry in entries:
                prefix = "D " if entry.is_dir() else "F "
                size = ""
                if entry.is_file():
                    try:
                        size = f" ({entry.stat().st_size} bytes)"
                    except OSError:
                        pass
                lines.append(f"{prefix}{entry.name}{size}")
            return ToolResult("LIST_DIR", True, "\n".join(lines) or "(empty)")
        except Exception as exc:
            return ToolResult("LIST_DIR", False, str(exc))

    def _write_file(self, attrs: Dict[str, str], body: str) -> ToolResult:
        raw = attrs.get("path", "")
        if not raw:
            return ToolResult("WRITE_FILE", False, "Missing path attribute")
        path = self._resolve(raw)
        if self.safety_tier != SafetyTier.UNLEASHED and not _is_path_safe(path, self.sandbox_dir):
            return ToolResult("WRITE_FILE", False, f"Path outside sandbox: {path}")
        if self.safety_tier == SafetyTier.SAFE:
            return ToolResult("WRITE_FILE", False, "Write operations not allowed in safe tier")

        desc = f"Write {len(body.splitlines())} lines to {path}"
        if self.dry_run:
            return ToolResult("WRITE_FILE", True, f"[DRY RUN] {desc}")
        if not self.confirm_fn(desc):
            return ToolResult("WRITE_FILE", False, "User declined write")

        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(body, encoding="utf-8")
            return ToolResult("WRITE_FILE", True, f"Wrote {path} ({len(body)} chars)")
        except Exception as exc:
            return ToolResult("WRITE_FILE", False, str(exc))

    def _patch_file(self, attrs: Dict[str, str], body: str) -> ToolResult:
        raw = attrs.get("path", "")
        if not raw:
            return ToolResult("PATCH_FILE", False, "Missing path attribute")
        path = self._resolve(raw)
        if self.safety_tier != SafetyTier.UNLEASHED and not _is_path_safe(path, self.sandbox_dir):
            return ToolResult("PATCH_FILE", False, f"Path outside sandbox: {path}")
        if self.safety_tier == SafetyTier.SAFE:
            return ToolResult("PATCH_FILE", False, "Patch operations not allowed in safe tier")
        if not path.exists():
            return ToolResult(
                "PATCH_FILE", False,
                f"File not found: {path}. Use WRITE_FILE for new files.",
            )

        desc = f"Patch {path}"
        if self.dry_run:
            return ToolResult("PATCH_FILE", True, f"[DRY RUN] {desc}\n{body}")
        if not self.confirm_fn(desc):
            return ToolResult("PATCH_FILE", False, "User declined patch")

        try:
            original = path.read_text(encoding="utf-8")
            patched = _apply_unified_patch(original, body, str(path))
            if patched is None:
                return ToolResult("PATCH_FILE", False, "Patch did not apply cleanly")
            path.write_text(patched, encoding="utf-8")
            diff_lines = len(body.strip().splitlines())
            return ToolResult(
                "PATCH_FILE", True,
                f"Patched {path} ({diff_lines} diff lines applied)",
            )
        except Exception as exc:
            return ToolResult("PATCH_FILE", False, str(exc))

    def _run_command(self, _attrs: Dict[str, str], body: str) -> ToolResult:
        cmd = body.strip()
        if not cmd:
            return ToolResult("RUN_COMMAND", False, "Empty command")

        if _is_command_dangerous(cmd):
            if self.safety_tier != SafetyTier.UNLEASHED:
                return ToolResult("RUN_COMMAND", False, f"Blocked command: {cmd}")

        if self.safety_tier == SafetyTier.SAFE and not _is_command_readonly(cmd):
            return ToolResult("RUN_COMMAND", False, f"Non-read-only command blocked in safe tier: {cmd}")

        if not _is_command_readonly(cmd):
            desc = f"Run command: {cmd}"
            if self.dry_run:
                return ToolResult("RUN_COMMAND", True, f"[DRY RUN] {desc}")
            if not self.confirm_fn(desc):
                return ToolResult("RUN_COMMAND", False, "User declined command")

        if self.dry_run and not _is_command_readonly(cmd):
            return ToolResult("RUN_COMMAND", True, f"[DRY RUN] {cmd}")

        try:
            cmd_parts = shlex.split(cmd)
            result = subprocess.run(
                cmd_parts,
                shell=False,
                capture_output=True,
                text=True,
                timeout=60,
                cwd=str(self.sandbox_dir),
            )
            output = result.stdout
            if result.stderr:
                output += f"\nSTDERR:\n{result.stderr}"
            if result.returncode != 0:
                output += f"\nExit code: {result.returncode}"
            # Truncate very long output
            if len(output) > 8000:
                output = output[:8000] + f"\n... truncated ({len(output) - 8000} more chars)"
            success = result.returncode == 0
            return ToolResult("RUN_COMMAND", success, output)
        except subprocess.TimeoutExpired:
            return ToolResult("RUN_COMMAND", False, "Command timed out (60s)")
        except Exception as exc:
            return ToolResult("RUN_COMMAND", False, str(exc))

    def _scan(self, attrs: Dict[str, str], _body: str) -> ToolResult:
        """Run static security scanner on a path."""
        if self.safety_tier == SafetyTier.SAFE:
            raw = attrs.get("path", ".")
            path = self._resolve(raw)
            if not _is_path_safe(path, self.sandbox_dir):
                return ToolResult("SCAN", False, f"Path outside sandbox: {path}")
        raw = attrs.get("path", ".")
        path = self._resolve(raw)
        if not path.exists():
            return ToolResult("SCAN", False, f"Path not found: {path}")
        try:
            from mythos_cli.static_scanner import scan_directory
            findings = scan_directory(str(path))
            if not findings:
                return ToolResult("SCAN", True, "No vulnerabilities found")
            lines = []
            for f in findings:
                lines.append(f"[{f.severity}] {f.rule_id}: {f.title}")
                lines.append(f"  Location: {f.path}:{f.line}")
                if f.snippet:
                    snippet = f.snippet.strip()[:120]
                    lines.append(f"  Code: {snippet}")
                if f.recommendation:
                    lines.append(f"  Fix: {f.recommendation}")
            output = "\n".join(lines)
            if len(output) > 12000:
                output = output[:12000] + f"\n... truncated ({len(findings)} total findings)"
            return ToolResult("SCAN", True, output)
        except ImportError:
            return ToolResult("SCAN", False, "Static scanner not available (mythos_cli.static_scanner)")
        except Exception as exc:
            return ToolResult("SCAN", False, f"Scan error: {exc}")

    def _deep_scan(self, attrs: Dict[str, str], _body: str) -> ToolResult:
        """Run AI-powered deep security audit."""
        if self.safety_tier == SafetyTier.SAFE:
            raw = attrs.get("path", ".")
            path = self._resolve(raw)
            if not _is_path_safe(path, self.sandbox_dir):
                return ToolResult("DEEP_SCAN", False, f"Path outside sandbox: {path}")
        raw = attrs.get("path", ".")
        path = self._resolve(raw)
        if not path.exists():
            return ToolResult("DEEP_SCAN", False, f"Path not found: {path}")
        try:
            from mythos_cli.deep_scanner import run_deep_audit
            findings = run_deep_audit(str(path), self.engine)
            if not findings:
                return ToolResult("DEEP_SCAN", True, "No deep vulnerabilities found")
            lines = []
            for f in findings:
                sev = getattr(f, "severity", "unknown")
                title = getattr(f, "title", "finding")
                desc = getattr(f, "description", "")
                lines.append(f"[{sev}] {title}")
                if desc:
                    lines.append(f"  {desc[:200]}")
            output = "\n".join(lines)
            if len(output) > 12000:
                output = output[:12000] + "\n... truncated"
            return ToolResult("DEEP_SCAN", True, output)
        except ImportError:
            return ToolResult("DEEP_SCAN", False, "Deep scanner not available (mythos_cli.deep_scanner)")
        except Exception as exc:
            return ToolResult("DEEP_SCAN", False, f"Deep scan error: {exc}")

    def _fix(self, attrs: Dict[str, str], _body: str) -> ToolResult:
        """Auto-fix security findings in a directory."""
        if self.safety_tier == SafetyTier.SAFE:
            return ToolResult("FIX", False, "Fix operations not allowed in safe tier")
        raw = attrs.get("path", ".")
        path = self._resolve(raw)
        if self.safety_tier != SafetyTier.UNLEASHED and not _is_path_safe(path, self.sandbox_dir):
            return ToolResult("FIX", False, f"Path outside sandbox: {path}")
        if not path.exists():
            return ToolResult("FIX", False, f"Path not found: {path}")
        desc = f"Auto-fix security issues in {path}"
        if self.dry_run:
            return ToolResult("FIX", True, f"[DRY RUN] {desc}")
        if not self.confirm_fn(desc):
            return ToolResult("FIX", False, "User declined fix")
        try:
            from mythos_cli.auto_fix import apply_fixes_to_tree
            fixes = apply_fixes_to_tree(str(path))
            if not fixes:
                return ToolResult("FIX", True, "No auto-fixable issues found")
            lines = []
            for fix in fixes:
                lines.append(f"Fixed: {fix}")
            output = "\n".join(lines)
            return ToolResult("FIX", True, output)
        except ImportError:
            return ToolResult("FIX", False, "Auto-fix not available (mythos_cli.auto_fix)")
        except Exception as exc:
            return ToolResult("FIX", False, f"Fix error: {exc}")

    def _grep(self, attrs: Dict[str, str], _body: str) -> ToolResult:
        """Search for pattern in files."""
        pattern = attrs.get("pattern", "")
        raw_path = attrs.get("path", ".")
        if not pattern:
            return ToolResult("GREP", False, "Missing pattern attribute")
        path = self._resolve(raw_path)
        if self.safety_tier != SafetyTier.UNLEASHED and not _is_path_safe(path, self.sandbox_dir):
            return ToolResult("GREP", False, f"Path outside sandbox: {path}")
        if not path.exists():
            return ToolResult("GREP", False, f"Path not found: {path}")
        try:
            cmd_parts = ["grep", "-rn", "--", pattern, str(path)]
            result = subprocess.run(
                cmd_parts,
                shell=False,
                capture_output=True,
                text=True,
                timeout=30,
                cwd=str(self.sandbox_dir),
            )
            output = result.stdout
            if result.stderr and "Permission denied" not in result.stderr:
                output += f"\nSTDERR:\n{result.stderr}"
            if len(output) > 12000:
                output = output[:12000] + "\n... truncated"
            if not output.strip():
                return ToolResult("GREP", True, "No matches found")
            return ToolResult("GREP", True, output)
        except subprocess.TimeoutExpired:
            return ToolResult("GREP", False, "Grep timed out (30s)")
        except Exception as exc:
            return ToolResult("GREP", False, str(exc))

    def _container_detect(self, _attrs: Dict[str, str], _body: str) -> ToolResult:
        """Detect container environment and escape vectors."""
        try:
            from engine.container_detect import detect_container, check_escape_vectors
            info = detect_container()
            findings = check_escape_vectors()
            lines = []
            lines.append(f"Container: {'Yes' if info.is_container else 'No'}")
            if info.is_container:
                lines.append(f"Type: {info.container_type}")
                if info.container_id:
                    lines.append(f"ID: {info.container_id[:12]}")
                lines.append(f"Hostname: {info.hostname}")
            if findings:
                lines.append(f"\nEscape Vectors ({len(findings)} found):")
                for f in findings:
                    lines.append(f"  [{f.severity}] {f.vector}: {f.description}")
                    if f.detail:
                        lines.append(f"    {f.detail}")
            else:
                lines.append("\nNo escape vectors detected")
            output = "\n".join(lines)
            return ToolResult("CONTAINER_DETECT", True, output)
        except ImportError:
            return ToolResult("CONTAINER_DETECT", False, "Container detection not available (engine.container_detect)")
        except Exception as exc:
            return ToolResult("CONTAINER_DETECT", False, f"Container detect error: {exc}")

    def _network_scan(self, attrs: Dict[str, str], _body: str) -> ToolResult:
        """Network scanning: LAN discovery, port scan, or DNS lookup."""
        scan_type = attrs.get("type", "lan")
        host = attrs.get("host", "")
        ports_str = attrs.get("ports", "")
        if self.safety_tier == SafetyTier.SAFE and scan_type != "lan":
            return ToolResult("NETWORK_SCAN", False, f"Network scan type '{scan_type}' not allowed in safe tier")
        try:
            from engine.network_tools import port_scan, lan_discover, dns_lookup
            if scan_type == "lan":
                result = lan_discover()
                interfaces = result.get("interfaces", [])
                hosts = result.get("hosts", [])
                lines = []
                lines.append(f"Interfaces: {len(interfaces)}")
                for iface in interfaces:
                    lines.append(f"  {iface}")
                lines.append(f"Hosts: {len(hosts)}")
                for h in hosts:
                    lines.append(f"  {h}")
                output = "\n".join(lines)
                if len(output) > 12000:
                    output = output[:12000] + "\n... truncated"
                return ToolResult("NETWORK_SCAN", True, output)
            elif scan_type == "port":
                if not host:
                    return ToolResult("NETWORK_SCAN", False, "Missing host attribute for port scan")
                if not ports_str:
                    return ToolResult("NETWORK_SCAN", False, "Missing ports attribute for port scan")
                try:
                    ports = [int(p.strip()) for p in ports_str.split(",")]
                except ValueError:
                    return ToolResult("NETWORK_SCAN", False, "Invalid ports format (use comma-separated integers)")
                results = port_scan(host, ports)
                lines = []
                for pr in results:
                    lines.append(f"  Port {pr.port}: {pr.state} ({pr.service})")
                    if pr.banner:
                        lines.append(f"    Banner: {pr.banner[:100]}")
                output = "\n".join(lines) or "No open ports found"
                return ToolResult("NETWORK_SCAN", True, output)
            elif scan_type == "dns":
                if not host:
                    return ToolResult("NETWORK_SCAN", False, "Missing host attribute for DNS lookup")
                result = dns_lookup(host)
                lines = [f"Hostname: {result.hostname}"]
                if result.addresses:
                    lines.append(f"Addresses: {', '.join(result.addresses)}")
                if result.cname:
                    lines.append(f"CNAME: {result.cname}")
                if result.mx_records:
                    lines.append(f"MX: {', '.join(result.mx_records)}")
                output = "\n".join(lines)
                return ToolResult("NETWORK_SCAN", True, output)
            else:
                return ToolResult("NETWORK_SCAN", False, f"Unknown scan type: {scan_type}. Use lan, port, or dns.")
        except ImportError:
            return ToolResult("NETWORK_SCAN", False, "Network tools not available (engine.network_tools)")
        except Exception as exc:
            return ToolResult("NETWORK_SCAN", False, f"Network scan error: {exc}")


# -- Patch application --------------------------------------------------------

def _apply_unified_patch(
    original: str, patch_text: str, label: str = "file"
) -> Optional[str]:
    """Apply a simple unified diff patch. Returns None on failure."""
    lines = original.splitlines(keepends=True)
    patch_lines = patch_text.splitlines()

    # Parse hunks from the patch
    hunks: List[Tuple[int, List[str]]] = []
    i = 0
    while i < len(patch_lines):
        line = patch_lines[i]
        hunk_match = re.match(
            r"^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@", line
        )
        if hunk_match:
            target_line = int(hunk_match.group(2))
            hunk_body: List[str] = []
            i += 1
            while i < len(patch_lines) and not patch_lines[i].startswith("@@"):
                if not patch_lines[i].startswith("---") and not patch_lines[i].startswith("+++"):
                    hunk_body.append(patch_lines[i])
                i += 1
            hunks.append((target_line, hunk_body))
        else:
            i += 1

    if not hunks:
        # Fallback: try a simple search-and-replace approach
        return _apply_simple_patch(original, patch_text)

    # Apply hunks in reverse order so line numbers stay valid
    result = list(lines)
    for target_line, hunk_body in reversed(hunks):
        new_lines: List[str] = []
        for hline in hunk_body:
            if hline.startswith("+"):
                new_lines.append(hline[1:] + "\n")
            elif hline.startswith("-"):
                # Remove the corresponding line
                continue
            elif hline.startswith(" "):
                new_lines.append(hline[1:] + "\n")
            else:
                new_lines.append(hline + "\n")

        # Replace lines at target_line-1 (1-indexed to 0-indexed)
        idx = target_line - 1
        if idx < 0 or idx > len(result):
            logger.warning(f"Patch hunk at line {target_line} out of range for {label}")
            continue

        # Find how many original lines this hunk consumed
        old_count = sum(1 for h in hunk_body if h.startswith("-") or h.startswith(" "))
        result[idx:idx + old_count] = new_lines

    return "".join(result)


def _apply_simple_patch(original: str, patch_text: str) -> Optional[str]:
    """Fallback: apply patch by searching for - lines and replacing with + lines."""
    patch_lines = patch_text.strip().splitlines()
    removals: List[str] = []
    additions: List[str] = []

    for line in patch_lines:
        if line.startswith("-") and not line.startswith("---"):
            removals.append(line[1:])
        elif line.startswith("+") and not line.startswith("+++"):
            additions.append(line[1:])

    if not removals:
        return None

    original_lines = original.splitlines()
    old_text = "\n".join(removals)
    new_text = "\n".join(additions)

    result = original.replace(old_text, new_text, 1)
    if result == original and old_text not in original:
        return None

    return result


# -- Agent loop ---------------------------------------------------------------

def parse_tool_calls(text: str) -> List[Tuple[str, Dict[str, str], str]]:
    """Parse all tool-call blocks from model response text.

    Returns list of (tool_name, attrs, body) tuples.
    """
    calls: List[Tuple[str, Dict[str, str], str]] = []

    # Full blocks with <<<END_TOOL>>>
    for m in TOOL_BLOCK_RE.finditer(text):
        tool = m.group(1)
        attrs = _parse_tool_attrs(m.group(2) or "")
        body = m.group(3).strip()
        calls.append((tool, attrs, body))

    # DONE blocks
    for m in TOOL_DONE_RE.finditer(text):
        calls.append(("DONE", {}, m.group(1).strip()))

    # Inline tags (READ_FILE, LIST_DIR with no body)
    for m in TOOL_INLINE_RE.finditer(text):
        tool = m.group(1)
        if tool in ("READ_FILE", "LIST_DIR", "SCAN", "DEEP_SCAN", "GREP", "CONTAINER_DETECT", "NETWORK_SCAN"):
            attrs = _parse_tool_attrs(m.group(2) or "")
            # Skip if already captured as a full block
            already = any(c[0] == tool and c[1].get("path") == attrs.get("path") for c in calls)
            if not already:
                calls.append((tool, attrs, ""))

    return calls


def extract_text_outside_tools(text: str) -> str:
    """Get the prose parts of the response (outside tool blocks)."""
    result = text
    # Remove full tool blocks
    result = TOOL_BLOCK_RE.sub("", result)
    result = TOOL_DONE_RE.sub("", result)
    # Remove inline tool tags
    result = TOOL_INLINE_RE.sub("", result)
    return result.strip()


class AgentLoop:
    """Orchestrates the autonomous agent loop.

    Flow:
      1. Send user task + system prompt to model
      2. Parse tool calls from response
      3. Execute each tool call via AgentToolExecutor
      4. Feed tool results back as assistant/user messages
      5. Repeat until DONE or max iterations
    """

    def __init__(
        self,
        engine: Any,
        prompt_manager: Any,
        config: Dict[str, Any],
        sandbox_dir: Path,
        confirm_fn: Optional[Callable[[str], bool]] = None,
        dry_run: bool = False,
        on_thinking: Optional[Callable[[str], None]] = None,
        on_response: Optional[Callable[[str], None]] = None,
        on_tool_result: Optional[Callable[[ToolResult], None]] = None,
    ):
        self.engine = engine
        self.prompt_manager = prompt_manager
        self.config = config
        self.sandbox_dir = sandbox_dir
        self.dry_run = dry_run
        self.on_thinking = on_thinking
        self.on_response = on_response
        self.on_tool_result = on_tool_result

        self.safety_tier = config.get("operative", {}).get("safety_tier", "elevated")
        if isinstance(self.safety_tier, str):
            self.safety_tier = SafetyTier(self.safety_tier)
        self.executor = AgentToolExecutor(
            sandbox_dir=sandbox_dir,
            confirm_fn=confirm_fn or self._default_confirm,
            dry_run=dry_run,
            safety_tier=self.safety_tier,
        )
        self.max_iterations = config.get("agent", {}).get("max_iterations", MAX_ITERATIONS)

    @staticmethod
    def _default_confirm(desc: str) -> bool:
        """Default confirmation: require explicit approval for all operations."""
        return False

    def run(
        self,
        task: str,
        history: Optional[List[Dict[str, str]]] = None,
    ) -> str:
        """Run the agent loop on a task.

        Args:
            task: The user's task description.
            history: Optional prior conversation messages.

        Returns:
            Summary of what was accomplished.
        """
        from engine.context_budget import fit_chat_context

        # Build system prompt
        prompt_name = "operative" if self.safety_tier != SafetyTier.SAFE else "agent"
        try:
            system_prompt = self.prompt_manager.load_prompt(prompt_name)
        except Exception:
            try:
                system_prompt = Path(f"prompts/{prompt_name}.txt").read_text(encoding="utf-8")
            except FileNotFoundError:
                system_prompt = Path("prompts/agent.txt").read_text(encoding="utf-8")

        system_prompt += f"\n\nWorking directory: {self.sandbox_dir}"

        # Build initial messages
        messages: List[Dict[str, str]] = list(history) if history else []
        messages.append({"role": "user", "content": task})

        gen_cfg = self.config.get("generation", {})
        max_tokens = int(gen_cfg.get("max_tokens", 4096))
        temperature = float(gen_cfg.get("temperature", 0.3))
        reserve = self.config.get("context", {}).get("reserve_tokens", 2048)

        summary_parts: List[str] = []

        for iteration in range(self.max_iterations):
            # Trim context to fit
            messages = fit_chat_context(
                messages,
                max_context=self.engine.context_length if hasattr(self.engine, "context_length") else 8192,
                reserve_tokens=reserve,
            )

            # Generate response
            if self.on_thinking:
                self.on_thinking(f"Agent iteration {iteration + 1}/{self.max_iterations}")

            try:
                if hasattr(self.engine, "stream_chat"):
                    # Cloud engine with streaming
                    response_text = ""
                    for token in self.engine.stream_chat(messages, system_prompt=system_prompt):
                        response_text += token
                        if self.on_response:
                            self.on_response(token)
                elif hasattr(self.engine, "chat"):
                    response_text = self.engine.chat(
                        messages, system_prompt=system_prompt,
                        temperature=temperature, max_tokens=max_tokens,
                    )
                elif hasattr(self.engine, "generate"):
                    prompt = self.engine.format_chat_prompt(messages, system_prompt)
                    response_text = self.engine.generate(
                        prompt,
                        temperature=temperature,
                        max_tokens=max_tokens,
                    )
                else:
                    return "Error: engine has no supported generate method"
            except Exception as exc:
                logger.error(f"Agent generation error: {exc}")
                return f"Agent stopped due to error: {exc}"

            # Add assistant response to history
            messages.append({"role": "assistant", "content": response_text})

            # Parse tool calls
            tool_calls = parse_tool_calls(response_text)

            if not tool_calls:
                # Model gave a prose response with no tool calls
                prose = extract_text_outside_tools(response_text)
                if prose:
                    summary_parts.append(prose)
                break

            # Execute tool calls
            tool_outputs: List[str] = []
            done = False
            for tool, attrs, body in tool_calls:
                if tool == "DONE":
                    summary_parts.append(body or "Task complete")
                    done = True
                    break

                result = self.executor.execute(tool, attrs, body)
                if self.on_tool_result:
                    self.on_tool_result(result)
                tool_outputs.append(result.to_message())

            if done:
                break

            if tool_outputs:
                # Feed results back as user message
                feedback = "Tool results:\n\n" + "\n\n".join(tool_outputs)
                messages.append({"role": "user", "content": feedback})

                # Also capture any prose the model said alongside tools
                prose = extract_text_outside_tools(response_text)
                if prose:
                    summary_parts.append(prose)
        else:
            summary_parts.append(
                f"Agent reached maximum iterations ({self.max_iterations})"
            )

        return "\n".join(summary_parts) if summary_parts else "Agent finished (no summary)"