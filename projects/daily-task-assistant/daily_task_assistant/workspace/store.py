"""Persistent workspace storage for task collaboration content."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..firestore import get_firestore_client


def _workspace_collection() -> str:
    return os.getenv("DTA_WORKSPACE_COLLECTION", "workspaces")


def _force_file_fallback() -> bool:
    return os.getenv("DTA_WORKSPACE_FORCE_FILE", "0") == "1"


def _workspace_dir() -> Path:
    return Path(
        os.getenv(
            "DTA_WORKSPACE_DIR",
            Path(__file__).resolve().parents[2] / "workspace_log",
        )
    )


@dataclass
class WorkspaceData:
    """Workspace content for a task."""
    task_id: str
    items: List[str] = field(default_factory=list)
    updated_at: str = ""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def save_workspace(task_id: str, items: List[str]) -> WorkspaceData:
    """Save workspace content for a task.
    
    Args:
        task_id: The Smartsheet row ID
        items: List of markdown text blocks
    
    Returns:
        The saved WorkspaceData
    """
    data = WorkspaceData(
        task_id=task_id,
        items=items,
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
                print(f"[Workspace] Firestore write failed, falling back to local: {e}")
                _save_to_file(task_id, data)
        else:
            _save_to_file(task_id, data)
    
    return data


def load_workspace(task_id: str) -> WorkspaceData:
    """Load workspace content for a task.
    
    Args:
        task_id: The Smartsheet row ID
    
    Returns:
        WorkspaceData with items (empty list if none saved)
    """
    if _force_file_fallback():
        return _load_from_file(task_id)
    
    db = get_firestore_client()
    if db:
        try:
            return _load_from_firestore(db, task_id)
        except Exception as e:
            print(f"[Workspace] Firestore read failed, falling back to local: {e}")
            return _load_from_file(task_id)
    
    return _load_from_file(task_id)


def clear_workspace(task_id: str) -> None:
    """Clear workspace content for a task (e.g., when task is completed).
    
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

def _save_to_firestore(db: Any, task_id: str, data: WorkspaceData) -> None:
    """Save workspace to Firestore."""
    collection = db.collection(_workspace_collection())
    doc_ref = collection.document(task_id)
    doc_ref.set(asdict(data))


def _load_from_firestore(db: Any, task_id: str) -> WorkspaceData:
    """Load workspace from Firestore."""
    collection = db.collection(_workspace_collection())
    doc_ref = collection.document(task_id)
    doc = doc_ref.get()
    
    if doc.exists:
        data = doc.to_dict()
        return WorkspaceData(
            task_id=data.get("task_id", task_id),
            items=data.get("items", []),
            updated_at=data.get("updated_at", ""),
        )
    
    return WorkspaceData(task_id=task_id)


def _clear_firestore(db: Any, task_id: str) -> None:
    """Delete workspace document from Firestore."""
    collection = db.collection(_workspace_collection())
    doc_ref = collection.document(task_id)
    doc_ref.delete()


# --- File helpers ---

def _workspace_file(task_id: str) -> Path:
    """Get the file path for a task's workspace."""
    directory = _workspace_dir()
    directory.mkdir(parents=True, exist_ok=True)
    # Sanitize task_id for filename
    safe_id = task_id.replace("/", "_").replace("\\", "_")
    return directory / f"{safe_id}.json"


def _save_to_file(task_id: str, data: WorkspaceData) -> None:
    """Save workspace to local JSON file."""
    filepath = _workspace_file(task_id)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(asdict(data), f, indent=2)


def _load_from_file(task_id: str) -> WorkspaceData:
    """Load workspace from local JSON file."""
    filepath = _workspace_file(task_id)
    
    if not filepath.exists():
        return WorkspaceData(task_id=task_id)
    
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
            return WorkspaceData(
                task_id=data.get("task_id", task_id),
                items=data.get("items", []),
                updated_at=data.get("updated_at", ""),
            )
    except (json.JSONDecodeError, IOError):
        return WorkspaceData(task_id=task_id)


def _clear_file(task_id: str) -> None:
    """Delete workspace file."""
    filepath = _workspace_file(task_id)
    if filepath.exists():
        filepath.unlink()

