"""
Training Package - Fine-tuning capabilities for local models

Note: Training on CPU is slow. This is provided as an optional feature.
For AMD GPUs, ROCm support may be limited. CPU training is the most reliable option.
"""

__all__ = ['finetune', 'prepare_data', 'merge_lora']
