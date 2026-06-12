#!/usr/bin/env python3
"""
Open-Mythos-2 Training Pipeline - LOW RAM EDITION

Tuned for 14GB RAM, CPU-only, AMD Ryzen (no CUDA/ROCm compute).
Survives on ~8.6GB free RAM + 4GB swap by using:
  - Qwen2.5-1.5B-Instruct (6GB float32) instead of 3B (12GB)
  - LoRA rank 4, only q_proj + v_proj (fewer trainable params)
  - Max seq length 512 (not 1024)
  - 100 samples, 1 epoch
  - Gradient checkpointing (trade compute for memory)
  - Adafactor optimizer (less memory than AdamW)
  - Memory guard: monitors RSS, aborts before OOM kill
  - gc.collect() + torch.cuda.empty_cache() after each step
  - No eval during training (saves memory)

Steps:
  1. Prepare dataset (reuse existing openhermes_prepared.jsonl)
  2. LoRA fine-tune
  3. Merge adapter
  4. Convert to GGUF (optional)
"""

import gc
import logging
import os
import resource
import sys
import time
from pathlib import Path

import psutil

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

# ── Config ──────────────────────────────────────────────────────────────
NUM_SAMPLES = 100               # small dataset = fast + low memory
BASE_MODEL = "Qwen/Qwen2.5-1.5B-Instruct"  # ~6GB float32, fits in 14GB RAM
LORA_R = 4                      # minimal rank (was 16)
LORA_ALPHA = 8
LORA_DROPOUT = 0.1
TARGET_MODULES = ["q_proj", "v_proj"]  # only 2 modules (was 7)
NUM_EPOCHS = 1
BATCH_SIZE = 1
GRAD_ACCUM = 4                  # effective batch = 4
LEARNING_RATE = 3e-4
MAX_SEQ_LENGTH = 512            # half of 1024
CONVERT_GGUF = False
QUANT = "q4_k_m"
USE_ADAFACTOR = True            # ~30% less optimizer memory than AdamW
GRADIENT_CHECKPOINTING = True
MEMORY_LIMIT_GB = 12.0          # abort if RSS exceeds this (leave 2GB for OS)


def check_memory() -> float:
    """Return current process RSS in GB."""
    proc = psutil.Process(os.getpid())
    return proc.memory_info().rss / 1e9


def memory_guard(limit_gb: float = MEMORY_LIMIT_GB):
    """Abort training before the OOM killer gets us."""
    rss = check_memory()
    if rss > limit_gb:
        logger.error(f"RSS {rss:.1f}GB exceeds {limit_gb:.1f}GB limit. Aborting to prevent OOM kill.")
        gc.collect()
        sys.exit(2)
    return rss


def aggressive_gc():
    """Force garbage collection between steps."""
    gc.collect()
    # torch.cuda.empty_cache is a no-op on CPU but harmless
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except ImportError:
        pass


# ── Step 1: Prepare data ────────────────────────────────────────────────
logger.info("=" * 60)
logger.info("STEP 1: Preparing dataset")
logger.info("=" * 60)

# Reuse existing prepared data if available
existing_data = Path("training_data/openhermes_prepared.jsonl")
if existing_data.exists():
    logger.info(f"Reusing existing dataset: {existing_data}")
    dataset_path = existing_data
else:
    from training.prepare_data import DatasetPreparer
    preparer = DatasetPreparer(output_dir="training_data")
    dataset_path = preparer.download_openhermes(num_samples=NUM_SAMPLES)

logger.info(f"Dataset ready: {dataset_path}")
rss = memory_guard()
logger.info(f"Memory after data prep: {rss:.1f} GB")

# ── Step 2: Fine-tune ──────────────────────────────────────────────────
logger.info("=" * 60)
logger.info("STEP 2: LoRA fine-tuning (CPU-safe config)")
logger.info("=" * 60)
logger.info(f"  Base model:  {BASE_MODEL}")
logger.info(f"  LoRA r={LORA_R}, alpha={LORA_ALPHA}, targets={TARGET_MODULES}")
logger.info(f"  Max seq len: {MAX_SEQ_LENGTH}")
logger.info(f"  Batch: {BATCH_SIZE} x {GRAD_ACCUM} accum = {BATCH_SIZE * GRAD_ACCUM} effective")
logger.info(f"  Samples: {NUM_SAMPLES}, epochs: {NUM_EPOCHS}")
logger.info(f"  Gradient checkpointing: {GRADIENT_CHECKPOINTING}")
logger.info(f"  Optimizer: {'Adafactor' if USE_ADAFACTOR else 'AdamW'}")
logger.info(f"  Memory limit: {MEMORY_LIMIT_GB} GB")

import torch
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    TrainingArguments,
    Trainer,
    DataCollatorForSeq2Seq,
    Adafactor,
)
from peft import LoraConfig, get_peft_model, TaskType
from datasets import load_dataset

# Load tokenizer
logger.info("Loading tokenizer...")
tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL, trust_remote_code=True)
if tokenizer.pad_token is None:
    tokenizer.pad_token = tokenizer.eos_token
rss = memory_guard()
logger.info(f"Memory after tokenizer: {rss:.1f} GB")

# Load model in float32 (CPU only - no 8-bit without bitsandbytes GPU)
logger.info("Loading model (this takes ~30s on CPU)...")
model = AutoModelForCausalLM.from_pretrained(
    BASE_MODEL,
    trust_remote_code=True,
    torch_dtype=torch.float32,
    low_cpu_mem_usage=True,
)
model.config.use_cache = False  # disable KV cache during training

rss = memory_guard()
logger.info(f"Memory after model load: {rss:.1f} GB")

# Apply LoRA
lora_config = LoraConfig(
    task_type=TaskType.CAUSAL_LM,
    r=LORA_R,
    lora_alpha=LORA_ALPHA,
    lora_dropout=LORA_DROPOUT,
    target_modules=TARGET_MODULES,
    bias="none",
)

model = get_peft_model(model, lora_config)
model.print_trainable_parameters()

if GRADIENT_CHECKPOINTING:
    model.gradient_checkpointing_enable()
    logger.info("Gradient checkpointing enabled (saves ~40% memory, 20% slower)")

rss = memory_guard()
logger.info(f"Memory after LoRA: {rss:.1f} GB")

# Load and tokenize dataset
logger.info("Loading and tokenizing dataset...")
raw_dataset = load_dataset("json", data_files=str(dataset_path), split="train")

# Subsample if larger than NUM_SAMPLES
if len(raw_dataset) > NUM_SAMPLES:
    raw_dataset = raw_dataset.select(range(NUM_SAMPLES))
    logger.info(f"Subsampled to {NUM_SAMPLES} examples")


def tokenize_function(examples):
    """Tokenize chat messages with truncation."""
    texts = []
    for messages in examples["messages"]:
        # Format as chat string using tokenizer's chat template
        text = tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=False
        )
        texts.append(text)

    tokenized = tokenizer(
        texts,
        truncation=True,
        max_length=MAX_SEQ_LENGTH,
        padding="max_length",
        return_tensors=None,
    )
    tokenized["labels"] = tokenized["input_ids"].copy()
    # Mask padding tokens in labels
    for i in range(len(tokenized["labels"])):
        pad_id = tokenizer.pad_token_id
        tokenized["labels"][i] = [
            -100 if tid == pad_id else tid
            for tid in tokenized["labels"][i]
        ]
    return tokenized


tokenized_dataset = raw_dataset.map(
    tokenize_function,
    batched=True,
    remove_columns=raw_dataset.column_names,
    desc="Tokenizing",
)
logger.info(f"Tokenized dataset: {len(tokenized_dataset)} examples")

rss = memory_guard()
logger.info(f"Memory after tokenization: {rss:.1f} GB")

# Training arguments - maximally conservative for CPU
training_args = TrainingArguments(
    output_dir="lora",
    num_train_epochs=NUM_EPOCHS,
    per_device_train_batch_size=BATCH_SIZE,
    gradient_accumulation_steps=GRAD_ACCUM,
    learning_rate=LEARNING_RATE,
    lr_scheduler_type="cosine",
    warmup_ratio=0.05,
    logging_steps=5,
    save_strategy="epoch",
    save_total_limit=1,
    no_cuda=True,
    use_cpu=True,
    dataloader_num_workers=0,       # single process = no extra memory
    dataloader_pin_memory=False,    # no GPU to pin to
    fp16=False,
    bf16=False,
    gradient_checkpointing=GRADIENT_CHECKPOINTING,
    report_to="none",               # no wandb/tensorboard overhead
    max_grad_norm=1.0,
    remove_unused_columns=False,
    optim="adafactor" if USE_ADAFACTOR else "adamw_torch",
)

# Data collator
data_collator = DataCollatorForSeq2Seq(
    tokenizer=tokenizer,
    padding=True,
    max_length=MAX_SEQ_LENGTH,
)

# Custom trainer with memory guard
class MemorySafeTrainer(Trainer):
    """Trainer that monitors memory and gc's between steps."""

    def training_step(self, model, inputs):
        rss = memory_guard()
        if int(self.state.global_step) % 10 == 0:
            logger.info(f"Step {self.state.global_step} | RSS: {rss:.1f} GB")
        result = super().training_step(model, inputs)
        aggressive_gc()
        return result


trainer = MemorySafeTrainer(
    model=model,
    args=training_args,
    train_dataset=tokenized_dataset,
    data_collator=data_collator,
)

# Train
logger.info("Starting training...")
start_time = time.time()

try:
    trainer.train()
    elapsed = time.time() - start_time
    logger.info(f"Training completed in {elapsed:.0f}s ({elapsed/60:.1f} min)")
except MemoryError:
    logger.error("OOM during training. Try reducing MAX_SEQ_LENGTH or NUM_SAMPLES further.")
    sys.exit(2)
except RuntimeError as e:
    if "out of memory" in str(e).lower():
        logger.error("OOM during training. Try reducing MAX_SEQ_LENGTH or NUM_SAMPLES further.")
        sys.exit(2)
    raise

# Save adapter
adapter_path = Path("lora/final_adapter")
trainer.save_model(str(adapter_path))
tokenizer.save_pretrained(str(adapter_path))
logger.info(f"Adapter saved: {adapter_path}")

# Free model memory before merge
del model, trainer, tokenized_dataset, raw_dataset
aggressive_gc()

rss = check_memory()
logger.info(f"Memory after cleanup: {rss:.1f} GB")

# ── Step 3: Merge ──────────────────────────────────────────────────────
logger.info("=" * 60)
logger.info("STEP 3: Merging LoRA adapter into base model")
logger.info("=" * 60)

from training.merge_lora import merge_lora_adapter, convert_to_gguf

merged_path = merge_lora_adapter(
    base_model=BASE_MODEL,
    adapter_path=str(adapter_path),
    output_path="merged_model",
)
logger.info(f"Merged model: {merged_path}")

# ── Step 4: GGUF (optional) ────────────────────────────────────────────
if CONVERT_GGUF:
    logger.info("=" * 60)
    logger.info("STEP 4: Converting to GGUF")
    logger.info("=" * 60)

    gguf_file = str(merged_path) + ".gguf"
    result = convert_to_gguf(str(merged_path), gguf_file, quantization=QUANT)
    if result:
        logger.info(f"GGUF model: {result}")
    else:
        logger.warning("GGUF conversion skipped -- llama.cpp not found.")
        logger.warning("Clone it: git clone https://github.com/ggerganov/llama.cpp")
else:
    logger.info("GGUF conversion skipped (set CONVERT_GGUF=True to enable)")

logger.info("=" * 60)
logger.info("DONE")
logger.info("=" * 60)
