"""Calendar Store - persistent storage for calendar settings.

This module provides Firestore CRUD operations for storing calendar settings
per email account. Settings include enabled calendars, work calendar designation,
and display preferences.

Storage is keyed by email ACCOUNT (church/personal), not user ID, so the same
data is accessible regardless of which user identity is used to log in.

Firestore Structure:
    email_accounts/{account}/calendar_settings/config -> CalendarSettings document

File Storage Structure:
    calendar_store/{account}/settings.json

Environment Variables:
    DTA_CALENDAR_FORCE_FILE: Set to "1" to use local file storage (dev mode)
    DTA_CALENDAR_DIR: Directory for file-based storage (default: calendar_store/)
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from ..firestore import get_firestore_client
from .types import CalendarSettings


# Default settings for each account type
DEFAULT_CALENDAR_SETTINGS: Dict[str, CalendarSettings] = {
    "personal": CalendarSettings(
        enabled_calendars=[],  # Will be populated on first load
        work_calendar_id=None,  # User designates which is "work"
        show_declined_events=False,
        show_all_day_events=True,
        default_days_ahead=14,
    ),
    "church": CalendarSettings(
        enabled_calendars=[],
        work_calendar_id=None,
        show_declined_events=False,
        show_all_day_events=True,
        default_days_ahead=14,
    ),
}


# ============================================================================
# Configuration Helpers
# ============================================================================


def _force_file_fallback() -> bool:
    """Check if file-based storage should be used (dev mode)."""
    return os.getenv("DTA_CALENDAR_FORCE_FILE", "0") == "1"


def _calendar_store_dir() -> Path:
    """Return the directory for file-based calendar storage."""
    return Path(
        os.getenv(
            "DTA_CALENDAR_DIR",
            Path(__file__).resolve().parents[2] / "calendar_store",
        )
    )


def _now() -> datetime:
    """Return current UTC datetime."""
    return datetime.now(timezone.utc)


def _settings_to_dict(settings: CalendarSettings) -> Dict[str, Any]:
    """Convert CalendarSettings to storage dict."""
    return {
        "enabled_calendars": settings.enabled_calendars,
        "work_calendar_id": settings.work_calendar_id,
        "show_declined_events": settings.show_declined_events,
        "show_all_day_events": settings.show_all_day_events,
        "default_days_ahead": settings.default_days_ahead,
        "last_synced_at": settings.last_synced_at.isoformat() if settings.last_synced_at else None,
    }


def _dict_to_settings(data: Dict[str, Any]) -> CalendarSettings:
    """Convert storage dict to CalendarSettings."""
    last_synced = None
    if data.get("last_synced_at"):
        last_synced = datetime.fromisoformat(data["last_synced_at"])

    return CalendarSettings(
        enabled_calendars=data.get("enabled_calendars", []),
        work_calendar_id=data.get("work_calendar_id"),
        show_declined_events=data.get("show_declined_events", False),
        show_all_day_events=data.get("show_all_day_events", True),
        default_days_ahead=data.get("default_days_ahead", 14),
        last_synced_at=last_synced,
    )


# ============================================================================
# CRUD Operations
# ============================================================================


def get_calendar_settings(account: str) -> CalendarSettings:
    """Get calendar settings for an email account.

    Args:
        account: Email account ("church" or "personal")

    Returns:
        CalendarSettings for the account (defaults if not found)
    """
    if _force_file_fallback():
        return _get_settings_file(account)
    return _get_settings_firestore(account)


def _get_settings_file(account: str) -> CalendarSettings:
    """Get calendar settings from file storage."""
    file_path = _calendar_store_dir() / account / "settings.json"

    if not file_path.exists():
        return DEFAULT_CALENDAR_SETTINGS.get(account, CalendarSettings())

    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    return _dict_to_settings(data)


def _get_settings_firestore(account: str) -> CalendarSettings:
    """Get calendar settings from Firestore."""
    db = get_firestore_client()
    if db is None:
        return _get_settings_file(account)

    doc_ref = (
        db.collection("email_accounts")
        .document(account)
        .collection("calendar_settings")
        .document("config")
    )
    doc = doc_ref.get()

    if not doc.exists:
        return DEFAULT_CALENDAR_SETTINGS.get(account, CalendarSettings())

    return _dict_to_settings(doc.to_dict())


def save_calendar_settings(account: str, settings: CalendarSettings) -> None:
    """Save calendar settings for an email account.

    Args:
        account: Email account ("church" or "personal")
        settings: CalendarSettings to save
    """
    # Update last synced timestamp
    settings.last_synced_at = _now()

    if _force_file_fallback():
        _save_settings_file(account, settings)
    else:
        _save_settings_firestore(account, settings)


def _save_settings_file(account: str, settings: CalendarSettings) -> None:
    """Save calendar settings to file storage."""
    store_dir = _calendar_store_dir() / account
    store_dir.mkdir(parents=True, exist_ok=True)

    file_path = store_dir / "settings.json"
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(_settings_to_dict(settings), f, indent=2)


def _save_settings_firestore(account: str, settings: CalendarSettings) -> None:
    """Save calendar settings to Firestore."""
    db = get_firestore_client()
    if db is None:
        # Fall back to file storage if Firestore unavailable
        _save_settings_file(account, settings)
        return

    doc_ref = (
        db.collection("email_accounts")
        .document(account)
        .collection("calendar_settings")
        .document("config")
    )
    doc_ref.set(_settings_to_dict(settings))


def update_enabled_calendars(account: str, calendar_ids: list) -> CalendarSettings:
    """Update the list of enabled calendars.

    Args:
        account: Email account ("church" or "personal")
        calendar_ids: List of calendar IDs to enable

    Returns:
        Updated CalendarSettings
    """
    settings = get_calendar_settings(account)
    settings.enabled_calendars = calendar_ids
    save_calendar_settings(account, settings)
    return settings


def set_work_calendar(account: str, calendar_id: Optional[str]) -> CalendarSettings:
    """Designate which calendar represents "work" in this account.

    Args:
        account: Email account (typically "personal" since work calendar is shared there)
        calendar_id: Calendar ID to designate as work calendar (or None to clear)

    Returns:
        Updated CalendarSettings
    """
    settings = get_calendar_settings(account)
    settings.work_calendar_id = calendar_id
    save_calendar_settings(account, settings)
    return settings
