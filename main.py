#!/usr/bin/env python3
"""
Mythos Local - Main Entry Point

High-quality local language model with AMD GPU support via Vulkan.
"""

import argparse
import logging
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
  python main.py --mode chat                    # Start terminal chat
  python main.py --mode web                     # Start web interface
  python main.py --mode web --port 8080        # Web UI on custom port
  python main.py --mode benchmark               # Run benchmarks
  python main.py --mode download                # Download default model
  python main.py --mode rag-index               # Index RAG documents
  python main.py --config custom.yaml           # Use custom config
        """
    )
    
    parser.add_argument(
        '--mode',
        type=str,
        default='chat',
        choices=['chat', 'web', 'benchmark', 'download', 'rag-index', 'finetune'],
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
        print(f"  File size: {model_path.stat().st_size / (1024**3):.2f} GB")
        
    except Exception as e:
        logger.error(f"Download error: {e}", exc_info=True)
        sys.exit(1)


def mode_rag_index(config_path: str):
    """Index documents for RAG"""
    logger.info("Indexing RAG documents...")
    
    try:
        from engine.rag import RAGPipeline
        
        rag = RAGPipeline(config_path)
        
        print(f"\nIndexing documents from: {rag.docs_dir}")
        print("This may take a few minutes...\n")
        
        rag.index_directory()
        
        stats = rag.get_stats()
        print(f"\n✓ Indexing complete!")
        print(f"  Total chunks: {stats['total_chunks']}")
        print(f"  Chunk size: {stats['chunk_size']} tokens")
        
    except Exception as e:
        logger.error(f"RAG indexing error: {e}", exc_info=True)
        sys.exit(1)


def mode_finetune(config_path: str):
    """Run fine-tuning"""
    logger.info("Starting fine-tuning...")
    
    print("\n" + "=" * 70)
    print("MYTHOS LOCAL - FINE-TUNING")
    print("=" * 70)
    print("\nWARNING: Fine-tuning on CPU is very slow and resource-intensive.")
    print("This feature is provided for educational purposes.")
    print("\nFor production fine-tuning, consider:")
    print("  1. Using a cloud GPU service (RunPod, Vast.ai, Google Colab)")
    print("  2. Using unsloth library for faster training")
    print("  3. Training on a system with NVIDIA GPU support")
    print("\n" + "=" * 70 + "\n")
    
    response = input("Continue with CPU training? (yes/no): ")
    if response.lower() != 'yes':
        print("Fine-tuning cancelled.")
        return
    
    try:
        from training.prepare_data import DatasetPreparer
        from training.finetune import run_finetuning
        
        # Prepare data
        preparer = DatasetPreparer()
        
        print("\nPreparing training data...")
        dataset_path = preparer.download_openhermes(num_samples=100)
        
        print(f"\nDataset ready: {dataset_path}")
        print("Starting training with max_steps=100 (limited for demo)...\n")
        
        run_finetuning(dataset_path, max_steps=100)
        
    except Exception as e:
        logger.error(f"Fine-tuning error: {e}", exc_info=True)
        sys.exit(1)


def main():
    """Main entry point"""
    parser = setup_arg_parser()
    args = parser.parse_args()
    
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
        
        elif args.mode == 'web':
            mode_web(str(config_path), args.port, args.share)
        
        elif args.mode == 'benchmark':
            mode_benchmark(str(config_path), args.model)
        
        elif args.mode == 'download':
            mode_download(str(config_path))
        
        elif args.mode == 'rag-index':
            mode_rag_index(str(config_path))
        
        elif args.mode == 'finetune':
            mode_finetune(str(config_path))
        
    except KeyboardInterrupt:
        logger.info("\nInterrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
