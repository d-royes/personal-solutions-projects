"""Shared Firestore client helper."""
from __future__ import annotations

_firestore_client = None


def get_firestore_client():
    """Return a cached Firestore client instance."""

    global _firestore_client
    if _firestore_client is not None:
        return _firestore_client

    try:
        import firebase_admin
        from firebase_admin import firestore
    except ModuleNotFoundError as exc:  # pragma: no cover
        raise RuntimeError(
            "firebase-admin is required for Firestore features. "
            "Install dependencies before enabling Firestore logging."
        ) from exc

    if not firebase_admin._apps:
        firebase_admin.initialize_app()
    _firestore_client = firestore.client()
    return _firestore_client

