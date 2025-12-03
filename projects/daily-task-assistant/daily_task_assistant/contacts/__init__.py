"""Contact search and storage module."""
from .search import (
    ContactCard,
    ContactSearchResult,
    search_contacts,
    extract_entities,
)
from .store import (
    SavedContact,
    save_contact,
    list_contacts,
    delete_contact,
    get_contact,
)

__all__ = [
    # Search
    "ContactCard",
    "ContactSearchResult", 
    "search_contacts",
    "extract_entities",
    # Storage
    "SavedContact",
    "save_contact",
    "list_contacts",
    "delete_contact",
    "get_contact",
]

