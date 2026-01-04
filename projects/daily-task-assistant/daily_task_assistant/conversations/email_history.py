"""Email Conversation History - persistent storage for email-related conversations.

This module provides conversation persistence for email discussions with DATA.
Conversations are keyed by thread_id (Gmail's thread grouping) and account,
allowing context to follow across Dashboard, Suggestions, and Attention views.

Storage is keyed by email ACCOUNT (church/personal), not user ID, so the same
data is accessible regardless of which user identity is used to log in.

Firestore Structure:
    email_accounts/{account}/email_conversations/{thread_id}/
        metadata (doc)  -> EmailThreadMetadata
        messages (collection) -> EmailConversationMessage documents

File Storage Structure:
    email_conversation_log/{account}/{thread_id}.jsonl

Environment Variables:
    DTA_EMAIL_CONVERSATION_FORCE_FILE: Set to "1" to use local file storage (dev mode)
    DTA_EMAIL_CONVERSATION_DIR: Directory for file-based storage
    DTA_EMAIL_CONVERSATION_TTL_DAYS: Days to keep conversations (default: 90)
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
AccountType = Literal["church", "personal"]
MessageRole = Literal["user", "assistant"]
SensitivityLevel = Literal["normal", "sensitive", "blocked"]


# Configuration helpers
def _force_file_fallback() -> bool:
    """Check if file-based storage should be used (dev mode)."""
    return os.getenv("DTA_EMAIL_CONVERSATION_FORCE_FILE", "0") == "1"


def _conversation_dir() -> Path:
    """Return the directory for file-based conversation storage."""
    return Path(
        os.getenv(
            "DTA_EMAIL_CONVERSATION_DIR",
            Path(__file__).resolve().parents[2] / "email_conversation_log",
        )
    )


def _ttl_days() -> int:
    """Return TTL for email conversations in days (default: 90)."""
    return int(os.getenv("DTA_EMAIL_CONVERSATION_TTL_DAYS", "90"))


def _now() -> datetime:
    """Return current UTC datetime."""
    return datetime.now(timezone.utc)


def _now_str() -> str:
    """Return current UTC datetime as ISO string."""
    return _now().isoformat()


def _validate_account(account: str) -> AccountType:
    """Validate and normalize account identifier."""
    if account not in ("church", "personal"):
        raise ValueError(f"Invalid account: {account}. Must be 'church' or 'personal'")
    return account  # type: ignore


@dataclass
class EmailConversationMessage:
    """A single message in an email conversation.

    Attributes:
        role: "user" or "assistant"
        content: The message text
        ts: ISO timestamp when message was logged
        email_context: Specific email_id being discussed (optional)
        metadata: Additional metadata (user info, etc.)
    """
    role: MessageRole
    content: str
    ts: str = field(default_factory=_now_str)
    email_context: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "role": self.role,
            "content": self.content,
            "ts": self.ts,
            "email_context": self.email_context,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EmailConversationMessage":
        """Create message from dictionary."""
        return cls(
            role=data["role"],
            content=data["content"],
            ts=data.get("ts", _now_str()),
            email_context=data.get("email_context"),
            metadata=data.get("metadata", {}),
        )


@dataclass
class EmailThreadMetadata:
    """Metadata snapshot for an email conversation thread.

    Stored separately from messages for quick access without loading full history.

    Attributes:
        thread_id: Gmail thread ID
        account: "church" or "personal"
        subject: Email subject line
        from_email: Original sender email
        from_name: Original sender display name
        last_email_date: Date of most recent email in thread
        sensitivity: "normal", "sensitive", or "blocked"
        override_granted: User explicitly shared this email with DATA (persists across sessions)
        created_at: When conversation was first started
        expires_at: TTL expiration (90 days from creation)
        message_count: Number of messages in conversation
        last_message_at: When last message was logged
    """
    thread_id: str
    account: AccountType
    subject: str = ""
    from_email: str = ""
    from_name: Optional[str] = None
    last_email_date: Optional[str] = None
    sensitivity: SensitivityLevel = "normal"
    override_granted: bool = False
    created_at: str = field(default_factory=_now_str)
    expires_at: Optional[str] = None
    message_count: int = 0
    last_message_at: Optional[str] = None

    def __post_init__(self):
        """Set default expires_at based on TTL."""
        if self.expires_at is None:
            expiry = _now() + timedelta(days=_ttl_days())
            self.expires_at = expiry.isoformat()

    def is_expired(self) -> bool:
        """Check if this conversation has expired."""
        if self.expires_at is None:
            return False
        expires = datetime.fromisoformat(self.expires_at)
        return _now() > expires

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "thread_id": self.thread_id,
            "account": self.account,
            "subject": self.subject,
            "from_email": self.from_email,
            "from_name": self.from_name,
            "last_email_date": self.last_email_date,
            "sensitivity": self.sensitivity,
            "override_granted": self.override_granted,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "message_count": self.message_count,
            "last_message_at": self.last_message_at,
        }

    def to_api_dict(self) -> Dict[str, Any]:
        """Convert to API-friendly dict (camelCase)."""
        return {
            "threadId": self.thread_id,
            "account": self.account,
            "subject": self.subject,
            "fromEmail": self.from_email,
            "fromName": self.from_name,
            "lastEmailDate": self.last_email_date,
            "sensitivity": self.sensitivity,
            "overrideGranted": self.override_granted,
            "createdAt": self.created_at,
            "expiresAt": self.expires_at,
            "messageCount": self.message_count,
            "lastMessageAt": self.last_message_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EmailThreadMetadata":
        """Create metadata from dictionary."""
        return cls(
            thread_id=data["thread_id"],
            account=data["account"],
            subject=data.get("subject", ""),
            from_email=data.get("from_email", ""),
            from_name=data.get("from_name"),
            last_email_date=data.get("last_email_date"),
            sensitivity=data.get("sensitivity", "normal"),
            override_granted=data.get("override_granted", False),
            created_at=data.get("created_at", _now_str()),
            expires_at=data.get("expires_at"),
            message_count=data.get("message_count", 0),
            last_message_at=data.get("last_message_at"),
        )


# =============================================================================
# Public API
# =============================================================================

def log_email_message(
    account: str,
    thread_id: str,
    role: MessageRole,
    content: str,
    email_context: Optional[str] = None,
    user_email: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> EmailConversationMessage:
    """Log a message to an email thread's conversation.

    Creates the conversation if it doesn't exist.

    Args:
        account: Email account ("church" or "personal")
        thread_id: Gmail thread ID
        role: "user" or "assistant"
        content: Message text
        email_context: Specific email_id being discussed (optional)
        user_email: User's email for metadata (optional)
        metadata: Additional metadata (optional)

    Returns:
        The created EmailConversationMessage
    """
    account = _validate_account(account)

    msg_metadata = metadata or {}
    if user_email:
        msg_metadata["user"] = user_email

    message = EmailConversationMessage(
        role=role,
        content=content.strip(),
        ts=_now_str(),
        email_context=email_context,
        metadata=msg_metadata,
    )

    if _force_file_fallback():
        _append_message_file(account, thread_id, message)
    else:
        _append_message_firestore(account, thread_id, message)

    return message


def fetch_email_conversation(
    account: str,
    thread_id: str,
    limit: int = 50,
) -> List[EmailConversationMessage]:
    """Retrieve conversation history for a thread.

    Args:
        account: Email account ("church" or "personal")
        thread_id: Gmail thread ID
        limit: Maximum messages to return (default: 50)

    Returns:
        List of EmailConversationMessage, ordered oldest → newest
    """
    account = _validate_account(account)

    if _force_file_fallback():
        return _fetch_conversation_file(account, thread_id, limit)
    return _fetch_conversation_firestore(account, thread_id, limit)


def get_conversation_metadata(
    account: str,
    thread_id: str,
) -> Optional[EmailThreadMetadata]:
    """Get thread metadata (subject, from, sensitivity).

    Args:
        account: Email account ("church" or "personal")
        thread_id: Gmail thread ID

    Returns:
        EmailThreadMetadata if conversation exists, None otherwise
    """
    account = _validate_account(account)

    if _force_file_fallback():
        return _get_metadata_file(account, thread_id)
    return _get_metadata_firestore(account, thread_id)


def update_conversation_metadata(
    account: str,
    thread_id: str,
    subject: Optional[str] = None,
    from_email: Optional[str] = None,
    from_name: Optional[str] = None,
    last_email_date: Optional[str] = None,
    sensitivity: Optional[SensitivityLevel] = None,
    override_granted: Optional[bool] = None,
) -> Optional[EmailThreadMetadata]:
    """Update thread metadata.

    Creates metadata if it doesn't exist.

    Args:
        account: Email account ("church" or "personal")
        thread_id: Gmail thread ID
        subject: Email subject line (optional)
        from_email: Sender email (optional)
        from_name: Sender display name (optional)
        last_email_date: Date of most recent email (optional)
        sensitivity: Privacy level (optional)
        override_granted: User explicitly shared email with DATA (optional)

    Returns:
        Updated EmailThreadMetadata
    """
    account = _validate_account(account)

    # Get existing or create new
    existing = get_conversation_metadata(account, thread_id)
    if existing:
        if subject is not None:
            existing.subject = subject
        if from_email is not None:
            existing.from_email = from_email
        if from_name is not None:
            existing.from_name = from_name
        if last_email_date is not None:
            existing.last_email_date = last_email_date
        if sensitivity is not None:
            existing.sensitivity = sensitivity
        if override_granted is not None:
            existing.override_granted = override_granted
        metadata = existing
    else:
        metadata = EmailThreadMetadata(
            thread_id=thread_id,
            account=account,
            subject=subject or "",
            from_email=from_email or "",
            from_name=from_name,
            last_email_date=last_email_date,
            sensitivity=sensitivity or "normal",
            override_granted=override_granted or False,
        )

    if _force_file_fallback():
        _save_metadata_file(account, thread_id, metadata)
    else:
        _save_metadata_firestore(account, thread_id, metadata)

    return metadata


def has_conversation(account: str, thread_id: str) -> bool:
    """Check if a conversation exists for this thread.

    Args:
        account: Email account ("church" or "personal")
        thread_id: Gmail thread ID

    Returns:
        True if conversation has messages
    """
    account = _validate_account(account)
    metadata = get_conversation_metadata(account, thread_id)
    return metadata is not None and metadata.message_count > 0


def clear_email_conversation(account: str, thread_id: str) -> bool:
    """Delete a conversation and its messages.

    Args:
        account: Email account ("church" or "personal")
        thread_id: Gmail thread ID

    Returns:
        True if conversation was deleted, False if not found
    """
    account = _validate_account(account)

    if _force_file_fallback():
        return _clear_conversation_file(account, thread_id)
    return _clear_conversation_firestore(account, thread_id)


def purge_expired_conversations(account: str) -> int:
    """Purge expired conversations for an email account.

    Args:
        account: Email account ("church" or "personal")

    Returns:
        Count of conversations purged
    """
    account = _validate_account(account)

    if _force_file_fallback():
        return _purge_expired_file(account)
    return _purge_expired_firestore(account)


def list_recent_conversations(
    account: str,
    limit: int = 20,
) -> List[EmailThreadMetadata]:
    """List recent email conversations for an account.

    Args:
        account: Email account ("church" or "personal")
        limit: Maximum conversations to return (default: 20)

    Returns:
        List of EmailThreadMetadata, ordered by last_message_at descending
    """
    account = _validate_account(account)

    if _force_file_fallback():
        return _list_recent_file(account, limit)
    return _list_recent_firestore(account, limit)


# =============================================================================
# Firestore Implementation
# =============================================================================

def _get_thread_doc_ref(account: str, thread_id: str):
    """Get Firestore document reference for a thread."""
    db = get_firestore_client()
    if db is None:
        return None
    return (
        db.collection("email_accounts")
        .document(account)
        .collection("email_conversations")
        .document(thread_id)
    )


def _append_message_firestore(
    account: str,
    thread_id: str,
    message: EmailConversationMessage,
) -> None:
    """Append message to Firestore."""
    db = get_firestore_client()
    if db is None:
        _append_message_file(account, thread_id, message)
        return

    thread_ref = _get_thread_doc_ref(account, thread_id)
    if thread_ref is None:
        _append_message_file(account, thread_id, message)
        return

    # Add message to subcollection
    thread_ref.collection("messages").add(message.to_dict())

    # Update metadata
    metadata_doc = thread_ref.get()
    if metadata_doc.exists:
        thread_ref.update({
            "message_count": metadata_doc.to_dict().get("message_count", 0) + 1,
            "last_message_at": message.ts,
        })
    else:
        # Create new metadata
        metadata = EmailThreadMetadata(
            thread_id=thread_id,
            account=account,
            message_count=1,
            last_message_at=message.ts,
        )
        thread_ref.set(metadata.to_dict())


def _fetch_conversation_firestore(
    account: str,
    thread_id: str,
    limit: int,
) -> List[EmailConversationMessage]:
    """Fetch conversation from Firestore."""
    db = get_firestore_client()
    if db is None:
        return _fetch_conversation_file(account, thread_id, limit)

    thread_ref = _get_thread_doc_ref(account, thread_id)
    if thread_ref is None:
        return _fetch_conversation_file(account, thread_id, limit)

    # Check expiration first
    metadata_doc = thread_ref.get()
    if metadata_doc.exists:
        metadata = EmailThreadMetadata.from_dict(metadata_doc.to_dict())
        if metadata.is_expired():
            _clear_conversation_firestore(account, thread_id)
            return []

    from firebase_admin import firestore as fb_firestore  # type: ignore

    query = (
        thread_ref.collection("messages")
        .order_by("ts", direction=fb_firestore.Query.ASCENDING)
        .limit(limit)
    )

    messages = []
    for doc in query.stream():
        messages.append(EmailConversationMessage.from_dict(doc.to_dict()))

    return messages


def _get_metadata_firestore(account: str, thread_id: str) -> Optional[EmailThreadMetadata]:
    """Get metadata from Firestore."""
    db = get_firestore_client()
    if db is None:
        return _get_metadata_file(account, thread_id)

    thread_ref = _get_thread_doc_ref(account, thread_id)
    if thread_ref is None:
        return _get_metadata_file(account, thread_id)

    doc = thread_ref.get()
    if not doc.exists:
        return None

    metadata = EmailThreadMetadata.from_dict(doc.to_dict())
    if metadata.is_expired():
        _clear_conversation_firestore(account, thread_id)
        return None

    return metadata


def _save_metadata_firestore(
    account: str,
    thread_id: str,
    metadata: EmailThreadMetadata,
) -> None:
    """Save metadata to Firestore."""
    db = get_firestore_client()
    if db is None:
        _save_metadata_file(account, thread_id, metadata)
        return

    thread_ref = _get_thread_doc_ref(account, thread_id)
    if thread_ref is None:
        _save_metadata_file(account, thread_id, metadata)
        return

    thread_ref.set(metadata.to_dict(), merge=True)


def _clear_conversation_firestore(account: str, thread_id: str) -> bool:
    """Clear conversation from Firestore."""
    db = get_firestore_client()
    if db is None:
        return _clear_conversation_file(account, thread_id)

    thread_ref = _get_thread_doc_ref(account, thread_id)
    if thread_ref is None:
        return _clear_conversation_file(account, thread_id)

    # Delete all messages in subcollection
    messages_ref = thread_ref.collection("messages")
    for doc in messages_ref.stream():
        doc.reference.delete()

    # Delete metadata document
    thread_ref.delete()
    return True


def _purge_expired_firestore(account: str) -> int:
    """Purge expired conversations from Firestore."""
    db = get_firestore_client()
    if db is None:
        return _purge_expired_file(account)

    collection_ref = (
        db.collection("email_accounts")
        .document(account)
        .collection("email_conversations")
    )

    now_str = _now().isoformat()
    query = collection_ref.where("expires_at", "<", now_str)

    count = 0
    for doc in query.stream():
        thread_id = doc.id
        _clear_conversation_firestore(account, thread_id)
        count += 1

    return count


def _list_recent_firestore(account: str, limit: int) -> List[EmailThreadMetadata]:
    """List recent conversations from Firestore."""
    db = get_firestore_client()
    if db is None:
        return _list_recent_file(account, limit)

    from firebase_admin import firestore as fb_firestore  # type: ignore

    collection_ref = (
        db.collection("email_accounts")
        .document(account)
        .collection("email_conversations")
    )

    query = (
        collection_ref
        .order_by("last_message_at", direction=fb_firestore.Query.DESCENDING)
        .limit(limit)
    )

    results = []
    for doc in query.stream():
        metadata = EmailThreadMetadata.from_dict(doc.to_dict())
        if not metadata.is_expired():
            results.append(metadata)

    return results


# =============================================================================
# File Storage Implementation
# =============================================================================

def _conversation_file(account: str, thread_id: str) -> Path:
    """Get file path for a thread's conversation."""
    directory = _conversation_dir() / account
    directory.mkdir(parents=True, exist_ok=True)
    # Sanitize thread_id for filesystem
    safe_id = thread_id.replace("/", "_").replace("\\", "_")
    return directory / f"{safe_id}.jsonl"


def _metadata_file(account: str, thread_id: str) -> Path:
    """Get file path for a thread's metadata."""
    directory = _conversation_dir() / account
    directory.mkdir(parents=True, exist_ok=True)
    safe_id = thread_id.replace("/", "_").replace("\\", "_")
    return directory / f"{safe_id}.meta.json"


def _append_message_file(
    account: str,
    thread_id: str,
    message: EmailConversationMessage,
) -> None:
    """Append message to file storage."""
    conv_path = _conversation_file(account, thread_id)
    with conv_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(message.to_dict()))
        f.write("\n")

    # Update metadata
    meta_path = _metadata_file(account, thread_id)
    if meta_path.exists():
        with meta_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        metadata = EmailThreadMetadata.from_dict(data)
        metadata.message_count += 1
        metadata.last_message_at = message.ts
    else:
        metadata = EmailThreadMetadata(
            thread_id=thread_id,
            account=account,
            message_count=1,
            last_message_at=message.ts,
        )

    with meta_path.open("w", encoding="utf-8") as f:
        json.dump(metadata.to_dict(), f, indent=2)


def _fetch_conversation_file(
    account: str,
    thread_id: str,
    limit: int,
) -> List[EmailConversationMessage]:
    """Fetch conversation from file storage."""
    # Check expiration first
    metadata = _get_metadata_file(account, thread_id)
    if metadata and metadata.is_expired():
        _clear_conversation_file(account, thread_id)
        return []

    conv_path = _conversation_file(account, thread_id)
    if not conv_path.exists():
        return []

    messages = []
    lines = conv_path.read_text(encoding="utf-8").splitlines()
    for line in lines[-limit:]:
        try:
            data = json.loads(line)
            messages.append(EmailConversationMessage.from_dict(data))
        except json.JSONDecodeError:
            continue

    return messages


def _get_metadata_file(account: str, thread_id: str) -> Optional[EmailThreadMetadata]:
    """Get metadata from file storage."""
    meta_path = _metadata_file(account, thread_id)
    if not meta_path.exists():
        return None

    with meta_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    metadata = EmailThreadMetadata.from_dict(data)
    if metadata.is_expired():
        _clear_conversation_file(account, thread_id)
        return None

    return metadata


def _save_metadata_file(
    account: str,
    thread_id: str,
    metadata: EmailThreadMetadata,
) -> None:
    """Save metadata to file storage."""
    meta_path = _metadata_file(account, thread_id)
    with meta_path.open("w", encoding="utf-8") as f:
        json.dump(metadata.to_dict(), f, indent=2)


def _clear_conversation_file(account: str, thread_id: str) -> bool:
    """Clear conversation from file storage."""
    conv_path = _conversation_file(account, thread_id)
    meta_path = _metadata_file(account, thread_id)

    deleted = False
    if conv_path.exists():
        conv_path.unlink()
        deleted = True
    if meta_path.exists():
        meta_path.unlink()
        deleted = True

    return deleted


def _purge_expired_file(account: str) -> int:
    """Purge expired conversations from file storage."""
    directory = _conversation_dir() / account
    if not directory.exists():
        return 0

    count = 0
    for meta_path in directory.glob("*.meta.json"):
        with meta_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        metadata = EmailThreadMetadata.from_dict(data)
        if metadata.is_expired():
            thread_id = metadata.thread_id
            _clear_conversation_file(account, thread_id)
            count += 1

    return count


def _list_recent_file(account: str, limit: int) -> List[EmailThreadMetadata]:
    """List recent conversations from file storage."""
    directory = _conversation_dir() / account
    if not directory.exists():
        return []

    results = []
    for meta_path in directory.glob("*.meta.json"):
        with meta_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        metadata = EmailThreadMetadata.from_dict(data)
        if not metadata.is_expired():
            results.append(metadata)

    # Sort by last_message_at descending
    results.sort(
        key=lambda m: m.last_message_at or m.created_at,
        reverse=True,
    )

    return results[:limit]
