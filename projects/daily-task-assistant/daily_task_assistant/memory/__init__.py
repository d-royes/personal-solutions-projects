"""Memory package for DATA persistent profile and knowledge storage."""
from __future__ import annotations

from .profile import (
    DavidProfile,
    get_profile,
    save_profile,
    get_default_profile,
    get_or_create_profile,
)

__all__ = [
    "DavidProfile",
    "get_profile",
    "save_profile",
    "get_default_profile",
    "get_or_create_profile",
]
