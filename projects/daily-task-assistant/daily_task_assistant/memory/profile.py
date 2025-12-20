"""David Profile - persistent user context for role-aware email management.

This module provides the DavidProfile dataclass and Firestore CRUD operations
for storing and retrieving user profile data. The profile enables role-aware
email detection by understanding David's church roles and personal contexts.

IMPORTANT: Profile is GLOBAL (not per-login-identity).
David has multiple login emails but ONE profile shared across all logins.

Firestore Structure:
    global/david/profile/current  -> DavidProfile document
    global/david/profile/v_{timestamp} -> Historical versions (audit)

File Storage (dev mode):
    profile_store/global/profile.json

Environment Variables:
    DTA_PROFILE_FORCE_FILE: Set to "1" to use local file storage (dev mode)
    DTA_PROFILE_DIR: Directory for file-based storage (default: profile_store/)
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..firestore import get_firestore_client


# Global user identifier (profile is shared across all login identities)
GLOBAL_USER_ID = "david"


# Configuration helpers
def _profile_collection() -> str:
    """Return the Firestore collection path for profiles."""
    return os.getenv("DTA_PROFILE_COLLECTION", "global")


def _force_file_fallback() -> bool:
    """Check if file-based storage should be used (dev mode)."""
    return os.getenv("DTA_PROFILE_FORCE_FILE", "0") == "1"


def _profile_dir() -> Path:
    """Return the directory for file-based profile storage."""
    return Path(
        os.getenv(
            "DTA_PROFILE_DIR",
            Path(__file__).resolve().parents[2] / "profile_store",
        )
    )


def _now() -> str:
    """Return current UTC timestamp as ISO string."""
    return datetime.now(timezone.utc).isoformat()


@dataclass
class DavidProfile:
    """David's profile for role-aware email management.

    This profile captures church roles, personal contexts, VIP senders,
    attention patterns, and not-actionable patterns to enable intelligent
    email detection that goes beyond simple regex matching.

    Attributes:
        user_id: Unique identifier (typically email address)
        church_roles: List of church leadership roles (e.g., "Treasurer", "Head Elder")
        personal_contexts: List of personal life contexts (e.g., "Homeowner", "Parent")
        vip_senders: Dict mapping account type to list of VIP sender descriptions
        church_attention_patterns: Dict mapping church role to attention keywords
        personal_attention_patterns: Dict mapping personal context to attention keywords
        not_actionable_patterns: Dict mapping account type to patterns to skip
        version: Profile schema version for migrations
        created_at: ISO timestamp of profile creation
        updated_at: ISO timestamp of last update
    """
    user_id: str

    # Church Roles (for church email context)
    church_roles: List[str] = field(default_factory=list)

    # Personal Life Contexts (for personal email context)
    personal_contexts: List[str] = field(default_factory=list)

    # VIP Senders (high priority regardless of content)
    vip_senders: Dict[str, List[str]] = field(default_factory=dict)

    # Role/Context-Specific Attention Patterns
    church_attention_patterns: Dict[str, List[str]] = field(default_factory=dict)
    personal_attention_patterns: Dict[str, List[str]] = field(default_factory=dict)

    # Not-Actionable Patterns (skip these)
    not_actionable_patterns: Dict[str, List[str]] = field(default_factory=dict)

    # Metadata
    version: str = "1.0.0"
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)

    def to_dict(self) -> Dict[str, Any]:
        """Convert profile to dictionary for storage."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DavidProfile":
        """Create profile from dictionary."""
        return cls(**data)


def get_default_profile() -> DavidProfile:
    """Return the default David profile with initial seed data.

    This provides a starting point for David's profile with his known
    church roles and personal contexts. The profile is designed to be
    editable via the UI as life circumstances change.

    Note: Profile is GLOBAL - shared across all login identities.
    """
    return DavidProfile(
        user_id=GLOBAL_USER_ID,

        # Church Roles
        church_roles=[
            "Treasurer",
            "Procurement Lead",
            "Maintenance Lead",
            "Head Elder",  # Temporary - leading church while pastorless
            "IT Lead",
        ],

        # Personal Contexts
        personal_contexts=[
            "Homeowner",
            "Parent",
            "Family Coordinator",
            "Pet Owner",
            "Financial",
        ],

        # VIP Senders (always high priority)
        vip_senders={
            "personal": [
                "esther",  # Wife - ALWAYS high priority
                "elijah",  # Son
                "daniel",  # Son
                "scarlett",  # Mother
                "gloria",  # Mother-in-law
            ],
            "church": [
                "earl fenstermacher",  # Head elder
                "florida conference",  # FL Conference treasury
                "floridaconference.com",
            ],
        },

        # Church Attention Patterns (role -> keywords)
        church_attention_patterns={
            "Treasurer": [
                "past due",
                "invoice",
                "year-end",
                "1099",
                "payment",
                "reimbursement",
                "check request",
                "deposit",
                "bank statement",
                "time record",  # Payroll time records from staff
                "timesheet",
                "payroll",
                "expense report",
            ],
            "Procurement Lead": [
                "pending purchase",
                "PO-",
                "MSR-",
                "delivery pending",
                "approval status",
                "purchase request",
                "order status",
            ],
            "Maintenance Lead": [
                "maintenance issue",
                "open maintenance",
                "repair needed",
                "facility",
                "building issue",
            ],
            "Head Elder": [
                "board meeting",
                "did not receive approval",
                "elder in charge",
                "pastor search",
                "church leadership",
                "membership",
                "discipline",
                "nominating committee",
            ],
            "IT Lead": [
                "website",
                "streaming",
                "AV issue",
                "tech support",
                "sound system",
                "projector",
            ],
        },

        # Personal Attention Patterns (context -> keywords)
        personal_attention_patterns={
            "Homeowner": [
                "home repair",
                "maintenance due",
                "HOA",
                "utility bill",
                "property tax",
                "insurance renewal",
                "mortgage",
            ],
            "Parent": [
                "school",
                "pickup",
                "permission",
                "report card",
                "parent meeting",
                "elijah",
                "daniel",
                "teacher",
            ],
            "Family Coordinator": [
                "appointment",
                "reservation",
                "travel itinerary",
                "family event",
                "birthday",
                "anniversary",
            ],
            "Pet Owner": [
                "vet appointment",
                "koko",
                "nix",
                "pet",
            ],
            "Financial": [
                "statement ready",
                "payment due",
                "bill reminder",
                "account alert",
                "fraud alert",
                "tax document",
                "credit card",
            ],
        },

        # Not-Actionable Patterns (skip these emails)
        not_actionable_patterns={
            "church": [
                "prayer request from cliflobartley",
                "prayer request from flo.bartley",
                "onedrive memories",
                "google cloud marketing",
                "promotional",
            ],
            "personal": [
                "onedrive memories",
                "google photos memories",
                "smartsheet automation",
                "marketing newsletter",
                "promotional offer",
                "unsubscribe",
            ],
        },

        version="1.0.0",
        created_at=_now(),
        updated_at=_now(),
    )


# Firestore CRUD Operations

def get_profile() -> Optional[DavidProfile]:
    """Retrieve the global profile from storage.

    Profile is GLOBAL - shared across all login identities.

    Returns:
        DavidProfile if found, None otherwise
    """
    if _force_file_fallback():
        return _read_file_profile()

    try:
        client = get_firestore_client()
        doc_ref = (
            client.collection(_profile_collection())
            .document(GLOBAL_USER_ID)
            .collection("profile")
            .document("current")
        )
        doc = doc_ref.get()

        if doc.exists:
            return DavidProfile.from_dict(doc.to_dict())
        return None

    except Exception as exc:
        print(f"[Profile] Firestore read failed, falling back to file: {exc}")
        return _read_file_profile()


def save_profile(profile: DavidProfile) -> bool:
    """Save or update the global profile in storage.

    Also creates a versioned backup for audit purposes.
    Profile is GLOBAL - shared across all login identities.

    Args:
        profile: The DavidProfile to save

    Returns:
        True if save succeeded, False otherwise
    """
    # Update timestamp
    profile.updated_at = _now()

    if _force_file_fallback():
        return _write_file_profile(profile)

    try:
        client = get_firestore_client()
        # Use GLOBAL path, not profile.user_id
        global_ref = client.collection(_profile_collection()).document(GLOBAL_USER_ID)

        # Save current profile
        current_ref = global_ref.collection("profile").document("current")
        current_ref.set(profile.to_dict())

        # Save versioned backup
        version_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        version_ref = global_ref.collection("profile").document(f"v_{version_id}")
        version_ref.set(profile.to_dict())

        # Clean up old versions (keep last 5)
        _cleanup_old_versions(global_ref, keep=5)

        return True

    except Exception as exc:
        print(f"[Profile] Firestore save failed, falling back to file: {exc}")
        return _write_file_profile(profile)


def get_or_create_profile() -> DavidProfile:
    """Get existing profile or create default if none exists.

    Profile is GLOBAL - shared across all login identities.

    Returns:
        Existing profile or newly created default profile
    """
    profile = get_profile()
    if profile is None:
        profile = get_default_profile()
        save_profile(profile)
    return profile


def _cleanup_old_versions(user_ref, keep: int = 5) -> None:
    """Remove old profile versions, keeping only the most recent ones.

    Args:
        user_ref: Firestore document reference for the user
        keep: Number of versions to retain
    """
    try:
        versions = (
            user_ref.collection("profile")
            .where("__name__", ">=", "v_")
            .order_by("__name__")
            .stream()
        )

        version_docs = [doc for doc in versions if doc.id.startswith("v_")]

        # Delete older versions beyond the keep limit
        if len(version_docs) > keep:
            for doc in version_docs[:-keep]:
                doc.reference.delete()

    except Exception as exc:
        # Non-critical, just log and continue
        print(f"[Profile] Version cleanup failed: {exc}")


# File-based fallback for development

def _profile_file() -> Path:
    """Return the file path for the global profile."""
    directory = _profile_dir() / "global"
    directory.mkdir(parents=True, exist_ok=True)
    return directory / "profile.json"


def _read_file_profile() -> Optional[DavidProfile]:
    """Read profile from local JSON file."""
    path = _profile_file()
    if not path.exists():
        return None

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return DavidProfile.from_dict(data)
    except (json.JSONDecodeError, TypeError) as exc:
        print(f"[Profile] Failed to read file profile: {exc}")
        return None


def _write_file_profile(profile: DavidProfile) -> bool:
    """Write profile to local JSON file."""
    path = _profile_file()

    try:
        path.write_text(
            json.dumps(profile.to_dict(), indent=2),
            encoding="utf-8"
        )
        return True
    except Exception as exc:
        print(f"[Profile] Failed to write file profile: {exc}")
        return False


# Profile Feedback System (Sprint 5)


def add_not_actionable_pattern(
    account: str,
    pattern: str,
) -> bool:
    """Add a pattern to not-actionable list based on rejection feedback.

    Called when a user rejects suggestions multiple times with similar patterns.
    This teaches DATA to skip similar emails in the future.

    Args:
        account: Email account ("church" or "personal")
        pattern: The pattern to mark as not actionable

    Returns:
        True if pattern was added, False if it already exists or failed
    """
    profile = get_or_create_profile()

    # Get or initialize the account's not-actionable list
    patterns = profile.not_actionable_patterns.get(account, [])

    # Check if pattern already exists (case-insensitive)
    pattern_lower = pattern.lower()
    if any(p.lower() == pattern_lower for p in patterns):
        return False  # Already exists

    # Add the new pattern
    patterns.append(pattern)
    profile.not_actionable_patterns[account] = patterns

    return save_profile(profile)


def remove_not_actionable_pattern(
    account: str,
    pattern: str,
) -> bool:
    """Remove a pattern from not-actionable list.

    Called when user explicitly wants to receive attention for this pattern again.

    Args:
        account: Email account ("church" or "personal")
        pattern: The pattern to remove

    Returns:
        True if pattern was removed, False if not found
    """
    profile = get_profile()
    if profile is None:
        return False

    patterns = profile.not_actionable_patterns.get(account, [])

    # Find and remove pattern (case-insensitive)
    pattern_lower = pattern.lower()
    original_len = len(patterns)
    patterns = [p for p in patterns if p.lower() != pattern_lower]

    if len(patterns) == original_len:
        return False  # Pattern not found

    profile.not_actionable_patterns[account] = patterns
    return save_profile(profile)


def get_rejection_candidates(
    days: int = 30,
    min_rejections: int = 3,
) -> Dict[str, List[Dict[str, Any]]]:
    """Analyze rejected suggestions to find patterns for not-actionable.

    Returns patterns that have been rejected multiple times, suggesting
    they should be added to the not-actionable list.

    Note: This is a GLOBAL analysis function that queries suggestions
    from BOTH accounts (church and personal) to inform the global profile.

    Args:
        days: Days to look back
        min_rejections: Minimum rejections to suggest as pattern

    Returns:
        Dict with 'church' and 'personal' keys, each containing list of
        candidate patterns with rejection counts
    """
    from ..email.suggestion_store import (
        _force_file_fallback as _suggestion_force_file,
        _suggestion_dir,
        SuggestionRecord,
        _now,
    )
    from datetime import timedelta
    from collections import Counter

    cutoff = _now() - timedelta(days=days)

    # Track rejections by account and pattern
    rejections: Dict[str, Counter] = {
        "church": Counter(),
        "personal": Counter(),
    }

    # Query both accounts
    accounts = ["church", "personal"]

    # Try Firestore first (if not forcing file fallback)
    used_firestore = False
    if not _suggestion_force_file():
        try:
            from ..firestore import get_firestore_client
            db = get_firestore_client()
            if db:
                for account in accounts:
                    # Use account-based path (matches Phase 2.1 structure)
                    collection = (
                        db.collection("email_accounts")
                        .document(account)
                        .collection("suggestions")
                    )
                    query = collection.where(
                        "status", "==", "rejected"
                    ).where("created_at", ">=", cutoff.isoformat())

                    for doc in query.stream():
                        data = doc.to_dict()
                        pattern_key = data.get("rationale", "").lower()[:50]
                        rejections[account][pattern_key] += 1
                used_firestore = True
        except Exception:
            # Fall back to file-based storage
            pass

    # File-based: read suggestions from both accounts (if Firestore wasn't used)
    if not used_firestore:
        for account in accounts:
            store_dir = _suggestion_dir() / account
            if store_dir.exists():
                for file_path in store_dir.glob("*.json"):
                    with open(file_path, "r", encoding="utf-8") as f:
                        data = json.load(f)

                    record = SuggestionRecord.from_dict(data)

                    # Only count recent rejections
                    if record.status == "rejected" and record.created_at >= cutoff:
                        # Use rationale as the pattern identifier
                        pattern_key = record.rationale.lower()[:50]
                        rejections[account][pattern_key] += 1

    # Build candidate list
    candidates = {
        "church": [],
        "personal": [],
    }

    for account, counter in rejections.items():
        for pattern, count in counter.most_common():
            if count >= min_rejections:
                candidates[account].append({
                    "pattern": pattern,
                    "rejectionCount": count,
                    "suggestedAction": "add_to_not_actionable",
                })

    return candidates
