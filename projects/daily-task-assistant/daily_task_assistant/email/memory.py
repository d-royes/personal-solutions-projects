"""Email Memory Store for DATA.

This module provides persistent memory for email patterns and preferences,
enabling DATA to learn from David's email management decisions.

Architecture:
- Firestore path: users/{user_id}/email_memory/
  - category_patterns/{hash} - Domain/sender to category mappings
  - sender_profiles/{hash} - Sender relationship and importance
  - timing_patterns - Processing timing data

Storage follows Firestore + file fallback pattern.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional


class PatternType(str, Enum):
    """Type of category pattern."""
    
    DOMAIN = "domain"  # e.g., "amazon.com" -> Transactional
    SENDER = "sender"  # e.g., "pastor@church.org" -> Ministry Comms


class RelationshipType(str, Enum):
    """Types of sender relationships."""
    
    SPOUSE = "spouse"
    CHILD = "child"
    PARENT = "parent"
    PARENT_IN_LAW = "parent_in_law"
    SIBLING = "sibling"
    RELATIVE = "relative"
    FRIEND = "friend"
    WORK_SUPERIOR = "work_superior"
    WORK_SUBORDINATE = "subordinate"
    WORK_PEER = "peer"
    SKIP_LEVEL_SUPERIOR = "skip_level_superior"
    CHURCH_MEMBER = "church_member"
    CHURCH_LEADER = "church_leader"
    VENDOR = "vendor"
    SERVICE = "service"
    UNKNOWN = "unknown"


class ResponseExpectation(str, Enum):
    """Expected response time categories."""
    
    IMMEDIATE = "immediate"  # Within hours
    SAME_DAY = "same_day"
    NEXT_DAY = "next_day"
    WITHIN_WEEK = "within_week"
    NO_EXPECTATION = "no_expectation"


@dataclass(slots=True)
class CategoryPattern:
    """A learned pattern for categorizing emails.
    
    Hybrid approach:
    - Domain-level patterns for external vendors (amazon.com -> Transactional)
    - Sender-level patterns for internal/nuanced cases (pastor@church.org -> Ministry)
    """
    
    pattern_type: str  # PatternType value
    pattern: str  # Domain or full email address
    preferred_category: str  # Label/category to apply
    confidence: float  # 0.0 to 1.0
    sample_count: int  # How many times this pattern was confirmed
    last_updated: datetime
    
    # Tracking approved/dismissed for learning
    approved_count: int = 0
    dismissed_count: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "pattern_type": self.pattern_type,
            "pattern": self.pattern,
            "preferred_category": self.preferred_category,
            "confidence": self.confidence,
            "sample_count": self.sample_count,
            "last_updated": self.last_updated.isoformat(),
            "approved_count": self.approved_count,
            "dismissed_count": self.dismissed_count,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CategoryPattern":
        """Create from dictionary."""
        last_updated = data.get("last_updated")
        if isinstance(last_updated, str):
            last_updated = datetime.fromisoformat(last_updated)
        
        return cls(
            pattern_type=data["pattern_type"],
            pattern=data["pattern"],
            preferred_category=data["preferred_category"],
            confidence=data.get("confidence", 0.5),
            sample_count=data.get("sample_count", 1),
            last_updated=last_updated or datetime.now(timezone.utc),
            approved_count=data.get("approved_count", 0),
            dismissed_count=data.get("dismissed_count", 0),
        )


@dataclass(slots=True)
class SenderProfile:
    """Profile of a known sender with relationship information.
    
    Used for VIP detection and response time expectations.
    """
    
    email: str
    name: str
    relationship: str  # RelationshipType value
    response_expectation: str  # ResponseExpectation value
    vip: bool  # Show VIP indicator in UI
    domain: str  # "personal", "church", "work"
    last_updated: datetime
    
    # Additional context
    notes: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "email": self.email,
            "name": self.name,
            "relationship": self.relationship,
            "response_expectation": self.response_expectation,
            "vip": self.vip,
            "domain": self.domain,
            "last_updated": self.last_updated.isoformat(),
            "notes": self.notes,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SenderProfile":
        """Create from dictionary."""
        last_updated = data.get("last_updated")
        if isinstance(last_updated, str):
            last_updated = datetime.fromisoformat(last_updated)
        
        return cls(
            email=data["email"],
            name=data["name"],
            relationship=data.get("relationship", RelationshipType.UNKNOWN.value),
            response_expectation=data.get("response_expectation", ResponseExpectation.NO_EXPECTATION.value),
            vip=data.get("vip", False),
            domain=data.get("domain", "personal"),
            last_updated=last_updated or datetime.now(timezone.utc),
            notes=data.get("notes"),
        )


@dataclass(slots=True)
class ResponseTimeRecord:
    """Record of how long David took to respond to an email."""
    
    email_id: str
    sender_email: str
    sender_type: str  # RelationshipType
    received_at: datetime
    responded_at: Optional[datetime]
    hours_to_response: Optional[float]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "email_id": self.email_id,
            "sender_email": self.sender_email,
            "sender_type": self.sender_type,
            "received_at": self.received_at.isoformat(),
            "responded_at": self.responded_at.isoformat() if self.responded_at else None,
            "hours_to_response": self.hours_to_response,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ResponseTimeRecord":
        """Create from dictionary."""
        received = data.get("received_at")
        if isinstance(received, str):
            received = datetime.fromisoformat(received)
        
        responded = data.get("responded_at")
        if isinstance(responded, str):
            responded = datetime.fromisoformat(responded)
        
        return cls(
            email_id=data["email_id"],
            sender_email=data["sender_email"],
            sender_type=data.get("sender_type", "unknown"),
            received_at=received or datetime.now(timezone.utc),
            responded_at=responded,
            hours_to_response=data.get("hours_to_response"),
        )


@dataclass(slots=True)
class TimingPatterns:
    """Aggregated timing patterns for email processing."""
    
    peak_processing_hours: List[int]  # Hours of day when David processes email
    average_response_time_by_type: Dict[str, float]  # Type -> hours
    batch_vs_continuous: str  # "batch" or "continuous"
    last_updated: datetime
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "peak_processing_hours": self.peak_processing_hours,
            "average_response_time_by_type": self.average_response_time_by_type,
            "batch_vs_continuous": self.batch_vs_continuous,
            "last_updated": self.last_updated.isoformat(),
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TimingPatterns":
        """Create from dictionary."""
        last_updated = data.get("last_updated")
        if isinstance(last_updated, str):
            last_updated = datetime.fromisoformat(last_updated)
        
        return cls(
            peak_processing_hours=data.get("peak_processing_hours", [9, 14, 20]),
            average_response_time_by_type=data.get("average_response_time_by_type", {}),
            batch_vs_continuous=data.get("batch_vs_continuous", "batch"),
            last_updated=last_updated or datetime.now(timezone.utc),
        )


# =============================================================================
# Storage Helpers
# =============================================================================

def _use_file_storage() -> bool:
    """Check if we should use file-based storage."""
    return os.getenv("DTA_EMAIL_MEMORY_FORCE_FILE", "").strip() == "1"


def _get_memory_dir() -> Path:
    """Get the email memory storage directory."""
    env_dir = os.getenv("DTA_EMAIL_MEMORY_DIR", "").strip()
    if env_dir:
        return Path(env_dir)
    return Path(__file__).parent.parent.parent / "email_memory"


def _get_firestore_client():
    """Get Firestore client, or None if not available."""
    if _use_file_storage():
        return None
    
    try:
        from ..firestore import get_firestore_client
        return get_firestore_client()
    except Exception:
        return None


def _hash_pattern(pattern: str) -> str:
    """Create a hash key for a pattern."""
    return hashlib.md5(pattern.lower().encode()).hexdigest()[:16]


# =============================================================================
# Category Pattern Operations
# =============================================================================

def record_category_approval(
    user_id: str,
    pattern: str,
    pattern_type: str,
    category: str,
) -> CategoryPattern:
    """Record that David approved a category suggestion.
    
    This reinforces the pattern, increasing confidence.
    """
    existing = get_category_pattern(user_id, pattern, pattern_type)
    now = datetime.now(timezone.utc)
    
    if existing:
        # Update existing pattern
        existing.approved_count += 1
        existing.sample_count += 1
        # Increase confidence (cap at 0.99)
        existing.confidence = min(0.99, existing.confidence + 0.05)
        existing.last_updated = now
        _save_category_pattern(user_id, existing)
        return existing
    else:
        # Create new pattern
        new_pattern = CategoryPattern(
            pattern_type=pattern_type,
            pattern=pattern,
            preferred_category=category,
            confidence=0.6,
            sample_count=1,
            last_updated=now,
            approved_count=1,
            dismissed_count=0,
        )
        _save_category_pattern(user_id, new_pattern)
        return new_pattern


def record_category_dismissal(
    user_id: str,
    pattern: str,
    pattern_type: str,
) -> None:
    """Record that David dismissed a category suggestion.
    
    This decreases confidence in the pattern.
    """
    existing = get_category_pattern(user_id, pattern, pattern_type)
    
    if existing:
        existing.dismissed_count += 1
        # Decrease confidence (minimum 0.1)
        existing.confidence = max(0.1, existing.confidence - 0.1)
        existing.last_updated = datetime.now(timezone.utc)
        _save_category_pattern(user_id, existing)


def get_category_pattern(
    user_id: str,
    pattern: str,
    pattern_type: str,
) -> Optional[CategoryPattern]:
    """Get a category pattern if it exists."""
    pattern_hash = _hash_pattern(f"{pattern_type}:{pattern}")
    
    db = _get_firestore_client()
    if db is not None:
        return _get_pattern_from_firestore(db, user_id, pattern_hash)
    return _get_pattern_from_file(user_id, pattern_hash)


def get_category_patterns(
    user_id: str,
    limit: int = 100,
) -> List[CategoryPattern]:
    """Get all category patterns for a user."""
    db = _get_firestore_client()
    if db is not None:
        return _list_patterns_from_firestore(db, user_id, limit)
    return _list_patterns_from_file(user_id, limit)


def suggest_category_for_email(
    user_id: str,
    from_address: str,
) -> Optional[CategoryPattern]:
    """Suggest a category based on learned patterns.
    
    Checks both sender-level and domain-level patterns.
    """
    # First try sender-level pattern (more specific)
    sender_pattern = get_category_pattern(
        user_id, from_address.lower(), PatternType.SENDER.value
    )
    if sender_pattern and sender_pattern.confidence > 0.5:
        return sender_pattern
    
    # Fall back to domain-level pattern
    if "@" in from_address:
        domain = from_address.split("@")[1].lower()
        domain_pattern = get_category_pattern(
            user_id, domain, PatternType.DOMAIN.value
        )
        if domain_pattern and domain_pattern.confidence > 0.5:
            return domain_pattern
    
    return None


def _save_category_pattern(user_id: str, pattern: CategoryPattern) -> None:
    """Save a category pattern."""
    pattern_hash = _hash_pattern(f"{pattern.pattern_type}:{pattern.pattern}")
    
    db = _get_firestore_client()
    if db is not None:
        try:
            _save_pattern_to_firestore(db, user_id, pattern_hash, pattern)
        except Exception as e:
            print(f"[EmailMemory] Firestore save failed, falling back: {e}")
            _save_pattern_to_file(user_id, pattern_hash, pattern)
    else:
        _save_pattern_to_file(user_id, pattern_hash, pattern)


# Firestore operations
def _save_pattern_to_firestore(db, user_id: str, pattern_hash: str, pattern: CategoryPattern) -> None:
    """Save pattern to Firestore."""
    doc_ref = (
        db.collection("users")
        .document(user_id)
        .collection("email_memory")
        .document("category_patterns")
        .collection("patterns")
        .document(pattern_hash)
    )
    doc_ref.set(pattern.to_dict())


def _get_pattern_from_firestore(db, user_id: str, pattern_hash: str) -> Optional[CategoryPattern]:
    """Get pattern from Firestore."""
    doc_ref = (
        db.collection("users")
        .document(user_id)
        .collection("email_memory")
        .document("category_patterns")
        .collection("patterns")
        .document(pattern_hash)
    )
    doc = doc_ref.get()
    
    if doc.exists:
        return CategoryPattern.from_dict(doc.to_dict())
    return None


def _list_patterns_from_firestore(db, user_id: str, limit: int) -> List[CategoryPattern]:
    """List patterns from Firestore."""
    collection = (
        db.collection("users")
        .document(user_id)
        .collection("email_memory")
        .document("category_patterns")
        .collection("patterns")
    )
    query = collection.order_by("confidence", direction="DESCENDING").limit(limit)
    
    patterns = []
    for doc in query.stream():
        try:
            patterns.append(CategoryPattern.from_dict(doc.to_dict()))
        except Exception:
            continue
    
    return patterns


# File operations
def _get_patterns_file(user_id: str) -> Path:
    """Get the file path for category patterns."""
    memory_dir = _get_memory_dir()
    memory_dir.mkdir(parents=True, exist_ok=True)
    
    safe_id = user_id.replace("@", "_at_").replace(".", "_")
    return memory_dir / f"{safe_id}_category_patterns.jsonl"


def _save_pattern_to_file(user_id: str, pattern_hash: str, pattern: CategoryPattern) -> None:
    """Save pattern to file."""
    file_path = _get_patterns_file(user_id)
    
    # Read existing patterns
    patterns = {}
    if file_path.exists():
        with file_path.open("r", encoding="utf-8") as f:
            for line in f:
                try:
                    data = json.loads(line.strip())
                    patterns[data.get("_hash", "")] = data
                except Exception:
                    continue
    
    # Upsert
    pattern_data = pattern.to_dict()
    pattern_data["_hash"] = pattern_hash
    patterns[pattern_hash] = pattern_data
    
    # Write all
    with file_path.open("w", encoding="utf-8") as f:
        for data in patterns.values():
            f.write(json.dumps(data) + "\n")


def _get_pattern_from_file(user_id: str, pattern_hash: str) -> Optional[CategoryPattern]:
    """Get pattern from file."""
    file_path = _get_patterns_file(user_id)
    
    if not file_path.exists():
        return None
    
    with file_path.open("r", encoding="utf-8") as f:
        for line in f:
            try:
                data = json.loads(line.strip())
                if data.get("_hash") == pattern_hash:
                    return CategoryPattern.from_dict(data)
            except Exception:
                continue
    
    return None


def _list_patterns_from_file(user_id: str, limit: int) -> List[CategoryPattern]:
    """List patterns from file."""
    file_path = _get_patterns_file(user_id)
    
    if not file_path.exists():
        return []
    
    patterns = []
    with file_path.open("r", encoding="utf-8") as f:
        for line in f:
            try:
                data = json.loads(line.strip())
                patterns.append(CategoryPattern.from_dict(data))
            except Exception:
                continue
    
    # Sort by confidence descending
    patterns.sort(key=lambda p: p.confidence, reverse=True)
    return patterns[:limit]


# =============================================================================
# Sender Profile Operations
# =============================================================================

def get_sender_profile(user_id: str, email: str) -> Optional[SenderProfile]:
    """Get a sender profile if it exists."""
    email_hash = _hash_pattern(email.lower())
    
    db = _get_firestore_client()
    if db is not None:
        return _get_profile_from_firestore(db, user_id, email_hash)
    return _get_profile_from_file(user_id, email_hash)


def save_sender_profile(user_id: str, profile: SenderProfile) -> None:
    """Save or update a sender profile."""
    email_hash = _hash_pattern(profile.email.lower())
    profile.last_updated = datetime.now(timezone.utc)
    
    db = _get_firestore_client()
    if db is not None:
        try:
            _save_profile_to_firestore(db, user_id, email_hash, profile)
        except Exception as e:
            print(f"[EmailMemory] Firestore save failed, falling back: {e}")
            _save_profile_to_file(user_id, email_hash, profile)
    else:
        _save_profile_to_file(user_id, email_hash, profile)


def list_sender_profiles(
    user_id: str,
    vip_only: bool = False,
    limit: int = 100,
) -> List[SenderProfile]:
    """List sender profiles."""
    db = _get_firestore_client()
    if db is not None:
        profiles = _list_profiles_from_firestore(db, user_id, limit)
    else:
        profiles = _list_profiles_from_file(user_id, limit)
    
    if vip_only:
        profiles = [p for p in profiles if p.vip]
    
    return profiles


def is_vip_sender(user_id: str, email: str) -> bool:
    """Check if an email address belongs to a VIP sender."""
    profile = get_sender_profile(user_id, email)
    return profile.vip if profile else False


# Firestore profile operations
def _save_profile_to_firestore(db, user_id: str, email_hash: str, profile: SenderProfile) -> None:
    """Save profile to Firestore."""
    doc_ref = (
        db.collection("users")
        .document(user_id)
        .collection("email_memory")
        .document("sender_profiles")
        .collection("profiles")
        .document(email_hash)
    )
    doc_ref.set(profile.to_dict())


def _get_profile_from_firestore(db, user_id: str, email_hash: str) -> Optional[SenderProfile]:
    """Get profile from Firestore."""
    doc_ref = (
        db.collection("users")
        .document(user_id)
        .collection("email_memory")
        .document("sender_profiles")
        .collection("profiles")
        .document(email_hash)
    )
    doc = doc_ref.get()
    
    if doc.exists:
        return SenderProfile.from_dict(doc.to_dict())
    return None


def _list_profiles_from_firestore(db, user_id: str, limit: int) -> List[SenderProfile]:
    """List profiles from Firestore."""
    collection = (
        db.collection("users")
        .document(user_id)
        .collection("email_memory")
        .document("sender_profiles")
        .collection("profiles")
    )
    query = collection.limit(limit)
    
    profiles = []
    for doc in query.stream():
        try:
            profiles.append(SenderProfile.from_dict(doc.to_dict()))
        except Exception:
            continue
    
    return profiles


# File profile operations
def _get_profiles_file(user_id: str) -> Path:
    """Get the file path for sender profiles."""
    memory_dir = _get_memory_dir()
    memory_dir.mkdir(parents=True, exist_ok=True)
    
    safe_id = user_id.replace("@", "_at_").replace(".", "_")
    return memory_dir / f"{safe_id}_sender_profiles.jsonl"


def _save_profile_to_file(user_id: str, email_hash: str, profile: SenderProfile) -> None:
    """Save profile to file."""
    file_path = _get_profiles_file(user_id)
    
    # Read existing profiles
    profiles = {}
    if file_path.exists():
        with file_path.open("r", encoding="utf-8") as f:
            for line in f:
                try:
                    data = json.loads(line.strip())
                    profiles[data.get("_hash", "")] = data
                except Exception:
                    continue
    
    # Upsert
    profile_data = profile.to_dict()
    profile_data["_hash"] = email_hash
    profiles[email_hash] = profile_data
    
    # Write all
    with file_path.open("w", encoding="utf-8") as f:
        for data in profiles.values():
            f.write(json.dumps(data) + "\n")


def _get_profile_from_file(user_id: str, email_hash: str) -> Optional[SenderProfile]:
    """Get profile from file."""
    file_path = _get_profiles_file(user_id)
    
    if not file_path.exists():
        return None
    
    with file_path.open("r", encoding="utf-8") as f:
        for line in f:
            try:
                data = json.loads(line.strip())
                if data.get("_hash") == email_hash:
                    return SenderProfile.from_dict(data)
            except Exception:
                continue
    
    return None


def _list_profiles_from_file(user_id: str, limit: int) -> List[SenderProfile]:
    """List profiles from file."""
    file_path = _get_profiles_file(user_id)
    
    if not file_path.exists():
        return []
    
    profiles = []
    with file_path.open("r", encoding="utf-8") as f:
        for line in f:
            try:
                data = json.loads(line.strip())
                profiles.append(SenderProfile.from_dict(data))
            except Exception:
                continue
    
    return profiles[:limit]


# =============================================================================
# Timing Pattern Operations
# =============================================================================

def get_timing_patterns(user_id: str) -> Optional[TimingPatterns]:
    """Get timing patterns for a user."""
    db = _get_firestore_client()
    if db is not None:
        return _get_timing_from_firestore(db, user_id)
    return _get_timing_from_file(user_id)


def save_timing_patterns(user_id: str, patterns: TimingPatterns) -> None:
    """Save timing patterns."""
    patterns.last_updated = datetime.now(timezone.utc)
    
    db = _get_firestore_client()
    if db is not None:
        try:
            _save_timing_to_firestore(db, user_id, patterns)
        except Exception as e:
            print(f"[EmailMemory] Firestore save failed, falling back: {e}")
            _save_timing_to_file(user_id, patterns)
    else:
        _save_timing_to_file(user_id, patterns)


def record_response_time(
    user_id: str,
    email_id: str,
    sender_email: str,
    sender_type: str,
    received_at: datetime,
    responded_at: datetime,
) -> ResponseTimeRecord:
    """Record a response time for future analysis."""
    hours = (responded_at - received_at).total_seconds() / 3600
    
    record = ResponseTimeRecord(
        email_id=email_id,
        sender_email=sender_email,
        sender_type=sender_type,
        received_at=received_at,
        responded_at=responded_at,
        hours_to_response=hours,
    )
    
    # Store the record (simplified - just append to file for now)
    _append_response_record(user_id, record)
    
    # Update aggregated timing patterns
    _update_timing_aggregates(user_id, sender_type, hours)
    
    return record


def get_average_response_time(user_id: str, sender_type: str) -> Optional[float]:
    """Get average response time for a sender type."""
    patterns = get_timing_patterns(user_id)
    if patterns and sender_type in patterns.average_response_time_by_type:
        return patterns.average_response_time_by_type[sender_type]
    return None


def _append_response_record(user_id: str, record: ResponseTimeRecord) -> None:
    """Append a response time record to storage."""
    memory_dir = _get_memory_dir()
    memory_dir.mkdir(parents=True, exist_ok=True)
    
    safe_id = user_id.replace("@", "_at_").replace(".", "_")
    file_path = memory_dir / f"{safe_id}_response_times.jsonl"
    
    with file_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record.to_dict()) + "\n")


def _update_timing_aggregates(user_id: str, sender_type: str, hours: float) -> None:
    """Update aggregated timing patterns with new data point."""
    patterns = get_timing_patterns(user_id)
    
    if patterns is None:
        patterns = TimingPatterns(
            peak_processing_hours=[9, 14, 20],
            average_response_time_by_type={},
            batch_vs_continuous="batch",
            last_updated=datetime.now(timezone.utc),
        )
    
    # Simple rolling average update
    if sender_type in patterns.average_response_time_by_type:
        old_avg = patterns.average_response_time_by_type[sender_type]
        # Weight toward recent data (80% old, 20% new)
        patterns.average_response_time_by_type[sender_type] = old_avg * 0.8 + hours * 0.2
    else:
        patterns.average_response_time_by_type[sender_type] = hours
    
    save_timing_patterns(user_id, patterns)


# Firestore timing operations
def _save_timing_to_firestore(db, user_id: str, patterns: TimingPatterns) -> None:
    """Save timing patterns to Firestore."""
    doc_ref = (
        db.collection("users")
        .document(user_id)
        .collection("email_memory")
        .document("timing_patterns")
    )
    doc_ref.set(patterns.to_dict())


def _get_timing_from_firestore(db, user_id: str) -> Optional[TimingPatterns]:
    """Get timing patterns from Firestore."""
    doc_ref = (
        db.collection("users")
        .document(user_id)
        .collection("email_memory")
        .document("timing_patterns")
    )
    doc = doc_ref.get()
    
    if doc.exists:
        return TimingPatterns.from_dict(doc.to_dict())
    return None


# File timing operations
def _get_timing_file(user_id: str) -> Path:
    """Get the file path for timing patterns."""
    memory_dir = _get_memory_dir()
    memory_dir.mkdir(parents=True, exist_ok=True)
    
    safe_id = user_id.replace("@", "_at_").replace(".", "_")
    return memory_dir / f"{safe_id}_timing_patterns.json"


def _save_timing_to_file(user_id: str, patterns: TimingPatterns) -> None:
    """Save timing patterns to file."""
    file_path = _get_timing_file(user_id)
    
    with file_path.open("w", encoding="utf-8") as f:
        json.dump(patterns.to_dict(), f, indent=2)


def _get_timing_from_file(user_id: str) -> Optional[TimingPatterns]:
    """Get timing patterns from file."""
    file_path = _get_timing_file(user_id)
    
    if not file_path.exists():
        return None
    
    with file_path.open("r", encoding="utf-8") as f:
        data = json.load(f)
        return TimingPatterns.from_dict(data)


# =============================================================================
# Seed Data (from Memory Graph)
# =============================================================================

def seed_sender_profiles_from_memory_graph(user_id: str) -> int:
    """Seed sender profiles from David's memory graph.
    
    This creates initial sender profiles based on known relationships.
    Returns the number of profiles created.
    
    Seed data (from user's memory graph):
    - Family (VIP): Esther, Elijah, Daniel, Scarlett, Gloria
    - Work: Laura DeStella-Whippy (manager), Dave Gould (report), peers
    - Church: Members from @southpointsda.org
    """
    now = datetime.now(timezone.utc)
    count = 0
    
    # Family - VIP, immediate response
    family_profiles = [
        SenderProfile(
            email="esther@example.com",  # Placeholder - actual email unknown
            name="Esther Royes",
            relationship=RelationshipType.SPOUSE.value,
            response_expectation=ResponseExpectation.IMMEDIATE.value,
            vip=True,
            domain="personal",
            last_updated=now,
            notes="Wife",
        ),
        SenderProfile(
            email="scarlett@example.com",  # Placeholder
            name="Scarlett Royes",
            relationship=RelationshipType.PARENT.value,
            response_expectation=ResponseExpectation.SAME_DAY.value,
            vip=True,
            domain="personal",
            last_updated=now,
            notes="Mother",
        ),
        SenderProfile(
            email="gloria@example.com",  # Placeholder
            name="Gloria Mora-Ruiz",
            relationship=RelationshipType.PARENT_IN_LAW.value,
            response_expectation=ResponseExpectation.SAME_DAY.value,
            vip=True,
            domain="personal",
            last_updated=now,
            notes="Mother-in-law",
        ),
    ]
    
    # Work relationships (PGA TOUR)
    work_profiles = [
        SenderProfile(
            email="laura.destella-whippy@pgatour.com",
            name="Laura DeStella-Whippy",
            relationship=RelationshipType.WORK_SUPERIOR.value,
            response_expectation=ResponseExpectation.SAME_DAY.value,
            vip=False,  # Important but not VIP
            domain="work",
            last_updated=now,
            notes="Manager - Senior Program Manager Data Technology",
        ),
        SenderProfile(
            email="dave.gould@pgatour.com",
            name="Dave Gould",
            relationship=RelationshipType.WORK_SUBORDINATE.value,
            response_expectation=ResponseExpectation.NEXT_DAY.value,
            vip=False,
            domain="work",
            last_updated=now,
            notes="Direct report - Business Solutions Analyst",
        ),
        SenderProfile(
            email="doug.edwards@pgatour.com",
            name="Doug Edwards",
            relationship=RelationshipType.SKIP_LEVEL_SUPERIOR.value,
            response_expectation=ResponseExpectation.SAME_DAY.value,
            vip=False,
            domain="work",
            last_updated=now,
            notes="Skip-level - VP Technology Solutions",
        ),
        SenderProfile(
            email="mike.vitti@pgatour.com",
            name="Mike Vitti",
            relationship=RelationshipType.SKIP_LEVEL_SUPERIOR.value,
            response_expectation=ResponseExpectation.SAME_DAY.value,
            vip=False,
            domain="work",
            last_updated=now,
            notes="Skip-level - VP/SVP Technology Solutions",
        ),
        SenderProfile(
            email="dianna.haussler@pgatour.com",
            name="Dianna Haussler",
            relationship=RelationshipType.WORK_PEER.value,
            response_expectation=ResponseExpectation.NEXT_DAY.value,
            vip=False,
            domain="work",
            last_updated=now,
            notes="Peer - Project Manager II Technology",
        ),
        SenderProfile(
            email="joe.minutaglio@pgatour.com",
            name="Joe Minutaglio",
            relationship=RelationshipType.WORK_PEER.value,
            response_expectation=ResponseExpectation.NEXT_DAY.value,
            vip=False,
            domain="work",
            last_updated=now,
            notes="Peer - Associate Project Manager",
        ),
    ]
    
    # Save all profiles
    for profile in family_profiles + work_profiles:
        save_sender_profile(user_id, profile)
        count += 1
    
    return count

