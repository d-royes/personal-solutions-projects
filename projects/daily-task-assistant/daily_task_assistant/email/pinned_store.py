"""Pinned Email Store - persistent storage for pinned emails.

This module provides the PinnedRecord dataclass and Firestore CRUD operations
for storing pinned emails. Pinned emails allow David to quickly reference
emails he's actively working with.

IMPORTANT: Pins are stored by EMAIL ACCOUNT (not login identity).
David has multiple login emails but data is keyed by "church" or "personal".

Firestore Structure:
    email_accounts/{account}/pinned/{email_id} -> PinnedRecord document

File Storage (dev mode):
    pinned_store/{account}/{email_id}.json

Environment Variables:
    DTA_PINNED_FORCE_FILE: Set to "1" to use local file storage (dev mode)
    DTA_PINNED_DIR: Directory for file-based storage (default: pinned_store/)
    DTA_PINNED_TTL_DAYS: Days to keep unpinned emails (default: 30)
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..firestore import get_firestore_client


# Configuration helpers
def _force_file_fallback() -> bool:
    """Check if file-based storage should be used (dev mode)."""
    return os.getenv("DTA_PINNED_FORCE_FILE", "0") == "1"


def _pinned_dir() -> Path:
    """Return the directory for file-based pinned storage."""
    return Path(
        os.getenv(
            "DTA_PINNED_DIR",
            Path(__file__).resolve().parents[2] / "pinned_store",
        )
    )


def _ttl_days() -> int:
    """Return TTL for unpinned emails in days (from unpin date)."""
    return int(os.getenv("DTA_PINNED_TTL_DAYS", "30"))


def _now() -> datetime:
    """Return current UTC datetime."""
    return datetime.now(timezone.utc)


@dataclass
class PinnedRecord:
    """Persistent record for a pinned email.

    Represents an email that David has pinned for quick reference.
    Supports soft delete via unpinned_at with TTL-based cleanup.

    Attributes:
        email_id: Gmail message ID (used as document key)
        account: "church" or "personal"
        pinned_at: When the email was pinned
        unpinned_at: When unpinned (None if still pinned)
        subject: Email subject (cached for display)
        from_address: Sender email address
        snippet: Email preview snippet
        thread_id: Gmail thread ID (for conversation loading)
    """
    email_id: str
    account: str
    subject: str
    from_address: str
    snippet: str
    thread_id: Optional[str] = None
    pinned_at: datetime = field(default_factory=_now)
    unpinned_at: Optional[datetime] = None

    @property
    def is_active(self) -> bool:
        """Check if this email is currently pinned."""
        return self.unpinned_at is None

    @property
    def is_expired(self) -> bool:
        """Check if this unpinned record has expired (30-day TTL from unpin)."""
        if self.unpinned_at is None:
            return False
        return _now() > self.unpinned_at + timedelta(days=_ttl_days())

    def to_dict(self) -> Dict[str, Any]:
        """Convert record to dictionary for storage."""
        def dt_to_str(dt: Optional[datetime]) -> Optional[str]:
            return dt.isoformat() if dt else None

        return {
            "email_id": self.email_id,
            "account": self.account,
            "subject": self.subject,
            "from_address": self.from_address,
            "snippet": self.snippet,
            "thread_id": self.thread_id,
            "pinned_at": dt_to_str(self.pinned_at),
            "unpinned_at": dt_to_str(self.unpinned_at),
        }

    def to_api_dict(self) -> Dict[str, Any]:
        """Convert to API-friendly dict for frontend."""
        return {
            "emailId": self.email_id,
            "account": self.account,
            "subject": self.subject,
            "fromAddress": self.from_address,
            "snippet": self.snippet,
            "threadId": self.thread_id,
            "pinnedAt": self.pinned_at.isoformat() if self.pinned_at else None,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PinnedRecord":
        """Create record from dictionary."""
        def str_to_dt(s: Optional[str]) -> Optional[datetime]:
            if s is None:
                return None
            return datetime.fromisoformat(s)

        return cls(
            email_id=data["email_id"],
            account=data["account"],
            subject=data.get("subject", ""),
            from_address=data.get("from_address", ""),
            snippet=data.get("snippet", ""),
            thread_id=data.get("thread_id"),
            pinned_at=str_to_dt(data.get("pinned_at")) or _now(),
            unpinned_at=str_to_dt(data.get("unpinned_at")),
        )


# =============================================================================
# CRUD Operations
# =============================================================================

def _save_pinned(account: str, record: PinnedRecord) -> None:
    """Save a pinned record to storage.

    Args:
        account: Email account ("church" or "personal")
        record: PinnedRecord to save
    """
    if _force_file_fallback():
        _save_pinned_file(account, record)
    else:
        _save_pinned_firestore(account, record)


def _save_pinned_file(account: str, record: PinnedRecord) -> None:
    """Save pinned record to file storage."""
    store_dir = _pinned_dir() / account
    store_dir.mkdir(parents=True, exist_ok=True)

    file_path = store_dir / f"{record.email_id}.json"
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(record.to_dict(), f, indent=2)


def _save_pinned_firestore(account: str, record: PinnedRecord) -> None:
    """Save pinned record to Firestore."""
    db = get_firestore_client()
    if db is None:
        _save_pinned_file(account, record)
        return

    doc_ref = (
        db.collection("email_accounts")
        .document(account)
        .collection("pinned")
        .document(record.email_id)
    )
    doc_ref.set(record.to_dict())


def _get_pinned(account: str, email_id: str) -> Optional[PinnedRecord]:
    """Get a single pinned record.

    Args:
        account: Email account ("church" or "personal")
        email_id: Gmail message ID

    Returns:
        PinnedRecord if found, None otherwise
    """
    if _force_file_fallback():
        return _get_pinned_file(account, email_id)
    return _get_pinned_firestore(account, email_id)


def _get_pinned_file(account: str, email_id: str) -> Optional[PinnedRecord]:
    """Get pinned record from file storage."""
    file_path = _pinned_dir() / account / f"{email_id}.json"
    if not file_path.exists():
        return None

    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    return PinnedRecord.from_dict(data)


def _get_pinned_firestore(account: str, email_id: str) -> Optional[PinnedRecord]:
    """Get pinned record from Firestore."""
    db = get_firestore_client()
    if db is None:
        return _get_pinned_file(account, email_id)

    doc_ref = (
        db.collection("email_accounts")
        .document(account)
        .collection("pinned")
        .document(email_id)
    )
    doc = doc_ref.get()

    if not doc.exists:
        return None

    return PinnedRecord.from_dict(doc.to_dict())


def _delete_pinned(account: str, email_id: str) -> None:
    """Delete a pinned record from storage.

    Args:
        account: Email account ("church" or "personal")
        email_id: Gmail message ID
    """
    if _force_file_fallback():
        _delete_pinned_file(account, email_id)
    else:
        _delete_pinned_firestore(account, email_id)


def _delete_pinned_file(account: str, email_id: str) -> None:
    """Delete pinned record from file storage."""
    file_path = _pinned_dir() / account / f"{email_id}.json"
    if file_path.exists():
        file_path.unlink()


def _delete_pinned_firestore(account: str, email_id: str) -> None:
    """Delete pinned record from Firestore."""
    db = get_firestore_client()
    if db is None:
        _delete_pinned_file(account, email_id)
        return

    doc_ref = (
        db.collection("email_accounts")
        .document(account)
        .collection("pinned")
        .document(email_id)
    )
    doc_ref.delete()


# =============================================================================
# Public API
# =============================================================================

def pin_email(
    account: str,
    email_id: str,
    subject: str,
    from_address: str,
    snippet: str,
    thread_id: Optional[str] = None,
) -> PinnedRecord:
    """Pin an email for quick reference.

    If the email was previously pinned and unpinned, re-pins it.

    Args:
        account: Email account ("church" or "personal")
        email_id: Gmail message ID
        subject: Email subject line
        from_address: Sender email address
        snippet: Email preview snippet
        thread_id: Gmail thread ID (for loading conversation history)

    Returns:
        The created/updated PinnedRecord
    """
    # Check if already exists (may have been unpinned)
    existing = _get_pinned(account, email_id)

    if existing:
        # Re-pin: clear unpinned_at, update metadata
        existing.unpinned_at = None
        existing.pinned_at = _now()
        existing.subject = subject
        existing.from_address = from_address
        existing.snippet = snippet
        existing.thread_id = thread_id
        _save_pinned(account, existing)
        return existing

    # Create new pin
    record = PinnedRecord(
        email_id=email_id,
        account=account,
        subject=subject,
        from_address=from_address,
        snippet=snippet,
        thread_id=thread_id,
        pinned_at=_now(),
        unpinned_at=None,
    )
    _save_pinned(account, record)
    return record


def unpin_email(account: str, email_id: str) -> bool:
    """Unpin an email (soft delete with TTL).

    Sets unpinned_at timestamp. Record will be deleted after 30 days.

    Args:
        account: Email account ("church" or "personal")
        email_id: Gmail message ID

    Returns:
        True if unpinned, False if not found
    """
    record = _get_pinned(account, email_id)
    if record is None:
        return False

    record.unpinned_at = _now()
    _save_pinned(account, record)
    return True


def get_pinned_emails(account: str, include_unpinned: bool = False) -> List[PinnedRecord]:
    """Get all pinned emails for an account.

    Args:
        account: Email account ("church" or "personal")
        include_unpinned: If True, include soft-deleted (unpinned) records

    Returns:
        List of PinnedRecords sorted by pinned_at descending (newest first)
    """
    if _force_file_fallback():
        return _get_pinned_emails_file(account, include_unpinned)
    return _get_pinned_emails_firestore(account, include_unpinned)


def _get_pinned_emails_file(account: str, include_unpinned: bool) -> List[PinnedRecord]:
    """Get pinned emails from file storage."""
    store_dir = _pinned_dir() / account
    if not store_dir.exists():
        return []

    records = []
    for file_path in store_dir.glob("*.json"):
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        record = PinnedRecord.from_dict(data)

        # Skip expired records (cleanup happens separately)
        if record.is_expired:
            continue

        # Skip unpinned unless requested
        if not include_unpinned and not record.is_active:
            continue

        records.append(record)

    # Sort by pinned_at descending (newest first)
    records.sort(key=lambda r: r.pinned_at, reverse=True)
    return records


def _get_pinned_emails_firestore(account: str, include_unpinned: bool) -> List[PinnedRecord]:
    """Get pinned emails from Firestore."""
    db = get_firestore_client()
    if db is None:
        return _get_pinned_emails_file(account, include_unpinned)

    collection_ref = (
        db.collection("email_accounts")
        .document(account)
        .collection("pinned")
    )

    records = []
    for doc in collection_ref.stream():
        record = PinnedRecord.from_dict(doc.to_dict())

        # Skip expired records
        if record.is_expired:
            continue

        # Skip unpinned unless requested
        if not include_unpinned and not record.is_active:
            continue

        records.append(record)

    # Sort by pinned_at descending (newest first)
    records.sort(key=lambda r: r.pinned_at, reverse=True)
    return records


def is_pinned(account: str, email_id: str) -> bool:
    """Check if an email is currently pinned.

    Args:
        account: Email account ("church" or "personal")
        email_id: Gmail message ID

    Returns:
        True if email is pinned (active), False otherwise
    """
    record = _get_pinned(account, email_id)
    if record is None:
        return False
    return record.is_active


def cleanup_expired(account: str) -> int:
    """Delete expired unpinned records (30+ days since unpin).

    Args:
        account: Email account ("church" or "personal")

    Returns:
        Count of records deleted
    """
    if _force_file_fallback():
        return _cleanup_expired_file(account)
    return _cleanup_expired_firestore(account)


def _cleanup_expired_file(account: str) -> int:
    """Cleanup expired records from file storage."""
    store_dir = _pinned_dir() / account
    if not store_dir.exists():
        return 0

    count = 0
    for file_path in store_dir.glob("*.json"):
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        record = PinnedRecord.from_dict(data)

        if record.is_expired:
            file_path.unlink()
            count += 1

    return count


def _cleanup_expired_firestore(account: str) -> int:
    """Cleanup expired records from Firestore."""
    db = get_firestore_client()
    if db is None:
        return _cleanup_expired_file(account)

    collection_ref = (
        db.collection("email_accounts")
        .document(account)
        .collection("pinned")
    )

    count = 0
    cutoff = (_now() - timedelta(days=_ttl_days())).isoformat()

    # Query for unpinned records older than TTL
    query = collection_ref.where("unpinned_at", "<=", cutoff)

    for doc in query.stream():
        doc.reference.delete()
        count += 1

    return count
