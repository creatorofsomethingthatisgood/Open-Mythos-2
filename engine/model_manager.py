"""
Model Manager - Downloads and manages GGUF models from HuggingFace
"""

import logging
import os
from pathlib import Path
from typing import Optional, Dict, Any
import yaml
from huggingface_hub import hf_hub_download, HfApi
from tqdm import tqdm

logger = logging.getLogger(__name__)


class ModelManager:
    """Manages model downloads and model information"""
    
    def __init__(self, config_path: str = "config.yaml"):
        """
        Initialize ModelManager
        
        Args:
            config_path: Path to configuration file
        """
        self.config_path = Path(config_path)
        self.config = self._load_config()
        self.models_dir = Path("models")
        self.models_dir.mkdir(exist_ok=True)
        
    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from YAML file"""
        try:
            with open(self.config_path, 'r') as f:
                return yaml.safe_load(f)
        except Exception as e:
            logger.error(f"Failed to load config: {e}")
            return {}
    
    def get_model_info(self, model_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Get information about a model
        
        Args:
            model_name: Name of model (None for default)
            
        Returns:
            Dictionary with model information
        """
        if model_name is None:
            return self.config.get('model', {})
        
        # Check if it's in fallbacks
        for fallback in self.config.get('model', {}).get('fallbacks', []):
            if fallback['name'] == model_name:
                return fallback
        
        return {}
    
    def download_model(self, model_info: Optional[Dict[str, Any]] = None) -> Path:
        """
        Download a model from HuggingFace
        
        Args:
            model_info: Model information dict (None for default)
            
        Returns:
            Path to downloaded model file
        """
        if model_info is None:
            model_info = self.config.get('model', {})
        
        model_path = Path(model_info['path'])
        
        # Check if already exists
        if model_path.exists():
            logger.info(f"Model already exists at {model_path}")
            return model_path
        
        logger.info(f"Downloading model: {model_info['name']}")
        logger.info(f"This may take a while (~4-5GB)...")
        
        try:
            # Get repo_id and filename from config
            if 'repo_id' in model_info and 'filename' in model_info:
                repo_id = model_info['repo_id']
                filename = model_info['filename']
                logger.info(f"Using repo: {repo_id}, file: {filename}")
            elif 'download_url' in model_info:
                # Parse HuggingFace URL (fallback for old config format)
                # Format: https://huggingface.co/{repo_id}/resolve/main/{filename}
                download_url = model_info['download_url']
                parts = download_url.split('/')
                repo_id = f"{parts[3]}/{parts[4]}"
                filename = parts[-1]
                logger.info(f"Parsed from URL - repo: {repo_id}, file: {filename}")
            else:
                raise ValueError("Model config must have either repo_id+filename or download_url")
            
            # Ensure models directory exists
            model_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Download with progress bar
            logger.info(f"Downloading from HuggingFace: {repo_id}/{filename}")
            downloaded_path = hf_hub_download(
                repo_id=repo_id,
                filename=filename,
                local_dir=self.models_dir,
                local_dir_use_symlinks=False,
            )
            
            # Move to expected location if needed
            downloaded_path = Path(downloaded_path)
            if downloaded_path != model_path:
                downloaded_path.rename(model_path)
            
            # Verify file size
            file_size = model_path.stat().st_size / (1024 ** 3)  # GB
            logger.info(f"Download complete! File size: {file_size:.2f} GB")
            
            if file_size < 3.0:
                logger.warning(f"File size seems small ({file_size:.2f} GB). Download may be incomplete.")
            
            return model_path
            
        except Exception as e:
            logger.error(f"Failed to download model: {e}")
            raise
    
    def download_default(self) -> Path:
        """
        Download the default model
        
        Returns:
            Path to downloaded model
        """
        return self.download_model()
    
    def download_fallback(self, index: int = 0) -> Path:
        """
        Download a fallback model
        
        Args:
            index: Index of fallback model (0-based)
            
        Returns:
            Path to downloaded model
        """
        fallbacks = self.config.get('model', {}).get('fallbacks', [])
        if index >= len(fallbacks):
            raise ValueError(f"Fallback index {index} out of range")
        
        return self.download_model(fallbacks[index])
    
    def list_available_models(self) -> list:
        """
        List all available (downloaded) models
        
        Returns:
            List of model paths
        """
        available = []
        for path in self.models_dir.glob("*.gguf"):
            available.append(path)
        return available
    
    def find_model(self, model_name: Optional[str] = None) -> Optional[Path]:
        """
        Find a model file by name or use default
        
        Args:
            model_name: Name to search for (None for default)
            
        Returns:
            Path to model file or None if not found
        """
        if model_name is None:
            # Try default model
            default_path = Path(self.config.get('model', {}).get('path', ''))
            if default_path.exists():
                return default_path
        else:
            # Search for model by name
            for path in self.models_dir.glob("*.gguf"):
                if model_name.lower() in path.name.lower():
                    return path
        
        # Try any available model
        available = self.list_available_models()
        if available:
            logger.warning(f"Using first available model: {available[0]}")
            return available[0]
        
        return None
    
    def auto_download_if_needed(self) -> Path:
        """
        Automatically download default model if no models are available
        
        Returns:
            Path to model file
        """
        model_path = self.find_model()
        
        if model_path is None:
            logger.info("No models found. Downloading default model...")
            model_path = self.download_default()
        
        return model_path
