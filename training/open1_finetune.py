"""
Open-1 Efficient Training - QLoRA fine-tuning for low-memory environments.
Optimized for 4-bit quantization and gradient checkpointing.
"""

import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

try:
    import torch
    from transformers import (
        AutoModelForCausalLM, AutoTokenizer, TrainingArguments, Trainer,
        DataCollatorForSeq2Seq, BitsAndBytesConfig
    )
    from peft import LoraConfig, get_peft_model, TaskType, prepare_model_for_kbit_training
    from datasets import load_dataset
    TRAINING_DEPS_AVAILABLE = True
except ImportError:
    TRAINING_DEPS_AVAILABLE = False


class Open1Trainer:
    """QLoRA fine-tuner optimized for Open-1 (low-memory)."""

    def __init__(
        self,
        base_model: str = "Qwen/Qwen2.5-Coder-3B-Instruct",
        output_dir: str = "lora_open1",
        lora_r: int = 16, # Lower rank for memory efficiency
        lora_alpha: int = 32,
        lora_dropout: float = 0.1,
        max_seq_length: int = 2048, # Capped context for low-memory training
    ):
        if not TRAINING_DEPS_AVAILABLE:
            raise RuntimeError("Install dependencies: pip install torch transformers peft datasets accelerate bitsandbytes")

        self.base_model = base_model
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        self.lora_r = lora_r
        self.lora_alpha = lora_alpha
        self.lora_dropout = lora_dropout
        self.max_seq_length = max_seq_length
        self.device = "cuda" if torch.cuda.is_available() else "cpu"

    def prepare_model(self):
        """Load model in 4-bit and apply LoRA."""
        logger.info(f"Loading base model in 4-bit: {self.base_model}")

        # 4-bit quantization config (The "Efficient" part)
        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_use_double_quant=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.float16 if self.device == "cuda" else torch.float32
        )

        tokenizer = AutoTokenizer.from_pretrained(self.base_model, trust_remote_code=True)
        tokenizer.pad_token = tokenizer.eos_token

        model = AutoModelForCausalLM.from_pretrained(
            self.base_model,
            quantization_config=bnb_config,
            device_map="auto" if self.device == "cuda" else None,
            trust_remote_code=True,
            low_cpu_mem_usage=True,
        )

        # Prepare for k-bit training
        model = prepare_model_for_kbit_training(model)

        lora_config = LoraConfig(
            r=self.lora_r,
            lora_alpha=self.lora_alpha,
            target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
            lora_dropout=self.lora_dropout,
            bias="none",
            task_type=TaskType.CAUSAL_LM
        )

        model = get_peft_model(model, lora_config)
        model.print_trainable_parameters()
        return model, tokenizer

    def train(self, dataset_path: Path):
        """Execute QLoRA training."""
        model, tokenizer = self.prepare_model()
        
        dataset = load_dataset("json", data_files=str(dataset_path), split="train")
        
        # Simple tokenization for CoT and elite coding
        def tokenize_func(examples):
            return tokenizer(
                examples["text"],
                truncation=True,
                max_length=self.max_seq_length,
                padding="max_length"
            )

        tokenized = dataset.map(tokenize_func, batched=True, remove_columns=dataset.column_names)

        args = TrainingArguments(
            output_dir=str(self.output_dir / "checkpoints"),
            per_device_train_batch_size=1,
            gradient_accumulation_steps=8,
            learning_rate=2e-4,
            fp16=True if self.device == "cuda" else False,
            logging_steps=10,
            num_train_epochs=3,
            gradient_checkpointing=True, # Crucial for low memory
            report_to="none",
            save_total_limit=1,
        )

        trainer = Trainer(
            model=model,
            args=args,
            train_dataset=tokenized,
            data_collator=DataCollatorForSeq2Seq(tokenizer, pad_to_multiple_of=8, return_tensors="pt"),
        )

        logger.info("Starting Open-1 training pass...")
        trainer.train()
        
        adapter_path = self.output_dir / "open1_adapter"
        model.save_pretrained(str(adapter_path))
        logger.info(f"Open-1 Adapter saved to: {adapter_path}")
        return adapter_path

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    # This is a template script; requires dataset.jsonl to run
    logger.info("Open-1 Trainer Initialized. Use train(dataset_path) to begin.")
