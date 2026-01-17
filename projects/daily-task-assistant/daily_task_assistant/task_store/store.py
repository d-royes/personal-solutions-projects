"""Firestore-based Task Store for DATA.

This module provides a native task storage system that will eventually
replace Smartsheet as the primary task backend. It follows the same
Firestore + file fallback pattern used throughout DATA.

Architecture:
- Firestore path: global/{GLOBAL_USER_ID}/tasks/{task_id}
- File fallback: tasks_store/tasks.jsonl

Note: Tasks use GLOBAL_USER_ID (not login email) so David's tasks are
accessible regardless of which Google account he logs in with.

Task fields are designed for Smartsheet migration compatibility:
- Core fields match TaskDetail from tasks.py
- Three-date model for slippage tracking (planned_date, target_date, hard_deadline)
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


# =============================================================================
# Global User Configuration
# =============================================================================

# Global user identifier - tasks are shared across all login identities
# David logs in with either david.a.royes@gmail.com or davidroyes@southpointsda.org
# but both should access the same task list
GLOBAL_USER_ID = "david"

# Emails that map to the global user
GLOBAL_USER_EMAILS = {
    "david.a.royes@gmail.com",
    "davidroyes@southpointsda.org",
}


def _normalize_user_id(user_id: str) -> str:
    """Normalize user_id to global user ID if it's a known David email.
    
    This ensures tasks are accessible regardless of which Google account
    David logs in with.
    
    Args:
        user_id: The email or user identifier
        
    Returns:
        GLOBAL_USER_ID if the email belongs to David, otherwise the original user_id
    """
    if user_id.lower() in {e.lower() for e in GLOBAL_USER_EMAILS}:
        return GLOBAL_USER_ID
    return user_id


class TaskStatus(str, Enum):
    """Task status values (12-value model from migration plan).
    
    Core statuses (8):
    - scheduled: Task is planned for a specific date
    - in_progress: Currently being worked on
    - on_hold: Paused, waiting for external factor
    - blocked: Cannot proceed (similar to on_hold but more urgent)
    - awaiting_reply: Waiting for response from someone
    - follow_up: Needs follow-up action
    - completed: Done
    - cancelled: No longer needed
    
    Optional statuses (4):
    - delivered: Work done, handed off
    - validation: Awaiting verification
    - needs_approval: Waiting for approval
    - delegated: Assigned to someone else
    """
    
    # Core statuses
    SCHEDULED = "scheduled"
    IN_PROGRESS = "in_progress"
    ON_HOLD = "on_hold"
    BLOCKED = "blocked"
    AWAITING_REPLY = "awaiting_reply"
    FOLLOW_UP = "follow_up"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    
    # Optional statuses
    DELIVERED = "delivered"
    VALIDATION = "validation"
    NEEDS_APPROVAL = "needs_approval"
    DELEGATED = "delegated"
    
    # Legacy (kept for backward compatibility during migration)
    PENDING = "pending"  # Maps to SCHEDULED
    RECURRING = "recurring"  # Deprecated - use recurring_type field instead


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


class SyncStatus(str, Enum):
    """Sync status between Firestore and Smartsheet."""
    
    LOCAL_ONLY = "local_only"  # Only in Firestore, not synced
    SYNCED = "synced"  # In sync with Smartsheet
    PENDING = "pending"  # Changes waiting to sync
    CONFLICT = "conflict"  # Conflicts need resolution
    ORPHANED = "orphaned"  # SS row deleted, needs user review


class RecurringType(str, Enum):
    """Type of recurring pattern."""
    
    WEEKLY = "weekly"  # Specific days of week
    MONTHLY = "monthly"  # Specific day of month
    CUSTOM = "custom"  # Every N days/weeks


@dataclass(slots=True)
class FirestoreTask:
    """A task stored in Firestore.
    
    Field design mirrors Smartsheet's TaskDetail for migration compatibility,
    with additional fields for:
    - Three-date model (planned_date, target_date, hard_deadline) for slippage tracking
    - Recurring task patterns (weekly, monthly, custom)
    - Email integration and DATA features
    - Bidirectional sync with Smartsheet
    """
    
    # Identity
    id: str
    domain: str  # "personal", "church", "work"
    
    # Core fields
    title: str
    status: str  # TaskStatus value
    priority: str  # TaskPriority value
    project: Optional[str] = None
    number: Optional[float] = None  # Daily ordering field
    
    # Three-date model (Decision #1 from migration plan)
    planned_date: Optional[date] = None  # When to work on it (auto-rolls)
    target_date: Optional[date] = None  # Original goal (never changes)
    hard_deadline: Optional[date] = None  # External commitment (triggers alerts)
    times_rescheduled: int = 0  # Slippage counter
    
    # Legacy due_date field (maps to planned_date during migration)
    due_date: Optional[date] = None  # Deprecated - use planned_date
    
    # Recurring pattern (Decision #4 - attribute, not status)
    recurring_type: Optional[str] = None  # "weekly" | "monthly" | "custom"
    recurring_days: Optional[List[str]] = None  # ["M", "W", "F"] for weekly
    recurring_monthly: Optional[str] = None  # "1st" | "15th" | "last" | etc.
    recurring_interval: Optional[int] = None  # Every N days/weeks for custom
    
    # Task details
    notes: Optional[str] = None
    next_step: Optional[str] = None
    estimated_hours: Optional[float] = None
    assigned_to: Optional[str] = None
    contact_required: bool = False  # Task requires external contact
    
    # Completion
    done: bool = False
    completed_on: Optional[date] = None
    
    # Timestamps
    created_at: datetime = None  # type: ignore (set in __post_init__)
    updated_at: datetime = None  # type: ignore (set in __post_init__)
    
    # Source tracking
    source: str = TaskSource.MANUAL.value
    source_email_id: Optional[str] = None  # Links to Gmail message ID
    source_email_thread_id: Optional[str] = None  # Links to Gmail thread ID
    source_email_account: Optional[str] = None  # "personal" or "church"
    source_email_subject: Optional[str] = None  # For reference
    
    # Smartsheet sync fields
    smartsheet_row_id: Optional[str] = None  # For bidirectional sync
    smartsheet_sheet: Optional[str] = None  # "personal" or "work"
    smartsheet_modified_at: Optional[datetime] = None  # Smartsheet row's modifiedAt timestamp
    sync_status: str = SyncStatus.LOCAL_ONLY.value  # Sync state
    last_synced_at: Optional[datetime] = None  # Last sync timestamp
    attention_reason: Optional[str] = None  # Why task needs review (e.g., "orphaned")
    
    def __post_init__(self):
        """Initialize timestamps if not set."""
        now = datetime.now(timezone.utc)
        if self.created_at is None:
            object.__setattr__(self, 'created_at', now)
        if self.updated_at is None:
            object.__setattr__(self, 'updated_at', now)
        # Initialize recurring_days as empty list if None
        if self.recurring_days is None:
            object.__setattr__(self, 'recurring_days', [])
    
    @property
    def is_recurring(self) -> bool:
        """Check if this task has a recurring pattern."""
        return self.recurring_type is not None
    
    @property
    def is_overdue(self) -> bool:
        """Check if task is overdue based on planned_date or due_date."""
        check_date = self.planned_date or self.due_date
        if check_date and not self.done:
            return check_date < date.today()
        return False
    
    @property
    def days_until_deadline(self) -> Optional[int]:
        """Days until hard deadline (negative if past)."""
        if self.hard_deadline:
            return (self.hard_deadline - date.today()).days
        return None
    
    @property
    def effective_due_date(self) -> Optional[date]:
        """Get the effective due date (planned_date or legacy due_date)."""
        return self.planned_date or self.due_date
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            # Identity
            "id": self.id,
            "domain": self.domain,
            
            # Core fields
            "title": self.title,
            "status": self.status,
            "priority": self.priority,
            "project": self.project,
            "number": self.number,
            
            # Three-date model
            "planned_date": self.planned_date.isoformat() if self.planned_date else None,
            "target_date": self.target_date.isoformat() if self.target_date else None,
            "hard_deadline": self.hard_deadline.isoformat() if self.hard_deadline else None,
            "times_rescheduled": self.times_rescheduled,
            "due_date": self.due_date.isoformat() if self.due_date else None,  # Legacy
            
            # Recurring
            "recurring_type": self.recurring_type,
            "recurring_days": self.recurring_days,
            "recurring_monthly": self.recurring_monthly,
            "recurring_interval": self.recurring_interval,
            
            # Task details
            "notes": self.notes,
            "next_step": self.next_step,
            "estimated_hours": self.estimated_hours,
            "assigned_to": self.assigned_to,
            "contact_required": self.contact_required,
            
            # Completion
            "done": self.done,
            "completed_on": self.completed_on.isoformat() if self.completed_on else None,
            
            # Timestamps
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            
            # Source tracking
            "source": self.source,
            "source_email_id": self.source_email_id,
            "source_email_thread_id": self.source_email_thread_id,
            "source_email_account": self.source_email_account,
            "source_email_subject": self.source_email_subject,
            
            # Sync tracking
            "smartsheet_row_id": self.smartsheet_row_id,
            "smartsheet_sheet": self.smartsheet_sheet,
            "smartsheet_modified_at": self.smartsheet_modified_at.isoformat() if self.smartsheet_modified_at else None,
            "sync_status": self.sync_status,
            "last_synced_at": self.last_synced_at.isoformat() if self.last_synced_at else None,
            "attention_reason": self.attention_reason,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FirestoreTask":
        """Create from dictionary."""
        
        def parse_date(val) -> Optional[date]:
            if val and isinstance(val, str):
                return date.fromisoformat(val)
            return val if isinstance(val, date) else None
        
        def parse_datetime(val) -> Optional[datetime]:
            if val and isinstance(val, str):
                return datetime.fromisoformat(val)
            return val if isinstance(val, datetime) else None
        
        return cls(
            # Identity
            id=data["id"],
            domain=data.get("domain", "personal"),
            
            # Core fields
            title=data["title"],
            status=data.get("status", TaskStatus.SCHEDULED.value),
            priority=data.get("priority", TaskPriority.STANDARD.value),
            project=data.get("project"),
            number=data.get("number"),
            
            # Three-date model
            planned_date=parse_date(data.get("planned_date")),
            target_date=parse_date(data.get("target_date")),
            hard_deadline=parse_date(data.get("hard_deadline")),
            times_rescheduled=data.get("times_rescheduled", 0),
            due_date=parse_date(data.get("due_date")),  # Legacy
            
            # Recurring
            recurring_type=data.get("recurring_type"),
            recurring_days=data.get("recurring_days", []),
            recurring_monthly=data.get("recurring_monthly"),
            recurring_interval=data.get("recurring_interval"),
            
            # Task details
            notes=data.get("notes"),
            next_step=data.get("next_step"),
            estimated_hours=data.get("estimated_hours"),
            assigned_to=data.get("assigned_to"),
            contact_required=data.get("contact_required", False),
            
            # Completion
            done=data.get("done", False),
            completed_on=parse_date(data.get("completed_on")),
            
            # Timestamps
            created_at=parse_datetime(data.get("created_at")),
            updated_at=parse_datetime(data.get("updated_at")),
            
            # Source tracking
            source=data.get("source", TaskSource.MANUAL.value),
            source_email_id=data.get("source_email_id"),
            source_email_thread_id=data.get("source_email_thread_id"),
            source_email_account=data.get("source_email_account"),
            source_email_subject=data.get("source_email_subject"),
            
            # Sync tracking
            smartsheet_row_id=data.get("smartsheet_row_id"),
            smartsheet_sheet=data.get("smartsheet_sheet"),
            smartsheet_modified_at=parse_datetime(data.get("smartsheet_modified_at")),
            sync_status=data.get("sync_status", SyncStatus.LOCAL_ONLY.value),
            last_synced_at=parse_datetime(data.get("last_synced_at")),
            attention_reason=data.get("attention_reason"),
        )
    
    def to_api_dict(self) -> Dict[str, Any]:
        """Convert to API response format (camelCase)."""
        return {
            # Identity
            "id": self.id,
            "domain": self.domain,
            
            # Core fields
            "title": self.title,
            "status": self.status,
            "priority": self.priority,
            "project": self.project,
            "number": self.number,
            
            # Three-date model
            "plannedDate": self.planned_date.isoformat() if self.planned_date else None,
            "targetDate": self.target_date.isoformat() if self.target_date else None,
            "hardDeadline": self.hard_deadline.isoformat() if self.hard_deadline else None,
            "timesRescheduled": self.times_rescheduled,
            "dueDate": self.due_date.isoformat() if self.due_date else None,  # Legacy
            "effectiveDueDate": self.effective_due_date.isoformat() if self.effective_due_date else None,
            
            # Recurring
            "recurringType": self.recurring_type,
            "recurringDays": self.recurring_days,
            "recurringMonthly": self.recurring_monthly,
            "recurringInterval": self.recurring_interval,
            "isRecurring": self.is_recurring,
            
            # Task details
            "notes": self.notes,
            "nextStep": self.next_step,
            "estimatedHours": self.estimated_hours,
            "assignedTo": self.assigned_to,
            "contactRequired": self.contact_required,
            
            # Completion
            "done": self.done,
            "completedOn": self.completed_on.isoformat() if self.completed_on else None,
            
            # Status helpers
            "isOverdue": self.is_overdue,
            "daysUntilDeadline": self.days_until_deadline,
            
            # Timestamps
            "createdAt": self.created_at.isoformat() if self.created_at else None,
            "updatedAt": self.updated_at.isoformat() if self.updated_at else None,
            
            # Source tracking
            "source": self.source,
            "sourceEmailId": self.source_email_id,
            "sourceEmailThreadId": self.source_email_thread_id,
            "sourceEmailAccount": self.source_email_account,
            "sourceEmailSubject": self.source_email_subject,
            
            # Sync tracking
            "smartsheetRowId": self.smartsheet_row_id,
            "smartsheetSheet": self.smartsheet_sheet,
            "smartsheetModifiedAt": self.smartsheet_modified_at.isoformat() if self.smartsheet_modified_at else None,
            "syncStatus": self.sync_status,
            "lastSyncedAt": self.last_synced_at.isoformat() if self.last_synced_at else None,
            "attentionReason": self.attention_reason,
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
    status: str = TaskStatus.SCHEDULED.value,
    priority: str = TaskPriority.STANDARD.value,
    domain: str = "personal",
    # Three-date model
    planned_date: Optional[date] = None,
    target_date: Optional[date] = None,
    hard_deadline: Optional[date] = None,
    due_date: Optional[date] = None,  # Legacy - maps to planned_date
    # Core fields
    project: Optional[str] = None,
    number: Optional[float] = None,
    notes: Optional[str] = None,
    next_step: Optional[str] = None,
    estimated_hours: Optional[float] = None,
    assigned_to: Optional[str] = None,
    contact_required: bool = False,
    done: bool = False,
    completed_on: Optional[date] = None,  # When task was completed
    # Recurring
    recurring_type: Optional[str] = None,
    recurring_days: Optional[List[str]] = None,
    recurring_monthly: Optional[str] = None,
    recurring_interval: Optional[int] = None,
    # Source tracking
    source: str = TaskSource.MANUAL.value,
    source_email_id: Optional[str] = None,
    source_email_thread_id: Optional[str] = None,
    source_email_account: Optional[str] = None,
    source_email_subject: Optional[str] = None,
    # Sync tracking
    smartsheet_row_id: Optional[str] = None,
    smartsheet_sheet: Optional[str] = None,
    sync_status: str = SyncStatus.LOCAL_ONLY.value,
    last_synced_at: Optional[datetime] = None,
) -> FirestoreTask:
    """Create a new task.
    
    Args:
        user_id: The user who owns this task
        title: Task title
        status: Initial status
        priority: Task priority
        domain: "personal", "church", or "work"
        planned_date: When to work on it (auto-rolls forward)
        target_date: Original goal date (never changes, tracks slippage)
        hard_deadline: External commitment date (triggers alerts)
        due_date: Legacy field - maps to planned_date if provided
        project: Optional project category
        number: Daily ordering number
        notes: Optional notes
        next_step: Optional next action
        estimated_hours: Estimated time to complete
        assigned_to: Who is assigned
        contact_required: Whether task requires external contact
        done: Whether task is done
        completed_on: Date when task was completed
        recurring_type: "weekly", "monthly", or "custom"
        recurring_days: Days for weekly recurring ["M", "W", "F"]
        recurring_monthly: Day of month for monthly recurring
        recurring_interval: Interval for custom recurring
        source: Where task originated
        source_email_id: Gmail message ID if from email
        source_email_thread_id: Gmail thread ID if from email
        source_email_account: "personal" or "church" email account
        source_email_subject: Original email subject
        smartsheet_row_id: Smartsheet row ID for sync
        smartsheet_sheet: Smartsheet sheet name ("personal" or "work")
        sync_status: Current sync status
        last_synced_at: When task was last synced
    
    Returns:
        Created FirestoreTask
    """
    now = datetime.now(timezone.utc)
    
    # Handle legacy due_date -> planned_date mapping
    effective_planned_date = planned_date or due_date
    
    # If target_date not set but planned_date is, set target_date = planned_date
    # This captures the original intention
    effective_target_date = target_date
    if effective_planned_date and not effective_target_date:
        effective_target_date = effective_planned_date
    
    task = FirestoreTask(
        id=str(uuid.uuid4()),
        domain=domain,
        title=title,
        status=status,
        priority=priority,
        project=project,
        number=number,
        planned_date=effective_planned_date,
        target_date=effective_target_date,
        hard_deadline=hard_deadline,
        due_date=due_date,  # Keep legacy field for backward compatibility
        recurring_type=recurring_type,
        recurring_days=recurring_days or [],
        recurring_monthly=recurring_monthly,
        recurring_interval=recurring_interval,
        notes=notes,
        next_step=next_step,
        estimated_hours=estimated_hours,
        assigned_to=assigned_to,
        contact_required=contact_required,
        done=done,
        completed_on=completed_on,
        created_at=now,
        updated_at=now,
        source=source,
        source_email_id=source_email_id,
        source_email_thread_id=source_email_thread_id,
        source_email_account=source_email_account,
        source_email_subject=source_email_subject,
        smartsheet_row_id=smartsheet_row_id,
        smartsheet_sheet=smartsheet_sheet or domain,  # Default sheet matches domain
        sync_status=sync_status,
        last_synced_at=last_synced_at,
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
    
    Automatically:
    - Sets sync_status='pending' if task is synced with Smartsheet
    - Increments times_rescheduled when planned_date changes (slippage tracking)
    - Converts date strings to date objects
    
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
    
    # Convert date strings to date objects
    date_fields = ["planned_date", "target_date", "hard_deadline", "due_date", "effective_due_date", "completed_on"]
    for field in date_fields:
        if field in updates and updates[field] is not None:
            val = updates[field]
            if isinstance(val, str):
                updates[field] = date.fromisoformat(val)
    
    # Track if planned_date is changing (for slippage tracking)
    old_planned_date = task.planned_date
    new_planned_date = updates.get("planned_date")
    
    # Apply updates
    for key, value in updates.items():
        if hasattr(task, key):
            setattr(task, key, value)
    
    # Auto-increment times_rescheduled if planned_date changed
    # (only if caller didn't explicitly set times_rescheduled)
    if (
        new_planned_date is not None
        and old_planned_date != new_planned_date
        and "times_rescheduled" not in updates
    ):
        task.times_rescheduled = (task.times_rescheduled or 0) + 1
    
    # Update timestamp - but NOT if only sync-related fields are being updated
    # This prevents sync operations from triggering "local changes detected"
    SYNC_ONLY_FIELDS = {"sync_status", "last_synced_at", "smartsheet_row_id", "smartsheet_sheet", "smartsheet_modified_at", "attention_reason"}
    non_sync_fields = set(updates.keys()) - SYNC_ONLY_FIELDS
    if non_sync_fields:
        # Real content changes - update the timestamp
        task.updated_at = datetime.now(timezone.utc)
    
    # Auto-set sync_status to 'pending' if:
    # 1. Task is synced with Smartsheet (has smartsheet_row_id)
    # 2. Caller didn't explicitly set sync_status
    # 3. Current status is 'synced' (not already pending/conflict)
    if (
        task.smartsheet_row_id
        and "sync_status" not in updates
        and task.sync_status == SyncStatus.SYNCED.value
    ):
        task.sync_status = SyncStatus.PENDING.value
    
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
    normalized_id = _normalize_user_id(user_id)
    doc_ref = db.collection("global").document(normalized_id).collection("tasks").document(task.id)
    doc_ref.set(task.to_dict())


def _get_from_firestore(db, user_id: str, task_id: str) -> Optional[FirestoreTask]:
    """Get task from Firestore."""
    normalized_id = _normalize_user_id(user_id)
    doc_ref = db.collection("global").document(normalized_id).collection("tasks").document(task_id)
    doc = doc_ref.get()
    
    if doc.exists:
        return FirestoreTask.from_dict(doc.to_dict())
    return None


def _list_from_firestore(db, user_id: str, limit: int) -> List[FirestoreTask]:
    """List tasks from Firestore."""
    normalized_id = _normalize_user_id(user_id)
    collection = db.collection("global").document(normalized_id).collection("tasks")
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
    normalized_id = _normalize_user_id(user_id)
    doc_ref = db.collection("global").document(normalized_id).collection("tasks").document(task_id)
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
    
    # Normalize to global user ID for consistent file naming
    normalized_id = _normalize_user_id(user_id)
    
    # Sanitize user_id for filename
    safe_id = normalized_id.replace("@", "_at_").replace(".", "_")
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
# Task Update Helpers
# =============================================================================

def reschedule_task(
    user_id: str,
    task_id: str,
    new_planned_date: date,
) -> Optional[FirestoreTask]:
    """Reschedule a task to a new planned date.
    
    This updates planned_date, increments times_rescheduled, and preserves
    target_date (the original goal) for slippage tracking.
    
    Args:
        user_id: The user who owns the task
        task_id: The task ID
        new_planned_date: The new planned date
    
    Returns:
        Updated FirestoreTask if found, None otherwise
    """
    task = get_task(user_id, task_id)
    if not task:
        return None
    
    # Only increment rescheduled count if the date actually changed
    if task.planned_date != new_planned_date:
        updates = {
            "planned_date": new_planned_date,
            "times_rescheduled": task.times_rescheduled + 1,
            # Also update legacy due_date for backward compatibility
            "due_date": new_planned_date,
        }
        return update_task(user_id, task_id, updates)
    
    return task


def complete_task(
    user_id: str,
    task_id: str,
) -> Optional[FirestoreTask]:
    """Mark a task as complete.
    
    Sets done=True, completed_on=today, and status=completed.
    
    Args:
        user_id: The user who owns the task
        task_id: The task ID
    
    Returns:
        Updated FirestoreTask if found, None otherwise
    """
    updates = {
        "done": True,
        "completed_on": date.today(),
        "status": TaskStatus.COMPLETED.value,
    }
    return update_task(user_id, task_id, updates)


def get_slippage_info(task: FirestoreTask) -> Dict[str, Any]:
    """Get slippage information for a task.
    
    Returns:
        Dictionary with slippage metrics
    """
    info = {
        "times_rescheduled": task.times_rescheduled,
        "target_date": task.target_date,
        "planned_date": task.planned_date,
        "hard_deadline": task.hard_deadline,
        "days_slipped": None,
        "days_until_deadline": task.days_until_deadline,
        "is_overdue": task.is_overdue,
    }
    
    if task.target_date and task.planned_date:
        info["days_slipped"] = (task.planned_date - task.target_date).days
    
    return info


# =============================================================================
# Email-to-Task Helper
# =============================================================================

def create_task_from_email(
    user_id: str,
    email_id: str,
    email_account: Literal["personal", "church"],
    email_subject: str,
    *,
    email_thread_id: Optional[str] = None,
    title: Optional[str] = None,
    # Three-date model
    planned_date: Optional[date] = None,
    target_date: Optional[date] = None,
    hard_deadline: Optional[date] = None,
    # Core fields
    status: Optional[str] = None,
    priority: str = TaskPriority.STANDARD.value,
    domain: Optional[str] = None,
    project: Optional[str] = None,
    notes: Optional[str] = None,
    estimated_hours: Optional[float] = None,
) -> FirestoreTask:
    """Create a task from an email.
    
    Args:
        user_id: The user creating the task
        email_id: Gmail message ID
        email_thread_id: Gmail thread ID for conversation linking
        email_account: "personal" or "church"
        email_subject: Original email subject
        title: Task title (defaults to email subject)
        planned_date: When to work on it (auto-rolls forward)
        target_date: Original goal date (tracks slippage)
        hard_deadline: External commitment date
        status: Task status (defaults to scheduled)
        priority: Task priority
        domain: Task domain (defaults based on email account)
        project: Project category (e.g., "Church Tasks", "Around The House")
        notes: Optional notes
        estimated_hours: Estimated time to complete
    
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
        status=status or TaskStatus.SCHEDULED.value,
        priority=priority,
        domain=domain,
        planned_date=planned_date,
        target_date=target_date,
        hard_deadline=hard_deadline,
        project=project,
        notes=notes,
        estimated_hours=estimated_hours,
        source=TaskSource.EMAIL.value,
        source_email_id=email_id,
        source_email_thread_id=email_thread_id,
        source_email_account=email_account,
        source_email_subject=email_subject,
    )

