"""Rule Store - persistent storage for email rule suggestions.

This module provides the RuleSuggestionRecord dataclass and Firestore CRUD operations
for storing rule suggestions with approval tracking. This enables learning from
David's decisions and feeds the Trust Gradient system.

IMPORTANT: Rules are stored by EMAIL ACCOUNT (not login identity).
David has multiple login emails but data is keyed by "church" or "personal".

Firestore Structure:
    email_accounts/{account}/rule_suggestions/{rule_id} -> RuleSuggestionRecord document

File Storage (dev mode):
    rule_store/{account}/{rule_id}.json

Environment Variables:
    DTA_RULE_FORCE_FILE: Set to "1" to use local file storage (dev mode)
    DTA_RULE_DIR: Directory for file-based storage (default: rule_store/)
    DTA_RULE_TTL_PENDING: Days to keep pending rules (default: 30)
    DTA_RULE_TTL_APPROVED: Days to keep approved rules (default: 30)
    DTA_RULE_TTL_REJECTED: Days to keep rejected rules (default: 7)
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
RuleStatus = Literal["pending", "approved", "rejected", "expired"]
SuggestionType = Literal["new_label", "deletion", "attention", "category_change"]
AnalysisMethod = Literal["regex", "haiku", "profile_match"]


# Configuration helpers
def _force_file_fallback() -> bool:
    """Check if file-based storage should be used (dev mode)."""
    return os.getenv("DTA_RULE_FORCE_FILE", "0") == "1"


def _rule_dir() -> Path:
    """Return the directory for file-based rule storage."""
    return Path(
        os.getenv(
            "DTA_RULE_DIR",
            Path(__file__).resolve().parents[2] / "rule_store",
        )
    )


def _ttl_pending_days() -> int:
    """Return TTL for pending rule suggestions in days."""
    return int(os.getenv("DTA_RULE_TTL_PENDING", "30"))


def _ttl_approved_days() -> int:
    """Return TTL for approved rule suggestions in days."""
    return int(os.getenv("DTA_RULE_TTL_APPROVED", "30"))


def _ttl_rejected_days() -> int:
    """Return TTL for rejected rule suggestions in days."""
    return int(os.getenv("DTA_RULE_TTL_REJECTED", "7"))


def _now() -> datetime:
    """Return current UTC datetime."""
    return datetime.now(timezone.utc)


def _generate_id() -> str:
    """Generate a unique rule suggestion ID."""
    return str(uuid.uuid4())


@dataclass
class RuleSuggestionRecord:
    """Persistent rule suggestion.

    Represents a suggested email filter rule that DATA has identified.
    Includes Trust Gradient fields for tracking approval rates and
    enabling DATA to earn autonomy.

    Trust Gradient Philosophy:
        - Level 1 (current): Suggest with rationale → Receive vote
        - Track approval rates by analysis_method and category
        - 90%+ approval rate needed for Level 2 autonomy

    Attributes:
        rule_id: Unique identifier (UUID)
        email_account: "church" or "personal"
        user_id: User identifier (for audit trail)

        suggestion_type: Type of rule ("new_label", "deletion", "attention", "category_change")
        suggested_rule: FilterRule as dict (field, operator, value, action, label_name)
        reason: Why DATA suggests this rule (rationale for Level 1)
        examples: Sample email subjects/senders that matched
        email_count: How many emails matched this pattern

        confidence: Confidence score 0.0-1.0 (float for calibration)
        analysis_method: How suggestion was generated ("regex", "haiku", "profile_match")
        category: Email category ("Personal", "Church", "Work", etc.)

        status: "pending", "approved", "rejected", "expired"
        decided_at: When user made decision
        rejection_reason: Why rejected (for learning)

        created_at: Record creation time
        expires_at: TTL expiration time (based on status)
    """
    # Identity
    rule_id: str
    email_account: str
    user_id: str

    # Rule Details
    suggestion_type: SuggestionType
    suggested_rule: Dict[str, Any]  # FilterRule as dict
    reason: str
    examples: List[str] = field(default_factory=list)
    email_count: int = 0

    # Trust Gradient Fields
    confidence: float = 0.5
    analysis_method: AnalysisMethod = "regex"
    category: str = ""

    # Decision Tracking
    status: RuleStatus = "pending"
    decided_at: Optional[datetime] = None
    rejection_reason: Optional[str] = None

    # Metadata
    created_at: datetime = field(default_factory=_now)
    expires_at: Optional[datetime] = None

    def __post_init__(self):
        """Set default expires_at based on status."""
        if self.expires_at is None:
            self._update_expiration()

    def _update_expiration(self):
        """Update expiration based on current status (Trust Gradient TTL policy)."""
        if self.status == "pending":
            self.expires_at = _now() + timedelta(days=_ttl_pending_days())
        elif self.status == "approved":
            base = self.decided_at if self.decided_at else _now()
            self.expires_at = base + timedelta(days=_ttl_approved_days())
        elif self.status == "rejected":
            base = self.decided_at if self.decided_at else _now()
            self.expires_at = base + timedelta(days=_ttl_rejected_days())

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
            "rule_id": self.rule_id,
            "email_account": self.email_account,
            "user_id": self.user_id,
            "suggestion_type": self.suggestion_type,
            "suggested_rule": self.suggested_rule,
            "reason": self.reason,
            "examples": self.examples,
            "email_count": self.email_count,
            "confidence": self.confidence,
            "analysis_method": self.analysis_method,
            "category": self.category,
            "status": self.status,
            "decided_at": dt_to_str(self.decided_at),
            "rejection_reason": self.rejection_reason,
            "created_at": dt_to_str(self.created_at),
            "expires_at": dt_to_str(self.expires_at),
        }

    def to_api_dict(self) -> Dict[str, Any]:
        """Convert to API-friendly dict (camelCase for JavaScript)."""
        def dt_to_str(dt: Optional[datetime]) -> Optional[str]:
            return dt.isoformat() if dt else None

        return {
            "ruleId": self.rule_id,
            "emailAccount": self.email_account,
            "suggestionType": self.suggestion_type,
            "suggestedRule": self.suggested_rule,
            "reason": self.reason,
            "examples": self.examples,
            "emailCount": self.email_count,
            "confidence": self.confidence,
            "analysisMethod": self.analysis_method,
            "category": self.category,
            "status": self.status,
            "decidedAt": dt_to_str(self.decided_at),
            "rejectionReason": self.rejection_reason,
            "createdAt": dt_to_str(self.created_at),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RuleSuggestionRecord":
        """Create record from dictionary."""
        def str_to_dt(s: Optional[str]) -> Optional[datetime]:
            if s is None:
                return None
            return datetime.fromisoformat(s)

        return cls(
            rule_id=data["rule_id"],
            email_account=data["email_account"],
            user_id=data["user_id"],
            suggestion_type=data.get("suggestion_type", "new_label"),
            suggested_rule=data.get("suggested_rule", {}),
            reason=data.get("reason", ""),
            examples=data.get("examples", []),
            email_count=data.get("email_count", 0),
            confidence=data.get("confidence", 0.5),
            analysis_method=data.get("analysis_method", "regex"),
            category=data.get("category", ""),
            status=data.get("status", "pending"),
            decided_at=str_to_dt(data.get("decided_at")),
            rejection_reason=data.get("rejection_reason"),
            created_at=str_to_dt(data.get("created_at")) or _now(),
            expires_at=str_to_dt(data.get("expires_at")),
        )


# =============================================================================
# CRUD Operations
# =============================================================================

def save_rule_suggestion(account: str, record: RuleSuggestionRecord) -> None:
    """Save a rule suggestion record to storage.

    Args:
        account: Email account ("church" or "personal")
        record: RuleSuggestionRecord to save
    """
    if _force_file_fallback():
        _save_rule_file(account, record)
    else:
        _save_rule_firestore(account, record)


def _save_rule_file(account: str, record: RuleSuggestionRecord) -> None:
    """Save rule suggestion to file storage."""
    store_dir = _rule_dir() / account
    store_dir.mkdir(parents=True, exist_ok=True)

    file_path = store_dir / f"{record.rule_id}.json"
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(record.to_dict(), f, indent=2)


def _save_rule_firestore(account: str, record: RuleSuggestionRecord) -> None:
    """Save rule suggestion to Firestore."""
    db = get_firestore_client()
    if db is None:
        _save_rule_file(account, record)
        return

    doc_ref = (
        db.collection("email_accounts")
        .document(account)
        .collection("rule_suggestions")
        .document(record.rule_id)
    )
    doc_ref.set(record.to_dict())


def get_rule_suggestion(account: str, rule_id: str) -> Optional[RuleSuggestionRecord]:
    """Get a single rule suggestion record.

    Args:
        account: Email account ("church" or "personal")
        rule_id: Rule suggestion ID

    Returns:
        RuleSuggestionRecord if found, None otherwise
    """
    if _force_file_fallback():
        return _get_rule_file(account, rule_id)
    return _get_rule_firestore(account, rule_id)


def _get_rule_file(account: str, rule_id: str) -> Optional[RuleSuggestionRecord]:
    """Get rule suggestion from file storage."""
    file_path = _rule_dir() / account / f"{rule_id}.json"
    if not file_path.exists():
        return None

    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    record = RuleSuggestionRecord.from_dict(data)

    if record.is_expired():
        file_path.unlink()
        return None

    return record


def _get_rule_firestore(account: str, rule_id: str) -> Optional[RuleSuggestionRecord]:
    """Get rule suggestion from Firestore."""
    db = get_firestore_client()
    if db is None:
        return _get_rule_file(account, rule_id)

    doc_ref = (
        db.collection("email_accounts")
        .document(account)
        .collection("rule_suggestions")
        .document(rule_id)
    )
    doc = doc_ref.get()

    if not doc.exists:
        return None

    record = RuleSuggestionRecord.from_dict(doc.to_dict())

    if record.is_expired():
        doc_ref.delete()
        return None

    return record


def list_pending_rules(account: str) -> List[RuleSuggestionRecord]:
    """List all pending rule suggestions for an email account.

    Args:
        account: Email account ("church" or "personal")

    Returns:
        List of pending RuleSuggestionRecords
    """
    if _force_file_fallback():
        return _list_pending_rules_file(account)
    return _list_pending_rules_firestore(account)


def _list_pending_rules_file(account: str) -> List[RuleSuggestionRecord]:
    """List pending rule suggestions from file storage."""
    store_dir = _rule_dir() / account
    if not store_dir.exists():
        return []

    records = []
    for file_path in store_dir.glob("*.json"):
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        record = RuleSuggestionRecord.from_dict(data)

        if record.is_expired():
            file_path.unlink()
            continue

        if record.status == "pending":
            records.append(record)

    # Sort by confidence descending (highest confidence first)
    records.sort(key=lambda r: r.confidence, reverse=True)
    return records


def _list_pending_rules_firestore(account: str) -> List[RuleSuggestionRecord]:
    """List pending rule suggestions from Firestore."""
    db = get_firestore_client()
    if db is None:
        return _list_pending_rules_file(account)

    collection_ref = (
        db.collection("email_accounts")
        .document(account)
        .collection("rule_suggestions")
    )
    query = collection_ref.where("status", "==", "pending")

    records = []
    for doc in query.stream():
        record = RuleSuggestionRecord.from_dict(doc.to_dict())

        if record.is_expired():
            doc.reference.delete()
            continue

        records.append(record)

    records.sort(key=lambda r: r.confidence, reverse=True)
    return records


def decide_rule_suggestion(
    account: str,
    rule_id: str,
    approved: bool,
    rejection_reason: Optional[str] = None,
) -> bool:
    """Record a decision on a rule suggestion.

    Args:
        account: Email account ("church" or "personal")
        rule_id: Rule suggestion ID
        approved: True to approve, False to reject
        rejection_reason: Why the rule was rejected (for learning)

    Returns:
        True if decision recorded, False if rule not found
    """
    record = get_rule_suggestion(account, rule_id)
    if record is None:
        return False

    record.status = "approved" if approved else "rejected"
    record.decided_at = _now()
    if not approved and rejection_reason:
        record.rejection_reason = rejection_reason

    record._update_expiration()
    save_rule_suggestion(account, record)
    return True


def create_rule_suggestion(
    account: str,
    user_id: str,
    suggestion_type: SuggestionType,
    suggested_rule: Dict[str, Any],
    reason: str,
    examples: Optional[List[str]] = None,
    email_count: int = 0,
    confidence: float = 0.5,
    analysis_method: AnalysisMethod = "regex",
    category: str = "",
) -> RuleSuggestionRecord:
    """Create and save a new rule suggestion.

    Args:
        account: Email account ("church" or "personal")
        user_id: User identifier (for audit trail)
        suggestion_type: Type of rule suggestion
        suggested_rule: FilterRule as dict
        reason: Why this rule is suggested (rationale)
        examples: Sample email subjects/senders that matched
        email_count: How many emails matched
        confidence: Confidence score 0.0-1.0
        analysis_method: How suggestion was generated
        category: Email category

    Returns:
        The created RuleSuggestionRecord
    """
    record = RuleSuggestionRecord(
        rule_id=_generate_id(),
        email_account=account,
        user_id=user_id,
        suggestion_type=suggestion_type,
        suggested_rule=suggested_rule,
        reason=reason,
        examples=examples or [],
        email_count=email_count,
        confidence=confidence,
        analysis_method=analysis_method,
        category=category,
    )

    save_rule_suggestion(account, record)
    return record


def get_rule_approval_stats(account: str, days: int = 30) -> Dict[str, Any]:
    """Get rule approval statistics for Trust Gradient.

    Args:
        account: Email account ("church" or "personal")
        days: How many days to look back

    Returns:
        Dict with approval stats by analysis_method and category
    """
    if _force_file_fallback():
        return _get_rule_stats_file(account, days)
    return _get_rule_stats_firestore(account, days)


def _empty_rule_stats() -> Dict[str, Any]:
    """Return empty stats structure."""
    return {
        "total": 0,
        "approved": 0,
        "rejected": 0,
        "pending": 0,
        "approvalRate": 0.0,
        "byMethod": {},
        "byCategory": {},
    }


def _get_rule_stats_file(account: str, days: int = 30) -> Dict[str, Any]:
    """Get rule approval stats from file storage."""
    store_dir = _rule_dir() / account
    if not store_dir.exists():
        return _empty_rule_stats()

    cutoff = _now() - timedelta(days=days)
    stats = {
        "total": 0,
        "approved": 0,
        "rejected": 0,
        "pending": 0,
        "byMethod": {},
        "byCategory": {},
    }

    for file_path in store_dir.glob("*.json"):
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        record = RuleSuggestionRecord.from_dict(data)

        # Skip old records
        if record.created_at < cutoff:
            continue

        stats["total"] += 1
        status = record.status
        if status in ("approved", "rejected", "pending"):
            stats[status] += 1

        # Group by analysis method
        method = record.analysis_method
        if method not in stats["byMethod"]:
            stats["byMethod"][method] = {"approved": 0, "rejected": 0, "total": 0}
        stats["byMethod"][method]["total"] += 1
        if status in ("approved", "rejected"):
            stats["byMethod"][method][status] += 1

        # Group by category
        cat = record.category or "Uncategorized"
        if cat not in stats["byCategory"]:
            stats["byCategory"][cat] = {"approved": 0, "rejected": 0, "total": 0}
        stats["byCategory"][cat]["total"] += 1
        if status in ("approved", "rejected"):
            stats["byCategory"][cat][status] += 1

    # Calculate approval rates
    decided = stats["approved"] + stats["rejected"]
    stats["approvalRate"] = stats["approved"] / decided if decided > 0 else 0.0

    for method_stats in stats["byMethod"].values():
        method_decided = method_stats["approved"] + method_stats["rejected"]
        method_stats["rate"] = (
            method_stats["approved"] / method_decided if method_decided > 0 else 0.0
        )

    for cat_stats in stats["byCategory"].values():
        cat_decided = cat_stats["approved"] + cat_stats["rejected"]
        cat_stats["rate"] = (
            cat_stats["approved"] / cat_decided if cat_decided > 0 else 0.0
        )

    return stats


def _get_rule_stats_firestore(account: str, days: int = 30) -> Dict[str, Any]:
    """Get rule approval stats from Firestore."""
    db = get_firestore_client()
    if db is None:
        return _get_rule_stats_file(account, days)

    collection_ref = (
        db.collection("email_accounts")
        .document(account)
        .collection("rule_suggestions")
    )

    cutoff = (_now() - timedelta(days=days)).isoformat()
    query = collection_ref.where("created_at", ">=", cutoff)

    stats = {
        "total": 0,
        "approved": 0,
        "rejected": 0,
        "pending": 0,
        "byMethod": {},
        "byCategory": {},
    }

    for doc in query.stream():
        data = doc.to_dict()
        record = RuleSuggestionRecord.from_dict(data)

        stats["total"] += 1
        status = record.status
        if status in ("approved", "rejected", "pending"):
            stats[status] += 1

        method = record.analysis_method
        if method not in stats["byMethod"]:
            stats["byMethod"][method] = {"approved": 0, "rejected": 0, "total": 0}
        stats["byMethod"][method]["total"] += 1
        if status in ("approved", "rejected"):
            stats["byMethod"][method][status] += 1

        cat = record.category or "Uncategorized"
        if cat not in stats["byCategory"]:
            stats["byCategory"][cat] = {"approved": 0, "rejected": 0, "total": 0}
        stats["byCategory"][cat]["total"] += 1
        if status in ("approved", "rejected"):
            stats["byCategory"][cat][status] += 1

    # Calculate approval rates
    decided = stats["approved"] + stats["rejected"]
    stats["approvalRate"] = stats["approved"] / decided if decided > 0 else 0.0

    for method_stats in stats["byMethod"].values():
        method_decided = method_stats["approved"] + method_stats["rejected"]
        method_stats["rate"] = (
            method_stats["approved"] / method_decided if method_decided > 0 else 0.0
        )

    for cat_stats in stats["byCategory"].values():
        cat_decided = cat_stats["approved"] + cat_stats["rejected"]
        cat_stats["rate"] = (
            cat_stats["approved"] / cat_decided if cat_decided > 0 else 0.0
        )

    return stats


def purge_expired_rules(account: str) -> int:
    """Purge expired rule suggestions for an email account.

    Args:
        account: Email account ("church" or "personal")

    Returns:
        Count of records purged
    """
    if _force_file_fallback():
        return _purge_expired_rules_file(account)
    return _purge_expired_rules_firestore(account)


def _purge_expired_rules_file(account: str) -> int:
    """Purge expired rules from file storage."""
    store_dir = _rule_dir() / account
    if not store_dir.exists():
        return 0

    count = 0
    for file_path in store_dir.glob("*.json"):
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        record = RuleSuggestionRecord.from_dict(data)
        if record.is_expired():
            file_path.unlink()
            count += 1

    return count


def _purge_expired_rules_firestore(account: str) -> int:
    """Purge expired rules from Firestore."""
    db = get_firestore_client()
    if db is None:
        return _purge_expired_rules_file(account)

    collection_ref = (
        db.collection("email_accounts")
        .document(account)
        .collection("rule_suggestions")
    )
    now_str = _now().isoformat()

    query = collection_ref.where("expires_at", "<", now_str)

    count = 0
    for doc in query.stream():
        doc.reference.delete()
        count += 1

    return count


def has_pending_rule_for_pattern(
    account: str,
    field: str,
    value: str,
) -> bool:
    """Check if there's already a pending rule for this pattern.

    Used to prevent duplicate suggestions.

    Args:
        account: Email account ("church" or "personal")
        field: Filter field (e.g., "from", "subject")
        value: Filter value to match

    Returns:
        True if a pending rule already exists for this pattern
    """
    pending = list_pending_rules(account)

    for record in pending:
        rule = record.suggested_rule
        if rule.get("field") == field and rule.get("value") == value:
            return True

    return False
