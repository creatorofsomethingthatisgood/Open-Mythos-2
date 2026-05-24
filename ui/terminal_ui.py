"""
Terminal UI - Beautiful terminal interface using Rich library
"""

import logging
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
from engine.chat_fix import (
    REWRITE_WARNING,
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

logger = logging.getLogger(__name__)


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
        
        # Initialize components
        self.console.print("[bold cyan]Initializing Mythos Local...[/bold cyan]")
        
        try:
            self.engine = InferenceEngine(config_path)
            self.prompt_manager = PromptManager(config_path)
            self.memory = ConversationMemory(config_path)
            self.reflector = SelfReflector(config_path)
            
            # RAG is optional
            self.rag = None
            try:
                self.rag = RAGPipeline(config_path)
                self.rag_enabled = False
                stats = self.rag.get_stats()
                self.console.print(
                    f"[green]RAG ready[/green] ({stats['total_chunks']} chunks indexed)"
                )
            except Exception as rag_err:
                logger.exception("RAG init failed")
                self.console.print(f"[yellow]RAG not available: {rag_err}[/yellow]")
                self.console.print(
                    "[dim]  Fix: python main.py --mode rag-index --path <dir> "
                    "(needs network once for the embedding model)[/dim]"
                )
            
            # Benchmark suite
            self.benchmark = BenchmarkSuite(config_path)
            
        except Exception as e:
            self.console.print(f"[bold red]Error initializing engine: {e}[/bold red]")
            raise
        
        self.running = True
        self._pending_local_context = ""
        self._last_local_targets: list = []
        self._pending_rewrite_paths: List[str] = []
        
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
        
        header = """
╔═══════════════════════════════════════════════════════════════╗
║                      MYTHOS LOCAL                             ║
║           High-Quality Local Language Model                   ║
╚═══════════════════════════════════════════════════════════════╝
        """
        self.console.print(header, style="bold cyan")
        self.console.print(f"Model: [green]{self.engine.model_path.name}[/green]")
        self.console.print(
            f"Context: [green]{self.engine.context_length:,}[/green] tokens"
        )
        self.console.print(f"Mode: [bold magenta]{emoji} {mode_name}[/bold magenta]")
        self.console.print(f"System Prompt: [yellow]{self.prompt_manager.get_prompt()[:70]}...[/yellow]")
        self.console.print("\nType [bold]/help[/bold] for commands, [bold]/quit[/bold] to exit\n")
    
    def show_help(self):
        """Display help information"""
        help_text = """
[bold cyan]Available Commands:[/bold cyan]

[yellow]/help[/yellow]              - Show this help message
[yellow]/clear[/yellow]             - Clear conversation history
[yellow]/save[/yellow]              - Save current conversation
[yellow]/load[/yellow]              - Load a saved conversation
[yellow]/system <prompt>[/yellow]  - Change system prompt
[yellow]/model <name>[/yellow]     - Switch model (if available)
[yellow]/temp <float>[/yellow]     - Change temperature (0.0-2.0)
[yellow]/reflect on|off[/yellow]   - Toggle self-reflection
[yellow]/rag on|off[/yellow]       - Toggle RAG (if available)
[yellow]/file <path>[/yellow]      - Load a local file or folder into context
[yellow]/fix <path>[/yellow]       - Auto-fix safe vulns (yaml, TLS, debug flags)
[yellow]/rewrite <path>[/yellow]   - Rewrite file(s) on disk (LLM + auto-write)
[yellow]/benchmark[/yellow]        - Run benchmark suite
[yellow]/config[/yellow]           - Show current configuration
[yellow]/export[/yellow]           - Export conversation as text
[yellow]/quit[/yellow]             - Exit the chat

[bold cyan]🔥 Enhanced Coding Modes:[/bold cyan]
[yellow]/system coding[/yellow]     - ELITE 5-pass code verification mode
[yellow]/system code_review[/yellow] - Systematic code review mode
[yellow]/system debugging[/yellow]   - Methodical debugging mode
[yellow]/system default[/yellow]    - Return to general purpose mode

[bold cyan]Other Modes:[/bold cyan]
[yellow]/system creative[/yellow]   - Creative writing & storytelling
[yellow]/system analytical[/yellow] - Deep analysis & reasoning
[yellow]/system roleplay[/yellow]   - Character roleplay mode
[yellow]/system security_audit[/yellow] - Codebase security review mode
[yellow]/system security_fix[/yellow]   - Default — find + fix (MYTHOS_PATCH)

[bold cyan]Local files & fixes in chat:[/bold cyan]
- Paste a path: [dim]/Users/you/project/app.py[/dim]
- Or: [dim]file:///Users/you/project/app.py[/dim]
- [yellow]/file ~/my-repo[/yellow] then ask about vulnerabilities
- [dim]fix the vulns in '/Users/you/project'[/dim] — scans, warns, asks to rewrite full files (git)
- [yellow]/rewrite '/path/to/file.py'[/yellow] — LLM writes complete file (MYTHOS_PATCH; confirm required)
- [yellow]/fix ~/my-repo[/yellow] — CLI line-level fixes only (separate from chat full-file rewrite)
- Default mode is [yellow]security_fix[/yellow] (writes via MYTHOS_PATCH). Use [yellow]/system security_audit[/yellow] for report-only.
- Best with [yellow]/temp 0.3[/yellow] for fixes

[bold cyan]Tips:[/bold cyan]
- Use Ctrl+C to interrupt generation
- Coding mode verifies code 5 times for correctness
- Self-reflection improves quality but takes longer
- Combine /system coding + /reflect on for best code quality
        """
        self.console.print(Panel(help_text, title="Help", border_style="cyan"))
    
    def show_config(self):
        """Display current configuration"""
        table = Table(title="Current Configuration")
        table.add_column("Setting", style="cyan")
        table.add_column("Value", style="green")
        
        table.add_row("Model", str(self.engine.model_path.name))
        table.add_row("Temperature", str(self.engine.config.get('generation', {}).get('temperature', 0.7)))
        table.add_row("Max Tokens", str(self.engine.config.get('generation', {}).get('max_tokens', 2048)))
        table.add_row("Self-Reflection", "On" if self.reflector.should_reflect() else "Off")
        table.add_row("RAG", "On" if self.rag_enabled and self.rag else "Off")
        
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
            
            self.console.print("[cyan]Saved conversations:[/cyan]")
            for i, conv in enumerate(conversations[:10], 1):
                self.console.print(f"  {i}. {conv.name}")
            
            choice = Prompt.ask("Enter number to load", default="1")
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(conversations):
                    self.memory.load(conversations[idx].name)
                    self.console.print(f"[green]Loaded conversation[/green]")
                else:
                    self.console.print("[red]Invalid selection[/red]")
            except:
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
                self.console.print(f"[cyan]Available templates: {', '.join(templates)}[/cyan]")
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
            except:
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
                    "[red]Usage: /file <path>[/red]  "
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
                    "[red]Usage: /fix <path>[/red]  "
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

                self.console.print(f"[cyan]Scanning {target}...[/cyan]")
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
                    "[red]Usage: /rewrite <file-or-folder>[/red]  "
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
                    f"[cyan]Rewriting {target} (full file write)...[/cyan]"
                )
                self.console.print("[dim]This may take a minute.[/dim]\n")
                response, notices = run_rewrite_files(
                    [target],
                    self.engine,
                    self.prompt_manager,
                    self.memory,
                    self.engine.config,
                    stream=False,
                )
                for note in notices:
                    style = "green" if note.startswith("Wrote") else "yellow"
                    self.console.print(f"[{style}]{note}[/{style}]")
                if response.strip():
                    self.console.print("\n[bold green]Assistant:[/bold green]")
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
                self.console.print(f"  Indexed chunks: {stats['total_chunks']}")
                self.console.print(f"  Index path: {stats.get('persist_directory', 'chroma_db')}")
                
                if stats['total_chunks'] == 0:
                    self.console.print(
                        "[yellow]  No documents indexed. Quit chat, run:[/yellow]"
                    )
                    self.console.print(
                        "[yellow]    python main.py --mode rag-index --path <dir>[/yellow]"
                    )
                    self.console.print(
                        "[yellow]  Then restart chat and /rag on again.[/yellow]"
                    )
            elif args.lower() == "off":
                self.rag_enabled = False
                self.console.print("[yellow]RAG disabled[/yellow]")
            else:
                self.console.print("[red]Use /rag on or /rag off[/red]")
        
        elif cmd == "/benchmark":
            self.console.print("[cyan]Running benchmark suite...[/cyan]")
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
            
            with open(filename, 'w') as f:
                f.write(text)
            self.console.print(f"[green]Exported to: {filename}[/green]")
        
        elif cmd == "/quit":
            self.console.print("[cyan]Goodbye![/cyan]")
            return False
        
        else:
            self.console.print(f"[red]Unknown command: {cmd}[/red]")
            self.console.print("Type [bold]/help[/bold] for available commands")
        
        return True
    
    def generate_response(self, user_input: str) -> str:
        """
        Generate response with streaming
        
        Args:
            user_input: User's input text
            
        Returns:
            Complete response
        """
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
        confirm_only = user_confirms_rewrite(user_input)

        if confirm_only and self._pending_rewrite_paths:
            rewrite_approved = True
            rewrite_paths = list(self._pending_rewrite_paths)
            fix_context = ""
            fix_notices = [f"Continuing rewrite for {len(rewrite_paths)} file(s)…"]
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
                )
            )
            if fix_targets:
                self._last_local_targets = fix_targets
            if rewrite_paths:
                self._pending_rewrite_paths = rewrite_paths

        for note in local_notices + fix_notices:
            style = "green" if note.startswith(("Loaded", "Scanned", "Auto-fix", "Wrote")) else "dim"
            if note.startswith("Say "):
                style = "yellow"
            self.console.print(f"[{style}]{note}[/{style}]")
        
        # Confirm-only: skip chat generation and run dedicated rewrite immediately.
        if confirm_only and rewrite_approved and rewrite_paths:
            self.console.print(
                "[cyan]Running dedicated full-file rewrite…[/cyan]"
            )
            patch_notices = run_dedicated_rewrite(
                rewrite_paths,
                self.engine,
                self.prompt_manager,
                self.engine.config,
                targets=self._last_local_targets,
            )
            for note in patch_notices:
                style = "green" if note.startswith("Wrote") else "yellow"
                self.console.print(f"[bold {style}]{note}[/bold {style}]")
            if any(n.startswith("Wrote") for n in patch_notices):
                self._pending_rewrite_paths = []
            self.memory.add_message("assistant", "(rewrite run — see messages above)")
            return "(rewrite run)"

        # Prepare messages (fewer turns when RAG is on — large system block)
        max_turns = 10
        if self.rag_enabled and self.rag:
            max_turns = self.rag.max_history_turns
        messages = self.memory.get_recent_context(max_turns=max_turns)

        # Get system prompt (audit mode reports only — switch to security_fix when rewriting)
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

        extra_context = "\n\n".join(
            part for part in (rag_context, local_context, fix_context) if part
        )
        if extra_context:
            system_prompt = self.prompt_manager.format_with_context(extra_context)

        reserve = self.engine.config.get("context", {}).get(
            "reserve_tokens",
            self.engine.config.get("generation", {}).get("max_tokens", 2048),
        )
        messages, system_prompt, prompt_tokens = fit_chat_context(
            self.engine, messages, system_prompt, reserve_tokens=reserve
        )
        if prompt_tokens > 0:
            logger.debug("Prompt size after trim: %d tokens", prompt_tokens)

        # Format prompt
        prompt = self.engine.format_chat_prompt(messages, system_prompt)
        
        # Generate with streaming
        response_text = ""
        start_time = time.time()
        token_count = 0
        
        self.console.print("\n[bold green]Assistant:[/bold green] ", end="")
        
        try:
            for chunk in self.engine.generate(prompt, stream=True):
                response_text += chunk
                token_count += 1
                self.console.print(chunk, end="")
            
            self.console.print()  # Newline after response
            
            # Calculate stats
            elapsed = time.time() - start_time
            tokens_per_sec = token_count / elapsed if elapsed > 0 else 0
            
            self.console.print(
                f"\n[dim]Generated {token_count} tokens in {elapsed:.1f}s "
                f"({tokens_per_sec:.1f} tok/s)[/dim]\n"
            )
            
        except KeyboardInterrupt:
            self.console.print("\n\n[yellow]Generation interrupted[/yellow]\n")
            return response_text
        
        # Apply self-reflection if enabled
        if self.reflector.should_reflect() and response_text:
            self.console.print("[cyan]Applying self-reflection...[/cyan]")
            response_text = self.reflector.reflect(
                self.engine,
                user_input,
                response_text,
                stream=False
            )
            self.console.print("\n[bold green]Improved Response:[/bold green]")
            self.console.print(response_text)
            self.console.print()
        
        patch_notices = apply_patches_with_prompt(
            response_text,
            self.engine.config,
            message=user_input,
            rewrite_approved=rewrite_approved,
        )

        needs_dedicated = user_wants_fix(user_input) and not any(
            n.startswith("Wrote") for n in patch_notices
        )
        if needs_dedicated:
            if not rewrite_approved:
                self.console.print(
                    "[yellow]Chat reply had no usable MYTHOS_PATCH (audit-style markdown is OK).[/yellow]"
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
                self.console.print(
                    "[cyan]Running dedicated full-file rewrite…[/cyan]"
                )
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
                )
                patch_notices.extend(retry_notes)
                if any(n.startswith("Wrote") for n in retry_notes):
                    self._pending_rewrite_paths = []
            elif rewrite_paths:
                self._pending_rewrite_paths = rewrite_paths

        for note in patch_notices:
            style = "green" if note.startswith("Wrote") else "yellow"
            self.console.print(f"[bold {style}]{note}[/bold {style}]")

        # Add to memory
        self.memory.add_message("assistant", response_text)
        
        return response_text
    
    def run(self):
        """Main chat loop"""
        self.show_header()
        
        while self.running:
            try:
                # Get user input
                user_input = Prompt.ask("\n[bold blue]You[/bold blue]").strip()
                
                if not user_input:
                    continue
                
                # Handle commands
                if user_input.startswith("/"):
                    self.running = self.handle_command(user_input)
                    continue
                
                # Generate response
                self.generate_response(user_input)
                
            except KeyboardInterrupt:
                self.console.print("\n[yellow]Use /quit to exit[/yellow]")
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


def run_terminal_ui(config_path: str = "config.yaml"):
    """
    Run the terminal UI
    
    Args:
        config_path: Path to configuration file
    """
    ui = TerminalUI(config_path)
    ui.run()
