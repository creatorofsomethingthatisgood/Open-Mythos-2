"""
Inference Engine - Wrapper for llama-cpp-python with GPU acceleration
(Metal on macOS, Vulkan on Linux AMD, CPU fallback)
"""

import logging
import os
from pathlib import Path
from typing import Optional, Iterator, Dict, Any, List
import yaml

from .platform_utils import get_backend_name, get_default_gpu_layers, get_setup_script

try:
 from llama_cpp import Llama
 LLAMA_CPP_AVAILABLE = True
except ImportError:
 LLAMA_CPP_AVAILABLE = False
 Llama = None  # type: ignore[assignment,misc]
 logging.warning(f"llama-cpp-python not available. Run {get_setup_script()} first.")

from .model_manager import ModelManager

logger = logging.getLogger(__name__)


class InferenceEngine:
    """
    High-performance inference engine with AMD GPU support via Vulkan
    """
    
    def __init__(self, config_path: str = "config.yaml", model_path: Optional[str] = None):
        """
        Initialize the inference engine
        
        Args:
            config_path: Path to configuration file
            model_path: Override model path (optional)
        """
        if not LLAMA_CPP_AVAILABLE:
            raise RuntimeError(
                f"llama-cpp-python is not installed. Run {get_setup_script()} first."
            )
        
        self.config_path = Path(config_path)
        self.config = self._load_config()
        self.model_manager = ModelManager(config_path)
        
        # Determine model path
        if model_path:
            self.model_path = Path(model_path)
        else:
            self.model_path = self.model_manager.find_model()
            if self.model_path is None:
                logger.warning("No model found. Attempting auto-download...")
                self.model_path = self.model_manager.auto_download_if_needed()
        
        if not self.model_path or not self.model_path.exists():
            raise FileNotFoundError(f"Model file not found: {self.model_path}")
        
        logger.info(f"Loading model: {self.model_path}")
        
        # Initialize the model
        self.model = self._load_model()

        # Save original SIGINT handler so __del__ can restore it
        import signal as _signal
        self._orig_sigint = _signal.getsignal(_signal.SIGINT)
        
    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from YAML"""
        try:
            with open(self.config_path, 'r') as f:
                raw = yaml.safe_load(f) or {}
            from engine.chat_config import merge_chat_defaults
            return merge_chat_defaults(raw)
        except Exception as e:
            logger.error(f"Failed to load config: {e}")
            return {}
    
    def _load_model(self) -> "Llama":
        """
        Load the GGUF model with optimal settings for AMD hardware
        
        Returns:
            Loaded Llama model instance
        """
        model_config = self.config.get('model', {})
        
        # Determine number of threads
        n_threads = model_config.get('n_threads', 0)
        if n_threads == 0:
            n_threads = max(1, os.cpu_count() // 2)  # Use half of CPU cores
        
        # GPU layers (auto-enable Metal on Apple Silicon when config is 0)
        n_gpu_layers = get_default_gpu_layers(model_config.get('n_gpu_layers', 0))
        
        # Context length (Qwen2.5 supports 32K; larger n_ctx uses more RAM)
        n_ctx = model_config.get('context_length', 8192)
        self._context_length = n_ctx
        
        # Batch size
        n_batch = model_config.get('n_batch', 512)
        
        # Memory mapping
        use_mmap = model_config.get('use_mmap', True)
        use_mlock = model_config.get('use_mlock', False)
        
        logger.info(f"Model settings:")
        logger.info(f"  - Threads: {n_threads}")
        logger.info(f"  - GPU layers: {n_gpu_layers}")
        logger.info(f"  - Context length: {n_ctx}")
        logger.info(f"  - Batch size: {n_batch}")
        logger.info(f"  - Memory mapping: {use_mmap}")
        
        try:
            model = Llama(
                model_path=str(self.model_path),
                n_ctx=n_ctx,
                n_threads=n_threads,
                n_gpu_layers=n_gpu_layers,
                n_batch=n_batch,
                use_mmap=use_mmap,
                use_mlock=use_mlock,
                verbose=False,
            )
            
            logger.info("Model loaded successfully!")
            
            backend = get_backend_name(n_gpu_layers)
            if n_gpu_layers != 0:
                logger.info(f"GPU acceleration enabled ({backend})")
            else:
                logger.info("Running on CPU (set n_gpu_layers to -1 for GPU)")
            
            return model
            
        except Exception as e:
            logger.error(f"Failed to load model: {e}")
            
            # Try fallback without GPU
            if n_gpu_layers > 0:
                logger.warning("Retrying without GPU acceleration...")
                return Llama(
                    model_path=str(self.model_path),
                    n_ctx=n_ctx,
                    n_threads=n_threads,
                    n_gpu_layers=0,
                    n_batch=n_batch,
                    use_mmap=use_mmap,
                    use_mlock=use_mlock,
                    verbose=False,
                )
            else:
                raise
    
    def load_model(self, model_path: str) -> None:
        """
        Switch to a different GGUF model at runtime.

        Args:
            model_path: Path to the new GGUF model file
        """
        new_path = Path(model_path)
        if not new_path.exists():
            raise FileNotFoundError(f"Model file not found: {new_path}")
        if "-of-" in new_path.name:
            raise ValueError(
                f"'{new_path.name}' is a multi-part split file -- "
                "all parts must be merged first. "
                "Use: llama-gguf-split --merge <input> <output.gguf>"
            )
        self.model_path = new_path
        logger.info(f"Switching model to: {new_path}")
        self.model = self._load_model()

    @property
    def context_length(self) -> int:
        """Configured context window size (tokens)."""
        if hasattr(self, "_context_length"):
            return self._context_length
        return int(self.config.get("model", {}).get("context_length", 8192))

    def count_tokens(self, text: str) -> int:
        """Return token count for a string."""
        if not text:
            return 0
        return len(self.model.tokenize(text.encode("utf-8"), add_bos=False))

    def generate(
        self,
        prompt: str,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        top_k: Optional[int] = None,
        repeat_penalty: Optional[float] = None,
        stop: Optional[List[str]] = None,
        stream: bool = False,
    ) -> str:
        """
        Generate text from a prompt
        
        Args:
            prompt: Input text prompt
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature (0.0-2.0)
            top_p: Nucleus sampling threshold
            top_k: Top-k sampling
            repeat_penalty: Repetition penalty
            stop: Stop sequences
            stream: Whether to stream output
            
        Returns:
            Generated text (or iterator if stream=True)
        """
        # Get generation config
        gen_config = self.config.get('generation', {})
        
        # Use provided values or defaults from config
        max_tokens = max_tokens or gen_config.get('max_tokens', 2048)
        temperature = temperature if temperature is not None else gen_config.get('temperature', 0.7)
        top_p = top_p if top_p is not None else gen_config.get('top_p', 0.9)
        top_k = top_k if top_k is not None else gen_config.get('top_k', 40)
        repeat_penalty = repeat_penalty if repeat_penalty is not None else gen_config.get('repeat_penalty', 1.1)
        stop = stop or gen_config.get('stop_sequences', [])

        prompt_tokens = self.count_tokens(prompt)
        reserve = max_tokens
        if prompt_tokens + reserve > self.context_length:
            raise ValueError(
                f"Prompt uses {prompt_tokens} tokens but context window is "
                f"{self.context_length} (need ~{reserve} more for the reply). "
                f"Enable context trimming, reduce RAG top_k, or raise model.context_length "
                f"in config.yaml and restart chat."
            )

        try:
            output = self.model(
                prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                top_p=top_p,
                top_k=top_k,
                repeat_penalty=repeat_penalty,
                stop=stop,
                stream=stream,
                echo=False,
            )
            
            if stream:
                return self._stream_output(output)
            else:
                return output['choices'][0]['text'].strip()
                
        except Exception as e:
            logger.error(f"Generation failed: {e}")
            raise
    
    def _stream_output(self, output_iterator) -> Iterator[str]:
        """
        Process streaming output
        
        Args:
            output_iterator: Iterator from llama-cpp-python
            
        Yields:
            Text chunks
        """
        for chunk in output_iterator:
            text = chunk['choices'][0]['text']
            yield text
    
    def format_chat_prompt(
        self,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None
    ) -> str:
        """
        Format messages into a chat prompt
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            system_prompt: Optional system prompt to prepend
            
        Returns:
            Formatted prompt string
        """
        # Try to detect model type from path
        model_name = self.model_path.name.lower()
        
        if 'qwen' in model_name:
            # Qwen format
            return self._format_qwen_prompt(messages, system_prompt)
        elif 'mistral' in model_name:
            # Mistral format
            return self._format_mistral_prompt(messages, system_prompt)
        elif 'llama' in model_name:
            # Llama 3 format
            return self._format_llama3_prompt(messages, system_prompt)
        else:
            # Generic ChatML format
            return self._format_chatml_prompt(messages, system_prompt)
    
    def _format_qwen_prompt(self, messages: List[Dict[str, str]], system_prompt: Optional[str]) -> str:
        """Format prompt for Qwen models"""
        formatted = ""
        
        if system_prompt:
            formatted += f"<|im_start|>system\n{system_prompt}<|im_end|>\n"
        
        for msg in messages:
            role = msg['role']
            content = msg['content']
            formatted += f"<|im_start|>{role}\n{content}<|im_end|>\n"
        
        formatted += "<|im_start|>assistant\n"
        return formatted
    
    def _format_mistral_prompt(self, messages: List[Dict[str, str]], system_prompt: Optional[str]) -> str:
        """Format prompt for Mistral models"""
        formatted = ""
        
        if system_prompt:
            formatted += f"<s>[INST] {system_prompt}\n\n"
        else:
            formatted += "<s>[INST] "
        
        for i, msg in enumerate(messages):
            if msg['role'] == 'user':
                if i > 0:
                    formatted += f"[INST] {msg['content']} [/INST]"
                else:
                    formatted += f"{msg['content']} [/INST]"
            elif msg['role'] == 'assistant':
                formatted += f" {msg['content']}</s>"
        
        return formatted
    
    def _format_llama3_prompt(self, messages: List[Dict[str, str]], system_prompt: Optional[str]) -> str:
        """Format prompt for Llama 3 models"""
        formatted = "<|begin_of_text|>"
        
        if system_prompt:
            formatted += f"<|start_header_id|>system<|end_header_id|>\n\n{system_prompt}<|eot_id|>"
        
        for msg in messages:
            role = msg['role']
            content = msg['content']
            formatted += f"<|start_header_id|>{role}<|end_header_id|>\n\n{content}<|eot_id|>"
        
        formatted += "<|start_header_id|>assistant<|end_header_id|>\n\n"
        return formatted
    
    def _format_chatml_prompt(self, messages: List[Dict[str, str]], system_prompt: Optional[str]) -> str:
        """Format prompt using generic ChatML format"""
        formatted = ""
        
        if system_prompt:
            formatted += f"<|im_start|>system\n{system_prompt}<|im_end|>\n"
        
        for msg in messages:
            role = msg['role']
            content = msg['content']
            formatted += f"<|im_start|>{role}\n{content}<|im_end|>\n"
        
        formatted += "<|im_start|>assistant\n"
        return formatted
    
    def chat(
        self,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> str:
        """
        Generate a chat response
        
        Args:
            messages: List of message dicts
            system_prompt: System prompt
            **kwargs: Additional generation parameters
            
        Returns:
            Generated response
        """
        prompt = self.format_chat_prompt(messages, system_prompt)
        return self.generate(prompt, **kwargs)
    
    def __del__(self):
        """Cleanup on deletion -- interrupt-safe."""
        if hasattr(self, 'model'):
            import signal as _signal
            orig = getattr(self, '_orig_sigint', None)
            _signal.signal(_signal.SIGINT, _signal.SIG_IGN)
            try:
                del self.model
            except KeyboardInterrupt:
                pass
            finally:
                try:
                    if orig is not None:
                        _signal.signal(_signal.SIGINT, orig)
                    else:
                        _signal.signal(_signal.SIGINT, _signal.SIG_DFL)
                except (ValueError, OSError):
                    pass
