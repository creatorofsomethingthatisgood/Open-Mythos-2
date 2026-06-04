"""
Terminal UI - Beautiful terminal interface using Rich library
"""

import logging
import os
import signal
import sys
import threading
import time
from typing import List, Optional
from pathlib import Path

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.markdown import Markdown
    from rich.prompt import Prompt
    from rich.live import Live
    from rich.table import Table
    from rich import print as rprint
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False
    logging.warning("Rich library not available")

from engine.inference import InferenceEngine
from engine.cloud_inference import CloudInferenceEngine
from engine.prompt_manager import PromptManager
from engine.memory import ConversationMemory
from engine.rag import RAGPipeline
from engine.self_reflect import SelfReflector
from engine.benchmark import BenchmarkSuite
from engine.context_budget import fit_chat_context
from engine.local_refs import (
    build_local_file_context,
    extract_local_refs,
    extract_local_refs_from_messages,
    ref_to_path,
)
from engine.chat_config import merge_chat_defaults
from engine.rml import RMLEngine
from engine.cross_session_memory import CrossSessionMemory
from engine.session_summaries import SessionSummaries
from engine.chat_fix import (
    REWRITE_WARNING,
    _fix_cfg,
    apply_patches_with_prompt,
    handle_chat_fix,
    resolve_fix_targets,
    resolve_rewrite_file_paths,
    run_dedicated_rewrite,
    run_rewrite_files,
    user_confirms_rewrite,
    active_prompt_is_security_audit,
    build_fix_system_prompt,
    user_wants_fix,
    user_wants_rewrite,
)
from engine.progress import ProgressCallback, StreamCallback
from engine.voice import VoiceEngine
from engine.skills import SkillManager
try:
    from engine.marketplace import MarketplaceClient
    MARKETPLACE_AVAILABLE = True
except ImportError:
    MARKETPLACE_AVAILABLE = False
from ui.terminal_bitacora import TerminalBitacoraSession

logger = logging.getLogger(__name__)


class ThinkingSpinner:
    """Animated spinner cycling through unicode star glyphs, like Claude Code."""

    # Unicode star/symbol glyphs that rotate during thinking
    GLYPHS = [
        "\u2736", "\u2737", "\u2738", "\u2739", "\u273A",
        "\u274B", "\u274A", "\u2747", "\u2748", "\u2749",
        "\u2726", "\u2727", "\u22C6", "\u2042", "\u2734",
        "\u2735", "\u2731", "\u2732", "\u2733", "\u2743",
        "\u2744", "\u2745", "\u2746", "\u2605",
    ]

    # Moon-phase glyphs (toggle with M key while thinking)
    MOON_GLYPHS = ["\u25D0", "\u25D1", "\u25D2", "\u25D3"]

    COLORS = ["#EA580C", "#F97316", "#FB923C", "#EF4444", "#F97316", "#EA580C"]

    # Rotating labels when using default "Thinking" label
    LABELS = [
        "Thinking", "Reasoning", "Pondering", "Analyzing",
        "Musing", "Deliberating", "Contemplating", "Processing",
        "Reflecting", "Calculating",
    ]

    def __init__(self) -> None:
        self._idx = 0
        self._stop = threading.Event()
        self._thread = None
        self._live = None
        self._label = "Thinking"
        self._moon = False
        self._listener = None

    def start(self, console, label: str = "Thinking") -> None:
        # Ensure previous listener is fully stopped and terminal is restored
        # before we capture settings again in a new _start_listener().
        if self._listener and self._listener.is_alive():
            self._stop.set()
            self._listener.join(timeout=1.0)
            self._stop.clear()
        self._label = label
        self._moon = False
        self._stop.clear()
        self._live = Live("", console=console, transient=True, refresh_per_second=8)
        self._live.__enter__()
        self._thread = threading.Thread(target=self._spin, daemon=True)
        self._thread.start()
        self._start_listener()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=0.5)
        # Join listener first so terminal settings are restored before
        # the main thread touches stdin again (e.g. for Prompt input).
        if self._listener:
            self._listener.join(timeout=1.0)
            self._listener = None
        if self._live:
            self._live.__exit__(None, None, None)
            self._live = None

    def _frame_text(self) -> str:
        glyphs = self.MOON_GLYPHS if self._moon else self.GLYPHS
        glyph = glyphs[self._idx % len(glyphs)]
        color = self.COLORS[self._idx % len(self.COLORS)]
        label = self.LABELS[self._idx % len(self.LABELS)] if self._label == "Thinking" else self._label
        return f"[{color}]{glyph}[/{color}] [dim]{label}...[/dim]"

    def _spin(self) -> None:
        while not self._stop.is_set():
            if self._live:
                self._live.update(self._frame_text())
            self._idx += 1
            self._stop.wait(0.12)

    def _start_listener(self) -> None:
        """Spawn a daemon thread listening for 'm' keypress to toggle moon mode."""
        try:
            import tty
            import termios
            import select
        except ImportError:
            return
        if not sys.stdin.isatty():
            return

        def _listen():
            fd = sys.stdin.fileno()
            old_settings = None
            try:
                old_settings = termios.tcgetattr(fd)
                tty.setcbreak(fd)
                while not self._stop.is_set():
                    ready, _, _ = select.select([sys.stdin], [], [], 0.1)
                    if ready:
                        ch = sys.stdin.read(1)
                        if ch.lower() == "m":
                            self._moon = not self._moon
            except (termios.error, OSError, ValueError):
                pass
            finally:
                if old_settings is not None:
                    try:
                        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
                    except (termios.error, OSError):
                        pass

        self._listener = threading.Thread(target=_listen, daemon=True)
        self._listener.start()



def _render_code_blocks(text: str, console) -> None:
    """Parse markdown fenced code blocks and render with Rich Syntax."""
    import re as _re
    parts = _re.split(r"(```[\w]*\n.*?```)", text, flags=_re.DOTALL)
    for part in parts:
        if part.startswith("```"):
            lines = part.split("\n", 1)
            lang = lines[0].strip().removeprefix("```") or "text"
            code = lines[1].rstrip("`").rstrip("\n") if len(lines) > 1 else ""
            try:
                syntax = Syntax(code, lang, theme="monokai", line_numbers=True)
                console.print(syntax)
            except Exception:
                console.print(code)
        elif part.strip():
            console.print(part)


class TerminalUI:
    """Beautiful terminal chat interface"""

    def __init__(self, config_path: str = "config.yaml"):
        """
        Initialize TerminalUI

        Args:
            config_path: Path to configuration file
        """
        if not RICH_AVAILABLE:
            raise RuntimeError("Rich library required. Install with: pip install rich")

        self.console = Console()
        self.config_path = config_path

        # Detect cloud mode (env var or config)
        import yaml as _yaml
        _cfg_raw = {}
        try:
            with open(config_path, "r") as _f:
                _cfg_raw = _yaml.safe_load(_f) or {}
        except Exception:
            pass
        _cloud_cfg = _cfg_raw.get("cloud", {})
        self.cloud_mode = (
            os.environ.get("MYTHOS_CLOUD") == "1"
            or bool(_cloud_cfg.get("api_key"))
        )

        # Initialize components
        if self.cloud_mode:
            self.console.print("[bold #EA580C]Initializing Mythos Cloud...[/bold #EA580C]")
        else:
            self.console.print("[bold #EA580C]Initializing Mythos Local...[/bold #EA580C]")

        try:
            if self.cloud_mode:
                self.engine = CloudInferenceEngine(config_path)
            else:
                self.engine = InferenceEngine(config_path)
            self.prompt_manager = PromptManager(config_path)
            self.memory = ConversationMemory(config_path)
            self.reflector = SelfReflector(config_path)

            # RAG is optional (local only)
            self.rag = None
            self.rag_enabled = False
            if not self.cloud_mode:
                try:
                    self.rag = RAGPipeline(config_path)
                    if not getattr(self.rag, "available", True):
                        self.rag = None
                        self.console.print(
                            "[dim]RAG disabled (install chromadb + sentence-transformers to enable)[/dim]"
                        )
                    else:
                        self.rag_enabled = True
                        stats = self.rag.get_stats()
                        self.console.print(
                            f"[green]RAG ready[/green] ({stats['total_chunks']} chunks indexed)"
                        )
                except Exception as rag_err:
                    logger.debug("RAG init failed: %s", rag_err)
                    self.console.print(f"[yellow]RAG not available: {rag_err}[/yellow]")
                    self.console.print(
                        "[dim] Fix: python main.py --mode rag-index --path <dir> "
                        "(needs network once for the embedding model)[/dim]"
                    )

            # Benchmark suite (local only)
            if not self.cloud_mode:
                self.benchmark = BenchmarkSuite(config_path)

        except Exception as e:
            self.console.print(f"[bold red]Error initializing engine: {e}[/bold red]")
            raise
        # RML (Reinforcement Machine Learning) engine
        self.rml = RMLEngine(self.engine.config)
        if self.rml.enabled:
            self.console.print("[green]RML (Reinforcement ML) enabled â learning from your feedback[/green]")

        # Cross-Session Memory -- Mythos Remembers
        self.cross_memory = CrossSessionMemory(self.engine.config)
        if self.cross_memory.enabled:
            fact_count = len(self.cross_memory.list_facts())
            self.console.print(
            "[green]Cross-Session Memory enabled -- "
            f"remembering {fact_count} fact(s) from past sessions[/green]"
            )

        # Session Summaries -- Mythos Remembers Your Sessions
        self.session_summaries = SessionSummaries(self.engine.config)
        if self.session_summaries.enabled:
            summary_count = len(self.session_summaries.list_summaries(limit=1))
            self.console.print(
            "[green]Session Summaries enabled -- "
            "digest your sessions with /summary or /sessions[/green]"
            )
        self._session_start_time = time.time()

        self.running = True
        self._pending_local_context = ""
        self._last_local_targets: list = []
        self._pending_rewrite_paths: List[str] = []
        self._last_response_text: str = ""  # for RML explicit feedback
        self._last_ctrl_c_time: float = 0.0  # for double Ctrl+C exit

        # Voice input (whisper.cpp on AMD Vulkan)
        self.voice = VoiceEngine(self.engine.config)
        if self.voice.is_available():
            self.console.print("[green]  Voice input ready — /voice to enable, then hold [bold]v[/bold] to speak[/green]")
        elif self.engine.config.get("voice", {}).get("enabled"):
            self.console.print("[yellow]  Voice enabled but whisper-cli not found — run: scripts/install_whisper.sh[/yellow]")    

        # Skill system
        self.skill_manager = SkillManager(self.engine.config)
        self.skill_manager.discover()
        skill_count = len(self.skill_manager.list_skills())
        if skill_count > 0:
            self.console.print(f"[green]Skills loaded: {skill_count} available[/green] -- /skill list to see them")
        if MARKETPLACE_AVAILABLE:
            self.marketplace = MarketplaceClient(self.engine.config)
        else:
            self.marketplace = None
    def show_header(self):
        """Display welcome header"""
        # Detect which prompt mode is active
        current_prompt_file = self.engine.config.get(
            'system', {}
        ).get('prompt_file', 'prompts/security_fix.txt')
        mode_name = Path(current_prompt_file).stem.replace('_', ' ').title()

        mode_emoji = {
            'Default': '🚀',
            'Coding': '💻',
            'Code Review': '🔍',
            'Debugging': '🐛',
            'Creative': '✨',
            'Analytical': '🧠',
            'Roleplay': '🎭',
            'Security Audit': '🛡️',
            'Security Fix': '🔧',
        }
        emoji = mode_emoji.get(mode_name, '🚀')

        banner = """
 █████■ █████■ ██████▓ ███■   ██■
 ██▔░░░██■██▔░░██■▔░░░░░ ████■  ██■
 ██■   ██■██████▔░█████■   ██▔██■ ██■
 ██■   ██■██▔░░░░ ██▔░░░   ██■▚██■██■
 ▚██████▔░██■     ██████▓ ██■ ▚████■
  ▚░░░░░ ▚░░ ░    ▚░░░░░░▚░░  ▚░░░
███■   ███■██■   ██■████████■██■  ██■██████▓██████■
████■ ████■▚██■ ██▔░▚░░██▔░░██■  ██■██▔░░░░▚░░░░██■
██▔███▔██■ ▚████▔░░   ██■   ████████■█████■   █████▔░░
██■▚██▔░██■  ▚██▔░░   ██■   ██▔░░░██■██▔░░░  ██▔░░░■
██■ ▚░░ ██■   ██■      ██■   ██■  ██■██████▓██████▓
▚░░     ▚░░   ▚░░      ▚░░   ▚░░  ▚░░▚░░░░░░░▚░░░░░░░
"""
        self.console.print(banner, style="bold #EA580C")

        if self.cloud_mode:
            self.console.print("[bold #EA580C]\u2500\u2500 Cloud Mode \u2500\u2500[/bold #EA580C]")
            self.console.print(f"  Model: [green]{self.engine.model_name}[/green]")
            self.console.print(f"  Context: [green]{self.engine.context_length:,}[/green] tokens")
            self.console.print(f"  Endpoint: [dim]{self.engine.base_url}[/dim]")
        else:
            self.console.print("[bold #EA580C]\u2500\u2500 Local Mode \u2500\u2500[/bold #EA580C]")
            self.console.print(f"  Model: [green]{self.engine.model_path.name}[/green]")
            self.console.print(f"  Context: [green]{self.engine.context_length:,}[/green] tokens")

        self.console.print(f"  Mode: [bold #F97316]{emoji} {mode_name}[/bold #F97316]")
        self.console.print(f"  System Prompt: [yellow]{self.prompt_manager.get_prompt()[:70]}...[/yellow]")
        self.console.print("\nType [bold]/help[/bold] for commands, [bold]/quit[/bold] to exit\n")
    def _fix_progress(self, message: str) -> None:
        """Show live status during scan / rewrite (users see this while waiting)."""
        if message.startswith(" •"):
            self.console.print(f"[dim]{message}[/dim]")
        else:
            self.console.print(f"[#EA580C]{message}[/#EA580C]")

    def _fix_stream(self, chunk: str) -> None:
        """Stream dedicated-rewrite model tokens (usually MYTHOS_PATCH body)."""
        self.console.print(chunk, end="", style="dim")

    def _bitacora_enabled(self, user_input: str, *, confirm_only: bool = False) -> bool:
        fix_cfg = merge_chat_defaults(self.engine.config).get("chat", {}).get("fix", {})
        if not fix_cfg.get("bitacora", True):
            return False
        return user_wants_fix(user_input) or confirm_only

    def show_help(self):
        """Display help information"""
        help_text = """
[bold #EA580C]Available Commands:[/bold #EA580C]

[yellow]/help[/yellow] - Show this help message
[yellow]/voice on|off|status[/yellow] - Voice I/O: talk to AI & hear responses (needs whisper + espeak-ng)
[yellow]/rec[/yellow] - Quick voice recording (no toggle needed)
[yellow]/clear[/yellow] - Clear conversation history
[yellow]/save[/yellow] - Save current conversation
[yellow]/load[/yellow] - Load a saved conversation
[yellow]/system <prompt>[/yellow] - Change system prompt
[yellow]/model <name>[/yellow] - Switch model (if available)
[yellow]/temp <float>[/yellow] - Change temperature (0.0-2.0)
 [yellow]/reflect on|off[/yellow] - Toggle self-reflection
 [yellow]/think on|off[/yellow] - Show model's step-by-step reasoning process
 [yellow]/thinking on|off[/yellow] - Alias for /think
 [yellow]/rag on|off[/yellow] - Toggle RAG (if available)
[yellow]/rml on|off|stats|good|bad|reset[/yellow] - Reinforcement ML: learn from your feedback
[yellow]/memory [on|off|add|forget|clear|extract][/yellow] - Cross-session memory: facts Mythos remembers
[yellow]/summary[/yellow] - Generate a structured digest of this session
[yellow]/sessions [N|id][/yellow] - Browse past session summaries (list, or view #N / session-id)
[yellow]/sessions-clear[/yellow] - Delete all saved session summaries
[yellow]/file <path>[/yellow] - Load a local file or folder into context
[yellow]/fix <path>[/yellow] - Auto-fix safe vulns (yaml, TLS, debug flags)
[yellow]/rewrite <path>[/yellow] - Rewrite file(s) on disk (LLM + auto-write)
[yellow]/benchmark[/yellow] - Run benchmark suite
[yellow]/config[/yellow] - Show current configuration
[yellow]/version[/yellow] - Show Mythos version and model info
[yellow]/tokens[/yellow] - Show token/generation stats table
[yellow]/topp <0.0-1.0>[/yellow] - Set top-p (nucleus sampling)
[yellow]/topk <1-200>[/yellow] - Set top-k (token filtering)
[yellow]/reppen <1.0-2.0>[/yellow] - Set repeat penalty (alias: /repeat_penalty)
[yellow]/maxtokens <128-65536>[/yellow] - Set max generation tokens
[yellow]/history[/yellow] - Browse conversation message history
[yellow]/compact[/yellow] - Compress older messages into a summary
[yellow]/context[/yellow] - Show context window usage bar
[yellow]/copy[/yellow] - Copy last response to clipboard
[yellow]/rename <name>[/yellow] - Rename this conversation
[yellow]/dump [path][/yellow] - Dump conversation to a text file
[yellow]/wc[/yellow] - Word/char count and session duration stats
[yellow]/persona <name|desc>[/yellow] - Switch persona template or set custom
[yellow]/export[/yellow] - Export conversation as text
[yellow]/markdown[/yellow] - Export conversation as formatted Markdown
[yellow]/search <query>[/yellow] - Search through conversation history
[yellow]/cost[/yellow] - Estimate token usage and API-equivalent cost
[yellow]/models[/yellow] - List available GGUF models and switch
[yellow]/redo[/yellow] - Regenerate the last assistant response
[yellow]/edit[/yellow] - Edit and resubmit your last message
[yellow]/auto-title[/yellow] - Auto-generate a conversation title from context
[yellow]/sysinfo[/yellow] - Show system/hardware info for performance tuning
[yellow]/skill list|info|run|install|uninstall|create[/yellow] - Manage skills (built-in, marketplace, AI-created)
[yellow]/marketplace[/yellow] - Browse and install community skills
[yellow]/quit[/yellow] - Exit the chat

[bold #EA580C]🔥 Enhanced Coding Modes:[/bold #EA580C]
[yellow]/system coding[/yellow] - ELITE 5-pass code verification mode
[yellow]/system code_review[/yellow] - Systematic code review mode
[yellow]/system debugging[/yellow] - Methodical debugging mode
[yellow]/system default[/yellow] - Return to general purpose mode

[bold #EA580C]Other Modes:[/bold #EA580C]
[yellow]/system creative[/yellow] - Creative writing & storytelling
[yellow]/system analytical[/yellow] - Deep analysis & reasoning
[yellow]/system roleplay[/yellow] - Character roleplay mode
[yellow]/system security_audit[/yellow] - Codebase security review mode
[yellow]/system security_fix[/yellow] - Default — find + fix (MYTHOS_PATCH)

[bold #EA580C]Local files & fixes in chat:[/bold #EA580C]
- Paste a path: [dim]/Users/you/project/app.py[/dim]
- Or: [dim]file:///Users/you/project/app.py[/dim]
- [yellow]/file ~/my-repo[/yellow] then ask about vulnerabilities
- [dim]fix the vulns in '/Users/you/project'[/dim] — scans, warns, asks to rewrite full files (git)
- [yellow]/rewrite '/path/to/file.py'[/yellow] — LLM writes complete file (MYTHOS_PATCH; confirm required)
- [yellow]/fix ~/my-repo[/yellow] — CLI line-level fixes only (separate from chat full-file rewrite)
- Default mode is [yellow]security_fix[/yellow] (writes via MYTHOS_PATCH). Use [yellow]/system security_audit[/yellow] for report-only.
- Best with [yellow]/temp 0.3[/yellow] for fixes

[bold #EA580C]Tips:[/bold #EA580C]
- Use Ctrl+C to interrupt generation
- Type [yellow]|[/yellow] to start multiline paste mode
- Coding mode verifies code 5 times for correctness
- Self-reflection improves quality but takes longer
- Combine /system coding + /reflect on for best code quality
- Use [yellow]/context[/yellow] to check context window usage
        """
        self.console.print(Panel(help_text, title="Help", border_style="#EA580C"))

    def show_config(self):
        """Display current configuration"""
        table = Table(title="Current Configuration")
        table.add_column("Setting", style="#EA580C")
        table.add_column("Value", style="green")


        table.add_row("Model", str(self.engine.model_path.name) if hasattr(self.engine, "model_path") else self.engine.model_name)
        table.add_row("Temperature", str(self.engine.config.get('generation', {}).get('temperature', 0.7)))
        table.add_row("Max Tokens", str(self.engine.config.get('generation', {}).get('max_tokens', 2048)))
        table.add_row("Top-p", str(self.engine.config.get('generation', {}).get('top_p', 0.9)))
        table.add_row("Top-k", str(self.engine.config.get('generation', {}).get('top_k', 40)))
        table.add_row("Repeat Penalty", str(self.engine.config.get('generation', {}).get('repeat_penalty', 1.1)))
        table.add_row("Self-Reflection", "On" if self.reflector.should_reflect() else "Off")
        table.add_row("Thinking Mode", "On" if self.reflector.should_think() else "Off")
        table.add_row("RAG", "On" if self.rag_enabled and self.rag else "Off")
        table.add_row("RML", "On" if self.rml.enabled else "Off")
        table.add_row("Session Summaries", "On" if self.session_summaries.enabled else "Off")
        self.console.print(table)

    def handle_command(self, command: str) -> bool:
        """
        Handle slash commands

        Args:
            command: Command string

        Returns:
            True if should continue, False if should exit
        """
        parts = command.strip().split(maxsplit=1)
        cmd = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        if cmd == "/help":
            self.show_help()

        elif cmd == "/voice":
            # /voice on|off|male|female|status — toggle voice I/O + TTS gender
            sub = args.strip().lower()
            if sub in ("male", "female"):
                if self.voice.speaker.set_gender(sub):
                    self.engine.config.setdefault("voice", {})["tts_gender"] = sub
                    self.voice.speaker.piper_model, self.voice.speaker.espeak_voice = (
                        self.voice.speaker.VOICE_PRESETS[sub])
                    self.console.print(f"[green]Voice set to {sub}[/green]")
                else:
                    self.console.print("[red]Unknown gender — use male or female[/red]")
            elif sub in ("on", "enable", "true"):
                if not self.voice.is_available():
                    self.console.print("[red]whisper-cli not found — run: scripts/install_whisper.sh[/red]")
                else:
                    self.voice.enabled = True
                    self.engine.config.setdefault("voice", {})["enabled"] = True
                    mode = "push-to-talk (hold v)" if self.voice.push_to_talk else "toggle (press v)"
                    tts = "ON" if self.voice.speaker.is_available() else "unavailable (install espeak-ng)"
                    self.console.print(f"[green]Voice ON — {mode}[/green]  [dim]TTS: {tts}[/dim]")
            elif sub in ("off", "disable", "false"):
                self.voice.enabled = False
                self.engine.config.setdefault("voice", {})["enabled"] = False
                if self.voice.is_recording:
                    self.voice.cancel_recording()
                    self.voice.stop_speaking()
                self.console.print("[yellow]Voice OFF[/yellow]")
            else:
                # status or no arg
                avail = self.voice.is_available()
                en = self.voice.enabled
                rec = self.voice.is_recording
                self.console.print(
                    f"[#EA580C]Voice status:[/#EA580C] "
                    f"input={'[green]yes[/green]' if avail else '[red]no[/red]'}, "
                    f"enabled={'[green]on[/green]' if en else '[dim]off[/dim]'}, "
                    f"recording={'[bold red]YES[/bold red]' if rec else 'no'}, "
                    f"TTS={'[green]on[/green]' if self.voice.speaker.is_available() else '[dim]off[/dim]'}, "
                    f"voice={self.voice.speaker.gender}"
                )
                if avail and not en:
                    self.console.print("[dim]  Use /voice on to enable[/dim]")
                if not avail:
                    self.console.print("[dim]  Install: scripts/install_whisper.sh[/dim]")

        elif cmd == "/rec":
            # Quick voice record — no toggle needed, just record and transcribe
            if not self.voice.is_available():
                self.console.print("[red]whisper-cli not found — run: scripts/install_whisper.sh[/red]")
                return True
            try:
                self.voice.start_recording()
                self.console.print("[bold red][REC][/bold red] Recording... press Enter to stop")
                Prompt.ask("")
                transcript = self.voice.stop_and_transcribe()
                if transcript:
                    self.console.print(f"[green]> {transcript}[/green]")
                    self.generate_response(transcript)
                else:
                    self.console.print("[yellow]No speech detected[/yellow]")
            except RuntimeError as e:
                self.console.print(f"[red]Voice error: {e}[/red]")

        elif cmd == "/clear":
            self.memory.clear()
            self.console.print("[green]Conversation cleared[/green]")

        elif cmd == "/save":
            filepath = self.memory.save()
            self.console.print(f"[green]Saved to: {filepath}[/green]")

        elif cmd == "/load":
            conversations = self.memory.list_conversations()
            if not conversations:
                self.console.print("[yellow]No saved conversations found[/yellow]")
                return True

            self.console.print("[#EA580C]Saved conversations:[/#EA580C]")
            for i, conv in enumerate(conversations[:10], 1):
                self.console.print(f" {i}. {conv.name}")

            choice = Prompt.ask("Enter number to load", default="1")
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(conversations):
                    self.memory.load(conversations[idx].name)
                    self.console.print(f"[green]Loaded conversation[/green]")
                else:
                    self.console.print("[red]Invalid selection[/red]")
            except (ValueError, IndexError):
                self.console.print("[red]Invalid input[/red]")

        elif cmd == "/system":
            if args:
                templates = self.prompt_manager.list_templates()
                if args in templates:
                    prompt = self.prompt_manager.load_prompt(args)
                    self.prompt_manager.set_prompt(prompt)
                    self.console.print(f"[green]Loaded template: {args}[/green]")
                else:
                    self.prompt_manager.set_prompt(args)
                    self.console.print("[green]Custom system prompt set[/green]")
            else:
                templates = self.prompt_manager.list_templates()
                self.console.print(f"[#EA580C]Available templates: {', '.join(templates)}[/#EA580C]")
                template = Prompt.ask("Enter template name or custom prompt")
                if template in templates:
                    prompt = self.prompt_manager.load_prompt(template)
                    self.prompt_manager.set_prompt(prompt)
                    self.console.print(f"[green]Loaded template: {template}[/green]")
                else:
                    self.prompt_manager.set_prompt(template)
                    self.console.print("[green]Custom prompt set[/green]")

        elif cmd == "/temp":
            try:
                temp = float(args)
                if 0.0 <= temp <= 2.0:
                    self.engine.config['generation']['temperature'] = temp
                    self.console.print(f"[green]Temperature set to {temp}[/green]")
                else:
                    self.console.print("[red]Temperature must be between 0.0 and 2.0[/red]")
            except ValueError:
                self.console.print("[red]Invalid temperature value[/red]")

        elif cmd == "/reflect":
            if args.lower() == "on":
                self.engine.config['system']['self_reflect'] = True
                self.console.print("[green]Self-reflection enabled[/green]")
            elif args.lower() == "off":
                self.engine.config['system']['self_reflect'] = False
                self.console.print("[yellow]Self-reflection disabled[/yellow]")
            else:
                self.console.print("[red]Use /reflect on or /reflect off[/red]")

        elif cmd == "/file":
            if not args:
                self.console.print(
                    "[red]Usage: /file <path>[/red] "
                    "(file, folder, or file:// URL)"
                )
                return True
            fake_msg = f"Analyze {args.strip()}"
            ctx, notices = build_local_file_context(
                fake_msg, self.engine.config
            )
            for note in notices:
                style = "green" if note.startswith("Loaded") or "Scanned" in note else "yellow"
                self.console.print(f"[{style}]{note}[/{style}]")
            if ctx:
                self._pending_local_context = ctx
                self._last_local_targets = resolve_fix_targets(
                    fake_msg, self._last_local_targets
                )
                self.console.print(
                    "[green]Local file context ready — ask your security question next.[/green]"
                )
            else:
                self.console.print("[yellow]No file context loaded.[/yellow]")
            return True

        elif cmd == "/fix":
            if not args:
                self.console.print(
                    "[red]Usage: /fix <path>[/red] "
                    "(file or folder; dry-run preview, then confirm apply)"
                )
                return True
            target = ref_to_path(args.strip())
            if not target.exists():
                self.console.print(f"[red]Not found: {target}[/red]")
                return True
            try:
                from mythos_cli.fix_runner import run_fix_on_path
                from mythos_cli.fix_output import print_fix_results

                self.console.print(f"[#EA580C]Scanning {target}...[/#EA580C]")
                findings, fixes = run_fix_on_path(target, dry_run=True)
                print_fix_results(fixes, dry_run=True)

                pending = [f for f in fixes if f.status == "pending"]
                if not pending:
                    if findings:
                        self.console.print(
                            "[yellow]Remaining issues need manual or LLM review "
                            "(secrets, SQL, eval, etc.). Ask in chat with /file.[/yellow]"
                        )
                    return True

                self.console.print(
                    Panel(REWRITE_WARNING, title="Line-level fix", border_style="yellow")
                )
                if Prompt.ask("Apply line-level fixes to disk?", choices=["y", "n"], default="n") == "y":
                    _, applied = run_fix_on_path(target, dry_run=False)
                    print_fix_results(applied, dry_run=False)
                    self.console.print("[green]Fixes written — review with git diff.[/green]")
            except Exception as exc:
                self.console.print(f"[red]Fix failed: {exc}[/red]")
            return True

        elif cmd == "/rewrite":
            if not args:
                self.console.print(
                    "[red]Usage: /rewrite <file-or-folder>[/red] "
                    "(rewrites full file on disk via LLM)"
                )
                return True
            target = ref_to_path(args.strip())
            if not target.exists():
                self.console.print(f"[red]Not found: {target}[/red]")
                return True
            try:
                self.console.print(
                    Panel(REWRITE_WARNING, title="Full-file rewrite", border_style="yellow")
                )
                if Prompt.ask(
                    f"Rewrite {target} on disk (complete files)?",
                    choices=["y", "n"],
                    default="n",
                ) != "y":
                    self.console.print("[yellow]Rewrite cancelled.[/yellow]")
                    return True
                self.console.print(
                    f"[#EA580C]Rewriting {target} (full file write)...[/#EA580C]"
                )
                self.console.print("[dim]This may take a minute.[/dim]\n")
                use_bitacora = self._bitacora_enabled("/rewrite", confirm_only=False)
                bitacora_cm = None
                on_progress = self._fix_progress
                on_stream = self._fix_stream
                if use_bitacora:
                    bitacora_cm = TerminalBitacoraSession(self.console)
                    bitacora = bitacora_cm.__enter__()
                    on_progress = bitacora.as_progress_callback()
                    on_stream = (
                        bitacora_cm.stream_callback()
                        if _fix_cfg(self.engine.config).get("stream_rewrite", False)
                        else (lambda _c: None)
                    )
                try:
                    response, notices = run_rewrite_files(
                        [target],
                        self.engine,
                        self.prompt_manager,
                        self.memory,
                        self.engine.config,
                        stream=False,
                        on_progress=on_progress,
                        on_stream=on_stream,
                    )
                finally:
                    if bitacora_cm is not None:
                        bitacora_cm.__exit__(None, None, None)
                if on_stream is not self._fix_stream:
                    self.console.print()
                for note in notices:
                    style = "green" if note.startswith("Wrote") else "yellow"
                    self.console.print(f"[{style}]{note}[/{style}]")
                if response.strip():
                    self.console.print("\n[bold #EA580C]Assistant[/bold #EA580C]")
                    self.console.print(response)
                    self.memory.add_message("assistant", response)
            except Exception as exc:
                self.console.print(f"[red]Rewrite failed: {exc}[/red]")
            return True

        elif cmd == "/rag":
            if not self.rag:
                self.console.print("[red]RAG not available[/red]")
                return True

            if args.lower() == "on":
                self.rag_enabled = True
                self.console.print("[green]RAG enabled[/green]")

                # Show stats
                stats = self.rag.get_stats()
                self.console.print(f" Indexed chunks: {stats['total_chunks']}")
                self.console.print(f" Index path: {stats.get('persist_directory', 'chroma_db')}")

                if stats['total_chunks'] == 0:
                    self.console.print(
                        "[yellow] No documents indexed. Quit chat, run:[/yellow]"
                    )
                    self.console.print(
                        "[yellow] python main.py --mode rag-index --path <dir>[/yellow]"
                    )
                    self.console.print(
                        "[yellow] Then restart chat and /rag on again.[/yellow]"
                    )
            elif args.lower() == "off":
                self.rag_enabled = False
                self.console.print("[yellow]RAG disabled[/yellow]")
            else:
                self.console.print("[red]Use /rag on or /rag off[/red]")

        elif cmd == "/rml":
            sub = args.lower().strip()
            if sub == "on":
                self.rml.toggle(True)
                self.engine.config.setdefault("rml", {})["enabled"] = True
                self.console.print("[green]RML (Reinforcement ML) enabled[/green]")
                self.console.print("[dim]The model will now learn from your feedback.[/dim]")
                self.console.print("[dim]Use /rml good or /rml bad after a response to give explicit signals.[/dim]")
            elif sub == "off":
                self.rml.toggle(False)
                self.engine.config.setdefault("rml", {})["enabled"] = False
                self.console.print("[yellow]RML (Reinforcement ML) disabled[/yellow]")
                self.console.print("[dim]Learning paused. Previous preferences are kept.[/dim]")
            elif sub == "stats":
                self.console.print(self.rml.format_stats_table())
            elif sub == "good":
                if self._last_response_text:
                    self.rml.record_explicit(good=True, detail="user /rml good")
                    self.console.print("[green]RML: positive signal recorded (+2)[/green]")
                else:
                    self.console.print("[yellow]No previous response to rate[/yellow]")
            elif sub == "bad":
                if self._last_response_text:
                    self.rml.record_explicit(good=False, detail="user /rml bad")
                    self.console.print("[yellow]RML: negative signal recorded (-2)[/yellow]")
                else:
                    self.console.print("[yellow]No previous response to rate[/yellow]")
            elif sub == "reset":
                self.rml.reset()
                self.console.print("[yellow]RML preferences reset — starting fresh[/yellow]")
            else:
                self.console.print("[red]Usage: /rml on|off|stats|good|bad|reset[/red]")
                self.console.print("[dim]  on     — enable RML learning[/dim]")
                self.console.print("[dim]  off    — disable RML learning[/dim]")
                self.console.print("[dim]  stats  — show what RML has learned[/dim]")
                self.console.print("[dim]  good   — rate the last response as good (+2)[/dim]")
                self.console.print("[dim]  bad    — rate the last response as bad (-2)[/dim]")
                self.console.print("[dim] reset \u2014 wipe all learned preferences[/dim]")

        elif cmd == "/memory":
            sub_parts = args.strip().split(maxsplit=1)
            sub = sub_parts[0].lower() if sub_parts else ""
            mem_args = sub_parts[1] if len(sub_parts) > 1 else ""
            if sub == "on":
                self.cross_memory.enabled = True
                self.engine.config.setdefault("memory", {}).setdefault(
                    "cross_session", {}
                )["enabled"] = True
                self.console.print("[green]Cross-Session Memory enabled[/green]")
                self.console.print(
                    "[dim]Mythos will remember facts across sessions.[/dim]"
                )
            elif sub == "off":
                self.cross_memory.enabled = False
                self.engine.config.setdefault("memory", {}).setdefault(
                    "cross_session", {}
                )["enabled"] = False
                self.console.print("[yellow]Cross-Session Memory disabled[/yellow]")
                self.console.print(
                    "[dim]Memory paused. Stored facts are kept.[/dim]"
                )
            elif sub == "add":
                if not mem_args:
                    self.console.print("[red]Usage: /memory add <fact text>[/red]")
                else:
                    fid = self.cross_memory.add_fact(mem_args, source="manual")
                    if fid:
                        self.console.print(f"[green]Fact added: {mem_args}[/green]")
                    else:
                        self.console.print(
                            "[yellow]Fact skipped (empty or duplicate)[/yellow]"
                        )
            elif sub == "forget" or sub == "remove":
                if not mem_args:
                    self.console.print(
                        "[red]Usage: /memory forget <fact text or ID>[/red]"
                    )
                else:
                    removed = self.cross_memory.remove_fact(mem_args)
                    if removed:
                        self.console.print(
                            f"[green]Fact removed: {mem_args}[/green]"
                        )
                    else:
                        self.console.print(
                            "[yellow]No matching fact found[/yellow]"
                        )
            elif sub == "clear":
                self.cross_memory.clear()
                self.console.print("[yellow]All cross-session memory cleared[/yellow]")
            elif sub == "extract":
                msg_list = self.memory.get_recent_context(max_turns=50)
                n = self.cross_memory.extract_facts_from_messages(
                    msg_list, engine=self.engine
                )
                self.console.print(
                    f"[green]Extracted {n} new fact(s) from this session[/green]"
                )
            elif sub == "":
                # No subcommand -- show the facts table
                self.console.print(self.cross_memory.format_facts_table())
            else:
                self.console.print(
                    "[red]Usage: /memory [on|off|add|forget|clear|extract][/red]"
                )
                self.console.print("[dim] /memory       -- show stored facts[/dim]")
                self.console.print("[dim] /memory on    -- enable cross-session memory[/dim]")
                self.console.print("[dim] /memory off   -- disable cross-session memory[/dim]")
                self.console.print("[dim] /memory add <fact>   -- manually add a fact[/dim]")
                self.console.print("[dim] /memory forget <text> -- remove a fact[/dim]")
                self.console.print("[dim] /memory clear -- wipe all facts[/dim]")
                self.console.print("[dim] /memory extract -- scan session for facts now[/dim]")

        elif cmd == "/benchmark":
            self.console.print("[#EA580C]Running benchmark suite...[/#EA580C]")
            self.console.print("[yellow]This will take several minutes...[/yellow]\n")

            results = self.benchmark.run_full_benchmark(self.engine)

            # Display results
            self.console.print("\n" + self.benchmark.format_results_table(results))

            # Save results
            filepath = self.benchmark.save_results(results)
            self.console.print(f"\n[green]Results saved to: {filepath}[/green]")

        elif cmd == "/config":
            self.show_config()

        elif cmd == "/export":
            text = self.memory.export_text()
            filename = Prompt.ask("Save as", default="conversation_export.txt")

            target = Path(filename).expanduser().resolve()
            cwd = Path.cwd().resolve()
            if not target.is_relative_to(cwd):
                self.console.print(f"[red]Export path must be inside current directory: {cwd}[/red]")
                return True

            with open(target, 'w') as f:
                f.write(text)
            self.console.print(f"[green]Exported to: {target}[/green]")

        elif cmd == "/summary":
            if not self.session_summaries.enabled:
                self.console.print("[yellow]Session Summaries not enabled. Set session_summaries.enabled: true in config.[/yellow]")
                return True
            self.console.print("[#EA580C]Generating session summary...[/#EA580C]")
            msg_list = self.memory.get_recent_context(max_turns=50)
            model_name = self.engine.config.get("model", {}).get("name", "")
            summary = self.session_summaries.generate_summary(
                msg_list,
                engine=self.engine,
                session_start_time=getattr(self, "_session_start_time", None),
                model_name=model_name,
            )
            if summary is None:
                self.console.print("[yellow]Not enough conversation to summarize yet.[/yellow]")
                return True
            sid = self.session_summaries.save_summary(summary)
            detail = self.session_summaries.format_summary_detail(summary)
            self.console.print(detail)
            self.console.print(f"[green]Summary saved (id: {sid})[/green]")

        elif cmd == "/sessions":
            if not self.session_summaries.enabled:
                self.console.print("[yellow]Session Summaries not enabled.[/yellow]")
                return True
            if args and args.strip().isdigit():
                # /sessions <number> -- show detail for the Nth most recent
                idx = int(args.strip()) - 1
                listings = self.session_summaries.list_summaries(limit=idx + 1)
                if 0 <= idx < len(listings):
                    full = self.session_summaries.load_summary(listings[idx]["session_id"])
                    if full:
                        self.console.print(self.session_summaries.format_summary_detail(full))
                    else:
                        self.console.print("[red]Could not load that summary.[/red]")
                else:
                    self.console.print("[red]Invalid session number.[/red]")
            elif args:
                # /sessions <session_id> -- show detail by ID
                full = self.session_summaries.load_summary(args.strip())
                if full:
                    self.console.print(self.session_summaries.format_summary_detail(full))
                else:
                    self.console.print(f"[red]No summary found for: {args.strip()}[/red]")
            else:
                # /sessions -- list all
                listings = self.session_summaries.list_summaries(limit=20)
                self.console.print(self.session_summaries.format_sessions_list(listings))

        elif cmd == "/think" or cmd == "/thinking":
            if args.lower() == "on":
                self.engine.config['system']['thinking_mode'] = True
                self.reflector.config.setdefault('system', {})['thinking_mode'] = True
                self.console.print("[green]Thinking mode enabled[/green]")
                self.console.print("[dim]Mythos will now show its step-by-step reasoning before the answer.[/dim]")
            elif args.lower() == "off":
                self.engine.config['system']['thinking_mode'] = False
                self.reflector.config.setdefault('system', {})['thinking_mode'] = False
                self.console.print("[yellow]Thinking mode disabled[/yellow]")
            else:
                self.console.print("[red]Use /think on or /think off[/red]")

        elif cmd == "/sessions-clear":
            if not self.session_summaries.enabled:
                self.console.print("[yellow]Session Summaries not enabled.[/yellow]")
                return True
            count = self.session_summaries.clear_all()
            self.console.print(f"[green]Cleared {count} session summary/ies.[/green]")

        elif cmd == "/version":
            from mythos_cli import __version__
            self.console.print(f"[#EA580C]Mythos[/#EA580C] [bold]{__version__}[/bold]")
            self.console.print(f"[dim]Model: {self.engine.model_path.name if hasattr(self.engine, 'model_path') else self.engine.model_name}[/dim]")

        elif cmd == "/tokens":
            gen_cfg = self.engine.config.get('generation', {})
            ctx_len = self.engine.context_length
            max_tok = gen_cfg.get('max_tokens', 2048)
            temp = gen_cfg.get('temperature', 0.7)
            top_p = gen_cfg.get('top_p', 0.9)
            top_k = gen_cfg.get('top_k', 40)
            rp = gen_cfg.get('repeat_penalty', 1.1)
            table = Table(title="Token & Generation Stats")
            table.add_column("Setting", style="#EA580C")
            table.add_column("Value", style="green")
            table.add_row("Context window", f"{ctx_len:,}")
            table.add_row("Max tokens", str(max_tok))
            table.add_row("Temperature", str(temp))
            table.add_row("Top-p", str(top_p))
            table.add_row("Top-k", str(top_k))
            table.add_row("Repeat penalty", str(rp))
            table.add_row("Messages in memory", str(len(self.memory.messages)))
            self.console.print(table)

        elif cmd == "/topp":
            try:
                val = float(args)
                if 0.0 <= val <= 1.0:
                    self.engine.config['generation']['top_p'] = val
                    self.console.print(f"[green]Top-p set to {val}[/green]")
                else:
                    self.console.print("[red]Top-p must be between 0.0 and 1.0[/red]")
            except (ValueError, IndexError):
                current = self.engine.config.get('generation', {}).get('top_p', 0.9)
                self.console.print(f"[yellow]Current top-p: {current}[/yellow]")
                self.console.print("[dim]Usage: /topp <0.0-1.0>[/dim]")

        elif cmd == "/topk":
            try:
                val = int(args)
                if 1 <= val <= 200:
                    self.engine.config['generation']['top_k'] = val
                    self.console.print(f"[green]Top-k set to {val}[/green]")
                else:
                    self.console.print("[red]Top-k must be between 1 and 200[/red]")
            except (ValueError, IndexError):
                current = self.engine.config.get('generation', {}).get('top_k', 40)
                self.console.print(f"[yellow]Current top-k: {current}[/yellow]")
                self.console.print("[dim]Usage: /topk <1-200>[/dim]")

        elif cmd == "/reppen" or cmd == "/repeat_penalty":
            try:
                val = float(args)
                if 1.0 <= val <= 2.0:
                    self.engine.config['generation']['repeat_penalty'] = val
                    self.console.print(f"[green]Repeat penalty set to {val}[/green]")
                else:
                    self.console.print("[red]Repeat penalty must be between 1.0 and 2.0[/red]")
            except (ValueError, IndexError):
                current = self.engine.config.get('generation', {}).get('repeat_penalty', 1.1)
                self.console.print(f"[yellow]Current repeat penalty: {current}[/yellow]")
                self.console.print("[dim]Usage: /reppen <1.0-2.0>[/dim]")

        elif cmd == "/maxtokens":
            try:
                val = int(args)
                if 128 <= val <= 65536:
                    self.engine.config['generation']['max_tokens'] = val
                    self.console.print(f"[green]Max tokens set to {val:,}[/green]")
                else:
                    self.console.print("[red]Max tokens must be between 128 and 65536[/red]")
            except (ValueError, IndexError):
                current = self.engine.config.get('generation', {}).get('max_tokens', 2048)
                self.console.print(f"[yellow]Current max tokens: {current:,}[/yellow]")
                self.console.print("[dim]Usage: /maxtokens <128-65536>[/dim]")

        elif cmd == "/history":
            non_system = [m for m in self.memory.messages if m['role'] != 'system']
            if not non_system:
                self.console.print("[yellow]No conversation history[/yellow]")
                return True
            table = Table(title="Conversation History")
            table.add_column("#", style="dim", width=4)
            table.add_column("Role", style="#EA580C", width=10)
            table.add_column("Preview", style="green", max_width=60)
            table.add_column("Time", style="dim", width=19)
            for i, msg in enumerate(non_system, 1):
                role = msg['role']
                content = msg.get('content', '')
                preview = content[:80].replace('\n', ' ') + ('...' if len(content) > 80 else '')
                ts = msg.get('timestamp', '')[:19]
                table.add_row(str(i), role, preview, ts)
            self.console.print(table)
            self.console.print(f"[dim]{len(non_system)} message(s) total[/dim]")

        elif cmd == "/compact":
            non_system = [m for m in self.memory.messages if m['role'] != 'system']
            if len(non_system) < 6:
                self.console.print("[yellow]Not enough history to compact (need at least 3 turns)[/yellow]")
                return True
            self.console.print("[#EA580C]Compacting conversation...[/#EA580C]")
            # Keep the last 4 messages (2 turns), summarize the rest
            old_msgs = non_system[:-4]
            recent = non_system[-4:]
            # Build a compact summary of old messages
            summary_lines = ["[Previous conversation summary:]"]
            for m in old_msgs:
                role = m['role'].upper()
                text = m.get('content', '')[:200]
                summary_lines.append(f"{role}: {text}")
            summary_text = "\n".join(summary_lines)
            # Rebuild messages: system + compact summary + recent
            self.memory.messages = [
                {'role': 'system', 'content': summary_text, 'timestamp': datetime.now().isoformat()}
            ] + recent
            self.console.print(f"[green]Compacted {len(old_msgs)} older messages into a summary[/green]")
            self.console.print(f"[dim]Kept {len(recent)} recent messages[/dim]")

        elif cmd == "/copy":
            if not self._last_response_text:
                self.console.print("[yellow]No previous response to copy[/yellow]")
                return True
            try:
                import subprocess
                process = subprocess.Popen(
                    ['xclip', '-selection', 'clipboard'],
                    stdin=subprocess.PIPE,
                )
                process.communicate(self._last_response_text.encode('utf-8'))
                if process.returncode == 0:
                    self.console.print(f"[green]Copied {len(self._last_response_text)} chars to clipboard (xclip)[/green]")
                else:
                    raise RuntimeError("xclip failed")
            except FileNotFoundError:
                # Try xsel as fallback
                try:
                    import subprocess
                    process = subprocess.Popen(
                        ['xsel', '--clipboard', '--input'],
                        stdin=subprocess.PIPE,
                    )
                    process.communicate(self._last_response_text.encode('utf-8'))
                    self.console.print(f"[green]Copied {len(self._last_response_text)} chars to clipboard (xsel)[/green]")
                except FileNotFoundError:
                    # Try pbcopy (macOS)
                    try:
                        import subprocess
                        process = subprocess.Popen(
                            ['pbcopy'],
                            stdin=subprocess.PIPE,
                        )
                        process.communicate(self._last_response_text.encode('utf-8'))
                        self.console.print(f"[green]Copied {len(self._last_response_text)} chars to clipboard (pbcopy)[/green]")
                    except FileNotFoundError:
                        self.console.print("[yellow]No clipboard tool found. Install xclip, xsel, or pbcopy.[/yellow]")

        elif cmd == "/rename":
            if args:
                self.memory.metadata['name'] = args.strip()
                self.console.print(f"[green]Conversation renamed to: {args.strip()}[/green]")
            else:
                current = self.memory.metadata.get('name', 'untitled')
                self.console.print(f"[yellow]Current name: {current}[/yellow]")
                self.console.print("[dim]Usage: /rename <name>[/dim]")

        elif cmd == "/dump":
            if args:
                target_path = Path(args.strip()).expanduser().resolve()
            else:
                target_path = Path("mythos_dump.txt")
            cwd = Path.cwd().resolve()
            if not target_path.is_relative_to(cwd):
                self.console.print(f"[red]Dump path must be inside current directory: {cwd}[/red]")
                return True

            try:
                text = self.memory.export_text()
                with open(target_path, 'w') as f:
                    f.write(text)
                self.console.print(f"[green]Conversation dumped to: {target_path}[/green]")
            except Exception as e:
                self.console.print(f"[red]Failed to dump: {e}[/red]")

        elif cmd == "/wc":
            non_system = [m for m in self.memory.messages if m['role'] != 'system']
            user_msgs = [m for m in non_system if m['role'] == 'user']
            asst_msgs = [m for m in non_system if m['role'] == 'assistant']
            user_words = sum(len(m.get('content', '').split()) for m in user_msgs)
            asst_words = sum(len(m.get('content', '').split()) for m in asst_msgs)
            total_words = user_words + asst_words
            total_chars = sum(len(m.get('content', '')) for m in non_system)
            table = Table(title="Conversation Stats")
            table.add_column("Metric", style="#EA580C")
            table.add_column("Value", style="green")
            table.add_row("User messages", str(len(user_msgs)))
            table.add_row("Assistant messages", str(len(asst_msgs)))
            table.add_row("User words", f"{user_words:,}")
            table.add_row("Assistant words", f"{asst_words:,}")
            table.add_row("Total words", f"{total_words:,}")
            table.add_row("Total characters", f"{total_chars:,}")
            elapsed = time.time() - getattr(self, '_session_start_time', time.time())
            if elapsed > 0:
                mins = int(elapsed // 60)
                secs = int(elapsed % 60)
                table.add_row("Session duration", f"{mins}m {secs}s")
            self.console.print(table)

        elif cmd == "/persona":
            if args:
                templates = self.prompt_manager.list_templates()
                if args in templates:
                    prompt = self.prompt_manager.load_prompt(args)
                    self.prompt_manager.set_prompt(prompt)
                    self.console.print(f"[green]Switched to persona: {args}[/green]")
                else:
                    # Set a custom persona instruction
                    custom = f"You are {args}. Respond in that voice and style."
                    self.prompt_manager.set_prompt(custom)
                    self.console.print(f"[green]Custom persona set: {args}[/green]")
            else:
                templates = self.prompt_manager.list_templates()
                self.console.print("[#EA580C]Available personas:[/#EA580C]")
                for t in templates:
                    self.console.print(f"  [yellow]{t}[/yellow]")
                self.console.print("[dim]Usage: /persona <name> or /persona <description>[/dim]")

        elif cmd == "/markdown":
            # Export conversation as well-formatted Markdown
            lines = ["# Mythos Conversation", ""]
            name = self.memory.metadata.get("name")
            if name:
                lines.append(f"**Name:** {name}")
            created = self.memory.metadata.get("created_at", "")
            if created:
                lines.append(f"**Date:** {created[:19]}")
            lines.append("")
            lines.append("---")
            lines.append("")
            for msg in self.memory.messages:
                role = msg["role"]
                content = msg.get("content", "")
                if role == "system":
                    lines.append("### System Prompt")
                    lines.append("")
                    lines.append(content)
                elif role == "user":
                    lines.append("### User")
                    lines.append("")
                    lines.append(content)
                elif role == "assistant":
                    lines.append("### Assistant")
                    lines.append("")
                    lines.append(content)
                lines.append("")
                lines.append("---")
                lines.append("")
            md_text = "\n".join(lines)
            if args:
                target_path = Path(args.strip()).expanduser().resolve()
            else:
                target_path = Path("conversation_export.md")
            cwd = Path.cwd().resolve()
            if not target_path.is_relative_to(cwd):
                self.console.print(f"[red]Markdown export path must be inside current directory: {cwd}[/red]")
                return True
            try:
                with open(target_path, "w") as f_md:
                    f_md.write(md_text)
                self.console.print(f"[green]Markdown exported to: {target_path}[/green]")
            except Exception as e:
                self.console.print(f"[red]Failed to export markdown: {e}[/red]")

        elif cmd == "/search":
            if not args.strip():
                self.console.print("[red]Usage: /search <query>[/red]")
                self.console.print("[dim]Searches through all messages in this session.[/dim]")
                return True
            query = args.strip().lower()
            results = []
            for i, msg in enumerate(self.memory.messages):
                content = msg.get("content", "")
                if query in content.lower():
                    role = msg["role"]
                    preview = content[:120].replace("\n", " ") + ("..." if len(content) > 120 else "")
                    ts = msg.get("timestamp", "")[:19]
                    results.append((i, role, preview, ts))
            if not results:
                self.console.print(f"[yellow]No messages matching '{args.strip()}'[/yellow]")
                return True
            table = Table(title=f"Search Results: '{args.strip()}'")
            table.add_column("#", style="dim", width=4)
            table.add_column("Role", style="#EA580C", width=10)
            table.add_column("Preview", style="green", max_width=60)
            table.add_column("Time", style="dim", width=19)
            for idx, role, preview, ts in results:
                table.add_row(str(idx), role, preview, ts)
            self.console.print(table)
            self.console.print(f"[dim]{len(results)} match(es) found[/dim]")

        elif cmd == "/context":
            # Show context window usage
            total_ctx = getattr(self.engine, 'config', {}).get('model', {}).get('n_ctx', 4096)
            reserve = getattr(self.engine, 'config', {}).get('context', {}).get('reserve_tokens', 512)
            msg_count = len(self.memory.messages)
            est_tokens = msg_count * 60  # rough estimate
            avail = total_ctx - reserve
            pct = min(int(est_tokens / avail * 100), 100) if avail else 0
            bar_len = 30
            filled = int(pct / 100 * bar_len)
            bar = "\u2588" * filled + "\u2591" * (bar_len - filled)
            ctx_color = "#EA580C" if pct > 80 else ("yellow" if pct > 50 else "green")
            self.console.print("[bold #EA580C]Context Window[/bold #EA580C]")
            self.console.print(f"  Total: {total_ctx} | Reserved: {reserve} | Available: {avail}")
            self.console.print(f"  [{ctx_color}]{bar}[/{ctx_color}] {pct}% (~{est_tokens} tokens)")
            if pct > 80:
                self.console.print("[yellow]  Context nearing capacity. Use /compact to free space.[/yellow]")

        elif cmd == "/cost":
            # Estimate token usage and API-equivalent cost
            non_system = [m for m in self.memory.messages if m["role"] != "system"]
            total_chars = sum(len(m.get("content", "")) for m in self.memory.messages)
            total_words = sum(len(m.get("content", "").split()) for m in self.memory.messages)
            est_input_tokens = int(total_chars / 3.5)
            est_output_tokens = sum(
                len(m.get("content", "").split()) for m in non_system if m["role"] == "assistant"
            )
            est_output_tokens = int(est_output_tokens * 1.33)
            input_cost = est_input_tokens * 2.50 / 1_000_000
            output_cost = est_output_tokens * 10.00 / 1_000_000
            total_cost = input_cost + output_cost
            table = Table(title="Token Usage & Cost Estimate")
            table.add_column("Metric", style="#EA580C")
            table.add_column("Value", style="green", justify="right")
            table.add_row("Total messages", str(len(non_system)))
            table.add_row("Total characters", f"{total_chars:,}")
            table.add_row("Total words", f"{total_words:,}")
            table.add_row("Est. input tokens", f"{est_input_tokens:,}")
            table.add_row("Est. output tokens", f"{est_output_tokens:,}")
            table.add_row("Est. total tokens", f"{est_input_tokens + est_output_tokens:,}")
            table.add_row("---", "---")
            table.add_row("API-equiv. input cost", f"${input_cost:.4f}")
            table.add_row("API-equiv. output cost", f"${output_cost:.4f}")
            table.add_row("API-equiv. total cost", f"${total_cost:.4f}")
            table.add_row("---", "---")
            table.add_row("Local inference cost", "$0.00 (free!)")
            table.add_row("Savings vs cloud API", f"${total_cost:.4f}")
            self.console.print(table)
            self.console.print("[dim]Cost estimates use GPT-4o pricing as a reference.[/dim]")
            self.console.print("[dim]Actual token counts may vary by model and tokenizer.[/dim]")

        elif cmd == "/models":
            # List available GGUF models and switch
            if self.cloud_mode:
                self.console.print("[yellow]Model switching not available in cloud mode. Use 'mythos cloud set-key --model <name>' to change model.[/yellow]")
                return
            model_dir = self.engine.model_path.parent if hasattr(self.engine, "model_path") else Path("models")
            gguf_files = sorted(model_dir.glob("**/*.gguf")) if model_dir.exists() else []
            fallbacks = self.engine.config.get("model", {}).get("fallbacks", [])
            fb_paths = []
            for fb in fallbacks:
                fb_path = Path(fb.get("path", ""))
                if fb_path.exists():
                    fb_paths.append(fb_path)
            all_models = list(dict.fromkeys(([self.engine.model_path] if hasattr(self.engine, "model_path") else []) + gguf_files + fb_paths)) if hasattr(self.engine, 'model_path') else []
            all_models = [p for p in all_models if p.suffix == ".gguf" and "-of-" not in p.name]
            if not all_models:
                self.console.print("[yellow]No GGUF models found[/yellow]")
                return True
            current = self.engine.model_path if hasattr(self.engine, "model_path") else None if hasattr(self.engine, 'model_path') else None
            table = Table(title="Available Models")
            table.add_column("#", style="dim", width=4)
            table.add_column("Model", style="#EA580C")
            table.add_column("Size", style="green", justify="right")
            table.add_column("Status", style="yellow")
            for i, p in enumerate(all_models, 1):
                size_gb = p.stat().st_size / (1024 ** 3) if p.exists() else 0
                status = "active" if p == current else ""
                table.add_row(str(i), p.name, f"{size_gb:.2f} GB", status)
            self.console.print(table)
            if args:
                try:
                    if args.strip().isdigit():
                        idx = int(args.strip()) - 1
                        if 0 <= idx < len(all_models):
                            new_model = all_models[idx]
                        else:
                            self.console.print("[red]Invalid model number[/red]")
                            return True
                    else:
                        new_model = model_dir / args.strip()
                        if not new_model.exists():
                            self.console.print(f"[red]Model not found: {args.strip()}[/red]")
                            return True
                    self.console.print(f"[#EA580C]Switching to {new_model.name}...[/#EA580C]")
                    try:
                        self.engine.load_model(str(new_model))
                        self.engine.config["model"]["path"] = str(new_model)
                        self.console.print(f"[green]Model switched to: {new_model.name}[/green]")
                    except Exception as e:
                        self.console.print(f"[red]Failed to load model: {e}[/red]")
                except (ValueError, IndexError):
                    self.console.print("[red]Invalid selection[/red]")
            else:
                self.console.print("[dim]Use /models <#> to switch to a different model[/dim]")

        elif cmd == "/redo":
            # Regenerate the last assistant response
            non_system = [m for m in self.memory.messages if m["role"] != "system"]
            if len(non_system) < 2:
                self.console.print("[yellow]Not enough conversation to redo[/yellow]")
                return True
            last_user_msg = None
            for msg in reversed(self.memory.messages):
                if msg["role"] == "assistant":
                    self.memory.messages.remove(msg)
                    break
            for msg in reversed(self.memory.messages):
                if msg["role"] == "user":
                    last_user_msg = msg.get("content", "")
                    break
            if last_user_msg:
                self.console.print("[#EA580C]Regenerating last response...[/#EA580C]")
                self._last_response_text = ""
                self.generate_response(last_user_msg)
            else:
                self.console.print("[yellow]No user message found to regenerate from[/yellow]")

        elif cmd == "/edit":
            # Edit and resubmit the last user message
            non_system = [m for m in self.memory.messages if m["role"] != "system"]
            if not non_system:
                self.console.print("[yellow]No messages to edit[/yellow]")
                return True
            last_user_idx = None
            for i in range(len(self.memory.messages) - 1, -1, -1):
                if self.memory.messages[i]["role"] == "user":
                    last_user_idx = i
                    break
            if last_user_idx is None:
                self.console.print("[yellow]No user message found[/yellow]")
                return True
            old_content = self.memory.messages[last_user_idx].get("content", "")
            short = old_content[:100] + ("..." if len(old_content) > 100 else "")
            self.console.print(f"[dim]Last message: {short}[/dim]")
            new_content = Prompt.ask("Edit message", default=old_content)
            if new_content.strip() and new_content != old_content:
                self.memory.messages = self.memory.messages[:last_user_idx]
                self.console.print("[green]Message edited, regenerating response...[/green]")
                self._last_response_text = ""
                self.generate_response(new_content)
            else:
                self.console.print("[yellow]No changes made[/yellow]")

        elif cmd == "/sysinfo":
            # Display system/hardware information for performance tuning
            import platform as _platform
            import multiprocessing as _mp
            table = Table(title="System Information")
            table.add_column("Property", style="#EA580C")
            table.add_column("Value", style="green")
            table.add_row("OS", _platform.system())
            table.add_row("OS Version", _platform.version())
            table.add_row("Architecture", _platform.machine())
            table.add_row("Processor", _platform.processor() or "N/A")
            table.add_row("CPU Cores (logical)", str(_mp.cpu_count()))
            # RAM detection
            try:
                import subprocess as _sp
                result = _sp.run(
                    ["free", "-h"], capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0:
                    for line in result.stdout.strip().split("\n"):
                        if "Mem:" in line:
                            parts = line.split()
                            if len(parts) >= 3:
                                table.add_row("Total RAM", parts[1])
                                table.add_row("Available RAM", parts[-1] if len(parts) >= 7 else parts[2])
                            break
            except Exception:
                try:
                    import subprocess as _sp
                    result = _sp.run(
                        ["vm_stat"], capture_output=True, text=True, timeout=5
                    )
                    if result.returncode == 0:
                        for line in result.stdout.strip().split("\n"):
                            if "free" in line.lower():
                                table.add_row("Memory info", line.strip()[:50])
                                break
                except Exception:
                    table.add_row("RAM", "(unable to detect)")
            # GPU detection
            try:
                import subprocess as _sp
                result = _sp.run(
                    ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
                    capture_output=True, text=True, timeout=10,
                )
                if result.returncode == 0:
                    for gi, line in enumerate(result.stdout.strip().split("\n")):
                        parts = [p.strip() for p in line.split(",")]
                        label = f"GPU {gi}" if gi > 0 else "GPU"
                        table.add_row(label, " | ".join(parts))
                else:
                    table.add_row("GPU", "NVIDIA driver not found")
            except (FileNotFoundError, Exception):
                if _platform.system() == "Darwin" and "arm" in _platform.machine().lower():
                    table.add_row("GPU", "Apple Silicon (Metal)")
                else:
                    table.add_row("GPU", "None detected")
            # Python and model config
            table.add_row("Python", _platform.python_version())
            table.add_row("--- Model Config ---", "")
            table.add_row("Context length", f"{self.engine.context_length:,}")
            n_gpu = self.engine.config.get("model", {}).get("n_gpu_layers", 0)
            table.add_row("GPU layers", str(n_gpu) + " (0=auto, -1=all)")
            n_threads = self.engine.config.get("model", {}).get("n_threads", 0)
            table.add_row("Threads", str(n_threads) + " (0=auto)")
            n_batch = self.engine.config.get("model", {}).get("n_batch", 512)
            table.add_row("Batch size", str(n_batch))
            use_mmap = self.engine.config.get("model", {}).get("use_mmap", True)
            table.add_row("Memory-mapped", str(use_mmap))
            self.console.print(table)
            self.console.print("[dim]Tip: set n_gpu_layers=-1 in config.yaml for full GPU acceleration[/dim]")
            self.console.print("[dim]Tip: set n_threads=0 to auto-detect optimal thread count[/dim]")

        elif cmd == "/auto-title":
            # Generate a conversation title from the first exchange
            non_system = [m for m in self.memory.messages if m["role"] != "system"]
            if len(non_system) < 2:
                self.console.print("[yellow]Need at least one exchange to generate a title[/yellow]")
                return True
            first_user = ""
            first_assistant = ""
            for msg in non_system:
                if msg["role"] == "user" and not first_user:
                    first_user = msg.get("content", "")[:200]
                elif msg["role"] == "assistant" and not first_assistant:
                    first_assistant = msg.get("content", "")[:200]
                if first_user and first_assistant:
                    break
            prompt = (
                "Generate a short 3-6 word title for this conversation. "
                "Only output the title, nothing else.\n\n"
                f"User: {first_user}\n"
                f"Assistant: {first_assistant[:200]}"
            )
            self.console.print("[#EA580C]Generating conversation title...[/#EA580C]")
            try:
                title = self.engine.generate(
                    self.engine.format_chat_prompt(
                        [{"role": "user", "content": prompt}],
                        "You generate concise conversation titles. Output ONLY the title."
                    ),
                    max_tokens=30,
                    temperature=0.3,
                    stream=False,
                ).strip().strip('"').strip("'")
                if len(title) > 60:
                    title = title[:60].rsplit(" ", 1)[0]
                self.memory.metadata["name"] = title
                self.console.print(f"[green]Conversation titled: {title}[/green]")
            except Exception as e:
                self.console.print(f"[red]Failed to generate title: {e}[/red]")

        elif cmd == "/skill" or cmd == "/skills":
            self._handle_skill_command(arg_text)

        elif cmd == "/marketplace":
            self._handle_skill_command(f"marketplace {arg_text}")

        elif cmd == "/quit":
            self.console.print("[#EA580C]Goodbye![/#EA580C]")
            return False

        else:
            self.console.print(f"[red]Unknown command: {cmd}[/red]")
            self.console.print("Type [bold]/help[/bold] for available commands")

        return True

    def _handle_skill_command(self, args: str) -> None:
        """Handle /skill subcommands."""
        parts = args.strip().split(None, 1)
        subcmd = parts[0].lower() if parts else "list"
        sub_args = parts[1].strip() if len(parts) > 1 else ""

        if subcmd in ("list", "ls"):
            skills = self.skill_manager.list_skills()
            if not skills:
                self.console.print("[yellow]No skills installed.[/yellow]")
                return
            from rich.table import Table
            table = Table(title="Mythos Skills", show_lines=False)
            table.add_column("Name", style="#EA580C")
            table.add_column("Version", style="dim")
            table.add_column("Source", style="cyan")
            table.add_column("Description")
            table.add_column("Commands", style="green")
            for s in skills:
                cmds = ", ".join(f"/{c.name}" for c in s.commands)
                src_icon = {"preinstalled": "built-in", "marketplace": "store", "custom": "ai-made"}.get(s.source, s.source)
                table.add_row(s.name, s.version, src_icon, s.description[:50], cmds)
            self.console.print(table)

        elif subcmd in ("info", "about"):
            name = sub_args
            if not name:
                self.console.print("[yellow]Usage: /skill info <skill_name>[/yellow]")
                return
            skill = self.skill_manager.get_skill(name)
            if not skill:
                self.console.print(f"[red]Skill '{name}' not found.[/red]")
                return
            self.console.print(f"[bold]#EA580C]{skill.name}[/bold] v{skill.version}")
            self.console.print(f"  Description: {skill.description}")
            self.console.print(f"  Author: {skill.author}")
            self.console.print(f"  Source: {skill.source}")
            if skill.tags:
                self.console.print(f"  Tags: {', '.join(skill.tags)}")
            self.console.print("[bold]Commands:[/bold]")
            for c in skill.commands:
                self.console.print(f"  /{c.name} - {c.description}")

        elif subcmd == "run":
            # /skill run <skill_name> [command_name] [args]
            run_parts = sub_args.split(None, 2)
            if not run_parts:
                self.console.print("[yellow]Usage: /skill run <skill_name> [command] [args][/yellow]")
                return
            skill_name = run_parts[0]
            command_name = run_parts[1] if len(run_parts) > 1 else "run"
            cmd_args = run_parts[2] if len(run_parts) > 2 else ""
            context = {
                "messages": self.memory.messages[-10:] if hasattr(self, 'memory') and self.memory else [],
                "config": self.engine.config if hasattr(self, 'engine') else {},
            }
            try:
                result = self.skill_manager.run_skill(skill_name, command_name, cmd_args, context)
                self.console.print(f"[green][Skill: {skill_name}][/green] {result}")
            except Exception as e:
                self.console.print(f"[red]Skill error: {e}[/red]")

        elif subcmd in ("install", "add"):
            name = sub_args
            if not name:
                self.console.print("[yellow]Usage: /skill install <skill_name>[/yellow]")
                return
            if not self.marketplace:
                self.console.print("[red]Marketplace not available (missing httpx or urllib).[/red]")
                return
            self.console.print(f"Installing skill [bold]{name}[/bold] from marketplace...")
            result = self.marketplace.install(name, self.skill_manager)
            if result:
                self.console.print(f"[green]Skill '{result}' installed successfully![/green]")
            else:
                self.console.print(f"[red]Failed to install skill '{name}'. Check the name and try again.[/red]")

        elif subcmd in ("uninstall", "remove", "rm"):
            name = sub_args
            if not name:
                self.console.print("[yellow]Usage: /skill uninstall <skill_name>[/yellow]")
                return
            try:
                if self.skill_manager.uninstall_skill(name):
                    self.console.print(f"[green]Skill '{name}' uninstalled.[/green]")
                else:
                    self.console.print(f"[red]Skill '{name}' not found.[/red]")
            except ValueError as e:
                self.console.print(f"[red]{e}[/red]")

        elif subcmd in ("marketplace", "store", "browse"):
            if not self.marketplace:
                self.console.print("[red]Marketplace not available.[/red]")
                return
            self.console.print("[dim]Fetching marketplace listings...[/dim]")
            try:
                listings = self.marketplace.list_available(self.skill_manager)
                if not listings:
                    # Try cache
                    listings = self.skill_manager.load_marketplace_cache()
                if not listings:
                    self.console.print("[yellow]No marketplace skills found. Check your internet connection.[/yellow]")
                    return
                from rich.table import Table
                table = Table(title="Skill Marketplace", show_lines=False)
                table.add_column("Name", style="#EA580C")
                table.add_column("Version", style="dim")
                table.add_column("Description")
                table.add_column("Tags", style="cyan")
                table.add_column("Status", style="green")
                for s in listings[:30]:
                    name = s.get("name", "?")
                    ver = s.get("version", "?")
                    desc = s.get("description", "")[:50]
                    tags = ", ".join(s.get("tags", []))[:30]
                    status = "[green]installed[/green]" if s.get("installed") else ""
                    table.add_row(name, ver, desc, tags, status)
                self.console.print(table)
                self.console.print("[dim]Install with: /skill install <name>[/dim]")
            except Exception as e:
                self.console.print(f"[red]Marketplace error: {e}[/red]")

        elif subcmd in ("search", "find"):
            if not sub_args:
                self.console.print("[yellow]Usage: /skill search <query>[/yellow]")
                return
            if not self.marketplace:
                self.console.print("[red]Marketplace not available.[/red]")
                return
            results = self.marketplace.search(sub_args)
            if not results:
                self.console.print(f"[yellow]No marketplace skills matching '{sub_args}'.[/yellow]")
                return
            for s in results[:10]:
                name = s.get("name", "?")
                desc = s.get("description", "")
                self.console.print(f"  [#EA580C]{name}[/] - {desc}")
            self.console.print("[dim]Install with: /skill install <name>[/dim]")

        elif subcmd == "create":
            if not sub_args:
                self.console.print("[yellow]Usage: /skill create <description of what the skill should do>[/yellow]")
                self.console.print("[dim]Example: /skill create a skill that generates random passwords[/dim]")
                return
            self._create_ai_skill(sub_args)

        else:
            self.console.print(f"[red]Unknown skill subcommand: {subcmd}[/red]")
            self.console.print("[dim]Available: list, info, run, install, uninstall, marketplace, search, create[/dim]")

    def _create_ai_skill(self, description: str) -> None:
        """Create a new skill using AI generation."""
        from engine.skills import SkillManager as SM
        self.console.print(f"[#EA580C]Generating skill from description...[/]")
        prompt = SM.build_create_prompt(description)
        # Inject the prompt as a system message and generate
        messages = [{"role": "system", "content": prompt}]
        try:
            response = ""
            for chunk in self.engine.generate("Create the skill as described.", system_override=prompt):
                response += chunk
            manifest, skill_code = SM.parse_create_response(response)
            skill = self.skill_manager.create_custom_skill("ai_skill", manifest, skill_code)
            self.console.print(f"[green]AI-created skill '{skill.name}' saved![/green]")
            self.console.print(f"  Commands: {', '.join('/' + c.name for c in skill.commands)}")
            self.console.print("[dim]Run with: /skill run <name>[/dim]")
        except Exception as e:
            self.console.print(f"[red]Failed to create skill: {e}[/red]")
            self.console.print("[dim]The AI may not have generated a valid skill. Try again with a clearer description.[/dim]")


    def generate_response(self, user_input: str) -> str:
        """
        Generate response with streaming

        Args:
            user_input: User's input text

        Returns:
            Complete response
        """
        # RML: capture implicit feedback from user's follow-up
        if self.rml.enabled and self._last_response_text:
            implicit = self.rml.record_implicit(user_input)
            if implicit == "positive":
                self.console.print("[dim](RML: positive signal detected)[/dim]")
            elif implicit == "negative":
                self.console.print("[dim](RML: negative signal detected)[/dim]")

        # Add user message to memory
        self.memory.add_message("user", user_input)

        # Get context from RAG if enabled
        rag_context = ""
        if self.rag_enabled and self.rag:
            rag_context = self.rag.get_context(user_input)

        history_refs = extract_local_refs_from_messages(
            self.memory.get_recent_context(max_turns=20)
        )
        if extract_local_refs(user_input) or history_refs:
            self._last_local_targets = resolve_fix_targets(
                user_input,
                self._last_local_targets,
                extra_refs=history_refs,
            )

        local_context, local_notices = build_local_file_context(
            user_input, self.engine.config
        )
        if self._pending_local_context:
            local_context = "\n\n".join(
                part for part in (self._pending_local_context, local_context) if part
            )
            self._pending_local_context = ""

        rewrite_approved = False
        rewrite_paths: List[str] = []
        fix_context = ""
        fix_notices: List[str] = []
        fix_targets: List[Path] = list(self._last_local_targets or [])
        confirm_only = user_confirms_rewrite(user_input)
        use_bitacora = self._bitacora_enabled(user_input, confirm_only=confirm_only)
        on_progress: ProgressCallback = self._fix_progress
        on_stream: StreamCallback = self._fix_stream
        bitacora_panel = False
        bitacora_cm = None
        if use_bitacora:
            bitacora_cm = TerminalBitacoraSession(self.console)
            bitacora = bitacora_cm.__enter__()
            on_progress = bitacora.as_progress_callback()
            on_stream = (
                bitacora_cm.stream_callback()
                if _fix_cfg(self.engine.config).get("stream_rewrite", False)
                else (lambda _c: None)
            )
            bitacora_panel = True

        try:
            if user_wants_fix(user_input) or confirm_only:
                on_progress("Fix/rewrite requested — starting workflow…")

                if confirm_only and self._pending_rewrite_paths:
                    rewrite_approved = True
                    rewrite_paths = list(self._pending_rewrite_paths)
                    fix_context = ""
                    fix_notices = [f"Continuing rewrite for {len(rewrite_paths)} file(s)…"]
                    on_progress(fix_notices[0])
                    fix_targets = list(self._last_local_targets)
                else:
                    def _confirm_apply(summary: str) -> bool:
                        self.console.print(
                            Panel(REWRITE_WARNING, title="Full-file rewrite", border_style="yellow")
                        )
                        return Prompt.ask(summary, choices=["y", "n"], default="n") == "y"

                    fix_context, fix_notices, fix_targets, rewrite_approved, rewrite_paths = (
                        handle_chat_fix(
                            user_input,
                            self.engine.config,
                            last_targets=self._last_local_targets,
                            extra_refs=history_refs,
                            confirm_apply=_confirm_apply,
                            on_progress=on_progress,
                        )
                    )
                    if fix_targets:
                        self._last_local_targets = fix_targets
                    if rewrite_paths:
                        self._pending_rewrite_paths = rewrite_paths

                if not bitacora_panel:
                    for note in local_notices + fix_notices:
                        style = (
                            "green"
                            if note.startswith(("Loaded", "Scanned", "Auto-fix", "Wrote"))
                            else "dim"
                        )
                        if note.startswith("Say "):
                            style = "yellow"
                        self.console.print(f"[{style}]{note}[/{style}]")
                else:
                    for note in local_notices + fix_notices:
                        on_progress(note)

            # Confirm-only: skip chat generation and run dedicated rewrite immediately.
            if confirm_only and rewrite_approved and rewrite_paths:
                on_progress("Running dedicated full-file rewrite…")
                patch_notices = run_dedicated_rewrite(
                    rewrite_paths,
                    self.engine,
                    self.prompt_manager,
                    self.engine.config,
                    targets=self._last_local_targets,
                    on_progress=on_progress,
                    on_stream=on_stream,
                )
                if on_stream is not self._fix_stream:
                    self.console.print()
                if not bitacora_panel:
                    for note in patch_notices:
                        style = "green" if note.startswith("Wrote") else "yellow"
                        self.console.print(f"[bold {style}]{note}[/bold {style}]")
                if any(n.startswith("Wrote") for n in patch_notices):
                    self._pending_rewrite_paths = []
                self.memory.add_message("assistant", "(rewrite run — see bitácora above)")
                return "(rewrite run)"

            if fix_context and not confirm_only:
                on_progress(
                    "Fix mode: reasoning and patches appear in the assistant reply below"
                )
                on_progress("Generating chat response (fix mode)…")

            # Prepare messages (fewer turns when RAG is on — large system block)
            max_turns = 10
            if self.rag_enabled and self.rag:
                max_turns = self.rag.max_history_turns
            messages = self.memory.get_recent_context(max_turns=max_turns)

            system_prompt = self.prompt_manager.get_prompt()
            if rewrite_approved and active_prompt_is_security_audit(self.engine.config):
                self.console.print(
                    "[dim]Note: security_audit mode reports findings only — "
                    "using security_fix prompt for this rewrite.[/dim]"
                )
                system_prompt = build_fix_system_prompt(
                    self.prompt_manager,
                    system_prompt,
                    user_input,
                    rewrite_approved=rewrite_approved,
                )

            # RML: inject learned preference hints into the system prompt
            if self.rml.enabled:
                rml_hints = self.rml.get_learned_hints_text()
                if rml_hints:
                    system_prompt = system_prompt + "\n" + rml_hints

            # Cross-session memory: inject remembered facts into the system prompt
            if self.cross_memory.enabled:
                memory_block = self.cross_memory.get_prompt_block()
                if memory_block:
                    system_prompt = system_prompt + "\n" + memory_block

            extra_context = "\n\n".join(
                part for part in (rag_context, local_context, fix_context) if part
            )
            if extra_context:
                system_prompt = self.prompt_manager.format_with_context(extra_context)

            # Thinking mode: inject step-by-step reasoning prompt (after format_with_context)
            if self.reflector.should_think():
                system_prompt = system_prompt + "\n\n" + self.reflector.thinking_prompt

            reserve = self.engine.config.get("context", {}).get(
                "reserve_tokens",
                self.engine.config.get("generation", {}).get("max_tokens", 2048),
            )
            messages, system_prompt, prompt_tokens = fit_chat_context(
                self.engine, messages, system_prompt, reserve_tokens=reserve
            )
            if prompt_tokens > 0:
                logger.debug("Prompt size after trim: %d tokens", prompt_tokens)

            prompt = self.engine.format_chat_prompt(messages, system_prompt)

            # RML: apply parameter adjustments (temperature, top_p, repeat_penalty)
            gen_config = self.engine.config.get("generation", {})
            if self.rml.enabled:
                gen_config = self.rml.adjusted_generation_params(gen_config)

            response_text = ""
            start_time = time.time()
            token_count = 0

            thinking_mode = self.reflector.should_think()

            _spinner = ThinkingSpinner()
            _spinner.start(self.console, label="Thinking")

            # Thinking-mode streaming: detect think tags in real-time
            # Tags supported: ««««/»»»» (Qwen-style) and <thinking>/</thinking>
            _in_think = False
            _display_buf = ""
            _open_tags = ("««««", "<thinking>")
            _close_tags = ("»»»»", "</thinking>")
            _think_header_printed = False

            # Partial tag prefixes to detect when tags are split across chunks
            _partial_open = ("«««", "««", "«", "<thinking", "<thinkin", "<thinki", "<think", "<thin", "<thi", "<th", "<t", "<")
            _partial_close = ("»»»", "»»", "»", "</thinking", "</thinkin", "</thinki", "</think", "</thin", "</thi", "</th", "</t", "</")
            _max_tag_len = 11  # length of "</thinking>" — the longest tag

            # Style applied to the model's answer (non-thinking) output as it
            # streams. Grey instead of the default terminal foreground so the
            # answer reads as quieter prose after the bright-yellow thinking
            # block; users can still copy/paste it normally.
            _answer_style = "grey70"

            def _safe_print(buf: str, in_think: bool) -> str:
                """Print as much of buf as safe, keeping possible partial tags.
                Returns the unprinted suffix (potential partial tag)."""
                if not buf:
                    return buf
                partials = _partial_close if in_think else _partial_open
                for i in range(len(buf) - 1, max(len(buf) - _max_tag_len - 1, -1), -1):
                    suffix = buf[i:]
                    for p in partials:
                        if suffix == p or suffix.startswith(p):
                            if i > 0:
                                style = "yellow italic" if in_think else _answer_style
                                self.console.print(buf[:i], end="", style=style)
                            return buf[i:]
                style = "yellow italic" if in_think else _answer_style
                self.console.print(buf, end="", style=style)
                return ""

            try:
                _first_chunk = True
                for chunk in self.engine.generate(
                    prompt,
                    stream=True,
                    temperature=gen_config.get("temperature"),
                    top_p=gen_config.get("top_p"),
                    repeat_penalty=gen_config.get("repeat_penalty"),
                ):
                    response_text += chunk
                    token_count += 1
                    if _first_chunk:
                        _first_chunk = False
                        _spinner.stop()
                        self.console.print("\n[bold #EA580C]Assistant[/bold #EA580C] ", end="")

                    if not thinking_mode:
                        # Normal streaming — no tag processing
                        self.console.print(chunk, end="", style=_answer_style)
                        continue

                    # Thinking-mode: process buffer for think-tag display
                    _display_buf += chunk
                    while _display_buf:
                        if not _in_think:
                            # Look for opening tags «««« or <thinking>
                            earliest = -1
                            tag_len = 0
                            for tag in _open_tags:
                                idx = _display_buf.find(tag)
                                if idx != -1 and (earliest == -1 or idx < earliest):
                                    earliest = idx
                                    tag_len = len(tag)

                            if earliest == -1:
                                # No complete tag found — print safely, keep partial tags
                                old_len = len(_display_buf)
                                _display_buf = _safe_print(_display_buf, False)
                                if len(_display_buf) == old_len:
                                    break  # nothing was printed, wait for more data
                            else:
                                # Print content before the opening tag (if any)
                                if earliest > 0:
                                    self.console.print(
                                        _display_buf[:earliest], end="", style=_answer_style
                                    )
                                # Render "<Thinking>" header in place of the raw tag.
                                # Angle brackets are rendered in black so they
                                # blend into a dark terminal background; the word
                                # itself stays highlighted.
                                if not _think_header_printed:
                                    self.console.print(
                                        "\n[black]<[/black][bold yellow]Thinking[/bold yellow][black]>[/black] ",
                                        end="",
                                    )
                                    _think_header_printed = True
                                # Skip the opening tag itself
                                _display_buf = _display_buf[earliest + tag_len:]
                                _in_think = True
                        else:
                            # Inside a think tag — look for closing »»»» or </thinking>
                            earliest = -1
                            tag_len = 0
                            for tag in _close_tags:
                                idx = _display_buf.find(tag)
                                if idx != -1 and (earliest == -1 or idx < earliest):
                                    earliest = idx
                                    tag_len = len(tag)

                            if earliest == -1:
                                # No complete closing tag found — print safely, keep partial tags
                                old_len = len(_display_buf)
                                _display_buf = _safe_print(_display_buf, True)
                                if len(_display_buf) == old_len:
                                    break  # nothing was printed, wait for more data
                            else:
                                # Print reasoning content before the closing tag (colored)
                                if earliest > 0:
                                    self.console.print(
                                        _display_buf[:earliest], end="", style="#F97316 italic"
                                    )
                                # Skip the closing tag
                                _display_buf = _display_buf[earliest + tag_len:]
                                _in_think = False
                                # Visual separator between reasoning and answer
                                self.console.print()

                    # Flush any remaining display buffer
                    if _display_buf:
                        style = "yellow italic" if _in_think else _answer_style
                        self.console.print(_display_buf, end="", style=style)
                        _display_buf = ""
                self.console.print()

                elapsed = time.time() - start_time
                tokens_per_sec = token_count / elapsed if elapsed > 0 else 0

                # Response timing bar
                timing_bar = "─" * min(int(tokens_per_sec), 40)
                t_color = "#EA580C" if tokens_per_sec < 5 else ("yellow" if tokens_per_sec < 15 else "green")
                self.console.print()
                self.console.print(
                    f"[dim]Generated {token_count} tokens in {elapsed:.1f}s[/dim] "
                    f"[{t_color}]{tokens_per_sec:.1f} tok/s[/{t_color}] [{t_color}]{timing_bar}[/{t_color}]",
                    highlight=False,
                )
                self.console.print()

            except KeyboardInterrupt:
                _spinner.stop()
                self._last_ctrl_c_time = time.time()
                self.console.print("\n\n[yellow]Generation interrupted[/yellow]\n")
                # RML: record interrupt as negative signal (usually = too verbose / off-track)
                if self.rml.enabled:
                    self.rml.record_interrupt()
                self._last_response_text = response_text
                self.memory.add_message("assistant", response_text)
                return response_text
            except Exception as e:
                _spinner.stop()
                self.console.print(f"\n[red]Error: {e}[/red]\n")
                return ""


            if self.reflector.should_reflect() and response_text:
                self.console.print("[#EA580C]Applying self-reflection...[/#EA580C]")
                response_text = self.reflector.reflect(
                    self.engine,
                    user_input,
                    response_text,
                    stream=False,
                )
                self.console.print("\n[bold green]Improved Response:[/bold green]")
                self.console.print(response_text)
                self.console.print()

            patch_notices: List[str] = []
            if user_wants_fix(user_input):
                on_progress("Checking assistant reply for MYTHOS_PATCH blocks…")
                patch_notices = apply_patches_with_prompt(
                    response_text,
                    self.engine.config,
                    message=user_input,
                    rewrite_approved=rewrite_approved,
                    on_progress=on_progress,
                )

            needs_dedicated = user_wants_fix(user_input) and not any(
                n.startswith("Wrote") for n in patch_notices
            )
            if needs_dedicated:
                if not rewrite_approved:
                    self.console.print(
                        "[yellow]Chat reply had no usable MYTHOS_PATCH "
                        "(audit-style markdown is OK).[/yellow]"
                    )
                    rewrite_approved = (
                        Prompt.ask(
                            "Run dedicated full-file rewrite now?",
                            choices=["y", "n"],
                            default="y",
                        )
                        == "y"
                    )
                if rewrite_approved:
                    on_progress("Running dedicated full-file rewrite…")
                    limit_one = "one" in user_input.lower()
                    targets_for_rewrite = fix_targets or self._last_local_targets
                    paths_for_rewrite = rewrite_paths or resolve_rewrite_file_paths(
                        targets_for_rewrite, self.engine.config
                    )
                    retry_notes = run_dedicated_rewrite(
                        paths_for_rewrite,
                        self.engine,
                        self.prompt_manager,
                        self.engine.config,
                        targets=targets_for_rewrite,
                        limit_one=limit_one,
                        on_progress=on_progress,
                        on_stream=on_stream,
                    )
                    if on_stream is not self._fix_stream:
                        self.console.print()
                    patch_notices.extend(retry_notes)
                    if any(n.startswith("Wrote") for n in retry_notes):
                        self._pending_rewrite_paths = []
                    elif rewrite_paths:
                        self._pending_rewrite_paths = rewrite_paths

            if not bitacora_panel:
                for note in patch_notices:
                    style = "green" if note.startswith("Wrote") else "yellow"
                    self.console.print(f"[bold {style}]{note}[/bold {style}]")
        finally:
            if bitacora_cm is not None:
                bitacora_cm.__exit__(None, None, None)

        # TTS: speak the response aloud when voice is enabled
        if self.voice.enabled and response_text:
            self.voice.speak(response_text)

        self.memory.add_message("assistant", response_text)

        # RML: track the last response for explicit feedback (/rml good|bad)
        self._last_response_text = response_text

        return response_text

    def run(self):
        """Main chat loop"""
        self.show_header()

        while self.running:
            try:
                # Get user input
                prompt_str = "\n[bold #F97316]You[/bold #F97316]"
                if self.voice.enabled and self.voice.is_recording:
                    prompt_str = "\n[bold red][REC][/bold red] [bold #F97316]You[/bold #F97316] (press Enter to stop)"


                # Status bar - model, mode, messages, context usage
                model_name = getattr(self.engine, 'model_name', getattr(self.engine, 'model_path', ''))
                model_str = str(model_name) if model_name else ''
                model_short = model_str.split("/")[-1].replace(".gguf","") if model_str else ""
                msg_count = len(self.memory.messages) if hasattr(self, 'memory') else 0
                mode_tag = "[#FB923C]cloud[/#FB923C]" if self.cloud_mode else "[#FB923C]local[/#FB923C]"
                # Context usage estimate
                ctx_budget = getattr(self.engine, 'config', {}).get('context', {}).get('reserve_tokens', 512)
                total_ctx = getattr(self.engine, 'config', {}).get('model', {}).get('n_ctx', 4096)
                avail = max(total_ctx - ctx_budget, 1)
                ctx_pct = min(int((msg_count * 60) / avail * 100), 100) if avail else 0
                ctx_color = "#EA580C" if ctx_pct > 80 else ("yellow" if ctx_pct > 50 else "green")
                ctx_bar_len = 10
                ctx_filled = int(ctx_pct / 100 * ctx_bar_len)
                ctx_bar = "█" * ctx_filled + "░" * (ctx_bar_len - ctx_filled)
                status_parts = ["[bold #EA580C]Mythos[/bold #EA580C]"]
                if model_short:
                    status_parts.append(f"[#FB923C]{model_short}[/#FB923C]")
                status_parts.append(f"{mode_tag}")
                status_parts.append(f"[dim]{msg_count} msgs[/dim]")
                status_parts.append(f"[{ctx_color}]{ctx_bar}[/{ctx_color}] [dim]{ctx_pct}%[/dim]")
                self.console.print(" | ".join(status_parts), highlight=False)
                user_input = Prompt.ask(prompt_str).strip()

                if not user_input:
                    # Empty input: if voice is recording, stop and transcribe
                    if self.voice.enabled and self.voice.is_recording:
                        self.console.print("[dim]Transcribing...[/dim]")
                        transcript = self.voice.stop_and_transcribe()
                        if transcript:
                            self.console.print(f"[green]> {transcript}[/green]")
                            self.generate_response(transcript)
                        else:
                            self.console.print("[yellow]No speech detected[/yellow]")
                    continue

                # Handle commands
                if user_input.startswith("/"):
                    self.running = self.handle_command(user_input)
                    continue

                # Multiline paste mode: lines starting with | are joined
                if user_input.startswith("|"):
                    user_input = user_input[1:].strip()
                    if user_input:
                        user_input = user_input + "\n"
                    while True:
                        try:
                            extra = Prompt.ask("[dim]...[/dim]").strip()
                            if not extra:
                                break
                            if extra.startswith("|"):
                                user_input += extra[1:].strip() + "\n"
                            else:
                                user_input += extra + "\n"
                        except (EOFError, KeyboardInterrupt):
                            break
                    user_input = user_input.strip()
                    if not user_input:
                        continue

            # Voice shortcut: "v" on empty-ish line triggers recording
                if self.voice.enabled and user_input.lower() == "v" and self.voice.is_available():
                    try:
                        self.voice.start_recording()
                        self.console.print("[bold red][REC][/bold red] Recording... press Enter to stop")
                        # Wait for Enter to stop recording
                        Prompt.ask("")
                        transcript = self.voice.stop_and_transcribe()
                        if transcript:
                            self.console.print(f"[green]> {transcript}[/green]")
                            self.generate_response(transcript)
                        else:
                            self.console.print("[yellow]No speech detected[/yellow]")
                    except RuntimeError as e:
                        self.console.print(f"[red]Voice error: {e}[/red]")
                    continue

                # Generate response
                self.generate_response(user_input)

            except KeyboardInterrupt:
                now = time.time()
                if now - self._last_ctrl_c_time < 1.0:
                    self.console.print("\n[#EA580C]Exiting...[/#EA580C]")
                    # Install a SIGINT handler that force-kills on the
                    # NEXT Ctrl+C, so destructors (__del__, atexit) can't
                    # produce "Exception ignored" spam if the user mashes
                    # Ctrl+C while the model is being freed.
                    signal.signal(signal.SIGINT, lambda s, f: os._exit(0))
                    self.running = False
                    break
                self._last_ctrl_c_time = now
                self.console.print("\n[yellow]Press Ctrl+C again to exit[/yellow]")
                continue
            except EOFError:
                break
            except Exception as e:
                logger.error(f"Error in chat loop: {e}", exc_info=True)
                self.console.print(f"\n[bold red]Error: {e}[/bold red]\n")

        # Save conversation on exit
        if self.memory.messages:
            save = Prompt.ask("Save conversation before exit?", choices=["y", "n"], default="y")
            if save == "y":
                filepath = self.memory.save()
                self.console.print(f"[green]Saved to: {filepath}[/green]")

        # Cross-session memory: extract facts from this session before exiting
        if self.cross_memory.enabled and self.memory.messages:
            try:
                msg_list = self.memory.get_recent_context(max_turns=50)
                n_extracted = self.cross_memory.extract_facts_from_messages(
                    msg_list, engine=self.engine
                )
                if n_extracted > 0:
                    self.console.print(
                        f"[green]Cross-Session Memory: learned {n_extracted} new fact(s) from this session[/green]"
                    )
            except Exception as mem_err:
                logger.warning(f"Cross-session memory extraction failed on exit: {mem_err}")

        # Session Summaries: auto-generate a digest on exit
        if self.session_summaries.enabled and self.session_summaries.auto_on_exit and self.memory.messages:
            try:
                msg_list = self.memory.get_recent_context(max_turns=50)
                model_name = self.engine.config.get("model", {}).get("name", "")
                summary = self.session_summaries.generate_summary(
                    msg_list,
                    engine=self.engine,
                    session_start_time=getattr(self, "_session_start_time", None),
                    model_name=model_name,
                )
                if summary:
                    sid = self.session_summaries.save_summary(summary)
                    self.console.print(
                        f"[green]Session Summary saved (id: {sid})[/green]"
                    )
            except Exception as ss_err:
                logger.warning(f"Session summary auto-generation failed on exit: {ss_err}")

def run_terminal_ui(config_path: str = "config.yaml"):
    """
    Run the terminal UI

    Args:
        config_path: Path to configuration file
    """
    ui = TerminalUI(config_path)
    ui.run()
