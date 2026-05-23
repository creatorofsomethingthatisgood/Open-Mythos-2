"""
Fine-tuning Module - Train LoRA adapters on CPU

WARNING: Training on CPU is slow. This is provided as an optional educational feature.
For production use, consider using a cloud GPU service or a system with NVIDIA/AMD GPU support.
"""

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Check for optional dependencies
try:
    import torch
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False
    logger.warning("PyTorch not available")

try:
    from transformers import AutoModelForCausalLM, AutoTokenizer, TrainingArguments
    from peft import LoraConfig, get_peft_model, TaskType
    from datasets import load_dataset
    TRAINING_DEPS_AVAILABLE = True
except ImportError:
    TRAINING_DEPS_AVAILABLE = False
    logger.warning("Training dependencies not available")


class LoRAFineTuner:
    """Fine-tune models using LoRA on CPU"""
    
    def __init__(self, base_model: str = "Qwen/Qwen2.5-7B-Instruct"):
        """
        Initialize LoRAFineTuner
        
        Args:
            base_model: HuggingFace model ID
        """
        if not TORCH_AVAILABLE or not TRAINING_DEPS_AVAILABLE:
            raise RuntimeError(
                "Training dependencies not available. Install with:\n"
                "pip install torch transformers peft datasets accelerate"
            )
        
        self.base_model = base_model
        self.output_dir = Path("lora")
        self.output_dir.mkdir(exist_ok=True)
        
        logger.warning(
            "CPU training is very slow. Consider using a GPU or cloud service for production training."
        )
    
    def prepare_model(self):
        """
        Load and prepare model for LoRA fine-tuning
        
        Returns:
            Tuple of (model, tokenizer)
        """
        logger.info(f"Loading base model: {self.base_model}")
        logger.info("This may take several minutes...")
        
        # Load tokenizer
        tokenizer = AutoTokenizer.from_pretrained(self.base_model)
        
        # Load model in 8-bit mode for CPU (if bitsandbytes supports it)
        # Otherwise load in full precision
        try:
            model = AutoModelForCausalLM.from_pretrained(
                self.base_model,
                device_map="cpu",
                torch_dtype=torch.float32,
                low_cpu_mem_usage=True
            )
        except Exception as e:
            logger.error(f"Failed to load model: {e}")
            raise
        
        # Configure LoRA
        lora_config = LoraConfig(
            task_type=TaskType.CAUSAL_LM,
            r=16,  # LoRA rank
            lora_alpha=32,  # LoRA alpha
            lora_dropout=0.05,
            target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],  # Common for most models
            bias="none"
        )
        
        # Apply LoRA
        model = get_peft_model(model, lora_config)
        model.print_trainable_parameters()
        
        return model, tokenizer
    
    def train(
        self,
        dataset_path: Path,
        num_epochs: int = 1,
        batch_size: int = 1,
        learning_rate: float = 2e-4,
        max_steps: int = 100
    ):
        """
        Train LoRA adapter
        
        Args:
            dataset_path: Path to training dataset (JSONL)
            num_epochs: Number of training epochs
            batch_size: Training batch size
            learning_rate: Learning rate
            max_steps: Maximum training steps
        """
        logger.info("Starting fine-tuning...")
        logger.warning(f"Training on CPU with max_steps={max_steps}. This will take a while.")
        
        # Load model and tokenizer
        model, tokenizer = self.prepare_model()
        
        # Load dataset
        dataset = load_dataset('json', data_files=str(dataset_path), split='train')
        
        # Training arguments
        training_args = TrainingArguments(
            output_dir=str(self.output_dir / "checkpoints"),
            num_train_epochs=num_epochs,
            per_device_train_batch_size=batch_size,
            learning_rate=learning_rate,
            max_steps=max_steps,
            logging_steps=10,
            save_steps=50,
            save_total_limit=2,
            fp16=False,  # CPU doesn't support fp16
            logging_dir=str(self.output_dir / "logs"),
            report_to="none"
        )
        
        logger.info("Training configuration:")
        logger.info(f"  - Epochs: {num_epochs}")
        logger.info(f"  - Batch size: {batch_size}")
        logger.info(f"  - Learning rate: {learning_rate}")
        logger.info(f"  - Max steps: {max_steps}")
        
        # Note: Full training implementation would require a Trainer
        # This is a simplified placeholder
        
        logger.warning(
            "Full training implementation requires additional setup. "
            "This is a placeholder for educational purposes."
        )
        
        logger.info(
            "For production fine-tuning, consider:\n"
            "1. Using unsloth library for faster training\n"
            "2. Using a cloud GPU service (RunPod, Vast.ai, Google Colab)\n"
            "3. Training on a system with NVIDIA GPU support"
        )
        
        # Save LoRA adapter (placeholder)
        output_path = self.output_dir / "adapter"
        output_path.mkdir(exist_ok=True)
        
        logger.info(f"Would save adapter to: {output_path}")
        
        return output_path


def run_finetuning(
    dataset_path: Optional[Path] = None,
    base_model: str = "Qwen/Qwen2.5-7B-Instruct",
    max_steps: int = 100
):
    """
    Main fine-tuning function
    
    Args:
        dataset_path: Path to training data
        base_model: Base model to fine-tune
        max_steps: Maximum training steps
    """
    if dataset_path is None:
        logger.error("No dataset provided. Prepare data first with prepare_data.py")
        return
    
    if not dataset_path.exists():
        logger.error(f"Dataset not found: {dataset_path}")
        return
    
    trainer = LoRAFineTuner(base_model)
    trainer.train(dataset_path, max_steps=max_steps)
