"""
Coding Dataset Preparation for Phase 1 Curriculum Training.

Downloads and mixes high-quality coding datasets:
- nvidia/OpenCodeInstruct (5M samples, filtered to top 50K)
- m-a-p/Code-Feedback (60K multi-turn coding dialogues)
- Existing Mythos data for defensive security + general mix

Output: training_data/phase1_coding.jsonl (messages format)
"""

import json
import logging
import os
import random
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from datasets import load_dataset
    DATASETS_AVAILABLE = True
except ImportError:
    DATASETS_AVAILABLE = False


class CodingDataPreparer:
    """Download and prepare coding-focused training data for Phase 1."""

    def __init__(
        self,
        output_dir: str = "training_data",
        max_coding_samples: int = 50000,
        max_feedback_samples: int = 60000,
        seed: int = 42,
    ):
        if not DATASETS_AVAILABLE:
            raise RuntimeError(
                "datasets library not installed. Install with:\n"
                "  pip install datasets"
            )
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        self.max_coding_samples = max_coding_samples
        self.max_feedback_samples = max_feedback_samples
        self.seed = seed
        random.seed(seed)

    def download_opencode_instruct(self, max_samples: Optional[int] = None) -> list:
        """Download nvidia/OpenCodeInstruct, filter for quality, deduplicate.

        The dataset has ~5M samples. We filter for:
        - High quality (score >= 4 if available, otherwise keep all)
        - Deduplicate by instruction text
        - Take up to max_samples
        """
        max_samples = max_samples or self.max_coding_samples
        logger.info(f"Downloading nvidia/OpenCodeInstruct (target: {max_samples} samples)...")

        ds = load_dataset("nvidia/OpenCodeInstruct", split="train", streaming=True)

        samples = []
        seen_instructions = set()

        for row in ds:
            if len(samples) >= max_samples:
                break

            instruction = row.get("instruction", row.get("input", ""))
            if not instruction or len(instruction.strip()) < 20:
                continue

            # Dedup by instruction prefix (first 100 chars)
            dedup_key = instruction.strip()[:100].lower()
            if dedup_key in seen_instructions:
                continue
            seen_instructions.add(dedup_key)

            # Convert to messages format
            messages = []
            if instruction:
                messages.append({"role": "user", "content": instruction})
            output = row.get("output", row.get("response", ""))
            if output:
                messages.append({"role": "assistant", "content": output})

            if len(messages) >= 2:
                samples.append({"messages": messages})

        logger.info(f"OpenCodeInstruct: collected {len(samples)} samples")
        return samples

    def download_code_feedback(self, max_samples: Optional[int] = None) -> list:
        """Download m-a-p/Code-Feedback (multi-turn coding dialogues).

        These are high-quality multi-turn conversations about code,
        ideal for training conversational coding ability.
        """
        max_samples = max_samples or self.max_feedback_samples
        logger.info(f"Downloading m-a-p/Code-Feedback (target: {max_samples} samples)...")

        ds = load_dataset("m-a-p/Code-Feedback", split="train")

        samples = []
        for row in ds:
            if len(samples) >= max_samples:
                break

            # The dataset has conversations in various formats
            # Try to extract messages
            messages = self._extract_messages(row)
            if messages and len(messages) >= 2:
                samples.append({"messages": messages})

        logger.info(f"Code-Feedback: collected {len(samples)} samples")
        return samples

    def _extract_messages(self, row: dict) -> list:
        """Extract messages list from a dataset row in various formats."""
        messages = []

        # Format 1: already has 'messages' field
        if "messages" in row and isinstance(row["messages"], list):
            return row["messages"]

        # Format 2: conversation field
        if "conversation" in row and isinstance(row["conversation"], list):
            for turn in row["conversation"]:
                role = turn.get("role", "user")
                content = turn.get("content", turn.get("value", ""))
                if content:
                    messages.append({"role": role, "content": content})
            return messages

        # Format 3: separate instruction/response fields
        instruction = row.get("instruction", row.get("question", ""))
        response = row.get("response", row.get("answer", row.get("output", "")))

        if instruction:
            messages.append({"role": "user", "content": instruction})
        if response:
            messages.append({"role": "assistant", "content": response})

        return messages

    def _load_existing_mythos_data(self) -> list:
        """Load existing Mythos training data for defensive security + general mix."""
        samples = []
        for filename in ["mythos_4.8_data.jsonl", "data.jsonl", "openhermes_prepared.jsonl"]:
            path = self.output_dir / filename
            if path.exists():
                with open(path, "r") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            try:
                                data = json.loads(line)
                                if "messages" in data:
                                    samples.append(data)
                            except json.JSONDecodeError:
                                continue
                logger.info(f"Loaded {len(samples)} samples from {filename}")
        return samples

    def mix_datasets(
        self,
        coding_ratio: float = 0.85,
        defensive_ratio: float = 0.10,
        general_ratio: float = 0.05,
        output_filename: str = "phase1_coding.jsonl",
    ) -> Path:
        """Mix coding, defensive security, and general data at specified ratios.

        Args:
            coding_ratio: Fraction of coding data (default 85%).
            defensive_ratio: Fraction of defensive security data (default 10%).
            general_ratio: Fraction of general data (default 5%).
            output_filename: Output JSONL filename.

        Returns:
            Path to the mixed dataset file.
        """
        # Download coding datasets
        opencode_samples = self.download_opencode_instruct()
        feedback_samples = self.download_code_feedback()

        # Combine all coding samples
        all_coding = opencode_samples + feedback_samples

        # Load existing mythos data (defensive security + general)
        existing_samples = self._load_existing_mythos_data()

        # Separate defensive security from general
        defensive_samples = []
        general_samples = []
        for sample in existing_samples:
            content = " ".join(m["content"] for m in sample.get("messages", []))
            sec_keywords = ["vulnerability", "security", "exploit", "injection",
                          "xss", "ssrf", "csrf", "CVE", "CWE", "patch"]
            if any(kw.lower() in content.lower() for kw in sec_keywords):
                defensive_samples.append(sample)
            else:
                general_samples.append(sample)

        # Calculate target counts based on ratios
        total_target = len(all_coding) + len(defensive_samples) + len(general_samples)
        coding_target = int(total_target * coding_ratio)
        defensive_target = int(total_target * defensive_ratio)
        general_target = int(total_target * general_ratio)

        # Adjust coding samples
        if len(all_coding) > coding_target:
            all_coding = random.sample(all_coding, coding_target)

        # Adjust defensive samples (repeat if needed)
        if len(defensive_samples) < defensive_target and defensive_samples:
            defensive_samples = defensive_samples * (defensive_target // len(defensive_samples) + 1)
        defensive_samples = defensive_samples[:defensive_target]

        # Adjust general samples (repeat if needed)
        if len(general_samples) < general_target and general_samples:
            general_samples = general_samples * (general_target // len(general_samples) + 1)
        general_samples = general_samples[:general_target]

        # Mix and shuffle
        mixed = all_coding + defensive_samples + general_samples
        random.shuffle(mixed)

        # Write output
        output_path = self.output_dir / output_filename
        with open(output_path, "w") as f:
            for sample in mixed:
                f.write(json.dumps(sample) + "\n")

        logger.info(
            f"Phase 1 dataset written to {output_path}: "
            f"{len(all_coding)} coding + {len(defensive_samples)} defensive + "
            f"{len(general_samples)} general = {len(mixed)} total"
        )
        return output_path


def prepare_coding_data(output_dir: str = "training_data") -> Path:
    """Convenience function to prepare the Phase 1 coding dataset."""
    preparer = CodingDataPreparer(output_dir=output_dir)
    return preparer.mix_datasets()
