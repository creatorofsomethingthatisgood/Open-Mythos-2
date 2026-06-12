"""Model Manager - Downloads and manages GGUF models from HuggingFace"""

import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any
import yaml
from huggingface_hub import hf_hub_download, HfApi
from tqdm import tqdm

logger = logging.getLogger(__name__)


class ModelManager:
	"""Manages model downloads and model information"""

	def __init__(self, config_path: str = "config.yaml"):
		self.config_path = Path(config_path)
		self.config = self._load_config()
		self.models_dir = self._resolve_models_dir()
		self.models_dir.mkdir(parents=True, exist_ok=True)

	def _resolve_models_dir(self) -> Path:
		model_path = Path(self.config.get("model", {}).get("path", "models/model.gguf"))
		if model_path.is_absolute():
			return model_path.parent
		if self.config_path.is_absolute():
			return (self.config_path.parent / model_path).parent
		return Path("models")

	def _load_config(self) -> Dict[str, Any]:
		try:
			with open(self.config_path, 'r') as f:
				return yaml.safe_load(f)
		except Exception as e:
			logger.error(f"Failed to load config: {e}")
			return {}

	def get_model_info(self, model_name: Optional[str] = None) -> Dict[str, Any]:
		if model_name is None:
			return self.config.get('model', {})
		for fallback in self.config.get('model', {}).get('fallbacks', []):
			if fallback['name'] == model_name:
				return fallback
		return {}

	def download_model(self, model_info: Optional[Dict[str, Any]] = None) -> Path:
		"""Download a model from HuggingFace.

		Delegates to the native V binary if available (supporting parallel chunk curl downloads).
		Otherwise uses aria2c (16 parallel connections + resume) when available,
		otherwise falls back to huggingface_hub (single connection).
		"""
		if model_info is None:
			model_info = self.config.get('model', {})

		model_path = Path(model_info['path'])

		# Check if already exists and is large enough to be valid
		if model_path.exists():
			size_mb = model_path.stat().st_size / (1024 * 1024)
			if size_mb > 100:
				logger.info(f"Model already exists at {model_path} ({size_mb:.0f} MB)")
				return model_path
			logger.info(f"Partial download detected ({size_mb:.0f} MB), re-downloading...")

		# Check if compiled V binary exists
		project_root = Path(__file__).resolve().parent.parent
		v_binary = project_root / "mythos-v" / "build" / "mythos"
		if v_binary.exists() and os.access(v_binary, os.X_OK):
			logger.info("V binary found, delegating model download for native parallel chunk performance...")
			try:
				cmd = [str(v_binary), "model", "download"]
				result = subprocess.run(cmd, cwd=str(project_root))
				if result.returncode == 0 and model_path.exists():
					return model_path
				else:
					logger.warning(f"V model downloader exited with code {result.returncode}. Falling back to Python.")
			except Exception as e:
				logger.warning(f"Failed to run V downloader: {e}. Falling back to Python.")

		logger.info(f"Downloading model: {model_info['name']}")

		try:
			if 'repo_id' in model_info and 'filename' in model_info:
				repo_id = model_info['repo_id']
				filename = model_info['filename']
			elif 'download_url' in model_info:
				download_url = model_info['download_url']
				parts = download_url.split('/')
				repo_id = f"{parts[3]}/{parts[4]}"
				filename = parts[-1]
			else:
				raise ValueError("Model config must have either repo_id+filename or download_url")

			model_path.parent.mkdir(parents=True, exist_ok=True)
			url = f"https://huggingface.co/{repo_id}/resolve/main/{filename}"

			# Try to use V-compiled downloader for maximum speed (Native Parallel Orchestration)
			v_binary = Path("mythos-v/build/mythos")
			if v_binary.exists():
				logger.info("Using high-performance V-native downloader (Native Parallel Orchestrator)")
				try:
					import subprocess
					result = subprocess.run([str(v_binary), "model", "download"])
					if result.returncode == 0 and model_path.exists():
						return model_path
				except Exception as ve:
					logger.warning(f"V downloader failed, falling back to aria2c: {ve}")

			# Try aria2c first (much faster: 16 parallel connections + resume)
			if shutil.which('aria2c'):
				self._download_aria2c(url, model_path)
			else:
				logger.info("aria2c not found, using huggingface_hub (single connection)")
				logger.info("Install aria2c for 5-10x faster downloads: apt install aria2")
				logger.info(f"Downloading from HuggingFace: {repo_id}/{filename}")
				downloaded_path = hf_hub_download(
					repo_id=repo_id,
					filename=filename,
					local_dir=self.models_dir,
					local_dir_use_symlinks=False,
				)
				downloaded_path = Path(downloaded_path)
				if downloaded_path != model_path:
					downloaded_path.rename(model_path)

			# Verify file size
			file_size = model_path.stat().st_size / (1024 ** 3)
			logger.info(f"Download complete! File size: {file_size:.2f} GB")

			if file_size < 0.5:
				logger.warning(f"File size seems small ({file_size:.2f} GB). Download may be incomplete.")

			return model_path

		except Exception as e:
			logger.error(f"Failed to download model: {e}")
			raise

	def _download_aria2c(self, url: str, dest: Path) -> None:
		"""Download using aria2c with 16 parallel connections and resume support."""
		logger.info(f"Downloading with aria2c (16 parallel connections + resume)")
		logger.info(f"URL: {url}")
		cmd = [
			'aria2c',
			'--console-log-level=warn',
			'--summary-interval=1',
			'-x', '16',             # 16 connections per server
			'-s', '16',             # 16 parallel streams
			'-k', '1M',             # 1MB min chunk size
			'-c',                   # continue/resume partial downloads
			'--max-tries=5',
			'--retry-wait=5',
			'--file-allocation=falloc',
			'--max-download-limit=0',
			'-d', str(dest.parent),
			'-o', dest.name,
			url,
		]
		result = subprocess.run(cmd)
		if result.returncode != 0:
			raise RuntimeError(f"aria2c failed with exit code {result.returncode}")

	def download_default(self) -> Path:
		return self.download_model()

	def download_fallback(self, index: int = 0) -> Path:
		fallbacks = self.config.get('model', {}).get('fallbacks', [])
		if index >= len(fallbacks):
			raise ValueError(f"Fallback index {index} out of range")
		return self.download_model(fallbacks[index])

	def list_available_models(self) -> list:
		available = []
		for path in self.models_dir.glob("*.gguf"):
			if "-of-" in path.name:
				continue
			available.append(path)
		return sorted(available)

	def find_model(self, model_name: Optional[str] = None) -> Optional[Path]:
		if model_name is None:
			default_path = Path(self.config.get('model', {}).get('path', ''))
			if default_path.exists():
				return default_path
		else:
			for path in self.models_dir.glob("*.gguf"):
				if model_name.lower() in path.name.lower():
					return path

		available = self.list_available_models()
		if available:
			logger.warning(f"Using first available model: {available[0]}")
			return available[0]

		return None

	def auto_download_if_needed(self) -> Path:
		model_path = self.find_model()
		if model_path is None:
			logger.info("No models found. Downloading default model...")
			model_path = self.download_default()
		return model_path
