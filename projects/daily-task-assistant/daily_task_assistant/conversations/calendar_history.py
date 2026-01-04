"""Calendar Conversation History - persistent storage for calendar-related conversations.

This module provides conversation persistence for calendar discussions with DATA.
Conversations are keyed by domain (personal/church/work/combined), allowing context
to persist across the Calendar mode session.

Storage is keyed by DOMAIN (not user email) to prevent data fragmentation.

Firestore Structure:
    calendar_domains/{domain}/calendar_conversations/
        metadata (doc)  -> CalendarConversationMetadata
        messages (collection) -> CalendarConversationMessage documents

File Storage Structure:
    calendar_conversation_log/{domain}.jsonl

Environment Variables:
    DTA_CALENDAR_CONVERSATION_FORCE_FILE: Set to "1" to use local file storage (dev mode)
    DTA_CALENDAR_CONVERSATION_DIR: Directory for file-based storage
    DTA_CALENDAR_CONVERSATION_TTL_DAYS: Days to keep conversations (default: 7)
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from ..firestore import get_firestore_client


# Type aliases
DomainType = Literal["personal", "church", "work", "combined"]
MessageRole = Literal["user", "assistant"]


# Configuration helpers
def _force_file_fallback() -> bool:
    """Check if file-based storage should be used (dev mode)."""
    return os.getenv("DTA_CALENDAR_CONVERSATION_FORCE_FILE", "0") == "1"


def _conversation_dir() -> Path:
    """Return the directory for file-based conversation storage."""
    return Path(
        os.getenv(
            "DTA_CALENDAR_CONVERSATION_DIR",
            Path(__file__).resolve().parents[2] / "calendar_conversation_log",
        )
    )


def _ttl_days() -> int:
    """Return TTL for calendar conversations in days (default: 7)."""
    return int(os.getenv("DTA_CALENDAR_CONVERSATION_TTL_DAYS", "7"))


def _now() -> datetime:
    """Return current UTC datetime."""
    return datetime.now(timezone.utc)


def _now_str() -> str:
    """Return current UTC datetime as ISO string."""
    return _now().isoformat()


def _validate_domain(domain: str) -> DomainType:
    """Validate and normalize domain identifier."""
    if domain not in ("personal", "church", "work", "combined"):
        raise ValueError(f"Invalid domain: {domain}. Must be 'personal', 'church', 'work', or 'combined'")
    return domain  # type: ignore


@dataclass
class CalendarConversationMessage:
    """A single message in a calendar conversation.

    Attributes:
        role: "user" or "assistant"
        content: The message text
        ts: ISO timestamp when message was logged
        event_context: Specific event_id being discussed (optional)
        metadata: Additional metadata (user info, etc.)
    """
    role: MessageRole
    content: str
    ts: str = field(default_factory=_now_str)
    event_context: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "role": self.role,
            "content": self.content,
            "ts": self.ts,
            "event_context": self.event_context,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CalendarConversationMessage":
        """Create message from dictionary."""
        return cls(
            role=data["role"],
            content=data["content"],
            ts=data.get("ts", _now_str()),
            event_context=data.get("event_context"),
            metadata=data.get("metadata", {}),
        )


@dataclass
class CalendarConversationMetadata:
    """Metadata for a calendar conversation.

    Stored separately from messages for quick access without loading full history.

    Attributes:
        domain: Calendar domain (personal, church, work, combined)
        created_at: When conversation was first started
        expires_at: TTL expiration (7 days from creation)
        message_count: Number of messages in conversation
        last_message_at: When last message was logged
    """
    domain: DomainType
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
            "domain": self.domain,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "message_count": self.message_count,
            "last_message_at": self.last_message_at,
        }

    def to_api_dict(self) -> Dict[str, Any]:
        """Convert to API-friendly dict (camelCase)."""
        return {
            "domain": self.domain,
            "createdAt": self.created_at,
            "expiresAt": self.expires_at,
            "messageCount": self.message_count,
            "lastMessageAt": self.last_message_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CalendarConversationMetadata":
        """Create metadata from dictionary."""
        return cls(
            domain=data["domain"],
            created_at=data.get("created_at", _now_str()),
            expires_at=data.get("expires_at"),
            message_count=data.get("message_count", 0),
            last_message_at=data.get("last_message_at"),
        )


# =============================================================================
# Public API
# =============================================================================

def log_calendar_message(
    domain: str,
    role: MessageRole,
    content: str,
    event_context: Optional[str] = None,
    user_email: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> CalendarConversationMessage:
    """Log a message to a calendar conversation.

    Creates the conversation if it doesn't exist.

    Args:
        domain: Calendar domain ("personal", "church", "work", "combined")
        role: "user" or "assistant"
        content: Message text
        event_context: Specific event_id being discussed (optional)
        user_email: User's email for metadata (optional)
        metadata: Additional metadata (optional)

    Returns:
        The created CalendarConversationMessage
    """
    domain = _validate_domain(domain)

    msg_metadata = metadata or {}
    if user_email:
        msg_metadata["user"] = user_email

    message = CalendarConversationMessage(
        role=role,
        content=content.strip(),
        ts=_now_str(),
        event_context=event_context,
        metadata=msg_metadata,
    )

    if _force_file_fallback():
        _append_message_file(domain, message)
    else:
        _append_message_firestore(domain, message)

    return message


def fetch_calendar_conversation(
    domain: str,
    limit: int = 50,
) -> List[CalendarConversationMessage]:
    """Retrieve conversation history for a domain.

    Args:
        domain: Calendar domain ("personal", "church", "work", "combined")
        limit: Maximum messages to return (default: 50)

    Returns:
        List of CalendarConversationMessage, ordered oldest -> newest
    """
    domain = _validate_domain(domain)

    if _force_file_fallback():
        return _fetch_conversation_file(domain, limit)
    return _fetch_conversation_firestore(domain, limit)


def get_calendar_conversation_metadata(
    domain: str,
) -> Optional[CalendarConversationMetadata]:
    """Get conversation metadata.

    Args:
        domain: Calendar domain ("personal", "church", "work", "combined")

    Returns:
        CalendarConversationMetadata if conversation exists, None otherwise
    """
    domain = _validate_domain(domain)

    if _force_file_fallback():
        return _get_metadata_file(domain)
    return _get_metadata_firestore(domain)


def has_calendar_conversation(domain: str) -> bool:
    """Check if a conversation exists for this domain.

    Args:
        domain: Calendar domain

    Returns:
        True if conversation has messages
    """
    domain = _validate_domain(domain)
    metadata = get_calendar_conversation_metadata(domain)
    return metadata is not None and metadata.message_count > 0


def clear_calendar_conversation(domain: str) -> bool:
    """Delete a conversation and its messages.

    Args:
        domain: Calendar domain

    Returns:
        True if conversation was deleted, False if not found
    """
    domain = _validate_domain(domain)

    if _force_file_fallback():
        return _clear_conversation_file(domain)
    return _clear_conversation_firestore(domain)


def update_calendar_conversation(
    domain: str,
    messages: List[Dict[str, Any]],
) -> bool:
    """Replace conversation with new messages.

    Used when deleting individual messages - clears and re-adds remaining messages.

    Args:
        domain: Calendar domain
        messages: List of message dicts with role and content

    Returns:
        True if successful
    """
    domain = _validate_domain(domain)

    # Clear existing conversation
    clear_calendar_conversation(domain)

    # If no messages, we're done
    if not messages:
        return True

    # Re-add each message
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        log_calendar_message(domain, role, content)

    return True


# =============================================================================
# Firestore Implementation
# =============================================================================

def _get_conversation_doc_ref(domain: str):
    """Get Firestore document reference for a domain's conversation."""
    db = get_firestore_client()
    if db is None:
        return None
    return (
        db.collection("calendar_domains")
        .document(domain)
        .collection("calendar_conversations")
        .document("current")
    )


def _append_message_firestore(
    domain: str,
    message: CalendarConversationMessage,
) -> None:
    """Append message to Firestore."""
    db = get_firestore_client()
    if db is None:
        _append_message_file(domain, message)
        return

    conv_ref = _get_conversation_doc_ref(domain)
    if conv_ref is None:
        _append_message_file(domain, message)
        return

    # Add message to subcollection
    conv_ref.collection("messages").add(message.to_dict())

    # Update metadata
    metadata_doc = conv_ref.get()
    if metadata_doc.exists:
        conv_ref.update({
            "message_count": metadata_doc.to_dict().get("message_count", 0) + 1,
            "last_message_at": message.ts,
        })
    else:
        # Create new metadata
        metadata = CalendarConversationMetadata(
            domain=domain,
            message_count=1,
            last_message_at=message.ts,
        )
        conv_ref.set(metadata.to_dict())


def _fetch_conversation_firestore(
    domain: str,
    limit: int,
) -> List[CalendarConversationMessage]:
    """Fetch conversation from Firestore."""
    db = get_firestore_client()
    if db is None:
        return _fetch_conversation_file(domain, limit)

    conv_ref = _get_conversation_doc_ref(domain)
    if conv_ref is None:
        return _fetch_conversation_file(domain, limit)

    # Check expiration first
    metadata_doc = conv_ref.get()
    if metadata_doc.exists:
        metadata = CalendarConversationMetadata.from_dict(metadata_doc.to_dict())
        if metadata.is_expired():
            _clear_conversation_firestore(domain)
            return []

    from firebase_admin import firestore as fb_firestore  # type: ignore

    query = (
        conv_ref.collection("messages")
        .order_by("ts", direction=fb_firestore.Query.ASCENDING)
        .limit(limit)
    )

    messages = []
    for doc in query.stream():
        messages.append(CalendarConversationMessage.from_dict(doc.to_dict()))

    return messages


def _get_metadata_firestore(domain: str) -> Optional[CalendarConversationMetadata]:
    """Get metadata from Firestore."""
    db = get_firestore_client()
    if db is None:
        return _get_metadata_file(domain)

    conv_ref = _get_conversation_doc_ref(domain)
    if conv_ref is None:
        return _get_metadata_file(domain)

    doc = conv_ref.get()
    if not doc.exists:
        return None

    metadata = CalendarConversationMetadata.from_dict(doc.to_dict())
    if metadata.is_expired():
        _clear_conversation_firestore(domain)
        return None

    return metadata


def _clear_conversation_firestore(domain: str) -> bool:
    """Clear conversation from Firestore."""
    db = get_firestore_client()
    if db is None:
        return _clear_conversation_file(domain)

    conv_ref = _get_conversation_doc_ref(domain)
    if conv_ref is None:
        return _clear_conversation_file(domain)

    # Delete all messages in subcollection
    messages_ref = conv_ref.collection("messages")
    for doc in messages_ref.stream():
        doc.reference.delete()

    # Delete metadata document
    conv_ref.delete()
    return True


# =============================================================================
# File Storage Implementation
# =============================================================================

def _conversation_file(domain: str) -> Path:
    """Get file path for a domain's conversation."""
    directory = _conversation_dir()
    directory.mkdir(parents=True, exist_ok=True)
    return directory / f"{domain}.jsonl"


def _metadata_file(domain: str) -> Path:
    """Get file path for a domain's metadata."""
    directory = _conversation_dir()
    directory.mkdir(parents=True, exist_ok=True)
    return directory / f"{domain}.meta.json"


def _append_message_file(
    domain: str,
    message: CalendarConversationMessage,
) -> None:
    """Append message to file storage."""
    conv_path = _conversation_file(domain)
    with conv_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(message.to_dict()))
        f.write("\n")

    # Update metadata
    meta_path = _metadata_file(domain)
    if meta_path.exists():
        with meta_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        metadata = CalendarConversationMetadata.from_dict(data)
        metadata.message_count += 1
        metadata.last_message_at = message.ts
    else:
        metadata = CalendarConversationMetadata(
            domain=domain,
            message_count=1,
            last_message_at=message.ts,
        )

    with meta_path.open("w", encoding="utf-8") as f:
        json.dump(metadata.to_dict(), f, indent=2)


def _fetch_conversation_file(
    domain: str,
    limit: int,
) -> List[CalendarConversationMessage]:
    """Fetch conversation from file storage."""
    # Check expiration first
    metadata = _get_metadata_file(domain)
    if metadata and metadata.is_expired():
        _clear_conversation_file(domain)
        return []

    conv_path = _conversation_file(domain)
    if not conv_path.exists():
        return []

    messages = []
    lines = conv_path.read_text(encoding="utf-8").splitlines()
    for line in lines[-limit:]:
        try:
            data = json.loads(line)
            messages.append(CalendarConversationMessage.from_dict(data))
        except json.JSONDecodeError:
            continue

    return messages


def _get_metadata_file(domain: str) -> Optional[CalendarConversationMetadata]:
    """Get metadata from file storage."""
    meta_path = _metadata_file(domain)
    if not meta_path.exists():
        return None

    with meta_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    metadata = CalendarConversationMetadata.from_dict(data)
    if metadata.is_expired():
        _clear_conversation_file(domain)
        return None

    return metadata


def _clear_conversation_file(domain: str) -> bool:
    """Clear conversation from file storage."""
    conv_path = _conversation_file(domain)
    meta_path = _metadata_file(domain)

    deleted = False
    if conv_path.exists():
        conv_path.unlink()
        deleted = True
    if meta_path.exists():
        meta_path.unlink()
        deleted = True

    return deleted
