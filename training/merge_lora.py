"""
Merge LoRA - Merge trained LoRA adapter back into base model

Loads base model + adapter, merges weights, saves the merged model.
Optionally converts to GGUF for llama.cpp/llama-cpp-python usage.
"""

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

try:
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from peft import PeftModel
    MERGE_DEPS_AVAILABLE = True
except ImportError:
    MERGE_DEPS_AVAILABLE = False


def merge_lora_adapter(
    base_model: str,
    adapter_path: str,
    output_path: str,
    upload_to_hub: Optional[str] = None,
):
    """
    Merge LoRA adapter with base model and save.

    Args:
        base_model: HuggingFace model ID or local path.
        adapter_path: Path to trained LoRA adapter directory.
        output_path: Directory to save merged model.
        upload_to_hub: Optional HuggingFace repo ID to push after merge.

    Returns:
        Path to merged model directory.
    """
    if not MERGE_DEPS_AVAILABLE:
        raise RuntimeError(
            "Merge dependencies not available. Install with:\n"
            "  pip install torch transformers peft accelerate"
        )

    adapter_path = Path(adapter_path)
    output_path = Path(output_path)

    if not adapter_path.exists():
        raise FileNotFoundError(f"Adapter not found: {adapter_path}")

    logger.info("LoRA Merge Tool")
    logger.info("=" * 60)
    logger.info(f"  Base model: {base_model}")
    logger.info(f"  Adapter:    {adapter_path}")
    logger.info(f"  Output:     {output_path}")

    # Load base model
    logger.info("Loading base model...")
    dtype = torch.float16 if torch.cuda.is_available() else torch.float32
    model = AutoModelForCausalLM.from_pretrained(
        base_model,
        torch_dtype=dtype,
        device_map="cpu",
        low_cpu_mem_usage=True,
        trust_remote_code=True,
    )
    tokenizer = AutoTokenizer.from_pretrained(base_model, trust_remote_code=True)

    # Load and merge LoRA adapter
    logger.info("Loading LoRA adapter...")
    model = PeftModel.from_pretrained(model, str(adapter_path))

    logger.info("Merging adapter weights into base model...")
    model = model.merge_and_unload()

    # Save merged model
    output_path.mkdir(parents=True, exist_ok=True)
    logger.info(f"Saving merged model to {output_path}...")
    model.save_pretrained(str(output_path), safe_serialization=True)
    tokenizer.save_pretrained(str(output_path))

    logger.info(f"Merged model saved to: {output_path}")

    # Optional: push to HuggingFace Hub
    if upload_to_hub:
        logger.info(f"Pushing to HuggingFace Hub: {upload_to_hub}...")
        model.push_to_hub(upload_to_hub)
        tokenizer.push_to_hub(upload_to_hub)
        logger.info("Upload complete.")

    return output_path


def convert_to_gguf(
    merged_model_path: str,
    output_gguf_path: str,
    quantization: str = "q4_k_m",
):
    """
    Convert merged HuggingFace model to GGUF format.

    Requires llama.cpp to be installed (provides convert scripts).

    Args:
        merged_model_path: Path to merged HuggingFace model directory.
        output_gguf_path: Output .gguf file path.
        quantization: GGUF quantization type (q4_k_m, q5_k_m, q8_0, etc.).

    Returns:
        Path to GGUF file, or None if llama.cpp not available.
    """
    import subprocess

    merged_path = Path(merged_model_path)
    gguf_path = Path(output_gguf_path)
    gguf_path.parent.mkdir(parents=True, exist_ok=True)

    # Try to find llama.cpp convert script
    convert_candidates = [
        Path("llama.cpp/convert_hf_to_gguf.py"),
        Path("llama.cpp/convert.py"),
    ]

    convert_script = None
    for candidate in convert_candidates:
        if candidate.exists():
            convert_script = candidate
            break

    if convert_script is None:
        logger.warning(
            "llama.cpp convert script not found.\n"
            "To convert to GGUF:\n"
            "  1. Clone llama.cpp: git clone https://github.com/ggerganov/llama.cpp\n"
            "  2. Install deps: pip install gguf sentencepiece\n"
            f"  3. Run: python llama.cpp/convert_hf_to_gguf.py {merged_path} --outfile {gguf_path} --outtype {quantization}"
        )
        return None

    logger.info(f"Converting to GGUF ({quantization})...")
    cmd = [
        "python", str(convert_script),
        str(merged_path),
        "--outfile", str(gguf_path),
        "--outtype", quantization,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        logger.error(f"GGUF conversion failed:\n{result.stderr}")
        return None

    logger.info(f"GGUF model saved to: {gguf_path}")
    return str(gguf_path)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Merge LoRA adapter into base model")
    parser.add_argument("--base-model", required=True, help="HuggingFace model ID or path")
    parser.add_argument("--adapter", required=True, help="Path to LoRA adapter")
    parser.add_argument("--output", required=True, help="Output directory for merged model")
    parser.add_argument("--gguf", action="store_true", help="Also convert to GGUF")
    parser.add_argument("--quant", default="q4_k_m", help="GGUF quantization (default: q4_k_m)")
    parser.add_argument("--push-to-hub", default=None, help="HuggingFace repo ID to push")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    merged = merge_lora_adapter(
        base_model=args.base_model,
        adapter_path=args.adapter,
        output_path=args.output,
        upload_to_hub=args.push_to_hub,
    )

    if args.gguf and merged:
        gguf_path = str(merged) + ".gguf"
        convert_to_gguf(str(merged), gguf_path, quantization=args.quant)
