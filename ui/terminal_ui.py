"""
Terminal UI - Beautiful terminal interface using Rich library
"""

import logging
import time
from typing import Optional
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
            except:
                self.console.print("[yellow]RAG not available (optional)[/yellow]")
            
            # Benchmark suite
            self.benchmark = BenchmarkSuite(config_path)
            
        except Exception as e:
            self.console.print(f"[bold red]Error initializing engine: {e}[/bold red]")
            raise
        
        self.running = True
        
    def show_header(self):
        """Display welcome header"""
        # Detect which prompt mode is active
        current_prompt_file = self.engine.config.get('system', {}).get('prompt_file', 'prompts/default.txt')
        mode_name = Path(current_prompt_file).stem.replace('_', ' ').title()
        
        mode_emoji = {
            'Default': '🚀',
            'Coding': '💻',
            'Code Review': '🔍',
            'Debugging': '🐛',
            'Creative': '✨',
            'Analytical': '🧠',
            'Roleplay': '🎭'
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
                self.prompt_manager.set_prompt(args)
                self.console.print("[green]System prompt updated[/green]")
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
                
                if stats['total_chunks'] == 0:
                    self.console.print("[yellow]  No documents indexed. Add files to rag_docs/[/yellow]")
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
        
        # Prepare messages
        messages = self.memory.get_recent_context(max_turns=10)
        
        # Get system prompt
        system_prompt = self.prompt_manager.get_prompt()
        if rag_context:
            system_prompt = self.prompt_manager.format_with_context(rag_context)
        
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
