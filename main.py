#!/usr/bin/env python3
"""
Mythos Local - Main Entry Point

High-quality local language model (Metal on macOS, Vulkan on Linux AMD).
"""

import argparse
import logging
import os
import signal
import sys
from pathlib import Path

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('mythos.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)


def _configure_runtime() -> None:
    """Project-local HF cache and quieter third-party logs before heavy imports."""
    project_root = Path(__file__).resolve().parent
    try:
        from engine.hf_cache import configure_hf_cache, quiet_hf_loggers
        configure_hf_cache(project_root)
        quiet_hf_loggers()
    except ImportError:
        pass


def setup_arg_parser() -> argparse.ArgumentParser:
    """
    Setup command line argument parser

    Returns:
    ArgumentParser instance
    """
    parser = argparse.ArgumentParser(
        description="Mythos Local - High-Quality Local Language Model",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py --mode chat                          # Start terminal chat
  python main.py --mode web                            # Start web interface
  python main.py --mode web --port 8080                # Web UI on custom port
  python main.py --mode benchmark                      # Run benchmarks
  python main.py --mode download                       # Download default model
  python main.py --mode rag-index                      # Index RAG documents
  python main.py --mode rag-index --path ~/src/myapp
  python main.py --mode rag-explore --path /opt/projects
  python main.py --mode finetune --train-data data.jsonl
  python main.py --mode finetune --train-data data.jsonl --epochs 3 --lr 1e-4
  python main.py --mode finetune --train-data data.jsonl --merge --gguf
"""
    )

    parser.add_argument(
        '--mode',
        type=str,
        default='chat',
        choices=['chat', 'agent', 'operative', 'web', 'benchmark', 'download', 'rag-index', 'rag-explore', 'finetune'],
        help='Operation mode (default: chat)'
    )

    parser.add_argument(
        '--config',
        type=str,
        default='config.yaml',
        help='Path to configuration file (default: config.yaml)'
    )

    parser.add_argument(
        '--model',
        type=str,
        help='Override model path'
    )

    parser.add_argument(
        '--port',
        type=int,
        default=7860,
        help='Port for web interface (default: 7860)'
    )

    parser.add_argument(
        '--share',
        action='store_true',
        help='Create public Gradio link (web mode only)'
    )

    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable verbose logging'
    )

    parser.add_argument(
        '--path',
        type=str,
        default=None,
        help='Directory to index or explore for RAG (default: rag.docs_dir in config)'
    )

    # Operative mode arguments
    parser.add_argument(
        '--tier',
        type=str,
        default='elevated',
        choices=['safe', 'elevated', 'unleashed'],
        help='Operative safety tier (default: elevated)'
    )
    parser.add_argument(
        '--task',
        type=str,
        default=None,
        help='Task for agent/operative mode'
    )
    parser.add_argument(
        '--sandbox',
        type=str,
        default=None,
        help='Sandbox directory for agent/operative mode'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Dry run mode for agent/operative (preview actions without executing)'
    )

 # Training arguments
    parser.add_argument(
        '--train-data',
        type=str,
        default=None,
        help='Path to JSONL training dataset (finetune mode)'
    )
    parser.add_argument(
        '--base-model',
        type=str,
        default=None,
        help='Override base model for fine-tuning (finetune mode)'
    )
    parser.add_argument(
        '--epochs',
        type=int,
        default=1,
        help='Training epochs (finetune mode, default: 1)'
    )
    parser.add_argument(
        '--max-steps',
        type=int,
        default=-1,
        help='Max training steps, -1 = epoch-based (finetune mode)'
    )
    parser.add_argument(
        '--lr',
        type=float,
        default=2e-4,
        help='Learning rate (finetune mode, default: 2e-4)'
    )
    parser.add_argument(
        '--batch-size',
        type=int,
        default=1,
        help='Per-device batch size (finetune mode, default: 1)'
    )
    parser.add_argument(
        '--lora-r',
        type=int,
        default=16,
        help='LoRA rank (finetune mode, default: 16)'
    )
    parser.add_argument(
        '--lora-alpha',
        type=int,
        default=32,
        help='LoRA alpha (finetune mode, default: 32)'
    )
    parser.add_argument(
        '--grad-accum',
        type=int,
        default=8,
        help='Gradient accumulation steps (finetune mode, default: 8)'
    )
    parser.add_argument(
        '--yes', '-y',
        action='store_true',
        help='Skip confirmation prompt (finetune mode)'
    )
    parser.add_argument(
        '--merge',
        action='store_true',
        help='After training, merge LoRA adapter into base model'
    )
    parser.add_argument(
        '--gguf',
        action='store_true',
        help='After merging, convert to GGUF format'
    )

    return parser


def mode_chat(config_path: str):
    """Run terminal chat interface"""
    logger.info("Starting terminal chat interface...")

    try:
        from ui.terminal_ui import run_terminal_ui
        run_terminal_ui(config_path)
    except KeyboardInterrupt:
        logger.info("Chat interrupted by user")
    except Exception as e:
        logger.error(f"Chat error: {e}", exc_info=True)
        sys.exit(1)


def mode_agent(config_path: str, task: str = None, sandbox: str = None, dry_run: bool = False):
    """Run autonomous agent loop with tool access"""
    logger.info("Starting agent mode...")

    try:
        from engine.inference import InferenceEngine
        from engine.prompt_manager import PromptManager
        from engine.agent import AgentLoop

        engine = InferenceEngine(config_path)
        prompt_manager = PromptManager(config_path)

        sandbox_dir = Path(sandbox) if sandbox else Path.cwd()
        if not sandbox_dir.exists():
            logger.error(f"Sandbox directory does not exist: {sandbox_dir}")
            sys.exit(1)

        import yaml
        with open(config_path) as f:
            config = yaml.safe_load(f) or {}

        def confirm(desc: str) -> bool:
            if dry_run:
                print(f"  [DRY RUN] {desc}")
                return True
            answer = input(f"  Allow? {desc} [y/N]: ").strip().lower()
            return answer in ("y", "yes")

        agent = AgentLoop(
            engine=engine,
            prompt_manager=prompt_manager,
            config=config,
            sandbox_dir=sandbox_dir,
            confirm_fn=confirm,
            dry_run=dry_run,
            on_thinking=lambda msg: print(f"\n  [{msg}]"),
            on_tool_result=lambda r: print(f"  {r.to_message()}"),
        )

        if task:
            summary = agent.run(task)
            print(f"\nAgent complete: {summary}")
        else:
            print("\nMythos Agent - autonomous mode")
            print(f"Sandbox: {sandbox_dir}")
            print(f"Dry run: {dry_run}")
            print("Type a task or 'exit' to quit.\n")
            while True:
                try:
                    task = input("Agent> ").strip()
                except (EOFError, KeyboardInterrupt):
                    break
                if not task or task.lower() in ("exit", "quit", "q"):
                    break
                summary = agent.run(task)
                print(f"\nResult: {summary}\n")

    except KeyboardInterrupt:
        logger.info("Agent interrupted by user")
    except Exception as e:
        logger.error(f"Agent error: {e}", exc_info=True)
        sys.exit(1)


def mode_web(config_path: str, port: int, share: bool):
    """Run web interface"""
    logger.info(f"Starting web interface on port {port}...")

    try:
        from ui.web_ui import run_web_ui
        run_web_ui(config_path, share=share, port=port)
    except KeyboardInterrupt:
        logger.info("Web UI interrupted by user")
    except Exception as e:
        logger.error(f"Web UI error: {e}", exc_info=True)
        sys.exit(1)


def mode_benchmark(config_path: str, model_path: str = None):
    """Run benchmark suite"""
    logger.info("Starting benchmark suite...")

    try:
        from engine.inference import InferenceEngine
        from engine.benchmark import BenchmarkSuite

        # Initialize engine
        engine = InferenceEngine(config_path, model_path)
        benchmark = BenchmarkSuite(config_path)

        # Run benchmarks
        print("\n" + "=" * 70)
        print("MYTHOS LOCAL - BENCHMARK SUITE")
        print("=" * 70)
        print("\nThis will test reasoning, creativity, coding, and instruction following.")
        print("Estimated time: 5-10 minutes\n")

        input("Press Enter to start...")

        results = benchmark.run_full_benchmark(engine)

        # Display and save results
        print("\n" + benchmark.format_results_table(results))

        filepath = benchmark.save_results(results)
        print(f"\nResults saved to: {filepath}")

    except Exception as e:
        logger.error(f"Benchmark error: {e}", exc_info=True)
        sys.exit(1)


def mode_download(config_path: str):
    """Download default model"""
    logger.info("Downloading default model...")

    try:
        from engine.model_manager import ModelManager

        manager = ModelManager(config_path)
        model_path = manager.download_default()

        print(f"\n✓ Model downloaded successfully: {model_path}")
        print(f" File size: {model_path.stat().st_size / (1024**3):.2f} GB")

    except Exception as e:
        logger.error(f"Download error: {e}", exc_info=True)
        sys.exit(1)


def _format_bytes(num_bytes: int) -> str:
    if num_bytes < 1024:
        return f"{num_bytes} B"
    if num_bytes < 1024 ** 2:
        return f"{num_bytes / 1024:.1f} KB"
    if num_bytes < 1024 ** 3:
        return f"{num_bytes / (1024 ** 2):.1f} MB"
    return f"{num_bytes / (1024 ** 3):.2f} GB"


def _print_rag_explore(summary: dict) -> None:
    print("\n" + "=" * 70)
    print("RAG PATH EXPLORER")
    print("=" * 70)
    print(f"\nDirectory: {summary['directory']}")
    if not summary.get("exists"):
        print("\n⚠ Directory does not exist.")
        print(" Create it, pass another --path, or set rag.docs_dir in config.yaml")
        return

    print(f"Indexable files: {summary['file_count']}")
    print(f"Total size: {_format_bytes(summary['total_bytes'])}")
    print(f"\nExcluded dirs: {', '.join(summary['exclude_dirs'])}")
    print(f"Extensions: {', '.join(summary['supported_extensions'])}")

    if summary["by_extension"]:
        print("\nBy extension:")
        for ext, count in summary["by_extension"].items():
            print(f" {ext:12} {count}")
    else:
        print("\nNo indexable files found under this path.")

    if summary["sample_files"]:
        print("\nSample paths (first 25):")
        for rel in summary["sample_files"]:
            print(f" {rel}")
        remaining = summary["file_count"] - len(summary["sample_files"])
        if remaining > 0:
            print(f" ... and {remaining} more")


def mode_rag_explore(config_path: str, docs_path: str = None):
    """List files that would be indexed for RAG (no embedding)."""
    logger.info("Exploring RAG document path...")
    try:
        from engine.rag import RAGPipeline
        rag = RAGPipeline(config_path)
        summary = rag.explore_directory(docs_path)
        _print_rag_explore(summary)
        if not summary.get("exists"):
            sys.exit(1)
    except Exception as e:
        logger.error(f"RAG explore error: {e}", exc_info=True)
        sys.exit(1)


def mode_rag_index(config_path: str, docs_path: str = None):
    """Index documents for RAG"""
    logger.info("Indexing RAG documents...")

    try:
        from engine.rag import RAGPipeline

        rag = RAGPipeline(config_path)
        target = rag.resolve_docs_path(docs_path)
        print(f"\nIndexing documents from: {target}")
        print("Recursive scan (skips .git, node_modules, etc.). This may take several minutes...\n")

        file_count = sum(1 for _ in rag.iter_indexable_files(target))
        print(f" Files to index: {file_count}\n")
        if file_count == 0:
            print("⚠ No indexable files found.")
            print(" Run: python main.py --mode rag-explore --path <dir>")
            sys.exit(1)

        rag.index_directory(path=docs_path)

        stats = rag.get_stats()
        print(f"\n✓ Indexing complete!")
        print(f" Source directory: {stats['docs_directory']}")
        print(f" Persist directory: {stats['persist_directory']}")
        print(f" Total chunks: {stats['total_chunks']}")
        print(f" Chunk size: {stats['chunk_size']} words")
        if stats['total_chunks'] == 0:
            print("\n⚠ No chunks indexed — files may be empty or unsupported.")
            sys.exit(1)

    except Exception as e:
        logger.error(f"RAG indexing error: {e}", exc_info=True)
        sys.exit(1)


def mode_finetune(config_path: str, args):
    """Run fine-tuning with full CLI control"""
    logger.info("Starting fine-tuning...")

    # Load config for default model
    base_model = args.base_model
    if base_model is None:
        try:
            import yaml
            with open(config_path) as f:
                cfg = yaml.safe_load(f)
            base_model = cfg.get("model", {}).get("huggingface_id", "Qwen/Qwen2.5-7B-Instruct")
        except Exception:
            base_model = "Qwen/Qwen2.5-7B-Instruct"

    dataset_path = args.train_data

    # If no dataset provided, prepare one interactively
    if dataset_path is None:
        print("\n" + "=" * 70)
        print("MYTHOS LOCAL - FINE-TUNING")
        print("=" * 70)
        print("\nNo --train-data provided. Options:")
        print("  1. Prepare a sample dataset (OpenHermes subset)")
        print("  2. Cancel and prepare your own dataset")
        choice = input("\nChoose [1/2]: ").strip()
        if choice != "1":
            print("Cancelled. Prepare a JSONL dataset and run:")
            print(f"  python main.py --mode finetune --train-data your_data.jsonl")
            return

        try:
            from training.prepare_data import DatasetPreparer
            preparer = DatasetPreparer()
            try:
                num_samples = int(input("How many samples? [100]: ").strip() or "100")
            except EOFError:
                print("Non-interactive terminal, using 100 samples.")
                num_samples = 100
            dataset_path = preparer.download_openhermes(num_samples=num_samples)
            print(f"Dataset ready: {dataset_path}")
        except Exception as e:
            logger.error(f"Data preparation failed: {e}")
            return
    else:
        dataset_path = Path(dataset_path)
        if not dataset_path.exists():
            logger.error(f"Dataset not found: {dataset_path}")
            return

    # Show training config
    print("\n" + "=" * 70)
    print("TRAINING CONFIGURATION")
    print("=" * 70)
    print(f"  Base model:  {base_model}")
    print(f"  Dataset:     {dataset_path}")
    print(f"  Epochs:      {args.epochs}")
    print(f"  Max steps:   {args.max_steps if args.max_steps > 0 else 'epoch-based'}")
    print(f"  Batch size:  {args.batch_size}")
    print(f"  LoRA rank:   {args.lora_r}")
    print(f"  Learning rate: {args.lr}")
    print(f"  Merge after: {args.merge}")
    print(f"  GGUF after:  {args.gguf}")
    print("=" * 70)

    try:
        import torch
        device = "CUDA GPU" if torch.cuda.is_available() else "CPU (slow)"
        print(f"  Device:      {device}")
        if device.startswith("CPU"):
            print("\n  WARNING: No GPU detected. Training will be very slow.")
            print("  For faster training, use a machine with NVIDIA GPU.")
    except ImportError:
        print("  Device:      torch not installed — will fail at training time")

    if not args.yes:
        try:
            confirm = input("\nStart training? [y/N]: ").strip().lower()
            if confirm != "y":
                print("Cancelled.")
                return
        except EOFError:
            print("\nNon-interactive terminal. Use --yes or -y to skip confirmation.")
            return

    try:
        from training.finetune import run_finetuning

        adapter_path = run_finetuning(
            dataset_path=dataset_path,
            base_model=base_model,
            num_epochs=args.epochs,
            max_steps=args.max_steps,
            batch_size=args.batch_size,
            learning_rate=args.lr,
            lora_r=args.lora_r,
            lora_alpha=args.lora_alpha,
            gradient_accumulation_steps=args.grad_accum,
        )

        if adapter_path is None:
            logger.error("Training failed — no adapter produced.")
            return

        print(f"\n✓ Training complete! Adapter saved to: {adapter_path}")

        # Merge if requested
        if args.merge:
            from training.merge_lora import merge_lora_adapter

            merged_dir = str(Path(adapter_path).parent / "merged")
            print(f"\nMerging adapter into base model...")
            merged_path = merge_lora_adapter(
                base_model=base_model,
                adapter_path=str(adapter_path),
                output_path=merged_dir,
            )
            print(f"✓ Merged model saved to: {merged_path}")

            # GGUF if requested
            if args.gguf:
                from training.merge_lora import convert_to_gguf
                gguf_path = str(merged_path) + ".gguf"
                result = convert_to_gguf(str(merged_path), gguf_path)
                if result:
                    print(f"✓ GGUF model saved to: {result}")
                else:
                    print("GGUF conversion skipped — see logs for llama.cpp setup.")

        print("\nDone! To use the fine-tuned model, update config.yaml:")
        if args.merge:
            print(f"  model.name: {merged_dir}")
        else:
            print(f"  model.lora_path: {adapter_path}")

    except Exception as e:
        logger.error(f"Fine-tuning error: {e}", exc_info=True)
        sys.exit(1)


def main():
    """Main entry point"""
    parser = setup_arg_parser()
    args = parser.parse_args()
    _configure_runtime()

    # Set logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Verify config exists
    config_path = Path(args.config)
    if not config_path.exists():
        logger.error(f"Config file not found: {config_path}")
        logger.info("Using default config.yaml")
        config_path = Path("config.yaml")

    # Run appropriate mode
    try:
        if args.mode == 'chat':
            mode_chat(str(config_path))

        elif args.mode == 'agent':
            mode_agent(str(config_path),
                       task=getattr(args, 'task', None),
                       sandbox=getattr(args, 'sandbox', None),
                       dry_run=getattr(args, 'dry_run', False))

        elif args.mode == 'web':
            mode_web(str(config_path), args.port, args.share)

        elif args.mode == 'benchmark':
            mode_benchmark(str(config_path), args.model)

        elif args.mode == 'download':
            mode_download(str(config_path))

        elif args.mode == 'rag-index':
            mode_rag_index(str(config_path), args.path)

        elif args.mode == 'rag-explore':
            mode_rag_explore(str(config_path), args.path)

        elif args.mode == 'finetune':
            mode_finetune(str(config_path), args)

    except KeyboardInterrupt:
        # Force-kill on any further Ctrl+C so __del__/atexit cleanup
        # can't produce "Exception ignored" traceback spam.
        signal.signal(signal.SIGINT, lambda s, f: os._exit(0))
        logger.info("\nInterrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
