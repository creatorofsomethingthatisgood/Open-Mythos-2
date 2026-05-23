"""
Platform detection and backend defaults for cross-platform inference.
"""

import platform
import sys
from typing import Tuple


def is_macos() -> bool:
    return sys.platform == "darwin"


def is_linux() -> bool:
    return sys.platform.startswith("linux")


def get_default_gpu_layers(config_gpu_layers: int) -> int:
    """
    Return effective GPU layer count based on platform and config.

    On Apple Silicon, n_gpu_layers=0 in config means "use Metal" (-1).
    On Linux AMD, 0 means CPU-only unless the user sets layers explicitly.
    """
    if config_gpu_layers != 0:
        return config_gpu_layers

    if is_macos() and platform.machine() == "arm64":
        return -1

    return 0


def get_backend_name(n_gpu_layers: int) -> str:
    """Human-readable backend name for logging."""
    if n_gpu_layers == 0:
        return "CPU"

    if is_macos():
        return "Metal (Apple GPU)"

    if is_linux():
        return "Vulkan (AMD GPU)"

    return "GPU"


def get_setup_script() -> str:
    """Return the recommended setup script for this platform."""
    if is_macos():
        return "./setup-macos.sh"
    return "./setup.sh"
