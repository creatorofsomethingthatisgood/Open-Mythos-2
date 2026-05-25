"""
Self-Reflection Module - Enhances response quality through iterative improvement
"""

import logging
import re
from typing import Optional, Dict, Any
import yaml

logger = logging.getLogger(__name__)


class SelfReflector:
    """Self-reflection quality enhancement system"""
    
    def __init__(self, config_path: str = "config.yaml"):
        """
        Initialize SelfReflector
        
        Args:
            config_path: Path to configuration file
        """
        self.config_path = config_path
        self.config = self._load_config()
        
        # Reflection prompts
        self.reflection_prompt = """You are a self-reflection assistant. Review the following response for accuracy, completeness, and clarity. If the response can be improved, provide an improved version. If it's already good, return it unchanged.

Original question: {prompt}

Initial response: {response}

Provide your reviewed and improved response:"""
        
        self.thinking_prompt = """Before answering, reason step by step inside <thinking> tags, then give your final answer after </thinking>. Keep reasoning concise and avoid repetition."""
        
        self._load_settings()
    
    def _load_config(self) -> dict:
        """Load configuration from YAML file"""
        try:
            with open(self.config_path, 'r') as f:
                return yaml.safe_load(f) or {}
        except FileNotFoundError:
            logger.warning(f"Config file {self.config_path} not found, using defaults")
            return {}
        except Exception as e:
            logger.error(f"Error loading config: {e}")
            return {}
    
    def _load_settings(self):
        """Load reflection and thinking settings from config"""
        reflection_config = self.config.get('reflection', {})
        thinking_config = self.config.get('thinking', {})
        
        self.reflection_enabled = reflection_config.get('enabled', False)
        self.reflection_threshold = reflection_config.get('threshold', 0.7)
        self.reflection_iterations = reflection_config.get('iterations', 2)
        
        self.thinking_enabled = thinking_config.get('enabled', True)
        self.thinking_mode = self.config.get('thinking_mode', True)
    
    def should_reflect(self) -> bool:
        """Check if reflection should be applied"""
        return self.reflection_enabled
    
    def should_think(self) -> bool:
        """Check if thinking mode should be applied"""
        return self.thinking_enabled or self.thinking_mode
    
    def reflect(self, engine, prompt: str, response: str, **kwargs) -> str:
        """
        Apply self-reflection to improve a response
        
        Args:
            engine: InferenceEngine instance
            prompt: Original user prompt
            response: Initial response to improve
            **kwargs: Additional generation parameters
            
        Returns:
            Improved response (or original if no improvement found)
        """
        reflection_input = self.reflection_prompt.format(
            prompt=prompt,
            response=response
        )
        
        try:
            improved = engine.generate(reflection_input, **kwargs)
            if improved and len(improved.strip()) > len(response.strip()) * 0.5:
                logger.info("Self-reflection: Improved answer generated")
                return improved
        except Exception as e:
            logger.error(f"Self-reflection failed: {e}")
        
        return response
    
    def extract_reasoning(self, response: str) -> tuple[str, str]:
        """
        Extract reasoning and final answer from a thinking-mode response.
        
        Supports multiple thinking tag formats:
        - <think> ... </think>
        - <thinking> ... </thinking>
        -  ...  (Qwen-style)
        - Text separators like "FINAL ANSWER:", "Answer:", etc.
        
        Args:
            response: Full response with thinking
        
        Returns:
            Tuple of (reasoning, final_answer)
        """
        # Pattern 1: <think> ... </think> tags
        think_match = re.search(r'<think>(.*?)</think>', response, re.DOTALL)
        if think_match:
            reasoning = think_match.group(1).strip()
            after_tag = response[think_match.end():].strip()
            return reasoning, after_tag if after_tag else ""
        
        # Pattern 2: <thinking> ... </thinking> tags
        thinking_match = re.search(r'<thinking>(.*?)</thinking>', response, re.DOTALL)
        if thinking_match:
            reasoning = thinking_match.group(1).strip()
            after_tag = response[thinking_match.end():].strip()
            return reasoning, after_tag if after_tag else ""
        
        # Pattern 3:  ...  tags (Qwen2.5 style)
        qwen_think_open = '\u00ab\u00ab\u00ab\u00ab'
        qwen_think_close = '\u00bb\u00bb\u00bb\u00bb'
        if qwen_think_open in response and qwen_think_close in response:
            idx_open = response.index(qwen_think_open) + len(qwen_think_open)
            idx_close = response.index(qwen_think_close)
            if idx_close > idx_open:
                reasoning = response[idx_open:idx_close].strip()
                after_tag = response[idx_close + len(qwen_think_close):].strip()
                return reasoning, after_tag if after_tag else ""
        
        # Pattern 4: Text separators (fallback)
        separators = [
            "FINAL ANSWER:",
            "Final Answer:",
            "Answer:",
            "\n\nIn conclusion",
            "\n\nTo summarize",
        ]
        
        for sep in separators:
            if sep in response:
                parts = response.split(sep, 1)
                reasoning = parts[0].strip()
                answer = parts[1].strip() if len(parts) > 1 else response
                return reasoning, answer
        
        # If no separator found, treat whole response as answer
        return "", response
    
    def format_thinking_response(self, response: str, show_reasoning: bool = True) -> str:
        """
        Format a thinking-mode response
        
        Args:
            response: Raw response
            show_reasoning: Whether to show the reasoning process
            
        Returns:
            Formatted response
        """
        reasoning, answer = self.extract_reasoning(response)
        
        if show_reasoning and reasoning:
            return f"**REASONING:**\n{reasoning}\n\n**ANSWER:**\n{answer}"
        else:
            return answer
    
    def enhance_response(
        self,
        engine,
        prompt: str,
        initial_response: str,
        enable_thinking: Optional[bool] = None,
        enable_reflection: Optional[bool] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Apply full enhancement pipeline to a response
        
        Args:
            engine: InferenceEngine instance
            prompt: Original prompt
            initial_response: Initial response
            enable_thinking: Override thinking mode
            enable_reflection: Override reflection mode
            **kwargs: Additional generation parameters
            
        Returns:
            Dictionary with enhanced response and metadata
        """
        # Determine which enhancements to apply
        use_thinking = enable_thinking if enable_thinking is not None else self.should_think()
        use_reflection = enable_reflection if enable_reflection is not None else self.should_reflect()
        
        result = {
            'response': initial_response,
            'reasoning': None,
            'reflected': False,
            'original_response': initial_response
        }
        
        # Extract thinking if present
        if use_thinking:
            reasoning, answer = self.extract_reasoning(initial_response)
            result['reasoning'] = reasoning if reasoning else None
            result['response'] = answer
        
        # Apply reflection
        if use_reflection:
            improved = self.reflect(engine, prompt, result['response'], **kwargs)
            if improved != result['response']:
                result['response'] = improved
                result['reflected'] = True
        
        return result
