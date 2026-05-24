"""
File editing tools for Mythos Local.

Provides structured file operations that the LLM can invoke via special
markup in its generated output. The tool executor parses these calls,
validates them against security rules, and applies the edits.

Supported tools:
  - write_file: Create or overwrite a file
  - patch_file: Find-and-replace within a file
  - read_file: Read file contents (for the model to verify edits)
  - list_dir: List directory contents
  - create_dir: Create a directory
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tool-call markup format
# ---------------------------------------------------------------------------
# The LLM emits tool calls as XML-like blocks inside its response:
#
#   <tool_call>
#   {"name": "write_file", "arguments": {"path": "/tmp/hello.py", "content": "print('hi')"}}
#   