"""Calendar Attention Store - persistent storage for calendar attention items.

This module provides Firestore CRUD operations for storing calendar attention
items that require David's action. Follows the same pattern as email/attention_store.py.

Storage is keyed by calendar ACCOUNT (church/personal/work), not user ID, so the
same data is accessible regardless of which user identity is used to log in.

Firestore Structure:
    email_accounts/{account}/calendar_attention/{event_id} -> CalendarAttentionRecord

File Storage Structure:
    calendar_attention_store/{account}/{event_id}.json

Environment Variables:
    DTA_CALENDAR_ATTENTION_FORCE_FILE: Set to "1" to use local file storage (dev mode)
    DTA_CALENDAR_ATTENTION_DIR: Directory for file-based storage
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..firestore import get_firestore_client
from .types import CalendarAttentionRecord, _now


# Configuration helpers
def _force_file_fallback() -> bool:
    """Check if file-based storage should be used (dev mode)."""
    return os.getenv("DTA_CALENDAR_ATTENTION_FORCE_FILE", "0") == "1"


def _attention_dir() -> Path:
    """Return the directory for file-based calendar attention storage."""
    return Path(
        os.getenv(
            "DTA_CALENDAR_ATTENTION_DIR",
            Path(__file__).resolve().parents[2] / "calendar_attention_store",
        )
    )


# =============================================================================
# CRUD Operations
# =============================================================================

def save_attention(account: str, record: CalendarAttentionRecord) -> None:
    """Save a calendar attention record to storage.

    Args:
        account: Calendar account ("church", "personal", or "work")
        record: CalendarAttentionRecord to save
    """
    if _force_file_fallback():
        _save_attention_file(account, record)
    else:
        _save_attention_firestore(account, record)


def _save_attention_file(account: str, record: CalendarAttentionRecord) -> None:
    """Save attention record to file storage."""
    store_dir = _attention_dir() / account
    store_dir.mkdir(parents=True, exist_ok=True)

    file_path = store_dir / f"{record.event_id}.json"
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(record.to_dict(), f, indent=2)


def _save_attention_firestore(account: str, record: CalendarAttentionRecord) -> None:
    """Save attention record to Firestore."""
    db = get_firestore_client()
    if db is None:
        _save_attention_file(account, record)
        return

    doc_ref = (
        db.collection("email_accounts")
        .document(account)
        .collection("calendar_attention")
        .document(record.event_id)
    )
    doc_ref.set(record.to_dict())


def get_attention(account: str, event_id: str) -> Optional[CalendarAttentionRecord]:
    """Get a single calendar attention record.

    Args:
        account: Calendar account ("church", "personal", or "work")
        event_id: Google Calendar event ID

    Returns:
        CalendarAttentionRecord if found, None otherwise
    """
    if _force_file_fallback():
        return _get_attention_file(account, event_id)
    return _get_attention_firestore(account, event_id)


def _get_attention_file(account: str, event_id: str) -> Optional[CalendarAttentionRecord]:
    """Get attention record from file storage."""
    file_path = _attention_dir() / account / f"{event_id}.json"
    if not file_path.exists():
        return None

    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    record = CalendarAttentionRecord.from_dict(data)

    # Check expiration
    if record.is_expired():
        file_path.unlink()
        return None

    return record


def _get_attention_firestore(account: str, event_id: str) -> Optional[CalendarAttentionRecord]:
    """Get attention record from Firestore."""
    db = get_firestore_client()
    if db is None:
        return _get_attention_file(account, event_id)

    doc_ref = (
        db.collection("email_accounts")
        .document(account)
        .collection("calendar_attention")
        .document(event_id)
    )
    doc = doc_ref.get()

    if not doc.exists:
        return None

    record = CalendarAttentionRecord.from_dict(doc.to_dict())

    # Check expiration
    if record.is_expired():
        doc_ref.delete()
        return None

    return record


def list_active_attention(account: str) -> List[CalendarAttentionRecord]:
    """List all active attention items for a calendar account.

    Args:
        account: Calendar account ("church", "personal", or "work")

    Returns:
        List of active CalendarAttentionRecords, sorted by start time
    """
    if _force_file_fallback():
        return _list_active_attention_file(account)
    return _list_active_attention_firestore(account)


def _list_active_attention_file(account: str) -> List[CalendarAttentionRecord]:
    """List active attention records from file storage."""
    store_dir = _attention_dir() / account
    if not store_dir.exists():
        return []

    records = []
    for file_path in store_dir.glob("*.json"):
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        record = CalendarAttentionRecord.from_dict(data)

        # Skip expired records (and delete them)
        if record.is_expired():
            file_path.unlink()
            continue

        # Skip non-active records
        if record.status != "active":
            continue

        records.append(record)

    # Sort by start time (upcoming first)
    records.sort(key=lambda r: r.start)
    return records


def _list_active_attention_firestore(account: str) -> List[CalendarAttentionRecord]:
    """List active attention records from Firestore."""
    db = get_firestore_client()
    if db is None:
        return _list_active_attention_file(account)

    collection_ref = (
        db.collection("email_accounts")
        .document(account)
        .collection("calendar_attention")
    )

    # Query for active items
    query = collection_ref.where("status", "==", "active")

    records = []
    for doc in query.stream():
        record = CalendarAttentionRecord.from_dict(doc.to_dict())

        # Skip expired
        if record.is_expired():
            doc.reference.delete()
            continue

        records.append(record)

    # Sort by start time (upcoming first)
    records.sort(key=lambda r: r.start)
    return records


def is_already_analyzed(account: str, event_id: str) -> bool:
    """Check if an event has already been analyzed.

    Args:
        account: Calendar account ("church", "personal", or "work")
        event_id: Google Calendar event ID

    Returns:
        True if event has a stored attention record
    """
    return get_attention(account, event_id) is not None


def dismiss_attention(account: str, event_id: str) -> bool:
    """Dismiss a calendar attention item.

    Args:
        account: Calendar account ("church", "personal", or "work")
        event_id: Google Calendar event ID

    Returns:
        True if successfully dismissed, False if not found
    """
    record = get_attention(account, event_id)
    if record is None:
        return False

    record.status = "dismissed"
    record.dismissed_at = _now()

    # Phase 1A: Record action tracking
    record.action_taken_at = _now()
    record.action_type = "dismissed"

    save_attention(account, record)
    return True


def mark_acted(account: str, event_id: str, action_type: str = "task_linked") -> bool:
    """Mark a calendar attention item as acted upon.

    Args:
        account: Calendar account ("church", "personal", or "work")
        event_id: Google Calendar event ID
        action_type: What action was taken ("task_linked", "prep_started")

    Returns:
        True if successfully updated, False if not found
    """
    record = get_attention(account, event_id)
    if record is None:
        return False

    record.status = "acted"
    record.action_taken_at = _now()
    record.action_type = action_type

    save_attention(account, record)
    return True


# =============================================================================
# Phase 1A: Quality Tracking Functions
# =============================================================================

def mark_viewed(account: str, event_id: str) -> bool:
    """Record when a user first views a calendar attention item.

    Only sets first_viewed_at if it hasn't been set already.

    Args:
        account: Calendar account ("church", "personal", or "work")
        event_id: Google Calendar event ID

    Returns:
        True if successfully updated, False if not found
    """
    record = get_attention(account, event_id)
    if record is None:
        return False

    # Only set first_viewed_at once
    if record.first_viewed_at is None:
        record.first_viewed_at = _now()
        save_attention(account, record)

    return True


def get_quality_metrics(account: str, days: int = 30) -> Dict[str, Any]:
    """Get quality metrics for calendar attention items.

    Args:
        account: Calendar account ("church", "personal", or "work")
        days: Number of days to look back

    Returns:
        Dictionary with quality metrics including acceptance rates
    """
    from datetime import timedelta

    cutoff = _now() - timedelta(days=days)

    # Get all attention records
    if _force_file_fallback():
        records = _get_all_records_file(account)
    else:
        records = _get_all_records_firestore(account)

    # Filter by date
    filtered = [r for r in records if r.created_at >= cutoff]

    # Aggregate metrics
    total = len(filtered)
    by_status = {"active": 0, "dismissed": 0, "acted": 0, "expired": 0}
    by_type = {"vip_meeting": 0, "prep_needed": 0, "task_conflict": 0, "overcommitment": 0}
    by_action = {"viewed": 0, "dismissed": 0, "task_linked": 0, "prep_started": 0}

    for record in filtered:
        by_status[record.status] = by_status.get(record.status, 0) + 1
        by_type[record.attention_type] = by_type.get(record.attention_type, 0) + 1
        if record.action_type:
            by_action[record.action_type] = by_action.get(record.action_type, 0) + 1

    # Calculate acceptance rate (acted / total shown)
    accepted = by_status.get("acted", 0)
    acceptance_rate = accepted / total if total > 0 else 0.0

    return {
        "total": total,
        "by_status": by_status,
        "by_type": by_type,
        "by_action": by_action,
        "acceptance_rate": acceptance_rate,
        "dismissed_rate": by_action.get("dismissed", 0) / total if total > 0 else 0.0,
    }


def _get_all_records_file(account: str) -> List[CalendarAttentionRecord]:
    """Get all attention records from file storage."""
    store_dir = _attention_dir() / account
    if not store_dir.exists():
        return []

    records = []
    for file_path in store_dir.glob("*.json"):
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        records.append(CalendarAttentionRecord.from_dict(data))

    return records


def _get_all_records_firestore(account: str) -> List[CalendarAttentionRecord]:
    """Get all attention records from Firestore."""
    db = get_firestore_client()
    if db is None:
        return _get_all_records_file(account)

    collection_ref = (
        db.collection("email_accounts")
        .document(account)
        .collection("calendar_attention")
    )

    records = []
    for doc in collection_ref.stream():
        records.append(CalendarAttentionRecord.from_dict(doc.to_dict()))

    return records


def purge_expired_records(account: str) -> int:
    """Purge expired attention records for a calendar account.

    Args:
        account: Calendar account ("church", "personal", or "work")

    Returns:
        Count of records purged
    """
    if _force_file_fallback():
        return _purge_expired_file(account)
    return _purge_expired_firestore(account)


def _purge_expired_file(account: str) -> int:
    """Purge expired records from file storage."""
    store_dir = _attention_dir() / account
    if not store_dir.exists():
        return 0

    count = 0
    for file_path in store_dir.glob("*.json"):
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        record = CalendarAttentionRecord.from_dict(data)
        if record.is_expired():
            file_path.unlink()
            count += 1

    return count


def _purge_expired_firestore(account: str) -> int:
    """Purge expired records from Firestore."""
    db = get_firestore_client()
    if db is None:
        return _purge_expired_file(account)

    collection_ref = (
        db.collection("email_accounts")
        .document(account)
        .collection("calendar_attention")
    )
    now_str = _now().isoformat()

    # Query for expired items
    query = collection_ref.where("expires_at", "<", now_str)

    count = 0
    for doc in query.stream():
        doc.reference.delete()
        count += 1

    return count
