"""
Self-Reflection Module - Enhances response quality through iterative improvement
"""

import logging
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
        self.review_prompt = """Review your previous answer. Consider:
1. Accuracy - Are there any errors or inaccuracies?
2. Completeness - Did you fully address the question?
3. Clarity - Is the explanation clear and well-structured?
4. Quality - Could the response be improved?

If you find issues, provide an improved answer. If the original answer was excellent, confirm it's good as-is."""
        
        self.thinking_prompt = """Before answering, think through the problem step by step:
1. What is being asked?
2. What information is relevant?
3. What approach will work best?
4. What are potential pitfalls?

Then provide your complete answer."""
    
    def _load_config(self) -> Dict:
        """Load configuration from YAML"""
        try:
            with open(self.config_path, 'r') as f:
                return yaml.safe_load(f)
        except Exception as e:
            logger.error(f"Failed to load config: {e}")
            return {}
    
    def should_reflect(self) -> bool:
        """
        Check if self-reflection is enabled
        
        Returns:
            True if reflection is enabled
        """
        return self.config.get('system', {}).get('self_reflect', False)
    
    def should_think(self) -> bool:
        """
        Check if thinking mode is enabled
        
        Returns:
            True if thinking mode is enabled
        """
        return self.config.get('system', {}).get('thinking_mode', False)
    
    def create_thinking_prompt(self, original_prompt: str) -> str:
        """
        Create a prompt that encourages step-by-step thinking
        
        Args:
            original_prompt: The original user prompt
            
        Returns:
            Enhanced prompt with thinking instructions
        """
        return f"{self.thinking_prompt}\n\nUSER QUESTION:\n{original_prompt}"
    
    def create_reflection_prompt(self, original_prompt: str, initial_response: str) -> str:
        """
        Create a prompt for self-reflection
        
        Args:
            original_prompt: The original user prompt
            initial_response: The initial response to review
            
        Returns:
            Reflection prompt
        """
        return f"""ORIGINAL QUESTION:
{original_prompt}

YOUR PREVIOUS ANSWER:
{initial_response}

{self.review_prompt}"""
    
    def reflect(self, engine, original_prompt: str, initial_response: str, **kwargs) -> str:
        """
        Perform self-reflection to improve response quality
        
        Args:
            engine: InferenceEngine instance
            original_prompt: Original user prompt
            initial_response: Initial response to improve
            **kwargs: Additional generation parameters
            
        Returns:
            Improved response or original if already good
        """
        logger.info("Performing self-reflection...")
        
        # Create reflection prompt
        reflection_prompt = self.create_reflection_prompt(original_prompt, initial_response)
        
        # Get reflection response
        reflection = engine.generate(reflection_prompt, **kwargs)
        
        # Parse reflection to see if improvement was made
        # If the model says the answer is good, return original
        # Otherwise, return the improved version
        
        lower_reflection = reflection.lower()
        if any(phrase in lower_reflection for phrase in [
            "original answer was excellent",
            "original answer is good",
            "no improvements needed",
            "answer is already",
            "response was accurate"
        ]):
            logger.info("Self-reflection: Original answer deemed good")
            return initial_response
        else:
            logger.info("Self-reflection: Improved answer generated")
            return reflection
    
    def extract_reasoning(self, response: str) -> tuple[str, str]:
        """
        Extract reasoning and final answer from a thinking-mode response
        
        Args:
            response: Full response with thinking
            
        Returns:
            Tuple of (reasoning, final_answer)
        """
        # Look for common separators
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
