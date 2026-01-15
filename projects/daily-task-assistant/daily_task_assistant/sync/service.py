"""Bidirectional sync service between Smartsheet and Firestore.

This service handles:
- Pulling tasks from Smartsheet and creating/updating them in Firestore
- Pushing local Firestore changes back to Smartsheet
- Conflict detection and resolution
- Sync status tracking
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, date
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

from ..config import Settings
from ..smartsheet_client import SmartsheetClient
from ..tasks import TaskDetail
from ..task_store.store import (
    FirestoreTask,
    TaskStatus,
    SyncStatus,
    RecurringType,
    TaskSource,
    get_task,
    create_task,
    update_task,
    list_tasks as list_firestore_tasks,
)


class SyncDirection(Enum):
    """Direction of sync operation."""
    SMARTSHEET_TO_FIRESTORE = "smartsheet_to_firestore"
    FIRESTORE_TO_SMARTSHEET = "firestore_to_smartsheet"
    BIDIRECTIONAL = "bidirectional"


class ConflictResolution(Enum):
    """Strategy for resolving sync conflicts."""
    SMARTSHEET_WINS = "smartsheet_wins"  # Smartsheet is source of truth
    FIRESTORE_WINS = "firestore_wins"    # Firestore is source of truth
    NEWER_WINS = "newer_wins"            # Most recently modified wins
    MANUAL = "manual"                     # Flag for manual resolution


@dataclass(slots=True)
class SyncResult:
    """Result of a sync operation."""
    direction: SyncDirection
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    conflicts: int = 0
    errors: List[str] = field(default_factory=list)
    synced_at: datetime = field(default_factory=lambda: datetime.now(ZoneInfo("America/New_York")))
    
    @property
    def success(self) -> bool:
        """Return True if sync completed without errors."""
        return len(self.errors) == 0
    
    @property
    def total_processed(self) -> int:
        """Return total number of tasks processed."""
        return self.created + self.updated + self.unchanged + self.conflicts


# Mapping from Smartsheet status strings to TaskStatus enum
STATUS_MAP: Dict[str, TaskStatus] = {
    "Scheduled": TaskStatus.SCHEDULED,
    "Recurring": TaskStatus.RECURRING,
    "On Hold": TaskStatus.ON_HOLD,
    "In Progress": TaskStatus.IN_PROGRESS,
    "Follow-up": TaskStatus.FOLLOW_UP,
    "Awaiting Reply": TaskStatus.AWAITING_REPLY,
    "Delivered": TaskStatus.DELIVERED,
    "Create ZD Ticket": TaskStatus.SCHEDULED,  # Map to scheduled
    "Ticket Created": TaskStatus.SCHEDULED,     # Map to scheduled
    "Validation": TaskStatus.VALIDATION,
    "Needs Approval": TaskStatus.NEEDS_APPROVAL,
    "Cancelled": TaskStatus.CANCELLED,
    "Delegated": TaskStatus.DELEGATED,
    "Completed": TaskStatus.COMPLETED,
    # Work sheet uses numbered priorities
    "5-Critical": TaskStatus.SCHEDULED,
    "4-Urgent": TaskStatus.SCHEDULED,
    "3-Important": TaskStatus.SCHEDULED,
    "2-Standard": TaskStatus.SCHEDULED,
    "1-Low": TaskStatus.SCHEDULED,
}

# Reverse mapping from TaskStatus to Smartsheet status string
REVERSE_STATUS_MAP: Dict[TaskStatus, str] = {
    TaskStatus.SCHEDULED: "Scheduled",
    TaskStatus.RECURRING: "Recurring",
    TaskStatus.ON_HOLD: "On Hold",
    TaskStatus.IN_PROGRESS: "In Progress",
    TaskStatus.FOLLOW_UP: "Follow-up",
    TaskStatus.AWAITING_REPLY: "Awaiting Reply",
    TaskStatus.BLOCKED: "On Hold",  # Map blocked to On Hold in Smartsheet
    TaskStatus.DELIVERED: "Delivered",
    TaskStatus.VALIDATION: "Validation",
    TaskStatus.NEEDS_APPROVAL: "Needs Approval",
    TaskStatus.COMPLETED: "Completed",
    TaskStatus.CANCELLED: "Cancelled",
    TaskStatus.DELEGATED: "Delegated",
    TaskStatus.PENDING: "Scheduled",  # Legacy pending maps to scheduled
}

# Mapping from Smartsheet recurring pattern to RecurringType
RECURRING_PATTERN_MAP: Dict[str, Tuple[RecurringType, List[str]]] = {
    "M": (RecurringType.WEEKLY, ["M"]),
    "T": (RecurringType.WEEKLY, ["T"]),
    "W": (RecurringType.WEEKLY, ["W"]),
    "H": (RecurringType.WEEKLY, ["H"]),  # Thursday
    "F": (RecurringType.WEEKLY, ["F"]),
    "Sa": (RecurringType.WEEKLY, ["Sa"]),
    "Monthly": (RecurringType.MONTHLY, []),
}


class SyncService:
    """Service for bidirectional sync between Smartsheet and Firestore.
    
    Design Principles:
    - Smartsheet remains the source of truth for existing tasks
    - Firestore is the primary store for UI operations and new local tasks
    - Sync tracks last_synced_at to detect changes
    - Conflicts are flagged rather than auto-resolved (configurable)
    """
    
    def __init__(
        self,
        settings: Settings,
        *,
        conflict_resolution: ConflictResolution = ConflictResolution.SMARTSHEET_WINS,
        user_email: str = "david.a.royes@gmail.com",
    ) -> None:
        """Initialize the sync service.
        
        Args:
            settings: Application settings with API credentials
            conflict_resolution: Strategy for handling conflicts
            user_email: User identifier for Firestore operations
        """
        self.settings = settings
        self.smartsheet = SmartsheetClient(settings)
        self.conflict_resolution = conflict_resolution
        self.user_email = user_email
        self._tz = ZoneInfo("America/New_York")
    
    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    
    def sync_from_smartsheet(
        self,
        *,
        sources: Optional[List[str]] = None,
        include_work: bool = False,
    ) -> SyncResult:
        """Pull tasks from Smartsheet and sync to Firestore.
        
        This is the primary sync direction - Smartsheet → Firestore.
        Creates new FirestoreTasks for rows not yet synced, updates existing ones.
        
        Args:
            sources: Specific source keys to sync (e.g., ["personal", "work"])
            include_work: If True, include work tasks when sources is None
            
        Returns:
            SyncResult with counts of created, updated, unchanged, conflicts
        """
        result = SyncResult(direction=SyncDirection.SMARTSHEET_TO_FIRESTORE)
        
        try:
            # Fetch all tasks from Smartsheet
            smartsheet_tasks = self.smartsheet.list_tasks(
                sources=sources,
                include_work_in_all=include_work,
            )
        except Exception as e:
            result.errors.append(f"Failed to fetch Smartsheet tasks: {e}")
            return result
        
        # Process each task
        for ss_task in smartsheet_tasks:
            try:
                self._sync_smartsheet_task_to_firestore(ss_task, result)
            except Exception as e:
                result.errors.append(f"Error syncing task {ss_task.row_id}: {e}")
        
        return result
    
    def sync_to_smartsheet(
        self,
        *,
        task_ids: Optional[List[str]] = None,
    ) -> SyncResult:
        """Push Firestore changes back to Smartsheet.
        
        Only syncs tasks with sync_status='pending' or specific task_ids.
        
        Args:
            task_ids: Specific task IDs to sync, or None for all pending
            
        Returns:
            SyncResult with counts
        """
        result = SyncResult(direction=SyncDirection.FIRESTORE_TO_SMARTSHEET)
        
        try:
            if task_ids:
                # Sync specific tasks
                tasks_to_sync = []
                for task_id in task_ids:
                    task = get_task(self.user_email, task_id)
                    if task:
                        tasks_to_sync.append(task)
            else:
                # Get all tasks with pending sync status
                all_tasks = list_firestore_tasks(self.user_email)
                tasks_to_sync = [
                    t for t in all_tasks 
                    if t.sync_status == SyncStatus.PENDING.value
                ]
        except Exception as e:
            result.errors.append(f"Failed to fetch Firestore tasks: {e}")
            return result
        
        # Process each task
        for fs_task in tasks_to_sync:
            try:
                self._sync_firestore_task_to_smartsheet(fs_task, result)
            except Exception as e:
                result.errors.append(f"Error syncing task {fs_task.id}: {e}")
        
        return result
    
    def sync_bidirectional(
        self,
        *,
        sources: Optional[List[str]] = None,
        include_work: bool = False,
    ) -> SyncResult:
        """Perform bidirectional sync.
        
        1. First pulls from Smartsheet to get latest state
        2. Then pushes any local changes back to Smartsheet
        
        Args:
            sources: Specific source keys to sync
            include_work: If True, include work tasks
            
        Returns:
            Combined SyncResult
        """
        # Pull first
        pull_result = self.sync_from_smartsheet(
            sources=sources,
            include_work=include_work,
        )
        
        # Then push
        push_result = self.sync_to_smartsheet()
        
        # Combine results
        combined = SyncResult(direction=SyncDirection.BIDIRECTIONAL)
        combined.created = pull_result.created + push_result.created
        combined.updated = pull_result.updated + push_result.updated
        combined.unchanged = pull_result.unchanged + push_result.unchanged
        combined.conflicts = pull_result.conflicts + push_result.conflicts
        combined.errors = pull_result.errors + push_result.errors
        
        return combined
    
    def get_sync_status(self) -> Dict[str, Any]:
        """Get current sync status summary.
        
        Returns:
            Dict with sync statistics
        """
        try:
            all_tasks = list_firestore_tasks(self.user_email)
        except Exception:
            return {
                "total_tasks": 0,
                "synced": 0,
                "pending": 0,
                "local_only": 0,
                "conflicts": 0,
                "error": "Failed to fetch tasks",
            }
        
        synced = sum(1 for t in all_tasks if t.sync_status == SyncStatus.SYNCED.value)
        pending = sum(1 for t in all_tasks if t.sync_status == SyncStatus.PENDING.value)
        local_only = sum(1 for t in all_tasks if t.sync_status == SyncStatus.LOCAL_ONLY.value)
        conflicts = sum(1 for t in all_tasks if t.sync_status == SyncStatus.CONFLICT.value)
        
        return {
            "total_tasks": len(all_tasks),
            "synced": synced,
            "pending": pending,
            "local_only": local_only,
            "conflicts": conflicts,
        }
    
    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    
    def _sync_smartsheet_task_to_firestore(
        self,
        ss_task: TaskDetail,
        result: SyncResult,
    ) -> None:
        """Sync a single Smartsheet task to Firestore.
        
        Args:
            ss_task: TaskDetail from Smartsheet
            result: SyncResult to update with counts
        """
        # Check if task already exists in Firestore (by smartsheet_row_id)
        existing = self._find_firestore_task_by_row_id(ss_task.row_id, ss_task.source)
        
        if existing:
            # Check if update needed
            if self._needs_update(existing, ss_task):
                self._update_firestore_from_smartsheet(existing, ss_task)
                result.updated += 1
            else:
                result.unchanged += 1
        else:
            # Create new Firestore task
            self._create_firestore_from_smartsheet(ss_task)
            result.created += 1
    
    def _sync_firestore_task_to_smartsheet(
        self,
        fs_task: FirestoreTask,
        result: SyncResult,
    ) -> None:
        """Sync a single Firestore task to Smartsheet.
        
        Args:
            fs_task: FirestoreTask to sync
            result: SyncResult to update with counts
        """
        if not fs_task.smartsheet_row_id:
            # Local-only task - need to create in Smartsheet
            try:
                self._create_smartsheet_from_firestore(fs_task)
                result.created += 1
            except Exception as e:
                result.errors.append(f"Failed to create Smartsheet row: {e}")
            return
        
        # Update existing Smartsheet row
        try:
            updates = self._build_smartsheet_updates(fs_task)
            if updates:
                self.smartsheet.update_row(
                    fs_task.smartsheet_row_id,
                    updates,
                    source=fs_task.domain,
                )
                # Update sync status in Firestore
                update_task(
                    self.user_email,
                    fs_task.id,
                    {
                        "sync_status": SyncStatus.SYNCED.value,
                        "last_synced_at": datetime.now(self._tz),
                    }
                )
                result.updated += 1
            else:
                result.unchanged += 1
        except Exception as e:
            result.errors.append(f"Failed to update Smartsheet row {fs_task.smartsheet_row_id}: {e}")
    
    def _find_firestore_task_by_row_id(
        self,
        row_id: str,
        source: str,
    ) -> Optional[FirestoreTask]:
        """Find a Firestore task by its Smartsheet row ID.
        
        Args:
            row_id: Smartsheet row ID
            source: Source key (personal/work)
            
        Returns:
            FirestoreTask if found, None otherwise
        """
        try:
            all_tasks = list_firestore_tasks(self.user_email)
            for task in all_tasks:
                if task.smartsheet_row_id == row_id and task.domain == source:
                    return task
        except Exception:
            pass
        return None
    
    def _needs_update(self, existing: FirestoreTask, ss_task: TaskDetail) -> bool:
        """Check if Firestore task needs update from Smartsheet.
        
        Compares key fields to detect changes.
        
        Args:
            existing: Current FirestoreTask
            ss_task: TaskDetail from Smartsheet
            
        Returns:
            True if update needed
        """
        # Compare key fields
        if existing.title != ss_task.title:
            return True
        
        # Map Smartsheet status to enum for comparison
        # existing.status is a string value, ss_status is TaskStatus enum
        ss_status = STATUS_MAP.get(ss_task.status, TaskStatus.SCHEDULED)
        if existing.status != ss_status.value:
            return True
        
        if existing.priority != ss_task.priority:
            return True
        
        if existing.project != ss_task.project:
            return True
        
        if existing.done != ss_task.done:
            return True
        
        # Compare due date (planned_date)
        ss_due = ss_task.due.date() if hasattr(ss_task.due, 'date') else ss_task.due
        if existing.planned_date != ss_due:
            return True
        
        if existing.notes != ss_task.notes:
            return True
        
        if existing.estimated_hours != ss_task.estimated_hours:
            return True
        
        return False
    
    def _update_firestore_from_smartsheet(
        self,
        existing: FirestoreTask,
        ss_task: TaskDetail,
    ) -> None:
        """Update Firestore task with data from Smartsheet.
        
        Args:
            existing: Existing FirestoreTask to update
            ss_task: TaskDetail from Smartsheet with new data
        """
        # Map status
        status = STATUS_MAP.get(ss_task.status, TaskStatus.SCHEDULED)
        
        # Extract date
        due_date = ss_task.due.date() if hasattr(ss_task.due, 'date') else ss_task.due
        
        # Build updates dict
        updates = {
            "title": ss_task.title,
            "status": status.value,
            "priority": ss_task.priority,
            "project": ss_task.project,
            "planned_date": due_date,
            "notes": ss_task.notes,
            "estimated_hours": ss_task.estimated_hours,
            "done": ss_task.done,
            "sync_status": SyncStatus.SYNCED.value,
            "last_synced_at": datetime.now(self._tz),
        }
        
        # Update the task
        update_task(self.user_email, existing.id, updates)
    
    def _create_firestore_from_smartsheet(self, ss_task: TaskDetail) -> FirestoreTask:
        """Create a new Firestore task from Smartsheet data.
        
        Args:
            ss_task: TaskDetail from Smartsheet
            
        Returns:
            Created FirestoreTask
        """
        # Map status
        status = STATUS_MAP.get(ss_task.status, TaskStatus.SCHEDULED)
        
        # Extract date
        due_date = ss_task.due.date() if hasattr(ss_task.due, 'date') else ss_task.due
        
        # Determine recurring attributes if applicable
        recurring_type_val = None
        if ss_task.status == "Recurring" or (ss_task.number and 0 < ss_task.number < 1):
            # Task appears to be recurring based on status or number field
            recurring_type_val = RecurringType.WEEKLY.value
        
        # Create the task
        task = create_task(
            self.user_email,  # user_id
            ss_task.title,    # title
            status=status.value,
            priority=ss_task.priority,
            domain=ss_task.source,
            planned_date=due_date,
            target_date=due_date,  # Initially same as planned
            notes=ss_task.notes,
            estimated_hours=ss_task.estimated_hours,
            done=ss_task.done,
            project=ss_task.project,
            number=ss_task.number,
            smartsheet_row_id=ss_task.row_id,
            recurring_type=recurring_type_val,
            sync_status=SyncStatus.SYNCED.value,
            last_synced_at=datetime.now(self._tz),
            source=TaskSource.SMARTSHEET_SYNC.value,
        )
        
        return task
    
    def _create_smartsheet_from_firestore(self, fs_task: FirestoreTask) -> None:
        """Create a new Smartsheet row from Firestore task.
        
        Args:
            fs_task: FirestoreTask to create in Smartsheet
        """
        # Map status back to Smartsheet string
        # fs_task.status is a string value, need to convert to enum for lookup
        try:
            status_enum = TaskStatus(fs_task.status)
            status_str = REVERSE_STATUS_MAP.get(status_enum, "Scheduled")
        except ValueError:
            status_str = "Scheduled"
        
        # Format due date
        due_str = fs_task.planned_date.isoformat() if fs_task.planned_date else None
        
        task_data = {
            "task": fs_task.title,
            "status": status_str,
            "priority": fs_task.priority,
            "project": fs_task.project,
            "due_date": due_str,
            "notes": fs_task.notes,
            "estimated_hours": str(fs_task.estimated_hours) if fs_task.estimated_hours else "1",
        }
        
        # Create in Smartsheet
        response = self.smartsheet.create_row(task_data, source=fs_task.domain)
        
        # Update Firestore with new row ID
        if response and "result" in response:
            rows = response.get("result", [])
            if rows:
                new_row_id = str(rows[0].get("id", ""))
                if new_row_id:
                    update_task(
                        self.user_email,
                        fs_task.id,
                        {
                            "smartsheet_row_id": new_row_id,
                            "sync_status": SyncStatus.SYNCED.value,
                            "last_synced_at": datetime.now(self._tz),
                        }
                    )
    
    def _build_smartsheet_updates(self, fs_task: FirestoreTask) -> Dict[str, Any]:
        """Build update dict for Smartsheet from Firestore task.
        
        Args:
            fs_task: FirestoreTask with changes
            
        Returns:
            Dict of field updates for Smartsheet
        """
        updates: Dict[str, Any] = {}
        
        # Always include core fields that might have changed
        if fs_task.title:
            updates["task"] = fs_task.title
        
        if fs_task.status:
            updates["status"] = REVERSE_STATUS_MAP.get(fs_task.status, "Scheduled")
        
        if fs_task.priority:
            updates["priority"] = fs_task.priority
        
        if fs_task.project:
            updates["project"] = fs_task.project
        
        if fs_task.planned_date:
            updates["due_date"] = fs_task.planned_date.isoformat()
        
        if fs_task.hard_deadline:
            updates["deadline"] = fs_task.hard_deadline.isoformat()
        
        if fs_task.notes is not None:
            updates["notes"] = fs_task.notes
        
        updates["done"] = fs_task.done
        
        return updates
