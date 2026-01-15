"""Analysis Store - persistent storage for last analysis results.

This module stores the last inbox analysis result per account for auditing.
Allows David to check from any machine if an analysis was recently run.

Storage is keyed by email ACCOUNT (church/personal), not user ID.

Firestore Structure:
    email_accounts/{account}/metadata/last_analysis -> LastAnalysisRecord document

File Storage Structure:
    analysis_store/{account}/last_analysis.json

Environment Variables:
    DTA_ANALYSIS_FORCE_FILE: Set to "1" to use local file storage (dev mode)
    DTA_ANALYSIS_DIR: Directory for file-based storage (default: analysis_store/)
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from ..firestore import get_firestore_client


def _force_file_fallback() -> bool:
    """Check if file-based storage should be used (dev mode)."""
    return os.getenv("DTA_ANALYSIS_FORCE_FILE", "0") == "1"


def _analysis_dir() -> Path:
    """Return the directory for file-based analysis storage."""
    return Path(
        os.getenv(
            "DTA_ANALYSIS_DIR",
            Path(__file__).resolve().parents[2] / "analysis_store",
        )
    )


def _now() -> datetime:
    """Return current UTC datetime."""
    return datetime.now(timezone.utc)


@dataclass
class LastAnalysisRecord:
    """Last analysis result for auditing."""

    account: str  # "church" or "personal"
    timestamp: str  # ISO format
    emails_fetched: int
    emails_analyzed: int
    already_tracked: int
    dismissed: int
    suggestions_generated: int
    rules_generated: int
    attention_items: int
    haiku_analyzed: int
    haiku_remaining_daily: Optional[int] = None
    haiku_remaining_weekly: Optional[int] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for storage."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "LastAnalysisRecord":
        """Create from dictionary."""
        return cls(
            account=data.get("account", ""),
            timestamp=data.get("timestamp", ""),
            emails_fetched=data.get("emails_fetched", 0),
            emails_analyzed=data.get("emails_analyzed", 0),
            already_tracked=data.get("already_tracked", 0),
            dismissed=data.get("dismissed", 0),
            suggestions_generated=data.get("suggestions_generated", 0),
            rules_generated=data.get("rules_generated", 0),
            attention_items=data.get("attention_items", 0),
            haiku_analyzed=data.get("haiku_analyzed", 0),
            haiku_remaining_daily=data.get("haiku_remaining_daily"),
            haiku_remaining_weekly=data.get("haiku_remaining_weekly"),
        )


def _get_file_path(account: str) -> Path:
    """Get file path for account's last analysis."""
    base = _analysis_dir()
    return base / account / "last_analysis.json"


def save_last_analysis(account: str, record: LastAnalysisRecord) -> None:
    """Save last analysis result for an account."""
    if _force_file_fallback():
        # File-based storage
        file_path = _get_file_path(account)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, "w") as f:
            json.dump(record.to_dict(), f, indent=2)
    else:
        # Firestore storage
        db = get_firestore_client()
        if db:
            doc_ref = db.collection("email_accounts").document(account).collection("metadata").document("last_analysis")
            doc_ref.set(record.to_dict())
        else:
            # Fall back to file if Firestore unavailable
            file_path = _get_file_path(account)
            file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(file_path, "w") as f:
                json.dump(record.to_dict(), f, indent=2)


def get_last_analysis(account: str) -> Optional[LastAnalysisRecord]:
    """Get last analysis result for an account."""
    if _force_file_fallback():
        # File-based storage
        file_path = _get_file_path(account)
        if file_path.exists():
            with open(file_path) as f:
                data = json.load(f)
                return LastAnalysisRecord.from_dict(data)
        return None
    else:
        # Firestore storage
        db = get_firestore_client()
        if db:
            doc_ref = db.collection("email_accounts").document(account).collection("metadata").document("last_analysis")
            doc = doc_ref.get()
            if doc.exists:
                return LastAnalysisRecord.from_dict(doc.to_dict())
            return None
        else:
            # Fall back to file if Firestore unavailable
            file_path = _get_file_path(account)
            if file_path.exists():
                with open(file_path) as f:
                    data = json.load(f)
                    return LastAnalysisRecord.from_dict(data)
            return None
