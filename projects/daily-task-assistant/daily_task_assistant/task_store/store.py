"""Firestore-based Task Store for DATA.

This module provides a native task storage system that will eventually
replace Smartsheet as the primary task backend. It follows the same
Firestore + file fallback pattern used throughout DATA.

Architecture:
- Firestore path: users/{user_id}/tasks/{task_id}
- File fallback: tasks_store/tasks.jsonl

Task fields are designed for Smartsheet migration compatibility:
- Core fields match TaskDetail from tasks.py
- Additional fields support email-to-task workflow
- Source tracking enables bidirectional sync
"""
from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, date, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional


class TaskStatus(str, Enum):
    """Task status values matching Smartsheet workflow."""
    
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    # Smartsheet-compatible statuses
    SCHEDULED = "scheduled"
    RECURRING = "recurring"
    ON_HOLD = "on_hold"
    FOLLOW_UP = "follow_up"
    AWAITING_REPLY = "awaiting_reply"
    DELEGATED = "delegated"


class TaskPriority(str, Enum):
    """Task priority levels matching Smartsheet."""
    
    CRITICAL = "Critical"
    URGENT = "Urgent"
    IMPORTANT = "Important"
    STANDARD = "Standard"
    LOW = "Low"


class TaskSource(str, Enum):
    """Where the task originated."""
    
    EMAIL = "email"  # Created from email action suggestion
    MANUAL = "manual"  # Created manually in UI
    SMARTSHEET_SYNC = "smartsheet_sync"  # Imported from Smartsheet
    CHAT = "chat"  # Created via DATA chat


@dataclass(slots=True)
class FirestoreTask:
    """A task stored in Firestore.
    
    Field design mirrors Smartsheet's TaskDetail for migration compatibility,
    with additional fields for email integration and DATA features.
    """
    
    id: str
    title: str
    status: str  # TaskStatus value
    priority: str  # TaskPriority value
    domain: str  # "personal", "church", "work"
    created_at: datetime
    updated_at: datetime
    
    # Optional fields matching Smartsheet
    due_date: Optional[date] = None
    project: Optional[str] = None
    assigned_to: Optional[str] = None
    estimated_hours: Optional[float] = None
    notes: Optional[str] = None
    next_step: Optional[str] = None
    number: Optional[float] = None  # Ordering field from Smartsheet
    
    # DATA-specific fields
    source: str = TaskSource.MANUAL.value
    source_email_id: Optional[str] = None  # Links to Gmail message ID
    source_email_account: Optional[str] = None  # "personal" or "church"
    source_email_subject: Optional[str] = None  # For reference
    
    # Smartsheet sync fields
    smartsheet_row_id: Optional[str] = None  # For bidirectional sync
    smartsheet_sheet: Optional[str] = None  # "personal" or "work"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "id": self.id,
            "title": self.title,
            "status": self.status,
            "priority": self.priority,
            "domain": self.domain,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "due_date": self.due_date.isoformat() if self.due_date else None,
            "project": self.project,
            "assigned_to": self.assigned_to,
            "estimated_hours": self.estimated_hours,
            "notes": self.notes,
            "next_step": self.next_step,
            "number": self.number,
            "source": self.source,
            "source_email_id": self.source_email_id,
            "source_email_account": self.source_email_account,
            "source_email_subject": self.source_email_subject,
            "smartsheet_row_id": self.smartsheet_row_id,
            "smartsheet_sheet": self.smartsheet_sheet,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FirestoreTask":
        """Create from dictionary."""
        due = data.get("due_date")
        if due and isinstance(due, str):
            due = date.fromisoformat(due)
        
        created = data.get("created_at")
        if isinstance(created, str):
            created = datetime.fromisoformat(created)
        
        updated = data.get("updated_at")
        if isinstance(updated, str):
            updated = datetime.fromisoformat(updated)
        
        return cls(
            id=data["id"],
            title=data["title"],
            status=data.get("status", TaskStatus.PENDING.value),
            priority=data.get("priority", TaskPriority.STANDARD.value),
            domain=data.get("domain", "personal"),
            created_at=created or datetime.now(timezone.utc),
            updated_at=updated or datetime.now(timezone.utc),
            due_date=due,
            project=data.get("project"),
            assigned_to=data.get("assigned_to"),
            estimated_hours=data.get("estimated_hours"),
            notes=data.get("notes"),
            next_step=data.get("next_step"),
            number=data.get("number"),
            source=data.get("source", TaskSource.MANUAL.value),
            source_email_id=data.get("source_email_id"),
            source_email_account=data.get("source_email_account"),
            source_email_subject=data.get("source_email_subject"),
            smartsheet_row_id=data.get("smartsheet_row_id"),
            smartsheet_sheet=data.get("smartsheet_sheet"),
        )
    
    def to_api_dict(self) -> Dict[str, Any]:
        """Convert to API response format (camelCase)."""
        return {
            "id": self.id,
            "title": self.title,
            "status": self.status,
            "priority": self.priority,
            "domain": self.domain,
            "createdAt": self.created_at.isoformat(),
            "updatedAt": self.updated_at.isoformat(),
            "dueDate": self.due_date.isoformat() if self.due_date else None,
            "project": self.project,
            "assignedTo": self.assigned_to,
            "estimatedHours": self.estimated_hours,
            "notes": self.notes,
            "nextStep": self.next_step,
            "number": self.number,
            "source": self.source,
            "sourceEmailId": self.source_email_id,
            "sourceEmailAccount": self.source_email_account,
            "sourceEmailSubject": self.source_email_subject,
            "smartsheetRowId": self.smartsheet_row_id,
            "smartsheetSheet": self.smartsheet_sheet,
        }


@dataclass(slots=True)
class TaskFilters:
    """Filter criteria for listing tasks."""
    
    status: Optional[List[str]] = None
    priority: Optional[List[str]] = None
    domain: Optional[str] = None
    project: Optional[str] = None
    source: Optional[str] = None
    has_due_date: Optional[bool] = None
    overdue_only: bool = False


def _use_file_storage() -> bool:
    """Check if we should use file-based storage."""
    return os.getenv("DTA_TASK_STORE_FORCE_FILE", "").strip() == "1"


def _get_tasks_dir() -> Path:
    """Get the tasks storage directory."""
    env_dir = os.getenv("DTA_TASK_STORE_DIR", "").strip()
    if env_dir:
        return Path(env_dir)
    return Path(__file__).parent.parent.parent / "task_store"


def _get_firestore_client():
    """Get Firestore client, or None if not available."""
    if _use_file_storage():
        return None
    
    try:
        from ..firestore import get_firestore_client
        return get_firestore_client()
    except Exception:
        return None


# =============================================================================
# CRUD Operations
# =============================================================================

def create_task(
    user_id: str,
    title: str,
    *,
    status: str = TaskStatus.PENDING.value,
    priority: str = TaskPriority.STANDARD.value,
    domain: str = "personal",
    due_date: Optional[date] = None,
    project: Optional[str] = None,
    notes: Optional[str] = None,
    next_step: Optional[str] = None,
    source: str = TaskSource.MANUAL.value,
    source_email_id: Optional[str] = None,
    source_email_account: Optional[str] = None,
    source_email_subject: Optional[str] = None,
) -> FirestoreTask:
    """Create a new task.
    
    Args:
        user_id: The user who owns this task
        title: Task title
        status: Initial status
        priority: Task priority
        domain: "personal", "church", or "work"
        due_date: Optional due date
        project: Optional project category
        notes: Optional notes
        next_step: Optional next action
        source: Where task originated
        source_email_id: Gmail message ID if from email
        source_email_account: "personal" or "church" email account
        source_email_subject: Original email subject
    
    Returns:
        Created FirestoreTask
    """
    now = datetime.now(timezone.utc)
    
    task = FirestoreTask(
        id=str(uuid.uuid4()),
        title=title,
        status=status,
        priority=priority,
        domain=domain,
        created_at=now,
        updated_at=now,
        due_date=due_date,
        project=project,
        notes=notes,
        next_step=next_step,
        source=source,
        source_email_id=source_email_id,
        source_email_account=source_email_account,
        source_email_subject=source_email_subject,
    )
    
    db = _get_firestore_client()
    if db is not None:
        try:
            _save_to_firestore(db, user_id, task)
        except Exception as e:
            print(f"[TaskStore] Firestore write failed, falling back to local: {e}")
            _save_to_file(user_id, task)
    else:
        _save_to_file(user_id, task)
    
    return task


def get_task(user_id: str, task_id: str) -> Optional[FirestoreTask]:
    """Get a task by ID.
    
    Args:
        user_id: The user who owns the task
        task_id: The task ID
    
    Returns:
        FirestoreTask if found, None otherwise
    """
    db = _get_firestore_client()
    if db is not None:
        return _get_from_firestore(db, user_id, task_id)
    return _get_from_file(user_id, task_id)


def list_tasks(
    user_id: str,
    filters: Optional[TaskFilters] = None,
    limit: int = 100,
) -> List[FirestoreTask]:
    """List tasks with optional filtering.
    
    Args:
        user_id: The user whose tasks to list
        filters: Optional filter criteria
        limit: Maximum number of tasks to return
    
    Returns:
        List of FirestoreTask objects
    """
    db = _get_firestore_client()
    if db is not None:
        tasks = _list_from_firestore(db, user_id, limit)
    else:
        tasks = _list_from_file(user_id, limit)
    
    # Apply filters if provided
    if filters:
        tasks = _apply_filters(tasks, filters)
    
    return tasks


def update_task(
    user_id: str,
    task_id: str,
    updates: Dict[str, Any],
) -> Optional[FirestoreTask]:
    """Update a task.
    
    Args:
        user_id: The user who owns the task
        task_id: The task ID
        updates: Dictionary of fields to update
    
    Returns:
        Updated FirestoreTask if found, None otherwise
    """
    task = get_task(user_id, task_id)
    if not task:
        return None
    
    # Apply updates
    for key, value in updates.items():
        if hasattr(task, key):
            setattr(task, key, value)
    
    # Update timestamp
    task.updated_at = datetime.now(timezone.utc)
    
    db = _get_firestore_client()
    if db is not None:
        try:
            _save_to_firestore(db, user_id, task)
        except Exception as e:
            print(f"[TaskStore] Firestore update failed, falling back to local: {e}")
            _save_to_file(user_id, task)
    else:
        _save_to_file(user_id, task)
    
    return task


def delete_task(user_id: str, task_id: str) -> bool:
    """Delete a task.
    
    Args:
        user_id: The user who owns the task
        task_id: The task ID
    
    Returns:
        True if deleted, False if not found
    """
    db = _get_firestore_client()
    if db is not None:
        return _delete_from_firestore(db, user_id, task_id)
    return _delete_from_file(user_id, task_id)


# =============================================================================
# Firestore Storage
# =============================================================================

def _save_to_firestore(db, user_id: str, task: FirestoreTask) -> None:
    """Save task to Firestore."""
    doc_ref = db.collection("users").document(user_id).collection("tasks").document(task.id)
    doc_ref.set(task.to_dict())


def _get_from_firestore(db, user_id: str, task_id: str) -> Optional[FirestoreTask]:
    """Get task from Firestore."""
    doc_ref = db.collection("users").document(user_id).collection("tasks").document(task_id)
    doc = doc_ref.get()
    
    if doc.exists:
        return FirestoreTask.from_dict(doc.to_dict())
    return None


def _list_from_firestore(db, user_id: str, limit: int) -> List[FirestoreTask]:
    """List tasks from Firestore."""
    collection = db.collection("users").document(user_id).collection("tasks")
    query = collection.order_by("updated_at", direction="DESCENDING").limit(limit)
    
    tasks = []
    for doc in query.stream():
        try:
            tasks.append(FirestoreTask.from_dict(doc.to_dict()))
        except Exception:
            continue
    
    return tasks


def _delete_from_firestore(db, user_id: str, task_id: str) -> bool:
    """Delete task from Firestore."""
    doc_ref = db.collection("users").document(user_id).collection("tasks").document(task_id)
    doc = doc_ref.get()
    
    if doc.exists:
        doc_ref.delete()
        return True
    return False


# =============================================================================
# File Storage (Fallback)
# =============================================================================

def _get_user_file(user_id: str) -> Path:
    """Get the file path for a user's tasks."""
    tasks_dir = _get_tasks_dir()
    tasks_dir.mkdir(parents=True, exist_ok=True)
    
    # Sanitize user_id for filename
    safe_id = user_id.replace("@", "_at_").replace(".", "_")
    return tasks_dir / f"{safe_id}_tasks.jsonl"


def _save_to_file(user_id: str, task: FirestoreTask) -> None:
    """Save task to file (upsert)."""
    file_path = _get_user_file(user_id)
    
    # Read existing tasks
    tasks = {}
    if file_path.exists():
        with file_path.open("r", encoding="utf-8") as f:
            for line in f:
                try:
                    data = json.loads(line.strip())
                    tasks[data["id"]] = data
                except Exception:
                    continue
    
    # Upsert
    tasks[task.id] = task.to_dict()
    
    # Write all tasks
    with file_path.open("w", encoding="utf-8") as f:
        for task_data in tasks.values():
            f.write(json.dumps(task_data) + "\n")


def _get_from_file(user_id: str, task_id: str) -> Optional[FirestoreTask]:
    """Get task from file."""
    file_path = _get_user_file(user_id)
    
    if not file_path.exists():
        return None
    
    with file_path.open("r", encoding="utf-8") as f:
        for line in f:
            try:
                data = json.loads(line.strip())
                if data["id"] == task_id:
                    return FirestoreTask.from_dict(data)
            except Exception:
                continue
    
    return None


def _list_from_file(user_id: str, limit: int) -> List[FirestoreTask]:
    """List tasks from file."""
    file_path = _get_user_file(user_id)
    
    if not file_path.exists():
        return []
    
    tasks = []
    with file_path.open("r", encoding="utf-8") as f:
        for line in f:
            try:
                data = json.loads(line.strip())
                tasks.append(FirestoreTask.from_dict(data))
            except Exception:
                continue
    
    # Sort by updated_at descending
    tasks.sort(key=lambda t: t.updated_at, reverse=True)
    return tasks[:limit]


def _delete_from_file(user_id: str, task_id: str) -> bool:
    """Delete task from file."""
    file_path = _get_user_file(user_id)
    
    if not file_path.exists():
        return False
    
    # Read all tasks except the one to delete
    tasks = {}
    found = False
    
    with file_path.open("r", encoding="utf-8") as f:
        for line in f:
            try:
                data = json.loads(line.strip())
                if data["id"] == task_id:
                    found = True
                else:
                    tasks[data["id"]] = data
            except Exception:
                continue
    
    if not found:
        return False
    
    # Write remaining tasks
    with file_path.open("w", encoding="utf-8") as f:
        for task_data in tasks.values():
            f.write(json.dumps(task_data) + "\n")
    
    return True


# =============================================================================
# Filter Helpers
# =============================================================================

def _apply_filters(tasks: List[FirestoreTask], filters: TaskFilters) -> List[FirestoreTask]:
    """Apply filter criteria to task list."""
    result = tasks
    
    if filters.status:
        result = [t for t in result if t.status in filters.status]
    
    if filters.priority:
        result = [t for t in result if t.priority in filters.priority]
    
    if filters.domain:
        result = [t for t in result if t.domain == filters.domain]
    
    if filters.project:
        result = [t for t in result if t.project == filters.project]
    
    if filters.source:
        result = [t for t in result if t.source == filters.source]
    
    if filters.has_due_date is True:
        result = [t for t in result if t.due_date is not None]
    elif filters.has_due_date is False:
        result = [t for t in result if t.due_date is None]
    
    if filters.overdue_only:
        today = date.today()
        result = [t for t in result if t.due_date and t.due_date < today]
    
    return result


# =============================================================================
# Email-to-Task Helper
# =============================================================================

def create_task_from_email(
    user_id: str,
    email_id: str,
    email_account: Literal["personal", "church"],
    email_subject: str,
    *,
    title: Optional[str] = None,
    due_date: Optional[date] = None,
    priority: str = TaskPriority.STANDARD.value,
    domain: Optional[str] = None,
    project: Optional[str] = None,
    notes: Optional[str] = None,
) -> FirestoreTask:
    """Create a task from an email.
    
    Args:
        user_id: The user creating the task
        email_id: Gmail message ID
        email_account: "personal" or "church"
        email_subject: Original email subject
        title: Task title (defaults to email subject)
        due_date: Optional due date
        priority: Task priority
        domain: Task domain (defaults based on email account)
        project: Project category (e.g., "Church Tasks", "Around The House")
        notes: Optional notes
    
    Returns:
        Created FirestoreTask
    """
    # Default title to email subject
    if not title:
        title = email_subject
        # Clean up subject prefixes
        for prefix in ["Re:", "Fwd:", "FW:", "RE:"]:
            if title.lower().startswith(prefix.lower()):
                title = title[len(prefix):].strip()
    
    # Default domain based on email account
    if not domain:
        domain = "church" if email_account == "church" else "personal"
    
    return create_task(
        user_id=user_id,
        title=title,
        priority=priority,
        domain=domain,
        due_date=due_date,
        project=project,
        notes=notes,
        source=TaskSource.EMAIL.value,
        source_email_id=email_id,
        source_email_account=email_account,
        source_email_subject=email_subject,
    )

