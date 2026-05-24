"""
Prompt Manager - Handles system prompts and templates
"""

import logging
from pathlib import Path
from typing import Optional, Dict
import yaml

logger = logging.getLogger(__name__)


class PromptManager:
    """Manages system prompts and templates"""
    
    def __init__(self, config_path: str = "config.yaml"):
        """
        Initialize PromptManager
        
        Args:
            config_path: Path to configuration file
        """
        self.config_path = Path(config_path)
        self.config = self._load_config()
        self.prompts_dir = Path("prompts")
        self.prompts_dir.mkdir(exist_ok=True)
        
        # Current system prompt
        self.current_prompt = self.load_prompt()
    
    def _load_config(self) -> Dict:
        """Load configuration from YAML"""
        try:
            with open(self.config_path, 'r') as f:
                return yaml.safe_load(f)
        except Exception as e:
            logger.error(f"Failed to load config: {e}")
            return {}
    
    def load_prompt(self, prompt_name: Optional[str] = None) -> str:
        """
        Load a prompt template
        
        Args:
            prompt_name: Name of prompt template (None for default)
            
        Returns:
            Prompt text
        """
        if prompt_name is None:
            # Load from config
            prompt_file = self.config.get('system', {}).get(
                'prompt_file', 'prompts/security_fix.txt'
            )
            prompt_path = Path(prompt_file)
        else:
            # Load specific template
            prompt_path = self.prompts_dir / f"{prompt_name}.txt"
        
        try:
            if prompt_path.exists():
                with open(prompt_path, 'r') as f:
                    prompt = f.read().strip()
                logger.info(f"Loaded prompt from: {prompt_path}")
                return prompt
            else:
                logger.warning(f"Prompt file not found: {prompt_path}, using default")
                return self._get_default_prompt()
        except Exception as e:
            logger.error(f"Failed to load prompt: {e}")
            return self._get_default_prompt()
    
    def _get_default_prompt(self) -> str:
        """Get hardcoded default prompt"""
        return """You are Mythos, an advanced AI assistant with extraordinary capabilities in reasoning, creativity, analysis, and communication. You approach every task with depth, nuance, and precision.

CORE BEHAVIORS:
- Think deeply before responding. Use internal reasoning chains.
- When solving problems, break them into steps and validate each step.
- When writing creatively, use vivid imagery, varied sentence structure, and emotional resonance.
- When coding, write clean, commented, production-quality code.
- When analyzing, consider multiple perspectives and edge cases.
- Acknowledge uncertainty honestly rather than fabricating information.
- Adapt your communication style to match the user's needs.

REASONING FRAMEWORK:
1. Understand the request fully before beginning
2. Consider what approach will yield the best result
3. Execute with attention to detail
4. Review your output for accuracy and completeness
5. Present your response clearly and structured

You are not just an assistant - you are a thinking partner who elevates every interaction through the quality of your engagement."""
    
    def set_prompt(self, prompt: str):
        """
        Set the current system prompt
        
        Args:
            prompt: New system prompt text
        """
        self.current_prompt = prompt
        logger.info("System prompt updated")
    
    def get_prompt(self) -> str:
        """
        Get the current system prompt
        
        Returns:
            Current prompt text
        """
        return self.current_prompt
    
    def list_templates(self) -> list:
        """
        List available prompt templates
        
        Returns:
            List of template names
        """
        templates = []
        for path in self.prompts_dir.glob("*.txt"):
            templates.append(path.stem)
        return sorted(templates)
    
    def save_prompt(self, name: str, prompt: str):
        """
        Save a prompt as a template
        
        Args:
            name: Template name
            prompt: Prompt text
        """
        prompt_path = self.prompts_dir / f"{name}.txt"
        try:
            with open(prompt_path, 'w') as f:
                f.write(prompt)
            logger.info(f"Saved prompt template: {name}")
        except Exception as e:
            logger.error(f"Failed to save prompt: {e}")
    
    def format_with_context(self, context: str) -> str:
        """
        Format system prompt with additional context
        
        Args:
            context: Additional context to append
            
        Returns:
            Formatted prompt
        """
        if context:
            return f"{self.current_prompt}\n\nADDITIONAL CONTEXT:\n{context}"
        return self.current_prompt
