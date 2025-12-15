"""Suggestion Store - persistent storage for email action suggestions.

This module provides the SuggestionRecord dataclass and Firestore CRUD operations
for storing action suggestions with approval tracking. This enables learning
from David's decisions and feeds the Trust Gradient system.

Firestore Structure:
    users/{user_id}/email_suggestions/{suggestion_id} -> SuggestionRecord document

Environment Variables:
    DTA_SUGGESTION_FORCE_FILE: Set to "1" to use local file storage (dev mode)
    DTA_SUGGESTION_DIR: Directory for file-based storage (default: suggestion_store/)
    DTA_SUGGESTION_TTL_DAYS: Days to keep suggestions (default: 7)
"""
from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from ..firestore import get_firestore_client


# Type aliases
SuggestionStatus = Literal["pending", "approved", "rejected", "expired"]
SuggestionAction = Literal["archive", "label", "delete", "star", "create_task", "mark_important"]
AnalysisMethod = Literal["regex", "haiku", "profile_match"]


# Configuration helpers
def _force_file_fallback() -> bool:
    """Check if file-based storage should be used (dev mode)."""
    return os.getenv("DTA_SUGGESTION_FORCE_FILE", "0") == "1"


def _suggestion_dir() -> Path:
    """Return the directory for file-based suggestion storage."""
    return Path(
        os.getenv(
            "DTA_SUGGESTION_DIR",
            Path(__file__).resolve().parents[2] / "suggestion_store",
        )
    )


def _ttl_days() -> int:
    """Return TTL for suggestions in days."""
    return int(os.getenv("DTA_SUGGESTION_TTL_DAYS", "7"))


def _now() -> datetime:
    """Return current UTC datetime."""
    return datetime.now(timezone.utc)


def _generate_id() -> str:
    """Generate a unique suggestion ID."""
    return str(uuid.uuid4())


def _sanitize_user_id(user_id: str) -> str:
    """Sanitize user ID for use as filename."""
    return user_id.replace("@", "_at_").replace(".", "_")


@dataclass
class SuggestionRecord:
    """Persistent suggestion with approval tracking.

    Represents a suggested action for a specific email that DATA has proposed.
    Tracks whether the suggestion was approved or rejected to feed the Trust
    Gradient learning system.

    Attributes:
        suggestion_id: Unique identifier for this suggestion
        email_id: Gmail message ID
        email_account: "church" or "personal"
        user_id: User identifier (email address)
        action: Suggested action type
        rationale: Why DATA suggests this action
        confidence: Confidence score 0.0-1.0
        label_name: Target label for LABEL action
        task_title: Task title for CREATE_TASK action
        status: "pending", "approved", "rejected", "expired"
        decided_at: When user made a decision (optional)
        analysis_method: "regex", "haiku", or "profile_match"
        created_at: When suggestion was created
        expires_at: TTL expiration time
    """
    # Identity
    suggestion_id: str
    email_id: str
    email_account: str
    user_id: str

    # Suggestion details
    action: SuggestionAction
    rationale: str
    confidence: float = 0.5
    label_name: Optional[str] = None
    task_title: Optional[str] = None

    # Status
    status: SuggestionStatus = "pending"
    decided_at: Optional[datetime] = None

    # For learning
    analysis_method: AnalysisMethod = "regex"
    created_at: datetime = field(default_factory=_now)
    expires_at: Optional[datetime] = None

    def __post_init__(self):
        """Set default expires_at if not provided."""
        if self.expires_at is None:
            self.expires_at = _now() + timedelta(days=_ttl_days())

    def is_expired(self) -> bool:
        """Check if this suggestion has expired."""
        if self.expires_at is None:
            return False
        return _now() > self.expires_at

    def to_dict(self) -> Dict[str, Any]:
        """Convert record to dictionary for storage."""
        def dt_to_str(dt: Optional[datetime]) -> Optional[str]:
            return dt.isoformat() if dt else None

        return {
            "suggestion_id": self.suggestion_id,
            "email_id": self.email_id,
            "email_account": self.email_account,
            "user_id": self.user_id,
            "action": self.action,
            "rationale": self.rationale,
            "confidence": self.confidence,
            "label_name": self.label_name,
            "task_title": self.task_title,
            "status": self.status,
            "decided_at": dt_to_str(self.decided_at),
            "analysis_method": self.analysis_method,
            "created_at": dt_to_str(self.created_at),
            "expires_at": dt_to_str(self.expires_at),
        }

    def to_api_dict(self) -> Dict[str, Any]:
        """Convert to API-friendly dict (camelCase for JavaScript)."""
        def dt_to_str(dt: Optional[datetime]) -> Optional[str]:
            return dt.isoformat() if dt else None

        return {
            "suggestionId": self.suggestion_id,
            "emailId": self.email_id,
            "emailAccount": self.email_account,
            "action": self.action,
            "rationale": self.rationale,
            "confidence": self.confidence,
            "labelName": self.label_name,
            "taskTitle": self.task_title,
            "status": self.status,
            "decidedAt": dt_to_str(self.decided_at),
            "analysisMethod": self.analysis_method,
            "createdAt": dt_to_str(self.created_at),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SuggestionRecord":
        """Create record from dictionary."""
        def str_to_dt(s: Optional[str]) -> Optional[datetime]:
            if s is None:
                return None
            return datetime.fromisoformat(s)

        return cls(
            suggestion_id=data["suggestion_id"],
            email_id=data["email_id"],
            email_account=data["email_account"],
            user_id=data["user_id"],
            action=data["action"],
            rationale=data.get("rationale", ""),
            confidence=data.get("confidence", 0.5),
            label_name=data.get("label_name"),
            task_title=data.get("task_title"),
            status=data.get("status", "pending"),
            decided_at=str_to_dt(data.get("decided_at")),
            analysis_method=data.get("analysis_method", "regex"),
            created_at=str_to_dt(data.get("created_at")) or _now(),
            expires_at=str_to_dt(data.get("expires_at")),
        )


# =============================================================================
# CRUD Operations
# =============================================================================

def save_suggestion(user_id: str, record: SuggestionRecord) -> None:
    """Save a suggestion record to storage.

    Args:
        user_id: User identifier (email address)
        record: SuggestionRecord to save
    """
    if _force_file_fallback():
        _save_suggestion_file(user_id, record)
    else:
        _save_suggestion_firestore(user_id, record)


def _save_suggestion_file(user_id: str, record: SuggestionRecord) -> None:
    """Save suggestion record to file storage."""
    store_dir = _suggestion_dir() / _sanitize_user_id(user_id)
    store_dir.mkdir(parents=True, exist_ok=True)

    file_path = store_dir / f"{record.suggestion_id}.json"
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(record.to_dict(), f, indent=2)


def _save_suggestion_firestore(user_id: str, record: SuggestionRecord) -> None:
    """Save suggestion record to Firestore."""
    db = get_firestore_client()
    if db is None:
        _save_suggestion_file(user_id, record)
        return

    doc_ref = db.collection("users").document(user_id).collection("email_suggestions").document(record.suggestion_id)
    doc_ref.set(record.to_dict())


def get_suggestion(user_id: str, suggestion_id: str) -> Optional[SuggestionRecord]:
    """Get a single suggestion record.

    Args:
        user_id: User identifier
        suggestion_id: Suggestion UUID

    Returns:
        SuggestionRecord if found, None otherwise
    """
    if _force_file_fallback():
        return _get_suggestion_file(user_id, suggestion_id)
    return _get_suggestion_firestore(user_id, suggestion_id)


def _get_suggestion_file(user_id: str, suggestion_id: str) -> Optional[SuggestionRecord]:
    """Get suggestion record from file storage."""
    file_path = _suggestion_dir() / _sanitize_user_id(user_id) / f"{suggestion_id}.json"
    if not file_path.exists():
        return None

    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    record = SuggestionRecord.from_dict(data)

    # Check expiration
    if record.is_expired() and record.status == "pending":
        record.status = "expired"
        save_suggestion(user_id, record)

    return record


def _get_suggestion_firestore(user_id: str, suggestion_id: str) -> Optional[SuggestionRecord]:
    """Get suggestion record from Firestore."""
    db = get_firestore_client()
    if db is None:
        return _get_suggestion_file(user_id, suggestion_id)

    doc_ref = db.collection("users").document(user_id).collection("email_suggestions").document(suggestion_id)
    doc = doc_ref.get()

    if not doc.exists:
        return None

    record = SuggestionRecord.from_dict(doc.to_dict())

    # Check expiration
    if record.is_expired() and record.status == "pending":
        record.status = "expired"
        save_suggestion(user_id, record)

    return record


def list_pending_suggestions(
    user_id: str,
    account: Optional[str] = None,
) -> List[SuggestionRecord]:
    """List all pending suggestions for a user.

    Args:
        user_id: User identifier
        account: Optional filter by email account

    Returns:
        List of pending SuggestionRecords
    """
    if _force_file_fallback():
        return _list_pending_suggestions_file(user_id, account)
    return _list_pending_suggestions_firestore(user_id, account)


def _list_pending_suggestions_file(
    user_id: str,
    account: Optional[str] = None,
) -> List[SuggestionRecord]:
    """List pending suggestions from file storage."""
    store_dir = _suggestion_dir() / _sanitize_user_id(user_id)
    if not store_dir.exists():
        return []

    records = []
    for file_path in store_dir.glob("*.json"):
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        record = SuggestionRecord.from_dict(data)

        # Skip non-pending
        if record.status != "pending":
            continue

        # Check expiration
        if record.is_expired():
            record.status = "expired"
            save_suggestion(user_id, record)
            continue

        # Filter by account
        if account and record.email_account != account:
            continue

        records.append(record)

    # Sort by created_at descending
    records.sort(key=lambda r: r.created_at, reverse=True)
    return records


def _list_pending_suggestions_firestore(
    user_id: str,
    account: Optional[str] = None,
) -> List[SuggestionRecord]:
    """List pending suggestions from Firestore."""
    db = get_firestore_client()
    if db is None:
        return _list_pending_suggestions_file(user_id, account)

    collection_ref = db.collection("users").document(user_id).collection("email_suggestions")
    query = collection_ref.where("status", "==", "pending")

    if account:
        query = query.where("email_account", "==", account)

    records = []
    for doc in query.stream():
        record = SuggestionRecord.from_dict(doc.to_dict())

        # Check expiration
        if record.is_expired():
            record.status = "expired"
            save_suggestion(user_id, record)
            continue

        records.append(record)

    # Sort by created_at descending
    records.sort(key=lambda r: r.created_at, reverse=True)
    return records


def record_suggestion_decision(
    user_id: str,
    suggestion_id: str,
    approved: bool,
) -> bool:
    """Record user's decision on a suggestion.

    This is the key feedback mechanism for the Trust Gradient.
    Approvals increase trust, rejections decrease it.

    Args:
        user_id: User identifier
        suggestion_id: Suggestion UUID
        approved: Whether user approved the suggestion

    Returns:
        True if decision recorded, False if suggestion not found
    """
    record = get_suggestion(user_id, suggestion_id)
    if record is None:
        return False

    record.status = "approved" if approved else "rejected"
    record.decided_at = _now()

    save_suggestion(user_id, record)
    return True


def create_suggestion(
    user_id: str,
    email_id: str,
    email_account: str,
    action: SuggestionAction,
    rationale: str,
    confidence: float = 0.5,
    label_name: Optional[str] = None,
    task_title: Optional[str] = None,
    analysis_method: AnalysisMethod = "regex",
) -> SuggestionRecord:
    """Create and save a new suggestion.

    Args:
        user_id: User identifier
        email_id: Gmail message ID
        email_account: "church" or "personal"
        action: Suggested action type
        rationale: Why this action is suggested
        confidence: Confidence score 0.0-1.0
        label_name: Target label for LABEL action
        task_title: Task title for CREATE_TASK action
        analysis_method: How suggestion was generated

    Returns:
        The created SuggestionRecord
    """
    record = SuggestionRecord(
        suggestion_id=_generate_id(),
        email_id=email_id,
        email_account=email_account,
        user_id=user_id,
        action=action,
        rationale=rationale,
        confidence=confidence,
        label_name=label_name,
        task_title=task_title,
        analysis_method=analysis_method,
    )

    save_suggestion(user_id, record)
    return record


def get_approval_stats(user_id: str, days: int = 30) -> Dict[str, Any]:
    """Get suggestion approval statistics for Trust Gradient.

    Args:
        user_id: User identifier
        days: How many days to look back

    Returns:
        Dict with approval stats
    """
    if _force_file_fallback():
        return _get_approval_stats_file(user_id, days)
    return _get_approval_stats_firestore(user_id, days)


def _get_approval_stats_file(user_id: str, days: int = 30) -> Dict[str, Any]:
    """Get approval stats from file storage."""
    store_dir = _suggestion_dir() / _sanitize_user_id(user_id)
    if not store_dir.exists():
        return _empty_stats()

    cutoff = _now() - timedelta(days=days)

    stats = {
        "total": 0,
        "approved": 0,
        "rejected": 0,
        "expired": 0,
        "pending": 0,
        "by_action": {},
        "by_method": {},
    }

    for file_path in store_dir.glob("*.json"):
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        record = SuggestionRecord.from_dict(data)

        # Only count recent records
        if record.created_at < cutoff:
            continue

        stats["total"] += 1
        stats[record.status] += 1

        # Track by action type
        action = record.action
        if action not in stats["by_action"]:
            stats["by_action"][action] = {"approved": 0, "rejected": 0}
        if record.status in ("approved", "rejected"):
            stats["by_action"][action][record.status] += 1

        # Track by analysis method
        method = record.analysis_method
        if method not in stats["by_method"]:
            stats["by_method"][method] = {"approved": 0, "rejected": 0}
        if record.status in ("approved", "rejected"):
            stats["by_method"][method][record.status] += 1

    # Calculate approval rate
    decided = stats["approved"] + stats["rejected"]
    stats["approval_rate"] = stats["approved"] / decided if decided > 0 else 0.0

    return stats


def _get_approval_stats_firestore(user_id: str, days: int = 30) -> Dict[str, Any]:
    """Get approval stats from Firestore."""
    db = get_firestore_client()
    if db is None:
        return _get_approval_stats_file(user_id, days)

    collection_ref = db.collection("users").document(user_id).collection("email_suggestions")
    cutoff = (_now() - timedelta(days=days)).isoformat()

    stats = {
        "total": 0,
        "approved": 0,
        "rejected": 0,
        "expired": 0,
        "pending": 0,
        "by_action": {},
        "by_method": {},
    }

    query = collection_ref.where("created_at", ">=", cutoff)

    for doc in query.stream():
        record = SuggestionRecord.from_dict(doc.to_dict())

        stats["total"] += 1
        stats[record.status] += 1

        # Track by action type
        action = record.action
        if action not in stats["by_action"]:
            stats["by_action"][action] = {"approved": 0, "rejected": 0}
        if record.status in ("approved", "rejected"):
            stats["by_action"][action][record.status] += 1

        # Track by analysis method
        method = record.analysis_method
        if method not in stats["by_method"]:
            stats["by_method"][method] = {"approved": 0, "rejected": 0}
        if record.status in ("approved", "rejected"):
            stats["by_method"][method][record.status] += 1

    # Calculate approval rate
    decided = stats["approved"] + stats["rejected"]
    stats["approval_rate"] = stats["approved"] / decided if decided > 0 else 0.0

    return stats


def _empty_stats() -> Dict[str, Any]:
    """Return empty stats dict."""
    return {
        "total": 0,
        "approved": 0,
        "rejected": 0,
        "expired": 0,
        "pending": 0,
        "approval_rate": 0.0,
        "by_action": {},
        "by_method": {},
    }


def purge_old_suggestions(user_id: str, days: int = 30) -> int:
    """Purge suggestions older than specified days.

    Args:
        user_id: User identifier
        days: Age threshold in days

    Returns:
        Count of suggestions purged
    """
    if _force_file_fallback():
        return _purge_old_suggestions_file(user_id, days)
    return _purge_old_suggestions_firestore(user_id, days)


def _purge_old_suggestions_file(user_id: str, days: int = 30) -> int:
    """Purge old suggestions from file storage."""
    store_dir = _suggestion_dir() / _sanitize_user_id(user_id)
    if not store_dir.exists():
        return 0

    cutoff = _now() - timedelta(days=days)
    count = 0

    for file_path in store_dir.glob("*.json"):
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        record = SuggestionRecord.from_dict(data)

        # Keep pending suggestions regardless of age
        if record.status == "pending":
            continue

        # Purge old decided suggestions
        if record.created_at < cutoff:
            file_path.unlink()
            count += 1

    return count


def _purge_old_suggestions_firestore(user_id: str, days: int = 30) -> int:
    """Purge old suggestions from Firestore."""
    db = get_firestore_client()
    if db is None:
        return _purge_old_suggestions_file(user_id, days)

    collection_ref = db.collection("users").document(user_id).collection("email_suggestions")
    cutoff = (_now() - timedelta(days=days)).isoformat()

    count = 0

    # Query for old non-pending suggestions
    for status in ["approved", "rejected", "expired"]:
        query = collection_ref.where("status", "==", status).where("created_at", "<", cutoff)

        for doc in query.stream():
            doc.reference.delete()
            count += 1

    return count
