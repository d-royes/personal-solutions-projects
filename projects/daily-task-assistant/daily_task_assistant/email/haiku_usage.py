"""Haiku Usage Tracking and Settings Storage.

This module provides usage tracking and settings management for the
Haiku Intelligence Layer. Tracks daily/weekly API call counts and
provides settings for enabling/disabling Haiku and setting limits.

IMPORTANT: Settings and usage are GLOBAL (not per-login-identity).
David has multiple login emails but ONE shared settings/usage state.
This prevents bypassing daily limits by switching login identities.

Firestore Structure:
    global/david/haiku_usage/current -> usage counters
    global/david/settings/haiku -> user settings

File Storage (dev mode):
    haiku_usage/global_settings.json
    haiku_usage/global_usage.json

Environment Variables:
    DTA_HAIKU_FORCE_FILE: Set to "1" to use local file storage (dev mode)
    DTA_HAIKU_STORAGE_DIR: Directory for file-based storage (default: haiku_usage/)
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, Optional

from ..firestore import get_firestore_client


# =============================================================================
# Configuration
# =============================================================================

# Global user identifier (settings/usage are shared across all login identities)
GLOBAL_USER_ID = "david"

DEFAULT_DAILY_LIMIT = 50
DEFAULT_WEEKLY_LIMIT = 200


def _force_file_fallback() -> bool:
    """Check if file-based storage should be used (dev mode)."""
    return os.getenv("DTA_HAIKU_FORCE_FILE", "0") == "1"


def _storage_dir() -> Path:
    """Return the directory for file-based storage."""
    default_dir = Path(__file__).resolve().parents[2] / "haiku_usage"
    return Path(os.getenv("DTA_HAIKU_STORAGE_DIR", str(default_dir)))


def _now() -> datetime:
    """Return current UTC datetime."""
    return datetime.now(timezone.utc)


def _get_daily_reset_time() -> datetime:
    """Get the next daily reset time (midnight UTC)."""
    now = _now()
    tomorrow = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    return tomorrow


def _get_weekly_reset_time() -> datetime:
    """Get the next weekly reset time (Monday midnight UTC)."""
    now = _now()
    # Days until next Monday (0 = Monday)
    days_until_monday = (7 - now.weekday()) % 7
    if days_until_monday == 0 and now.hour >= 0:
        # If it's Monday but past midnight, next Monday
        days_until_monday = 7
    next_monday = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=days_until_monday)
    return next_monday


# =============================================================================
# Dataclasses
# =============================================================================

@dataclass
class HaikuSettings:
    """User settings for Haiku analysis.

    Attributes:
        enabled: Whether Haiku analysis is enabled
        daily_limit: Maximum emails to analyze per day
        weekly_limit: Maximum emails to analyze per week
        updated_at: When settings were last updated
    """
    enabled: bool = True
    daily_limit: int = DEFAULT_DAILY_LIMIT
    weekly_limit: int = DEFAULT_WEEKLY_LIMIT
    updated_at: datetime = field(default_factory=_now)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "enabled": self.enabled,
            "daily_limit": self.daily_limit,
            "weekly_limit": self.weekly_limit,
            "updated_at": self.updated_at.isoformat(),
        }

    def to_api_dict(self) -> Dict[str, Any]:
        """Convert to API-friendly dict (camelCase)."""
        return {
            "enabled": self.enabled,
            "dailyLimit": self.daily_limit,
            "weeklyLimit": self.weekly_limit,
            "updatedAt": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "HaikuSettings":
        """Create from dictionary."""
        updated_at = data.get("updated_at")
        if isinstance(updated_at, str):
            updated_at = datetime.fromisoformat(updated_at)
        elif updated_at is None:
            updated_at = _now()

        return cls(
            enabled=data.get("enabled", True),
            daily_limit=data.get("daily_limit", DEFAULT_DAILY_LIMIT),
            weekly_limit=data.get("weekly_limit", DEFAULT_WEEKLY_LIMIT),
            updated_at=updated_at,
        )


@dataclass
class HaikuUsage:
    """Current Haiku usage counters.

    Attributes:
        daily_count: Emails analyzed today
        weekly_count: Emails analyzed this week
        daily_reset_at: When daily counter resets
        weekly_reset_at: When weekly counter resets
    """
    daily_count: int = 0
    weekly_count: int = 0
    daily_reset_at: datetime = field(default_factory=_get_daily_reset_time)
    weekly_reset_at: datetime = field(default_factory=_get_weekly_reset_time)

    def is_daily_expired(self) -> bool:
        """Check if daily counter should reset."""
        return _now() >= self.daily_reset_at

    def is_weekly_expired(self) -> bool:
        """Check if weekly counter should reset."""
        return _now() >= self.weekly_reset_at

    def reset_if_expired(self) -> bool:
        """Reset counters if expired. Returns True if any counter was reset."""
        reset_occurred = False

        if self.is_daily_expired():
            self.daily_count = 0
            self.daily_reset_at = _get_daily_reset_time()
            reset_occurred = True

        if self.is_weekly_expired():
            self.weekly_count = 0
            self.weekly_reset_at = _get_weekly_reset_time()
            reset_occurred = True

        return reset_occurred

    def can_analyze(self, settings: HaikuSettings) -> bool:
        """Check if we're under both limits.

        Args:
            settings: Current user settings with limits

        Returns:
            True if analysis is allowed
        """
        if not settings.enabled:
            return False

        # Reset expired counters first
        self.reset_if_expired()

        return (
            self.daily_count < settings.daily_limit and
            self.weekly_count < settings.weekly_limit
        )

    def increment(self) -> None:
        """Increment both daily and weekly counters."""
        self.daily_count += 1
        self.weekly_count += 1

    def remaining_daily(self, settings: HaikuSettings) -> int:
        """Get remaining daily quota."""
        self.reset_if_expired()
        return max(0, settings.daily_limit - self.daily_count)

    def remaining_weekly(self, settings: HaikuSettings) -> int:
        """Get remaining weekly quota."""
        self.reset_if_expired()
        return max(0, settings.weekly_limit - self.weekly_count)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "daily_count": self.daily_count,
            "weekly_count": self.weekly_count,
            "daily_reset_at": self.daily_reset_at.isoformat(),
            "weekly_reset_at": self.weekly_reset_at.isoformat(),
        }

    def to_api_dict(self, settings: HaikuSettings) -> Dict[str, Any]:
        """Convert to API-friendly dict with computed fields."""
        self.reset_if_expired()
        return {
            "dailyCount": self.daily_count,
            "weeklyCount": self.weekly_count,
            "dailyLimit": settings.daily_limit,
            "weeklyLimit": settings.weekly_limit,
            "dailyRemaining": self.remaining_daily(settings),
            "weeklyRemaining": self.remaining_weekly(settings),
            "dailyResetAt": self.daily_reset_at.isoformat(),
            "weeklyResetAt": self.weekly_reset_at.isoformat(),
            "enabled": settings.enabled,
            "canAnalyze": self.can_analyze(settings),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "HaikuUsage":
        """Create from dictionary."""
        def parse_dt(val) -> datetime:
            if isinstance(val, str):
                return datetime.fromisoformat(val)
            elif isinstance(val, datetime):
                return val
            return _now()

        return cls(
            daily_count=data.get("daily_count", 0),
            weekly_count=data.get("weekly_count", 0),
            daily_reset_at=parse_dt(data.get("daily_reset_at")) if data.get("daily_reset_at") else _get_daily_reset_time(),
            weekly_reset_at=parse_dt(data.get("weekly_reset_at")) if data.get("weekly_reset_at") else _get_weekly_reset_time(),
        )


# =============================================================================
# Settings CRUD
# =============================================================================

def get_settings() -> HaikuSettings:
    """Get GLOBAL Haiku settings.

    Settings are shared across all login identities.

    Returns:
        HaikuSettings (defaults if not found)
    """
    if _force_file_fallback():
        return _get_settings_file()
    return _get_settings_firestore()


def _get_settings_file() -> HaikuSettings:
    """Get settings from file storage."""
    file_path = _storage_dir() / "global_settings.json"

    if not file_path.exists():
        return HaikuSettings()

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return HaikuSettings.from_dict(data)
    except (json.JSONDecodeError, KeyError):
        return HaikuSettings()


def _get_settings_firestore() -> HaikuSettings:
    """Get settings from Firestore."""
    db = get_firestore_client()
    if db is None:
        return _get_settings_file()

    doc_ref = (
        db.collection("global")
        .document(GLOBAL_USER_ID)
        .collection("settings")
        .document("haiku")
    )
    doc = doc_ref.get()

    if not doc.exists:
        return HaikuSettings()

    return HaikuSettings.from_dict(doc.to_dict())


def save_settings(settings: HaikuSettings) -> None:
    """Save GLOBAL Haiku settings.

    Settings are shared across all login identities.

    Args:
        settings: HaikuSettings to save
    """
    settings.updated_at = _now()

    if _force_file_fallback():
        _save_settings_file(settings)
    else:
        _save_settings_firestore(settings)


def _save_settings_file(settings: HaikuSettings) -> None:
    """Save settings to file storage."""
    storage_dir = _storage_dir()
    storage_dir.mkdir(parents=True, exist_ok=True)

    file_path = storage_dir / "global_settings.json"
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(settings.to_dict(), f, indent=2)


def _save_settings_firestore(settings: HaikuSettings) -> None:
    """Save settings to Firestore."""
    db = get_firestore_client()
    if db is None:
        _save_settings_file(settings)
        return

    doc_ref = (
        db.collection("global")
        .document(GLOBAL_USER_ID)
        .collection("settings")
        .document("haiku")
    )
    doc_ref.set(settings.to_dict())


# =============================================================================
# Usage CRUD
# =============================================================================

def get_usage() -> HaikuUsage:
    """Get GLOBAL Haiku usage counters.

    Usage is shared across all login identities to prevent
    bypassing limits by switching accounts.

    Returns:
        HaikuUsage (fresh counters if not found)
    """
    if _force_file_fallback():
        return _get_usage_file()
    return _get_usage_firestore()


def _get_usage_file() -> HaikuUsage:
    """Get usage from file storage."""
    file_path = _storage_dir() / "global_usage.json"

    if not file_path.exists():
        return HaikuUsage()

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        usage = HaikuUsage.from_dict(data)
        # Reset expired counters
        if usage.reset_if_expired():
            _save_usage_file(usage)
        return usage
    except (json.JSONDecodeError, KeyError):
        return HaikuUsage()


def _get_usage_firestore() -> HaikuUsage:
    """Get usage from Firestore."""
    db = get_firestore_client()
    if db is None:
        return _get_usage_file()

    doc_ref = (
        db.collection("global")
        .document(GLOBAL_USER_ID)
        .collection("haiku_usage")
        .document("current")
    )
    doc = doc_ref.get()

    if not doc.exists:
        return HaikuUsage()

    usage = HaikuUsage.from_dict(doc.to_dict())
    # Reset expired counters
    if usage.reset_if_expired():
        _save_usage_firestore(usage)
    return usage


def save_usage(usage: HaikuUsage) -> None:
    """Save GLOBAL Haiku usage counters.

    Args:
        usage: HaikuUsage to save
    """
    if _force_file_fallback():
        _save_usage_file(usage)
    else:
        _save_usage_firestore(usage)


def _save_usage_file(usage: HaikuUsage) -> None:
    """Save usage to file storage."""
    storage_dir = _storage_dir()
    storage_dir.mkdir(parents=True, exist_ok=True)

    file_path = storage_dir / "global_usage.json"
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(usage.to_dict(), f, indent=2)


def _save_usage_firestore(usage: HaikuUsage) -> None:
    """Save usage to Firestore."""
    db = get_firestore_client()
    if db is None:
        _save_usage_file(usage)
        return

    doc_ref = (
        db.collection("global")
        .document(GLOBAL_USER_ID)
        .collection("haiku_usage")
        .document("current")
    )
    doc_ref.set(usage.to_dict())


def increment_usage() -> HaikuUsage:
    """Increment GLOBAL usage counters and save.

    Returns:
        Updated HaikuUsage
    """
    usage = get_usage()
    usage.increment()
    save_usage(usage)
    return usage


# =============================================================================
# Combined Operations
# =============================================================================

def can_use_haiku() -> bool:
    """Check if Haiku analysis is available.

    Checks both settings (enabled) and GLOBAL usage limits.
    This is shared across all login identities.

    Returns:
        True if Haiku can be used
    """
    settings = get_settings()
    if not settings.enabled:
        return False

    usage = get_usage()
    return usage.can_analyze(settings)


def get_usage_summary() -> Dict[str, Any]:
    """Get a complete GLOBAL usage summary for the API.

    Returns:
        Dictionary with settings and usage data for API response
    """
    settings = get_settings()
    usage = get_usage()
    return usage.to_api_dict(settings)
