"""Persistent contact storage for saved contacts (Phase 2 foundation)."""
from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..firestore import get_firestore_client


def _contacts_collection() -> str:
    return os.getenv("DTA_CONTACTS_COLLECTION", "contacts")


def _force_file_fallback() -> bool:
    return os.getenv("DTA_CONTACTS_FORCE_FILE", "0") == "1"


def _contacts_dir() -> Path:
    return Path(
        os.getenv(
            "DTA_CONTACTS_DIR",
            Path(__file__).resolve().parents[2] / "contacts_log",
        )
    )


@dataclass
class SavedContact:
    """A saved contact in the user's contact list."""
    id: str
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    title: Optional[str] = None
    organization: Optional[str] = None
    location: Optional[str] = None
    notes: Optional[str] = None
    source_task_id: Optional[str] = None  # Task where contact was found
    created_at: str = ""
    updated_at: str = ""
    user_email: Optional[str] = None  # Owner of this contact
    tags: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> SavedContact:
        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            email=data.get("email"),
            phone=data.get("phone"),
            title=data.get("title"),
            organization=data.get("organization"),
            location=data.get("location"),
            notes=data.get("notes"),
            source_task_id=data.get("source_task_id"),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            user_email=data.get("user_email"),
            tags=data.get("tags", []),
        )
    
    def to_markdown(self) -> str:
        """Format contact as markdown."""
        lines = [f"📇 **{self.name}**"]
        if self.email:
            lines.append(f"📧 {self.email}")
        if self.phone:
            lines.append(f"📱 {self.phone}")
        if self.title and self.organization:
            lines.append(f"🏢 {self.organization} - {self.title}")
        elif self.organization:
            lines.append(f"🏢 {self.organization}")
        elif self.title:
            lines.append(f"💼 {self.title}")
        if self.location:
            lines.append(f"📍 {self.location}")
        if self.notes:
            lines.append(f"📝 {self.notes}")
        return "\n".join(lines)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def save_contact(
    name: str,
    email: Optional[str] = None,
    phone: Optional[str] = None,
    title: Optional[str] = None,
    organization: Optional[str] = None,
    location: Optional[str] = None,
    notes: Optional[str] = None,
    source_task_id: Optional[str] = None,
    user_email: Optional[str] = None,
    tags: Optional[List[str]] = None,
    contact_id: Optional[str] = None,  # For updates
) -> SavedContact:
    """Save or update a contact.
    
    Args:
        name: Contact name (required)
        email: Email address
        phone: Phone number
        title: Job title
        organization: Company/organization name
        location: Location
        notes: Additional notes
        source_task_id: Task ID where contact was found
        user_email: Owner of this contact
        tags: List of tags for categorization
        contact_id: Existing contact ID for updates
    
    Returns:
        The saved contact
    """
    now = _now()
    
    if contact_id:
        # Update existing
        existing = get_contact(contact_id)
        if existing:
            contact = SavedContact(
                id=contact_id,
                name=name,
                email=email,
                phone=phone,
                title=title,
                organization=organization,
                location=location,
                notes=notes,
                source_task_id=source_task_id or existing.source_task_id,
                created_at=existing.created_at,
                updated_at=now,
                user_email=user_email or existing.user_email,
                tags=tags if tags is not None else existing.tags,
            )
        else:
            # Contact not found, create new with provided ID
            contact = SavedContact(
                id=contact_id,
                name=name,
                email=email,
                phone=phone,
                title=title,
                organization=organization,
                location=location,
                notes=notes,
                source_task_id=source_task_id,
                created_at=now,
                updated_at=now,
                user_email=user_email,
                tags=tags or [],
            )
    else:
        # Create new
        contact = SavedContact(
            id=str(uuid.uuid4()),
            name=name,
            email=email,
            phone=phone,
            title=title,
            organization=organization,
            location=location,
            notes=notes,
            source_task_id=source_task_id,
            created_at=now,
            updated_at=now,
            user_email=user_email,
            tags=tags or [],
        )
    
    if _force_file_fallback():
        _save_to_file(contact)
    else:
        db = get_firestore_client()
        if db:
            try:
                _save_to_firestore(db, contact)
            except Exception as e:
                print(f"[Contacts] Firestore write failed, falling back to local: {e}")
                _save_to_file(contact)
        else:
            _save_to_file(contact)
    
    return contact


def get_contact(contact_id: str) -> Optional[SavedContact]:
    """Get a contact by ID."""
    if _force_file_fallback():
        return _load_from_file(contact_id)
    
    db = get_firestore_client()
    if db:
        try:
            return _load_from_firestore(db, contact_id)
        except Exception as e:
            print(f"[Contacts] Firestore read failed, falling back to local: {e}")
            return _load_from_file(contact_id)
    
    return _load_from_file(contact_id)


def list_contacts(
    user_email: Optional[str] = None,
    limit: int = 100,
) -> List[SavedContact]:
    """List all contacts, optionally filtered by user.
    
    Args:
        user_email: Filter by owner email
        limit: Maximum number of contacts to return
    
    Returns:
        List of saved contacts
    """
    if _force_file_fallback():
        return _list_from_files(user_email, limit)
    
    db = get_firestore_client()
    if db:
        try:
            return _list_from_firestore(db, user_email, limit)
        except Exception as e:
            print(f"[Contacts] Firestore list failed, falling back to local: {e}")
            return _list_from_files(user_email, limit)
    
    return _list_from_files(user_email, limit)


def delete_contact(contact_id: str) -> bool:
    """Delete a contact by ID.
    
    Returns:
        True if deleted, False if not found
    """
    if _force_file_fallback():
        return _delete_from_file(contact_id)
    
    db = get_firestore_client()
    if db:
        try:
            return _delete_from_firestore(db, contact_id)
        except Exception as e:
            print(f"[Contacts] Firestore delete failed, falling back to local: {e}")
            return _delete_from_file(contact_id)
    
    return _delete_from_file(contact_id)


# --- Firestore helpers ---

def _save_to_firestore(db: Any, contact: SavedContact) -> None:
    """Save contact to Firestore."""
    collection = db.collection(_contacts_collection())
    doc_ref = collection.document(contact.id)
    doc_ref.set(contact.to_dict())


def _load_from_firestore(db: Any, contact_id: str) -> Optional[SavedContact]:
    """Load contact from Firestore."""
    collection = db.collection(_contacts_collection())
    doc_ref = collection.document(contact_id)
    doc = doc_ref.get()
    
    if doc.exists:
        return SavedContact.from_dict(doc.to_dict())
    return None


def _list_from_firestore(
    db: Any,
    user_email: Optional[str],
    limit: int,
) -> List[SavedContact]:
    """List contacts from Firestore."""
    collection = db.collection(_contacts_collection())
    query = collection.limit(limit)
    
    if user_email:
        query = query.where("user_email", "==", user_email)
    
    docs = query.stream()
    return [SavedContact.from_dict(doc.to_dict()) for doc in docs]


def _delete_from_firestore(db: Any, contact_id: str) -> bool:
    """Delete contact from Firestore."""
    collection = db.collection(_contacts_collection())
    doc_ref = collection.document(contact_id)
    doc = doc_ref.get()
    
    if doc.exists:
        doc_ref.delete()
        return True
    return False


# --- File helpers ---

def _contacts_file(contact_id: str) -> Path:
    """Get the file path for a contact."""
    directory = _contacts_dir()
    directory.mkdir(parents=True, exist_ok=True)
    safe_id = contact_id.replace("/", "_").replace("\\", "_")
    return directory / f"{safe_id}.json"


def _save_to_file(contact: SavedContact) -> None:
    """Save contact to local JSON file."""
    filepath = _contacts_file(contact.id)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(contact.to_dict(), f, indent=2)


def _load_from_file(contact_id: str) -> Optional[SavedContact]:
    """Load contact from local JSON file."""
    filepath = _contacts_file(contact_id)
    
    if not filepath.exists():
        return None
    
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
            return SavedContact.from_dict(data)
    except (json.JSONDecodeError, IOError):
        return None


def _list_from_files(
    user_email: Optional[str],
    limit: int,
) -> List[SavedContact]:
    """List contacts from local files."""
    directory = _contacts_dir()
    if not directory.exists():
        return []
    
    contacts = []
    for filepath in directory.glob("*.json"):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
                contact = SavedContact.from_dict(data)
                if user_email is None or contact.user_email == user_email:
                    contacts.append(contact)
                    if len(contacts) >= limit:
                        break
        except (json.JSONDecodeError, IOError):
            continue
    
    # Sort by updated_at descending
    contacts.sort(key=lambda c: c.updated_at, reverse=True)
    return contacts[:limit]


def _delete_from_file(contact_id: str) -> bool:
    """Delete contact file."""
    filepath = _contacts_file(contact_id)
    if filepath.exists():
        filepath.unlink()
        return True
    return False

