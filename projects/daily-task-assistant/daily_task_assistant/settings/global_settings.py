"""Global settings storage in Firestore.

This module manages application-wide settings stored in Firestore at
`settings/preferences`. Settings are shared across all email accounts
(work/church) since David is a single logical user.

Supported settings:
- inactivity_timeout_minutes: Auto-logout timeout (0=disabled, 5, 10, 15, 30)
- sync: Bidirectional sync configuration
  - enabled: Whether automated sync is active
  - interval_minutes: Sync frequency (5, 15, 30, 60)
  - last_sync_at: Timestamp of last sync
  - last_sync_result: Summary of last sync operation
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Dict, Optional

from daily_task_assistant.firestore import get_firestore_client


# Firestore path for global settings
SETTINGS_COLLECTION = "settings"
SETTINGS_DOCUMENT = "preferences"


@dataclass
class SyncSettings:
    """Sync-specific settings."""
    enabled: bool = True
    interval_minutes: int = 30  # 5, 15, 30, 60
    last_sync_at: Optional[str] = None  # ISO timestamp
    last_sync_result: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "enabled": self.enabled,
            "interval_minutes": self.interval_minutes,
            "last_sync_at": self.last_sync_at,
            "last_sync_result": self.last_sync_result,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SyncSettings":
        return cls(
            enabled=data.get("enabled", True),
            interval_minutes=data.get("interval_minutes", 30),
            last_sync_at=data.get("last_sync_at"),
            last_sync_result=data.get("last_sync_result"),
        )


@dataclass
class GlobalSettings:
    """Global application settings."""
    inactivity_timeout_minutes: int = 15  # 0=disabled, 5, 10, 15, 30
    sync: SyncSettings = field(default_factory=SyncSettings)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "inactivity_timeout_minutes": self.inactivity_timeout_minutes,
            "sync": self.sync.to_dict(),
        }
    
    def to_api_dict(self) -> Dict[str, Any]:
        """Return camelCase dict for API responses."""
        return {
            "inactivityTimeoutMinutes": self.inactivity_timeout_minutes,
            "sync": {
                "enabled": self.sync.enabled,
                "intervalMinutes": self.sync.interval_minutes,
                "lastSyncAt": self.sync.last_sync_at,
                "lastSyncResult": self.sync.last_sync_result,
            },
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GlobalSettings":
        sync_data = data.get("sync", {})
        return cls(
            inactivity_timeout_minutes=data.get("inactivity_timeout_minutes", 15),
            sync=SyncSettings.from_dict(sync_data),
        )


# Default settings for new installations
DEFAULT_SETTINGS = GlobalSettings()


def get_settings() -> GlobalSettings:
    """Fetch global settings from Firestore.
    
    Returns:
        GlobalSettings with current values, or defaults if not found.
    """
    db = get_firestore_client()
    doc_ref = db.collection(SETTINGS_COLLECTION).document(SETTINGS_DOCUMENT)
    doc = doc_ref.get()
    
    if doc.exists:
        return GlobalSettings.from_dict(doc.to_dict())
    
    # Return defaults (don't create document until explicit save)
    return GlobalSettings()


def update_settings(updates: Dict[str, Any]) -> GlobalSettings:
    """Update global settings in Firestore.
    
    Args:
        updates: Partial settings to update. Supports nested updates for sync:
            - {"inactivity_timeout_minutes": 30}
            - {"sync": {"enabled": False}}
            - {"sync": {"interval_minutes": 15}}
            
    Returns:
        Updated GlobalSettings.
    """
    db = get_firestore_client()
    doc_ref = db.collection(SETTINGS_COLLECTION).document(SETTINGS_DOCUMENT)
    
    # Get current settings
    current = get_settings()
    current_dict = current.to_dict()
    
    # Apply updates (handle nested sync updates)
    if "inactivity_timeout_minutes" in updates:
        current_dict["inactivity_timeout_minutes"] = updates["inactivity_timeout_minutes"]
    
    if "sync" in updates and isinstance(updates["sync"], dict):
        # Merge sync updates
        for key, value in updates["sync"].items():
            current_dict["sync"][key] = value
    
    # Save to Firestore
    doc_ref.set(current_dict)
    
    return GlobalSettings.from_dict(current_dict)


def record_sync_result(result: Dict[str, Any]) -> GlobalSettings:
    """Record the result of a sync operation.
    
    Args:
        result: Sync result containing created, updated, errors, etc.
        
    Returns:
        Updated GlobalSettings.
    """
    sync_updates = {
        "last_sync_at": datetime.utcnow().isoformat() + "Z",
        "last_sync_result": {
            "created": result.get("created", 0),
            "updated": result.get("updated", 0),
            "unchanged": result.get("unchanged", 0),
            "conflicts": result.get("conflicts", 0),
            "errors": result.get("errors", 0),
            "total_processed": result.get("total_processed", 0),
            "success": result.get("success", True),
        },
    }
    
    return update_settings({"sync": sync_updates})


def should_run_scheduled_sync() -> bool:
    """Check if a scheduled sync should run based on settings and timing.
    
    Used by Cloud Scheduler endpoint to determine if sync should execute.
    
    Returns:
        True if sync is enabled and enough time has passed since last sync.
    """
    settings = get_settings()
    
    # Check if sync is enabled
    if not settings.sync.enabled:
        return False
    
    # If never synced, run now
    if not settings.sync.last_sync_at:
        return True
    
    # Check if enough time has passed
    try:
        last_sync = datetime.fromisoformat(settings.sync.last_sync_at.replace("Z", "+00:00"))
        now = datetime.utcnow().replace(tzinfo=last_sync.tzinfo)
        minutes_since_last = (now - last_sync).total_seconds() / 60
        
        # Run if at least interval_minutes have passed (with 1 min buffer)
        return minutes_since_last >= (settings.sync.interval_minutes - 1)
    except (ValueError, TypeError):
        # If parsing fails, run sync
        return True
