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
    delete_task,
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

# === SMARTSHEET FIELD TRANSLATION UTILITIES ===
# These ensure Firestore values are formatted correctly for Smartsheet picklists

# Allowed estimated_hours values (must be EXACT match for Smartsheet picklist)
ESTIMATED_HOURS_VALUES = [".05", ".15", ".25", ".50", ".75", "1", "2", "3", "4", "5", "6", "7", "8"]

def _translate_estimated_hours(value: Optional[float]) -> str:
    """Translate numeric estimated_hours to Smartsheet picklist format.
    
    Args:
        value: Hours as float (e.g., 0.25, 1.0, 2.0)
        
    Returns:
        Smartsheet picklist string (e.g., ".25", "1", "2")
    """
    if value is None or value <= 0:
        return "1"  # Default to 1 hour
    
    # Direct mappings for fractional hours
    fraction_map = {
        0.05: ".05",
        0.15: ".15",
        0.25: ".25",
        0.5: ".50",
        0.50: ".50",
        0.75: ".75",
    }
    
    if value in fraction_map:
        return fraction_map[value]
    
    # For whole numbers, just use the integer string
    if value >= 1:
        int_val = int(value)
        if int_val <= 8:
            return str(int_val)
        return "8"  # Cap at 8 hours
    
    # For other fractional values, find closest match
    if value < 0.1:
        return ".05"
    elif value < 0.2:
        return ".15"
    elif value < 0.4:
        return ".25"
    elif value < 0.65:
        return ".50"
    else:
        return ".75"


# Priority values by domain
PERSONAL_PRIORITY_VALUES = ["Critical", "Urgent", "Important", "Standard", "Low"]
WORK_PRIORITY_VALUES = ["5-Critical", "4-Urgent", "3-Important", "2-Standard", "1-Low"]

# Priority mapping from internal to Smartsheet format (for work domain)
PRIORITY_TO_WORK_FORMAT: Dict[str, str] = {
    "Critical": "5-Critical",
    "Urgent": "4-Urgent",
    "Important": "3-Important",
    "Standard": "2-Standard",
    "Low": "1-Low",
}

def _translate_priority(value: Optional[str], domain: str) -> str:
    """Translate priority to domain-specific Smartsheet format.
    
    Args:
        value: Priority string (e.g., "Standard", "Critical")
        domain: Task domain ("personal", "church", or "work")
        
    Returns:
        Smartsheet-formatted priority string
    """
    if not value:
        if domain == "work":
            return "2-Standard"
        return "Standard"
    
    # Work domain uses numbered priorities
    if domain == "work":
        # If already in work format, return as-is
        if value in WORK_PRIORITY_VALUES:
            return value
        # Convert from personal format
        return PRIORITY_TO_WORK_FORMAT.get(value, "2-Standard")
    
    # Personal/church use plain text priorities
    if value in PERSONAL_PRIORITY_VALUES:
        return value
    
    # Try to convert from work format
    for personal, work in PRIORITY_TO_WORK_FORMAT.items():
        if value == work:
            return personal
    
    return "Standard"


# Project values by domain
PERSONAL_PROJECTS = [
    "Around The House",
    "Church Tasks",
    "Family Time",
    "Shopping",
    "Sm. Projects & Tasks",
    "Zendesk Ticket",
]

WORK_PROJECTS = [
    "Atlassian (Jira/Confluence)",
    "Crafter Studio",
    "Internal Application Support",
    "Team Management",
    "Strategic Planning",
    "Stakeholder Relations",
    "Process Improvement",
    "Daily Operations",
    "Zendesk Support",
    "Intranet Management",
    "Vendor Management",
    "AI/Automation Projects",
    "DTS Transformation",
    "New Technology Evaluation",
]

def _translate_project(value: Optional[str], domain: str) -> str:
    """Translate project to valid Smartsheet picklist value.
    
    Args:
        value: Project string
        domain: Task domain
        
    Returns:
        Valid Smartsheet project value
    """
    if domain == "work":
        if value and value in WORK_PROJECTS:
            return value
        return "Daily Operations"  # Default for work
    else:
        if value and value in PERSONAL_PROJECTS:
            return value
        return "Sm. Projects & Tasks"  # Default for personal/church


def _translate_status_to_smartsheet(status: Optional[str]) -> str:
    """Translate status to valid Smartsheet status string.
    
    Args:
        status: Status value (either TaskStatus value or raw string)
        
    Returns:
        Valid Smartsheet status string
    """
    if not status:
        return "Scheduled"
    
    # Try to match as TaskStatus enum value
    try:
        status_enum = TaskStatus(status)
        return REVERSE_STATUS_MAP.get(status_enum, "Scheduled")
    except ValueError:
        pass
    
    # If already a valid Smartsheet string, return as-is
    valid_statuses = [
        "Scheduled", "Recurring", "On Hold", "In Progress", "Follow-up",
        "Awaiting Reply", "Delivered", "Create ZD Ticket", "Ticket Created",
        "Validation", "Needs Approval", "Cancelled", "Delegated", "Completed"
    ]
    if status in valid_statuses:
        return status
    
    return "Scheduled"


def translate_firestore_to_smartsheet(fs_task: FirestoreTask) -> Dict[str, Any]:
    """Translate a FirestoreTask to Smartsheet field format.
    
    This ensures all fields are properly formatted for Smartsheet's
    picklist validation requirements.
    
    Args:
        fs_task: The Firestore task to translate
        
    Returns:
        Dict of properly formatted Smartsheet field values
    """
    domain = fs_task.domain or "personal"
    
    # Format due date - required, default to today
    if fs_task.planned_date:
        due_str = fs_task.planned_date.isoformat()
    else:
        due_str = date.today().isoformat()
    
    task_data = {
        "task": fs_task.title,
        "status": _translate_status_to_smartsheet(fs_task.status),
        "priority": _translate_priority(fs_task.priority, domain),
        "project": _translate_project(fs_task.project, domain),
        "due_date": due_str,
        "estimated_hours": _translate_estimated_hours(fs_task.estimated_hours),
        "assigned_to": fs_task.assigned_to or "david.a.royes@gmail.com",
    }
    
    # Optional fields
    if fs_task.notes:
        task_data["notes"] = fs_task.notes
    
    if fs_task.hard_deadline:
        task_data["deadline"] = fs_task.hard_deadline.isoformat()
    
    if fs_task.contact_required:
        task_data["contact_flag"] = True
    
    if fs_task.done:
        task_data["done"] = True
    
    if fs_task.number is not None:
        task_data["number"] = fs_task.number
    
    return task_data


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
        detect_deletions: bool = True,
    ) -> SyncResult:
        """Pull tasks from Smartsheet and sync to Firestore.
        
        This is the primary sync direction - Smartsheet → Firestore.
        Creates new FirestoreTasks for rows not yet synced, updates existing ones.
        Also detects tasks deleted from Smartsheet and removes them from Firestore.
        
        Args:
            sources: Specific source keys to sync (e.g., ["personal", "work"])
            include_work: If True, include work tasks when sources is None
            detect_deletions: If True, detect and delete orphaned FS tasks
            
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
        
        # Build set of SS row_ids for deletion detection
        ss_row_ids = {ss_task.row_id for ss_task in smartsheet_tasks}
        
        # Process each task
        for ss_task in smartsheet_tasks:
            try:
                self._sync_smartsheet_task_to_firestore(ss_task, result)
            except Exception as e:
                result.errors.append(f"Error syncing task {ss_task.row_id}: {e}")
        
        # Detect and delete tasks that were removed from Smartsheet
        if detect_deletions:
            deleted_count = self._detect_and_delete_orphans(ss_row_ids, sources)
            # Add deleted count to result (stored in errors for now, could add proper field)
            if deleted_count > 0:
                result.errors.append(f"Deleted {deleted_count} orphaned tasks from Firestore")
        
        return result
    
    def _detect_and_delete_orphans(
        self,
        ss_row_ids: set,
        sources: Optional[List[str]],
    ) -> int:
        """Detect Firestore tasks that were deleted from Smartsheet.
        
        Args:
            ss_row_ids: Set of row_ids that exist in Smartsheet
            sources: Source sheets that were synced
            
        Returns:
            Number of tasks deleted
        """
        deleted_count = 0
        
        # Get all Firestore tasks for this user (use large limit for full scan)
        try:
            all_fs_tasks = list_firestore_tasks(self.user_email, limit=10000)
        except Exception:
            return 0
        
        # Determine which domains were synced
        synced_domains = set()
        if sources:
            synced_domains = set(sources)
        else:
            synced_domains = {"personal"}  # Default
        
        # Find orphaned tasks (have SS row_id but row_id not in SS)
        for fs_task in all_fs_tasks:
            # Skip tasks that aren't synced with Smartsheet
            if not fs_task.smartsheet_row_id:
                continue
            
            # Skip tasks from domains we didn't sync
            if fs_task.domain not in synced_domains and fs_task.smartsheet_sheet not in synced_domains:
                continue
            
            # If the row_id doesn't exist in Smartsheet, it was deleted
            if fs_task.smartsheet_row_id not in ss_row_ids:
                try:
                    delete_task(self.user_email, fs_task.id)
                    deleted_count += 1
                except Exception:
                    pass
        
        return deleted_count
    
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
                # Get all tasks that need syncing (pending changes OR local-only)
                all_tasks = list_firestore_tasks(self.user_email, limit=10000)
                tasks_to_sync = [
                    t for t in all_tasks 
                    if t.sync_status in (SyncStatus.PENDING.value, SyncStatus.LOCAL_ONLY.value)
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
            all_tasks = list_firestore_tasks(self.user_email, limit=10000)
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
            source: Source key (personal/work) - used for smartsheet_sheet matching
            
        Returns:
            FirestoreTask if found, None otherwise
        """
        try:
            # Use large limit to ensure we check ALL tasks
            all_tasks = list_firestore_tasks(self.user_email, limit=10000)
            for task in all_tasks:
                # Match by row_id AND smartsheet_sheet (not domain, since church tasks
                # come from "personal" sheet but have domain="church")
                if task.smartsheet_row_id == row_id:
                    # Verify it's from the same sheet (row_ids are unique per sheet)
                    if task.smartsheet_sheet == source or task.smartsheet_sheet is None:
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
        
        # Extract dates (convert datetime to date if needed)
        due_date = ss_task.due.date() if hasattr(ss_task.due, 'date') else ss_task.due
        
        hard_deadline = None
        if ss_task.deadline:
            hard_deadline = ss_task.deadline.date() if hasattr(ss_task.deadline, 'date') else ss_task.deadline
        
        completed_on = None
        if ss_task.completed_on:
            completed_on = ss_task.completed_on.date() if hasattr(ss_task.completed_on, 'date') else ss_task.completed_on
        
        # Determine recurring attributes from recurring_pattern field
        recurring_type_val = None
        recurring_days_val = []
        
        if ss_task.recurring_pattern:
            patterns = ss_task.recurring_pattern
            if "Monthly" in patterns:
                recurring_type_val = RecurringType.MONTHLY.value
            else:
                recurring_type_val = RecurringType.WEEKLY.value
                recurring_days_val = patterns
        elif ss_task.status == "Recurring" or (ss_task.number and 0 < ss_task.number < 1):
            recurring_type_val = RecurringType.WEEKLY.value
        
        # Build updates dict
        # Note: We do NOT update target_date here - it tracks original intention
        updates = {
            "title": ss_task.title,
            "status": status.value,
            "priority": ss_task.priority,
            "project": ss_task.project,
            "planned_date": due_date,
            "hard_deadline": hard_deadline,
            "notes": ss_task.notes,
            "estimated_hours": ss_task.estimated_hours,
            "done": ss_task.done,
            "completed_on": completed_on,
            "number": ss_task.number,
            "contact_required": ss_task.contact_flag,
            "recurring_type": recurring_type_val,
            "recurring_days": recurring_days_val,
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
        
        # Extract dates (convert datetime to date if needed)
        due_date = ss_task.due.date() if hasattr(ss_task.due, 'date') else ss_task.due
        
        hard_deadline = None
        if ss_task.deadline:
            hard_deadline = ss_task.deadline.date() if hasattr(ss_task.deadline, 'date') else ss_task.deadline
        
        completed_on = None
        if ss_task.completed_on:
            completed_on = ss_task.completed_on.date() if hasattr(ss_task.completed_on, 'date') else ss_task.completed_on
        
        # Determine recurring attributes from recurring_pattern field
        recurring_type_val = None
        recurring_days_val = []
        
        if ss_task.recurring_pattern:
            # Parse recurring pattern from Smartsheet
            patterns = ss_task.recurring_pattern
            if "Monthly" in patterns:
                recurring_type_val = RecurringType.MONTHLY.value
            else:
                # Weekly recurring with specific days
                recurring_type_val = RecurringType.WEEKLY.value
                recurring_days_val = patterns  # ["M", "W", "F"] etc.
        elif ss_task.status == "Recurring" or (ss_task.number and 0 < ss_task.number < 1):
            # Fallback: detect recurring based on status or number field
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
            hard_deadline=hard_deadline,
            notes=ss_task.notes,
            estimated_hours=ss_task.estimated_hours,
            done=ss_task.done,
            completed_on=completed_on,
            project=ss_task.project,
            number=ss_task.number,
            contact_required=ss_task.contact_flag,
            smartsheet_row_id=ss_task.row_id,
            recurring_type=recurring_type_val,
            recurring_days=recurring_days_val,
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
        # Use the translation utility to format all fields correctly
        task_data = translate_firestore_to_smartsheet(fs_task)
        
        # Create in Smartsheet
        domain = fs_task.domain or "personal"
        response = self.smartsheet.create_row(task_data, source=domain)
        
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
        
        Uses translation utilities to ensure all field values match
        Smartsheet's picklist validation requirements.
        
        Args:
            fs_task: FirestoreTask with changes
            
        Returns:
            Dict of field updates for Smartsheet
        """
        domain = fs_task.domain or "personal"
        updates: Dict[str, Any] = {}
        
        # Always include core fields that might have changed
        # Use translation utilities to format correctly
        if fs_task.title:
            updates["task"] = fs_task.title
        
        if fs_task.status:
            updates["status"] = _translate_status_to_smartsheet(fs_task.status)
        
        if fs_task.priority:
            updates["priority"] = _translate_priority(fs_task.priority, domain)
        
        if fs_task.project:
            updates["project"] = _translate_project(fs_task.project, domain)
        
        if fs_task.planned_date:
            updates["due_date"] = fs_task.planned_date.isoformat()
        
        if fs_task.hard_deadline:
            updates["deadline"] = fs_task.hard_deadline.isoformat()
        
        if fs_task.notes is not None:
            updates["notes"] = fs_task.notes
        
        if fs_task.estimated_hours is not None:
            updates["estimated_hours"] = _translate_estimated_hours(fs_task.estimated_hours)
        
        updates["done"] = fs_task.done
        
        return updates
