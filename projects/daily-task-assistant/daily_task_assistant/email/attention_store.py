"""Attention Store - persistent storage for email attention items.

This module provides the AttentionRecord dataclass and Firestore CRUD operations
for storing attention items that require David's action. Persistence ensures
that dismissed items stay dismissed and analysis results don't require re-computation.

Firestore Structure:
    users/{user_id}/email_attention/{email_id} -> AttentionRecord document

Environment Variables:
    DTA_ATTENTION_FORCE_FILE: Set to "1" to use local file storage (dev mode)
    DTA_ATTENTION_DIR: Directory for file-based storage (default: attention_store/)
    DTA_ATTENTION_TTL_ACTIVE: Days to keep active items (default: 30)
    DTA_ATTENTION_TTL_DISMISSED: Days to keep dismissed items (default: 7)
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from ..firestore import get_firestore_client


# Type aliases
AttentionStatus = Literal["active", "dismissed", "snoozed", "task_created"]
DismissReason = Literal["not_actionable", "handled", "false_positive"]
AnalysisMethod = Literal["regex", "haiku", "profile_match"]
UrgencyLevel = Literal["high", "medium", "low"]


# Configuration helpers
def _force_file_fallback() -> bool:
    """Check if file-based storage should be used (dev mode)."""
    return os.getenv("DTA_ATTENTION_FORCE_FILE", "0") == "1"


def _attention_dir() -> Path:
    """Return the directory for file-based attention storage."""
    return Path(
        os.getenv(
            "DTA_ATTENTION_DIR",
            Path(__file__).resolve().parents[2] / "attention_store",
        )
    )


def _ttl_active_days() -> int:
    """Return TTL for active attention items in days."""
    return int(os.getenv("DTA_ATTENTION_TTL_ACTIVE", "30"))


def _ttl_dismissed_days() -> int:
    """Return TTL for dismissed attention items in days."""
    return int(os.getenv("DTA_ATTENTION_TTL_DISMISSED", "7"))


def _now() -> datetime:
    """Return current UTC datetime."""
    return datetime.now(timezone.utc)


def _sanitize_user_id(user_id: str) -> str:
    """Sanitize user ID for use as filename."""
    return user_id.replace("@", "_at_").replace(".", "_")


@dataclass
class AttentionRecord:
    """Persistent attention item.

    Represents an email that has been flagged as requiring David's attention.
    Includes analysis results, status tracking, and TTL management.

    Attributes:
        email_id: Gmail message ID
        email_account: "church" or "personal"
        user_id: User identifier (email address)
        subject: Email subject line
        from_address: Sender email address
        from_name: Sender display name (optional)
        date: Email date
        snippet: Email preview snippet
        reason: Why attention is needed
        urgency: "high", "medium", or "low"
        confidence: Confidence score 0.0-1.0
        suggested_action: e.g., "Create task", "Reply needed"
        extracted_task: Suggested task title (optional)
        matched_role: Which profile role triggered this (optional)
        status: "active", "dismissed", "snoozed", "task_created"
        dismissed_at: When item was dismissed (optional)
        dismissed_reason: Why item was dismissed (optional)
        snoozed_until: Snooze expiration (optional)
        linked_task_id: Created task ID (optional)
        analyzed_at: When analysis was performed
        analysis_method: "regex", "haiku", or "profile_match"
        created_at: Record creation time
        expires_at: TTL expiration time
    """
    # Identity
    email_id: str
    email_account: str
    user_id: str

    # Email snapshot
    subject: str
    from_address: str
    date: datetime
    snippet: str
    from_name: Optional[str] = None
    labels: List[str] = field(default_factory=list)  # Gmail label IDs

    # Analysis results
    reason: str = ""
    urgency: UrgencyLevel = "medium"
    confidence: float = 0.5
    suggested_action: Optional[str] = None
    extracted_task: Optional[str] = None
    matched_role: Optional[str] = None

    # Status
    status: AttentionStatus = "active"
    dismissed_at: Optional[datetime] = None
    dismissed_reason: Optional[DismissReason] = None
    snoozed_until: Optional[datetime] = None
    linked_task_id: Optional[str] = None

    # Analysis metadata
    analyzed_at: datetime = field(default_factory=_now)
    analysis_method: AnalysisMethod = "regex"

    # TTL
    created_at: datetime = field(default_factory=_now)
    expires_at: Optional[datetime] = None

    def __post_init__(self):
        """Set default expires_at based on status."""
        if self.expires_at is None:
            self._update_expiration()

    def _update_expiration(self):
        """Update expiration based on current status."""
        if self.status == "dismissed":
            self.expires_at = _now() + timedelta(days=_ttl_dismissed_days())
        else:
            self.expires_at = _now() + timedelta(days=_ttl_active_days())

    def is_expired(self) -> bool:
        """Check if this record has expired."""
        if self.expires_at is None:
            return False
        return _now() > self.expires_at

    def to_dict(self) -> Dict[str, Any]:
        """Convert record to dictionary for storage."""
        def dt_to_str(dt: Optional[datetime]) -> Optional[str]:
            return dt.isoformat() if dt else None

        return {
            "email_id": self.email_id,
            "email_account": self.email_account,
            "user_id": self.user_id,
            "subject": self.subject,
            "from_address": self.from_address,
            "from_name": self.from_name,
            "date": dt_to_str(self.date),
            "snippet": self.snippet,
            "labels": self.labels,
            "reason": self.reason,
            "urgency": self.urgency,
            "confidence": self.confidence,
            "suggested_action": self.suggested_action,
            "extracted_task": self.extracted_task,
            "matched_role": self.matched_role,
            "status": self.status,
            "dismissed_at": dt_to_str(self.dismissed_at),
            "dismissed_reason": self.dismissed_reason,
            "snoozed_until": dt_to_str(self.snoozed_until),
            "linked_task_id": self.linked_task_id,
            "analyzed_at": dt_to_str(self.analyzed_at),
            "analysis_method": self.analysis_method,
            "created_at": dt_to_str(self.created_at),
            "expires_at": dt_to_str(self.expires_at),
        }

    def to_api_dict(self) -> Dict[str, Any]:
        """Convert to API-friendly dict (camelCase for JavaScript)."""
        def dt_to_str(dt: Optional[datetime]) -> Optional[str]:
            return dt.isoformat() if dt else None

        return {
            "emailId": self.email_id,
            "emailAccount": self.email_account,
            "subject": self.subject,
            "fromAddress": self.from_address,
            "fromName": self.from_name,
            "date": dt_to_str(self.date),
            "snippet": self.snippet,
            "labels": self.labels,
            "reason": self.reason,
            "urgency": self.urgency,
            "confidence": self.confidence,
            "suggestedAction": self.suggested_action,
            "extractedTask": self.extracted_task,
            "matchedRole": self.matched_role,
            "status": self.status,
            "dismissedAt": dt_to_str(self.dismissed_at),
            "dismissedReason": self.dismissed_reason,
            "snoozedUntil": dt_to_str(self.snoozed_until),
            "linkedTaskId": self.linked_task_id,
            "analyzedAt": dt_to_str(self.analyzed_at),
            "analysisMethod": self.analysis_method,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AttentionRecord":
        """Create record from dictionary."""
        def str_to_dt(s: Optional[str]) -> Optional[datetime]:
            if s is None:
                return None
            return datetime.fromisoformat(s)

        return cls(
            email_id=data["email_id"],
            email_account=data["email_account"],
            user_id=data["user_id"],
            subject=data["subject"],
            from_address=data["from_address"],
            from_name=data.get("from_name"),
            date=str_to_dt(data["date"]) or _now(),
            snippet=data.get("snippet", ""),
            labels=data.get("labels", []),
            reason=data.get("reason", ""),
            urgency=data.get("urgency", "medium"),
            confidence=data.get("confidence", 0.5),
            suggested_action=data.get("suggested_action"),
            extracted_task=data.get("extracted_task"),
            matched_role=data.get("matched_role"),
            status=data.get("status", "active"),
            dismissed_at=str_to_dt(data.get("dismissed_at")),
            dismissed_reason=data.get("dismissed_reason"),
            snoozed_until=str_to_dt(data.get("snoozed_until")),
            linked_task_id=data.get("linked_task_id"),
            analyzed_at=str_to_dt(data.get("analyzed_at")) or _now(),
            analysis_method=data.get("analysis_method", "regex"),
            created_at=str_to_dt(data.get("created_at")) or _now(),
            expires_at=str_to_dt(data.get("expires_at")),
        )


# =============================================================================
# CRUD Operations
# =============================================================================

def save_attention(user_id: str, record: AttentionRecord) -> None:
    """Save an attention record to storage.

    Args:
        user_id: User identifier (email address)
        record: AttentionRecord to save
    """
    if _force_file_fallback():
        _save_attention_file(user_id, record)
    else:
        _save_attention_firestore(user_id, record)


def _save_attention_file(user_id: str, record: AttentionRecord) -> None:
    """Save attention record to file storage."""
    store_dir = _attention_dir() / _sanitize_user_id(user_id)
    store_dir.mkdir(parents=True, exist_ok=True)

    file_path = store_dir / f"{record.email_id}.json"
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(record.to_dict(), f, indent=2)


def _save_attention_firestore(user_id: str, record: AttentionRecord) -> None:
    """Save attention record to Firestore."""
    db = get_firestore_client()
    if db is None:
        # Fall back to file storage if Firestore unavailable
        _save_attention_file(user_id, record)
        return

    doc_ref = db.collection("users").document(user_id).collection("email_attention").document(record.email_id)
    doc_ref.set(record.to_dict())


def get_attention(user_id: str, email_id: str) -> Optional[AttentionRecord]:
    """Get a single attention record.

    Args:
        user_id: User identifier
        email_id: Gmail message ID

    Returns:
        AttentionRecord if found, None otherwise
    """
    if _force_file_fallback():
        return _get_attention_file(user_id, email_id)
    return _get_attention_firestore(user_id, email_id)


def _get_attention_file(user_id: str, email_id: str) -> Optional[AttentionRecord]:
    """Get attention record from file storage."""
    file_path = _attention_dir() / _sanitize_user_id(user_id) / f"{email_id}.json"
    if not file_path.exists():
        return None

    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    record = AttentionRecord.from_dict(data)

    # Check expiration
    if record.is_expired():
        file_path.unlink()
        return None

    return record


def _get_attention_firestore(user_id: str, email_id: str) -> Optional[AttentionRecord]:
    """Get attention record from Firestore."""
    db = get_firestore_client()
    if db is None:
        return _get_attention_file(user_id, email_id)

    doc_ref = db.collection("users").document(user_id).collection("email_attention").document(email_id)
    doc = doc_ref.get()

    if not doc.exists:
        return None

    record = AttentionRecord.from_dict(doc.to_dict())

    # Check expiration
    if record.is_expired():
        doc_ref.delete()
        return None

    return record


def list_active_attention(
    user_id: str,
    account: Optional[str] = None,
) -> List[AttentionRecord]:
    """List all active attention items for a user.

    Args:
        user_id: User identifier
        account: Optional filter by email account ("church" or "personal")

    Returns:
        List of active AttentionRecords
    """
    if _force_file_fallback():
        return _list_active_attention_file(user_id, account)
    return _list_active_attention_firestore(user_id, account)


def _list_active_attention_file(
    user_id: str,
    account: Optional[str] = None,
) -> List[AttentionRecord]:
    """List active attention records from file storage."""
    store_dir = _attention_dir() / _sanitize_user_id(user_id)
    if not store_dir.exists():
        return []

    records = []
    for file_path in store_dir.glob("*.json"):
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        record = AttentionRecord.from_dict(data)

        # Skip expired records (and delete them)
        if record.is_expired():
            file_path.unlink()
            continue

        # Skip non-active records
        if record.status != "active":
            # Check if snoozed item should be reactivated
            if record.status == "snoozed" and record.snoozed_until:
                if _now() >= record.snoozed_until:
                    record.status = "active"
                    record.snoozed_until = None
                    save_attention(user_id, record)
                else:
                    continue
            else:
                continue

        # Filter by account if specified
        if account and record.email_account != account:
            continue

        records.append(record)

    # Sort by date descending (newest first)
    records.sort(key=lambda r: r.date, reverse=True)
    return records


def _list_active_attention_firestore(
    user_id: str,
    account: Optional[str] = None,
) -> List[AttentionRecord]:
    """List active attention records from Firestore."""
    db = get_firestore_client()
    if db is None:
        return _list_active_attention_file(user_id, account)

    collection_ref = db.collection("users").document(user_id).collection("email_attention")

    # Query for active items
    query = collection_ref.where("status", "==", "active")
    if account:
        query = query.where("email_account", "==", account)

    records = []
    for doc in query.stream():
        record = AttentionRecord.from_dict(doc.to_dict())

        # Skip expired
        if record.is_expired():
            doc.reference.delete()
            continue

        records.append(record)

    # Also check for snoozed items that should be reactivated
    snooze_query = collection_ref.where("status", "==", "snoozed")
    for doc in snooze_query.stream():
        record = AttentionRecord.from_dict(doc.to_dict())

        if record.snoozed_until and _now() >= record.snoozed_until:
            record.status = "active"
            record.snoozed_until = None
            save_attention(user_id, record)

            if account is None or record.email_account == account:
                records.append(record)

    # Sort by date descending
    records.sort(key=lambda r: r.date, reverse=True)
    return records


def is_already_analyzed(user_id: str, email_id: str) -> bool:
    """Check if an email has already been analyzed.

    Args:
        user_id: User identifier
        email_id: Gmail message ID

    Returns:
        True if email has a stored attention record
    """
    return get_attention(user_id, email_id) is not None


def dismiss_attention(
    user_id: str,
    email_id: str,
    reason: DismissReason,
) -> bool:
    """Dismiss an attention item.

    Args:
        user_id: User identifier
        email_id: Gmail message ID
        reason: Why the item is being dismissed

    Returns:
        True if successfully dismissed, False if not found
    """
    record = get_attention(user_id, email_id)
    if record is None:
        return False

    record.status = "dismissed"
    record.dismissed_at = _now()
    record.dismissed_reason = reason
    record._update_expiration()

    save_attention(user_id, record)
    return True


def snooze_attention(
    user_id: str,
    email_id: str,
    until: datetime,
) -> bool:
    """Snooze an attention item until a specific time.

    Args:
        user_id: User identifier
        email_id: Gmail message ID
        until: When to resurface the item

    Returns:
        True if successfully snoozed, False if not found
    """
    record = get_attention(user_id, email_id)
    if record is None:
        return False

    record.status = "snoozed"
    record.snoozed_until = until

    save_attention(user_id, record)
    return True


def link_task(
    user_id: str,
    email_id: str,
    task_id: str,
) -> bool:
    """Link an attention item to a created task.

    Args:
        user_id: User identifier
        email_id: Gmail message ID
        task_id: ID of the created task

    Returns:
        True if successfully linked, False if not found
    """
    record = get_attention(user_id, email_id)
    if record is None:
        return False

    record.status = "task_created"
    record.linked_task_id = task_id

    save_attention(user_id, record)
    return True


def purge_expired_records(user_id: str) -> int:
    """Purge expired attention records for a user.

    Args:
        user_id: User identifier

    Returns:
        Count of records purged
    """
    if _force_file_fallback():
        return _purge_expired_file(user_id)
    return _purge_expired_firestore(user_id)


def _purge_expired_file(user_id: str) -> int:
    """Purge expired records from file storage."""
    store_dir = _attention_dir() / _sanitize_user_id(user_id)
    if not store_dir.exists():
        return 0

    count = 0
    for file_path in store_dir.glob("*.json"):
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        record = AttentionRecord.from_dict(data)
        if record.is_expired():
            file_path.unlink()
            count += 1

    return count


def _purge_expired_firestore(user_id: str) -> int:
    """Purge expired records from Firestore."""
    db = get_firestore_client()
    if db is None:
        return _purge_expired_file(user_id)

    collection_ref = db.collection("users").document(user_id).collection("email_attention")
    now_str = _now().isoformat()

    # Query for expired items
    query = collection_ref.where("expires_at", "<", now_str)

    count = 0
    for doc in query.stream():
        doc.reference.delete()
        count += 1

    return count


def get_dismissed_email_ids(user_id: str, account: Optional[str] = None) -> set:
    """Get set of dismissed email IDs for quick filtering.

    Args:
        user_id: User identifier
        account: Optional filter by email account

    Returns:
        Set of email IDs that have been dismissed
    """
    if _force_file_fallback():
        return _get_dismissed_email_ids_file(user_id, account)
    return _get_dismissed_email_ids_firestore(user_id, account)


def _get_dismissed_email_ids_file(user_id: str, account: Optional[str] = None) -> set:
    """Get dismissed email IDs from file storage."""
    store_dir = _attention_dir() / _sanitize_user_id(user_id)
    if not store_dir.exists():
        return set()

    dismissed_ids = set()
    for file_path in store_dir.glob("*.json"):
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if data.get("status") == "dismissed":
            if account is None or data.get("email_account") == account:
                dismissed_ids.add(data["email_id"])

    return dismissed_ids


def _get_dismissed_email_ids_firestore(user_id: str, account: Optional[str] = None) -> set:
    """Get dismissed email IDs from Firestore."""
    db = get_firestore_client()
    if db is None:
        return _get_dismissed_email_ids_file(user_id, account)

    collection_ref = db.collection("users").document(user_id).collection("email_attention")
    query = collection_ref.where("status", "==", "dismissed")

    if account:
        query = query.where("email_account", "==", account)

    dismissed_ids = set()
    for doc in query.stream():
        data = doc.to_dict()
        dismissed_ids.add(data["email_id"])

    return dismissed_ids
