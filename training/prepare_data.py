"""
Data Preparation - Download and prepare training datasets
"""

import json
import logging
from pathlib import Path
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

# Check for optional dependencies
try:
    from datasets import load_dataset
    DATASETS_AVAILABLE = True
except ImportError:
    DATASETS_AVAILABLE = False
    logger.warning("datasets library not available")


class DatasetPreparer:
    """Prepare datasets for fine-tuning"""
    
    def __init__(self, output_dir: str = "training_data"):
        """
        Initialize DatasetPreparer
        
        Args:
            output_dir: Directory to save prepared data
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
    
    def download_openhermes(self, num_samples: int = 1000) -> Path:
        """
        Download and prepare OpenHermes dataset
        
        Args:
            num_samples: Number of samples to download
            
        Returns:
            Path to prepared dataset
        """
        if not DATASETS_AVAILABLE:
            raise RuntimeError("datasets library required. Install with: pip install datasets")
        
        logger.info(f"Downloading OpenHermes dataset ({num_samples} samples)...")
        
        try:
            # Load dataset
            dataset = load_dataset(
                "teknium/OpenHermes-2.5",
                split=f"train[:{num_samples}]"
            )
            
            # Convert to chat format
            prepared_data = []
            
            for item in dataset:
                # OpenHermes format: conversations list
                conversations = item.get('conversations', [])
                
                # Convert to simple format
                messages = []
                for msg in conversations:
                    role = msg.get('from', 'user')
                    if role == 'human':
                        role = 'user'
                    elif role == 'gpt':
                        role = 'assistant'
                    
                    messages.append({
                        'role': role,
                        'content': msg.get('value', '')
                    })
                
                if messages:
                    prepared_data.append({'messages': messages})
            
            # Save to file
            output_file = self.output_dir / "openhermes_prepared.jsonl"
            with open(output_file, 'w') as f:
                for item in prepared_data:
                    f.write(json.dumps(item) + '\n')
            
            logger.info(f"Prepared {len(prepared_data)} samples")
            logger.info(f"Saved to: {output_file}")
            
            return output_file
            
        except Exception as e:
            logger.error(f"Failed to download dataset: {e}")
            raise
    
    def prepare_custom_dataset(
        self,
        data: List[Dict[str, Any]],
        filename: str = "custom_data.jsonl"
    ) -> Path:
        """
        Prepare custom dataset from list of conversations
        
        Args:
            data: List of conversation dictionaries
            filename: Output filename
            
        Returns:
            Path to prepared dataset
        """
        output_file = self.output_dir / filename
        
        with open(output_file, 'w') as f:
            for item in data:
                f.write(json.dumps(item) + '\n')
        
        logger.info(f"Prepared {len(data)} custom samples")
        logger.info(f"Saved to: {output_file}")
        
        return output_file
    
    def load_jsonl(self, filepath: Path) -> List[Dict]:
        """
        Load data from JSONL file
        
        Args:
            filepath: Path to JSONL file
            
        Returns:
            List of data items
        """
        data = []
        with open(filepath, 'r') as f:
            for line in f:
                data.append(json.loads(line))
        return data
    
    def format_for_chat_template(
        self,
        messages: List[Dict[str, str]],
        template: str = "chatml"
    ) -> str:
        """
        Format messages using a chat template
        
        Args:
            messages: List of message dicts
            template: Template name (chatml, llama3, mistral)
            
        Returns:
            Formatted text
        """
        if template == "chatml":
            formatted = ""
            for msg in messages:
                role = msg['role']
                content = msg['content']
                formatted += f"<|im_start|>{role}\n{content}<|im_end|>\n"
            return formatted
        
        elif template == "llama3":
            formatted = "<|begin_of_text|>"
            for msg in messages:
                role = msg['role']
                content = msg['content']
                formatted += f"<|start_header_id|>{role}<|end_header_id|>\n\n{content}<|eot_id|>"
            return formatted
        
        elif template == "mistral":
            formatted = ""
            for msg in messages:
                if msg['role'] == 'user':
                    formatted += f"[INST] {msg['content']} [/INST]"
                elif msg['role'] == 'assistant':
                    formatted += f" {msg['content']}</s>"
            return formatted
        
        else:
            raise ValueError(f"Unknown template: {template}")
