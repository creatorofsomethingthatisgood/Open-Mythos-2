"""
Cloud Inference Engine - OpenAI-compatible API backend for Mythos.

Uses any OpenAI-compatible endpoint (OpenAI, NVIDIA NIM, Together, etc.)
instead of a local GGUF model.
"""

import logging
import os
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

import yaml

try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False

logger = logging.getLogger(__name__)


PROVIDERS = {
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o-mini",
    },
    "nvidia": {
        "base_url": "https://integrate.api.nvidia.com/v1",
        "model": "meta/llama-3.3-70b-instruct",
    },
    "together": {
        "base_url": "https://api.together.xyz/v1",
        "model": "meta-llama/Llama-3.3-70B-Instruct-Turbo",
    },
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "model": "llama-3.3-70b-versatile",
    },
}


class CloudInferenceEngine:
    """
    Inference engine that calls an OpenAI-compatible API endpoint.
    Drop-in replacement for InferenceEngine when cloud mode is enabled.

    Supported providers: openai, nvidia, together, groq — or any custom
    OpenAI-compatible endpoint.
    """

    def __init__(self, config_path: str = "config.yaml"):
        if not HTTPX_AVAILABLE:
            raise RuntimeError(
                "httpx is required for cloud mode. Install with: pip install httpx"
            )

        self.config_path = Path(config_path)
        self.config = self._load_config()

        cloud_cfg = self.config.get("cloud", {})
        self.api_key = cloud_cfg.get("api_key") or os.environ.get("MYTHOS_API_KEY", "")

        # Provider preset: if "provider" is set, use its defaults
        provider = cloud_cfg.get("provider", "")
        preset = PROVIDERS.get(provider, {})
        self.base_url = cloud_cfg.get("base_url") or preset.get("base_url", "https://api.openai.com/v1")
        self.model_name = cloud_cfg.get("model") or preset.get("model", "gpt-4o-mini")
        self.context_length = int(
            cloud_cfg.get("context_length", 128000)
        )

        if not self.api_key:
            raise RuntimeError(
                "No API key configured. Run: mythos cloud set-key <your-key>\n"
                "Or set the MYTHOS_API_KEY environment variable."
            )

        # Strip trailing slash
        self.base_url = self.base_url.rstrip("/")

        # Verify connectivity
        self._client = httpx.Client(
            base_url=self.base_url,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            timeout=httpx.Timeout(120.0, connect=10.0),
        )
        logger.info(f"Cloud engine ready: {self.base_url} / {self.model_name}")

    # ── config ──────────────────────────────────────────────────────────

    def _load_config(self) -> Dict[str, Any]:
        try:
            with open(self.config_path, "r") as f:
                raw = yaml.safe_load(f) or {}
            from engine.chat_config import merge_chat_defaults
            return merge_chat_defaults(raw)
        except Exception as e:
            logger.error(f"Failed to load config: {e}")
            return {}

    # ── token counting (approximate) ────────────────────────────────────

    def count_tokens(self, text: str) -> int:
        """Rough token estimate (~4 chars per token for English)."""
        if not text:
            return 0
        return max(1, len(text) // 4)

    # ── chat completion ─────────────────────────────────────────────────

    def chat(
        self,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None,
        **kwargs,
    ) -> str:
        """Send a chat completion request and return the response text."""
        all_messages: List[Dict[str, str]] = []
        if system_prompt:
            all_messages.append({"role": "system", "content": system_prompt})
        all_messages.extend(messages)

        gen_config = self.config.get("generation", {})
        max_tokens = kwargs.get("max_tokens") or gen_config.get("max_tokens", 4096)
        temperature = kwargs.get("temperature") if kwargs.get("temperature") is not None else gen_config.get("temperature", 0.7)
        top_p = kwargs.get("top_p") if kwargs.get("top_p") is not None else gen_config.get("top_p", 0.9)
        stop = kwargs.get("stop") or gen_config.get("stop_sequences", [])

        body: Dict[str, Any] = {
            "model": self.model_name,
            "messages": all_messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "top_p": top_p,
            "stream": False,
        }
        if stop:
            body["stop"] = stop

        resp = self._client.post("/chat/completions", json=body)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"].strip()

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
        """Generate text from a raw prompt (wraps chat for compatibility)."""
        messages = [{"role": "user", "content": prompt}]
        return self.chat(
            messages,
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
            stop=stop,
        )

    # ── streaming ───────────────────────────────────────────────────────

    def generate_stream(
        self,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        stop: Optional[List[str]] = None,
    ) -> Iterator[str]:
        """Stream chat completion tokens."""
        all_messages: List[Dict[str, str]] = []
        if system_prompt:
            all_messages.append({"role": "system", "content": system_prompt})
        all_messages.extend(messages)

        gen_config = self.config.get("generation", {})
        body: Dict[str, Any] = {
            "model": self.model_name,
            "messages": all_messages,
            "max_tokens": max_tokens or gen_config.get("max_tokens", 4096),
            "temperature": temperature if temperature is not None else gen_config.get("temperature", 0.7),
            "top_p": top_p if top_p is not None else gen_config.get("top_p", 0.9),
            "stream": True,
        }
        if stop:
            body["stop"] = stop

        with self._client.stream("POST", "/chat/completions", json=body, timeout=httpx.Timeout(180.0, connect=10.0)) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line or not line.startswith("data: "):
                    continue
                payload = line[6:]
                if payload.strip() == "[DONE]":
                    break
                import json
                try:
                    chunk = json.loads(payload)
                    delta = chunk["choices"][0].get("delta", {})
                    content = delta.get("content", "")
                    if content:
                        yield content
                except (json.JSONDecodeError, KeyError, IndexError):
                    continue

    # ── format helpers (kept for interface compat) ──────────────────────

    def format_chat_prompt(
        self,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None,
    ) -> str:
        """Not used for cloud, but kept for interface compatibility."""
        parts = []
        if system_prompt:
            parts.append(f"System: {system_prompt}")
        for m in messages:
            parts.append(f"{m['role'].capitalize()}: {m['content']}")
        return "\n\n".join(parts)

    # ── cleanup ─────────────────────────────────────────────────────────

    def __del__(self):
        if hasattr(self, "_client"):
            try:
                self._client.close()
            except Exception:
                pass
