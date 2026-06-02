"""
Skill marketplace for Mythos.

Fetches skill listings from a GitHub-based JSON index.
Skills are served as raw files from the GitHub repository.

URL layout on GitHub (main branch):
  skills/marketplace/index.json        - listing of all available skills
  skills/<skill_name>/manifest.yaml    - skill metadata
  skills/<skill_name>/skill.py         - skill handler code

Community members add skills by opening a PR that adds a new
directory under skills/ and registers it in the index.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from engine.skills import SkillManager

logger = logging.getLogger(__name__)

# Base URL for raw files on the main branch
_REPO_RAW = (
    "https://raw.githubusercontent.com/creatorofsomethingthatisgood"
    "/Open-Mythos-2/main"
)

DEFAULT_MARKETPLACE_INDEX_URL = f"{_REPO_RAW}/skills/marketplace/index.json"
DEFAULT_MARKETPLACE_SKILLS_URL = f"{_REPO_RAW}/skills"


class MarketplaceClient:
    """Client for the Mythos skill marketplace."""

    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        # Allow overrides from config, otherwise use defaults
        self.index_url = self.config.get(
            "marketplace_index_url", DEFAULT_MARKETPLACE_INDEX_URL
        )
        self.skills_base_url = self.config.get(
            "marketplace_skills_url", DEFAULT_MARKETPLACE_SKILLS_URL
        )
        # Legacy: if old marketplace_url key is set, derive both from it
        legacy_url = self.config.get("marketplace_url")
        if legacy_url:
            self.index_url = f"{legacy_url}/marketplace/index.json"
            self.skills_base_url = legacy_url
        self._httpx = None
        self._urllib = None

    def _get_http(self):
        """Lazily load an HTTP library."""
        if self._httpx is not None:
            return self._httpx, "httpx"
        try:
            import httpx
            self._httpx = httpx
            return self._httpx, "httpx"
        except ImportError:
            pass
        import urllib.request
        self._urllib = urllib.request
        return self._urllib, "urllib"

    def _fetch(self, url: str, timeout: float = 15.0) -> str:
        """Fetch a URL and return the text content."""
        lib, kind = self._get_http()
        if kind == "httpx":
            resp = lib.get(url, timeout=timeout, follow_redirects=True)
            resp.raise_for_status()
            return resp.text
        else:
            req = lib.Request(url, headers={"User-Agent": "Mythos-SkillMarketplace/1.0"})
            with lib.urlopen(req, timeout=timeout) as resp:
                return resp.read().decode("utf-8")

    def fetch_index(self) -> List[Dict[str, Any]]:
        """
        Fetch the marketplace skill index from GitHub.
        Returns a list of skill metadata dicts.
        """
        try:
            text = self._fetch(self.index_url)
            data = json.loads(text)
            if isinstance(data, list):
                return data
            if isinstance(data, dict) and "skills" in data:
                return data["skills"]
            return []
        except Exception as e:
            logger.warning("Failed to fetch marketplace index: %s", e)
            return []

    def fetch_skill_files(self, skill_name: str) -> Optional[Dict[str, str]]:
        """
        Fetch a skill's manifest.yaml and skill.py from GitHub.
        Returns {"manifest": "...", "script": "..."} or None on failure.
        """
        try:
            manifest_url = f"{self.skills_base_url}/{skill_name}/manifest.yaml"
            script_url = f"{self.skills_base_url}/{skill_name}/skill.py"
            manifest = self._fetch(manifest_url)
            script = self._fetch(script_url)
            return {"manifest": manifest, "script": script}
        except Exception as e:
            logger.warning("Failed to fetch skill '%s': %s", skill_name, e)
            return None

    def search(self, query: str) -> List[Dict[str, Any]]:
        """Search marketplace skills by query (matches name, description, tags)."""
        index = self.fetch_index()
        q = query.lower()
        results = []
        for skill in index:
            name = skill.get("name", "").lower()
            desc = skill.get("description", "").lower()
            tags = " ".join(skill.get("tags", [])).lower()
            if q in name or q in desc or q in tags:
                results.append(skill)
        return results

    def install(self, skill_name: str, manager: SkillManager) -> Optional[str]:
        """
        Download and install a skill from the marketplace.
        Returns the skill name on success, None on failure.
        """
        files = self.fetch_skill_files(skill_name)
        if files is None:
            return None
        try:
            skill = manager.install_from_manifest_data(
                name=skill_name,
                manifest_yaml=files["manifest"],
                skill_py=files["script"],
            )
            # Update cache
            cache = manager.load_marketplace_cache()
            for entry in cache:
                if entry.get("name") == skill_name:
                    entry["installed"] = True
                    break
            manager.save_marketplace_cache(cache)
            return skill.name
        except Exception as e:
            logger.error("Failed to install skill '%s': %s", skill_name, e)
            return None

    def list_available(self, manager: SkillManager) -> List[Dict[str, Any]]:
        """
        List all marketplace skills, marking which are already installed.
        """
        index = self.fetch_index()
        installed_names = {s.name for s in manager.list_skills()}
        for skill in index:
            skill["installed"] = skill.get("name") in installed_names
        # Cache for offline use
        manager.save_marketplace_cache(index)
        return index
