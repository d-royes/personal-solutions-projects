"""Email draft storage package."""

from .store import (
    EmailDraft,
    save_draft,
    load_draft,
    delete_draft,
)

__all__ = ["EmailDraft", "save_draft", "load_draft", "delete_draft"]

