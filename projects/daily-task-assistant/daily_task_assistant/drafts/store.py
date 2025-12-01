"""Persistent email draft storage for tasks."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Optional

from ..firestore import get_firestore_client


def _draft_collection() -> str:
    return os.getenv("DTA_DRAFT_COLLECTION", "email_drafts")


def _force_file_fallback() -> bool:
    return os.getenv("DTA_DRAFT_FORCE_FILE", "0") == "1"


def _draft_dir() -> Path:
    return Path(
        os.getenv(
            "DTA_DRAFT_DIR",
            Path(__file__).resolve().parents[2] / "draft_log",
        )
    )


@dataclass
class EmailDraft:
    """Email draft for a task."""
    task_id: str
    to: List[str] = field(default_factory=list)
    cc: List[str] = field(default_factory=list)
    subject: str = ""
    body: str = ""
    from_account: str = ""
    source_content: str = ""  # Original content used to generate draft
    created_at: str = ""
    updated_at: str = ""
    
    def to_dict(self) -> dict:
        """Convert to dictionary for API response."""
        return {
            "taskId": self.task_id,
            "to": self.to,
            "cc": self.cc,
            "subject": self.subject,
            "body": self.body,
            "fromAccount": self.from_account,
            "sourceContent": self.source_content,
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
        }


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def save_draft(
    task_id: str,
    to: List[str],
    cc: List[str],
    subject: str,
    body: str,
    from_account: str = "",
    source_content: str = "",
) -> EmailDraft:
    """Save an email draft for a task.
    
    Args:
        task_id: The Smartsheet row ID
        to: List of recipient email addresses
        cc: List of CC email addresses
        subject: Email subject line
        body: Email body content
        from_account: Gmail account prefix (e.g., 'church', 'personal')
        source_content: Original content used to generate the draft
    
    Returns:
        The saved EmailDraft
    """
    # Check if draft already exists to preserve created_at
    existing = load_draft(task_id)
    created_at = existing.created_at if existing.created_at else _now()
    
    data = EmailDraft(
        task_id=task_id,
        to=to,
        cc=cc,
        subject=subject,
        body=body,
        from_account=from_account,
        source_content=source_content,
        created_at=created_at,
        updated_at=_now(),
    )
    
    if _force_file_fallback():
        _save_to_file(task_id, data)
    else:
        db = get_firestore_client()
        if db:
            try:
                _save_to_firestore(db, task_id, data)
            except Exception as e:
                print(f"[Draft] Firestore write failed, falling back to local: {e}")
                _save_to_file(task_id, data)
        else:
            _save_to_file(task_id, data)
    
    return data


def load_draft(task_id: str) -> EmailDraft:
    """Load an email draft for a task.
    
    Args:
        task_id: The Smartsheet row ID
    
    Returns:
        EmailDraft with content (empty fields if none saved)
    """
    if _force_file_fallback():
        return _load_from_file(task_id)
    
    db = get_firestore_client()
    if db:
        try:
            return _load_from_firestore(db, task_id)
        except Exception as e:
            print(f"[Draft] Firestore read failed, falling back to local: {e}")
            return _load_from_file(task_id)
    
    return _load_from_file(task_id)


def delete_draft(task_id: str) -> None:
    """Delete an email draft for a task (e.g., after sending).
    
    Args:
        task_id: The Smartsheet row ID
    """
    if _force_file_fallback():
        _clear_file(task_id)
    else:
        db = get_firestore_client()
        if db:
            try:
                _clear_firestore(db, task_id)
            except Exception:
                _clear_file(task_id)
        else:
            _clear_file(task_id)


# --- Firestore helpers ---

def _save_to_firestore(db: Any, task_id: str, data: EmailDraft) -> None:
    """Save draft to Firestore."""
    collection = db.collection(_draft_collection())
    doc_ref = collection.document(task_id)
    doc_ref.set(asdict(data))


def _load_from_firestore(db: Any, task_id: str) -> EmailDraft:
    """Load draft from Firestore."""
    collection = db.collection(_draft_collection())
    doc_ref = collection.document(task_id)
    doc = doc_ref.get()
    
    if doc.exists:
        data = doc.to_dict()
        return EmailDraft(
            task_id=data.get("task_id", task_id),
            to=data.get("to", []),
            cc=data.get("cc", []),
            subject=data.get("subject", ""),
            body=data.get("body", ""),
            from_account=data.get("from_account", ""),
            source_content=data.get("source_content", ""),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
        )
    
    return EmailDraft(task_id=task_id)


def _clear_firestore(db: Any, task_id: str) -> None:
    """Delete draft document from Firestore."""
    collection = db.collection(_draft_collection())
    doc_ref = collection.document(task_id)
    doc_ref.delete()


# --- File helpers ---

def _draft_file(task_id: str) -> Path:
    """Get the file path for a task's draft."""
    directory = _draft_dir()
    directory.mkdir(parents=True, exist_ok=True)
    # Sanitize task_id for filename
    safe_id = task_id.replace("/", "_").replace("\\", "_")
    return directory / f"{safe_id}.json"


def _save_to_file(task_id: str, data: EmailDraft) -> None:
    """Save draft to local JSON file."""
    filepath = _draft_file(task_id)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(asdict(data), f, indent=2)


def _load_from_file(task_id: str) -> EmailDraft:
    """Load draft from local JSON file."""
    filepath = _draft_file(task_id)
    
    if not filepath.exists():
        return EmailDraft(task_id=task_id)
    
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
            return EmailDraft(
                task_id=data.get("task_id", task_id),
                to=data.get("to", []),
                cc=data.get("cc", []),
                subject=data.get("subject", ""),
                body=data.get("body", ""),
                from_account=data.get("from_account", ""),
                source_content=data.get("source_content", ""),
                created_at=data.get("created_at", ""),
                updated_at=data.get("updated_at", ""),
            )
    except (json.JSONDecodeError, IOError):
        return EmailDraft(task_id=task_id)


def _clear_file(task_id: str) -> None:
    """Delete draft file."""
    filepath = _draft_file(task_id)
    if filepath.exists():
        filepath.unlink()

