"""
Fine-tuning Module - Train LoRA adapters on CPU or GPU

Supports real training via HuggingFace Trainer + PEFT LoRA.
Works on CPU (slow) and GPU (fast).
"""

import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Check for optional dependencies
try:
    import torch
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False

try:
    from transformers import (
        AutoModelForCausalLM, AutoTokenizer, TrainingArguments, Trainer,
        DataCollatorForSeq2Seq,
    )
    from peft import LoraConfig, get_peft_model, TaskType, PeftModel
    from datasets import load_dataset
    TRAINING_DEPS_AVAILABLE = True
except ImportError:
    TRAINING_DEPS_AVAILABLE = False


class LoRAFineTuner:
    """Fine-tune models using LoRA on CPU or GPU"""

    def __init__(
        self,
        base_model: str = "google/gemma-3-12b-it",
        output_dir: str = "lora",
        lora_r: int = 64,
        lora_alpha: int = 128,
        lora_dropout: float = 0.05,
        target_modules: Optional[list] = None,
        max_seq_length: int = 8192,
        use_rslora: bool = True,
        use_unsloth: bool = False,
        lr_scheduler_type: str = "cosine",
    ):
        if not TORCH_AVAILABLE or not TRAINING_DEPS_AVAILABLE:
            raise RuntimeError(
                "Training dependencies not available. Install with:\n"
                "  pip install torch transformers peft datasets accelerate"
            )

        self.base_model = base_model
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        self.lora_r = lora_r
        self.lora_alpha = lora_alpha
        self.lora_dropout = lora_dropout
        self.target_modules = target_modules or ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]
        self.max_seq_length = max_seq_length
        self.use_rslora = use_rslora
        self.use_unsloth = use_unsloth
        self.lr_scheduler_type = lr_scheduler_type

        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        if self.device == "cpu":
            logger.warning("No GPU detected — training on CPU will be very slow.")

    def prepare_model(self):
        """Load base model, apply LoRA, return (model, tokenizer)."""
        logger.info(f"Loading base model: {self.base_model}")

        if self.use_unsloth:
            try:
                from unsloth import FastLanguageModel
                model, tokenizer = FastLanguageModel.from_pretrained(
                    self.base_model,
                    max_seq_length=self.max_seq_length,
                    load_in_4bit=True,
                    dtype=None,
                )
                model = FastLanguageModel.get_peft_model(
                    model,
                    r=self.lora_r,
                    lora_alpha=self.lora_alpha,
                    lora_dropout=self.lora_dropout,
                    target_modules=self.target_modules,
                    use_rslora=self.use_rslora,
                    bias="none",
                )
                FastLanguageModel.for_training(model)
                model.print_trainable_parameters()
                return model, tokenizer
            except ImportError:
                logger.warning("unsloth not installed, falling back to standard loading")

        tokenizer = AutoTokenizer.from_pretrained(self.base_model, trust_remote_code=True)
        if tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token

        dtype = torch.float16 if self.device == "cuda" else torch.float32
        device_map = "auto" if self.device == "cuda" else "cpu"
        model = AutoModelForCausalLM.from_pretrained(
            self.base_model,
            device_map=device_map,
            torch_dtype=dtype,
            low_cpu_mem_usage=True,
            trust_remote_code=True,
        )

        lora_config = LoraConfig(
            task_type=TaskType.CAUSAL_LM,
            r=self.lora_r,
            lora_alpha=self.lora_alpha,
            lora_dropout=self.lora_dropout,
            target_modules=self.target_modules,
            bias="none",
            use_rslora=self.use_rslora,
        )

        model = get_peft_model(model, lora_config)
        model.enable_input_require_grads()
        model.print_trainable_parameters()

        # torch.compile for PyTorch 2.0+ (GPU only -- overhead rarely pays off on CPU)
        if self.device == "cuda":
            try:
                if hasattr(torch, "compile"):
                    model = torch.compile(model)
                    logger.info("torch.compile enabled")
            except Exception as e:
                logger.warning(f"torch.compile failed, skipping: {e}")

        return model, tokenizer

    def _tokenize(self, examples, tokenizer):
        """Tokenize a batch of chat-formatted examples, masking prompt tokens in labels."""
        texts = []
        prompt_texts = []
        for messages in examples["messages"]:
            prompt_messages = []
            for msg in messages:
                if msg["role"] == "assistant":
                    break
                prompt_messages.append(msg)

            prompt_texts.append(tokenizer.apply_chat_template(
                prompt_messages, tokenize=False, add_generation_prompt=True
            ))
            texts.append(tokenizer.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=False
            ))

        # Batch-encode prompts to compute lengths in one call
        prompt_encodings = tokenizer(
            prompt_texts, truncation=True, max_length=self.max_seq_length, padding=False
        )
        prompt_lens = [len(ids) for ids in prompt_encodings["input_ids"]]

        tokenized = tokenizer(
            texts,
            truncation=True,
            max_length=self.max_seq_length,
            padding=False,
        )

        # Mask prompt tokens with -100 so loss is only computed on assistant responses
        labels = []
        for ids, plen in zip(tokenized["input_ids"], prompt_lens):
            labels.append([-100] * plen + ids[plen:])
        tokenized["labels"] = labels
        return tokenized

    def train(
        self,
        dataset_path: Path,
        num_epochs: int = 1,
        batch_size: int = 1,
        gradient_accumulation_steps: int = 8,
        learning_rate: float = 2e-4,
        max_steps: int = -1,
        warmup_steps: int = 10,
        save_steps: int = 100,
        logging_steps: int = 10,
    ):
        """
        Train LoRA adapter — actually runs HuggingFace Trainer.

        Args:
            dataset_path: Path to JSONL training data (messages format).
            num_epochs: Training epochs.
            batch_size: Per-device batch size.
            gradient_accumulation_steps: Gradient accumulation for effective batch.
            learning_rate: Peak learning rate.
            max_steps: Max steps (-1 = epoch-based).
            warmup_steps: Warmup steps.
            save_steps: Save checkpoint every N steps.
            logging_steps: Log every N steps.

        Returns:
            Path to saved LoRA adapter.
        """
        logger.info("Starting LoRA fine-tuning...")

        # Load model
        model, tokenizer = self.prepare_model()

        # Load dataset
        dataset = load_dataset("json", data_files=str(dataset_path), split="train")
        logger.info(f"Dataset: {len(dataset)} examples")

        # Tokenize (parallel across CPU cores)
        num_proc = os.cpu_count() or 1
        tokenized = dataset.map(
            lambda x: self._tokenize(x, tokenizer),
            batched=True,
            remove_columns=dataset.column_names,
            num_proc=num_proc,
            desc="Tokenizing",
        )

        # Detect precision capabilities
        use_bf16 = (
            self.device == "cuda"
            and torch.cuda.is_available()
            and torch.cuda.get_device_capability()[0] >= 8
        )
        use_fp16 = self.device == "cuda" and not use_bf16
        is_cuda = self.device == "cuda"

        training_args = TrainingArguments(
            output_dir=str(self.output_dir / "checkpoints"),
            num_train_epochs=num_epochs,
            max_steps=max_steps,
            per_device_train_batch_size=batch_size,
            gradient_accumulation_steps=gradient_accumulation_steps,
            learning_rate=learning_rate,
            lr_scheduler_type=self.lr_scheduler_type,
            warmup_steps=warmup_steps,
            logging_steps=logging_steps,
            save_steps=save_steps,
            save_total_limit=2,
            fp16=use_fp16,
            bf16=use_bf16,
            gradient_checkpointing=True,
            gradient_checkpointing_kwargs={"use_reentrant": False},
            logging_dir=str(self.output_dir / "logs"),
            report_to="none",
            remove_unused_columns=False,
            dataloader_pin_memory=is_cuda,
            dataloader_num_workers=2 if is_cuda else 0,
            dataloader_prefetch_factor=2 if is_cuda else None,
        )

        logger.info("Training config:")
        logger.info(f"  Epochs: {num_epochs}, Max steps: {max_steps}")
        logger.info(f"  Batch: {batch_size} x {gradient_accumulation_steps} accum = {batch_size * gradient_accumulation_steps} effective")
        logger.info(f"  LR: {learning_rate}, Warmup: {warmup_steps}")
        logger.info(f"  Device: {self.device}, FP16: {use_fp16}, BF16: {use_bf16}")
        logger.info(f"  Gradient checkpointing: True")
        logger.info(f"  Tokenization workers: {num_proc}")

        # Run Trainer
        trainer = Trainer(
            model=model,
            args=training_args,
            train_dataset=tokenized,
            data_collator=DataCollatorForSeq2Seq(tokenizer, pad_to_multiple_of=8, return_tensors="pt"),
        )

        trainer.train()

        # Save adapter
        adapter_path = self.output_dir / "adapter"
        model.save_pretrained(str(adapter_path))
        tokenizer.save_pretrained(str(adapter_path))
        logger.info(f"LoRA adapter saved to: {adapter_path}")

        return adapter_path


def run_finetuning(
    dataset_path: Optional[Path] = None,
    base_model: str = "google/gemma-3-12b-it",
    output_dir: str = "lora",
    num_epochs: int = 2,
    max_steps: int = -1,
    batch_size: int = 2,
    learning_rate: float = 2e-4,
    lora_r: int = 64,
    lora_alpha: int = 128,
    gradient_accumulation_steps: int = 16,
    use_rslora: bool = True,
    use_unsloth: bool = False,
    max_seq_length: int = 8192,
):
    """Main fine-tuning entry point."""
    if dataset_path is None:
        logger.error("No dataset provided. Prepare data first with prepare_data.py")
        return None
    if not Path(dataset_path).exists():
        logger.error(f"Dataset not found: {dataset_path}")
        return None

    trainer = LoRAFineTuner(
        base_model=base_model,
        output_dir=output_dir,
        lora_r=lora_r,
        lora_alpha=lora_alpha,
        use_rslora=use_rslora,
        use_unsloth=use_unsloth,
        max_seq_length=max_seq_length,
    )
    return trainer.train(
        dataset_path=dataset_path,
        num_epochs=num_epochs,
        max_steps=max_steps,
        batch_size=batch_size,
        learning_rate=learning_rate,
        gradient_accumulation_steps=gradient_accumulation_steps,
    )
