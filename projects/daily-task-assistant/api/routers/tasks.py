"""Tasks Router - Smartsheet and Firestore task management.

Handles:
- Task listing (Smartsheet and Firestore)
- Task CRUD for Firestore
- Bidirectional sync between Smartsheet and Firestore
- Recurring task management
- Work badge counts

Migrated from api/main.py as part of the API refactoring initiative.
"""
from __future__ import annotations

import logging
import os
import time
from datetime import date, datetime
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from api.dependencies import (
    get_current_user,
    get_settings,
    serialize_task,
)
from daily_task_assistant.dataset import fetch_tasks as fetch_task_dataset

logger = logging.getLogger(__name__)

# Main tasks router (mounted at /tasks)
router = APIRouter()

# Sync router (mounted at /sync)
sync_router = APIRouter()


# =============================================================================
# Constants
# =============================================================================

VALID_PRIORITIES = ["Critical", "Urgent", "Important", "Standard", "Low"]
VALID_PRIORITIES_WORK = ["5-Critical", "4-Urgent", "3-Important", "2-Standard", "1-Low"]
VALID_RECURRING = ["M", "T", "W", "H", "F", "Sa", "Monthly"]
VALID_PROJECTS_PERSONAL = [
    "Around The House", "Church Tasks", "Family Time", "Shopping", 
    "Sm. Projects & Tasks", "Zendesk Ticket"
]
VALID_PROJECTS_WORK = [
    "Atlassian (Jira/Confluence)", "Crafter Studio", "Internal Application Support",
    "Team Management", "Strategic Planning", "Stakeholder Relations", "Process Improvement",
    "Daily Operations", "Zendesk Support", "Intranet Management", "Vendor Management",
    "Security & Compliance", "New Initiatives"
]
VALID_ESTIMATED_HOURS = [".05", ".15", ".25", ".50", ".75", "1", "2", "3", "4", "5", "6", "7", "8"]
TERMINAL_STATUSES = ["Completed", "Cancelled", "Delegated", "Ticket Created"]


# =============================================================================
# Pydantic Models
# =============================================================================

class FirestoreTaskCreateRequest(BaseModel):
    """Request body for creating a new Firestore task."""
    title: str
    domain: str = "personal"
    status: Optional[str] = None
    priority: Optional[str] = None
    project: Optional[str] = None
    planned_date: Optional[str] = None
    target_date: Optional[str] = None
    hard_deadline: Optional[str] = None
    notes: Optional[str] = None
    estimated_hours: Optional[float] = None
    recurring_type: Optional[str] = None
    recurring_days: Optional[List[str]] = None
    recurring_monthly: Optional[str] = None
    recurring_interval: Optional[int] = None
    auto_sync: bool = True


class SmartsheetTaskCreateRequest(BaseModel):
    """Request body for creating a new Smartsheet task."""
    source: Literal["personal", "work"] = "personal"
    task: str = Field(..., description="Task title (required)")
    project: str = Field(..., description="Project name (must match allowed values)")
    due_date: str = Field(..., description="Due date in YYYY-MM-DD format")
    priority: str = Field("Standard", description="Priority level")
    status: str = Field("Scheduled", description="Initial status")
    assigned_to: str = Field("david.a.royes@gmail.com", description="Assignee email")
    estimated_hours: str = Field("1", description="Estimated hours")
    notes: Optional[str] = Field(None, description="Optional notes")
    confirmed: bool = Field(False, description="User has confirmed this action")


class SyncRequest(BaseModel):
    """Request body for sync operations."""
    sources: Optional[List[str]] = Field(
        None,
        description="Specific source keys to sync (e.g., ['personal', 'work']). If None, syncs all."
    )
    include_work: bool = Field(
        False,
        description="Include work tasks when sources is None"
    )
    direction: str = Field(
        "bidirectional",
        description="Sync direction: 'smartsheet_to_firestore', 'firestore_to_smartsheet', or 'bidirectional'"
    )


# =============================================================================
# Smartsheet Task Endpoints
# =============================================================================

@router.get("")
def list_tasks(
    source: Literal["auto", "live", "stub"] = Query("auto"),
    limit: Optional[int] = Query(None, ge=1, le=500),
    include_work: bool = Query(False, alias="includeWork"),
    user: str = Depends(get_current_user),
) -> dict:
    """List tasks from Smartsheet."""
    tasks, live_tasks, settings, warning = fetch_task_dataset(
        limit=limit, source=source, include_work_in_all=include_work
    )
    return {
        "tasks": [serialize_task(task) for task in tasks],
        "liveTasks": live_tasks,
        "environment": settings.environment,
        "warning": warning,
    }


@router.post("/create")
def create_smartsheet_task(
    request: SmartsheetTaskCreateRequest,
    user: str = Depends(get_current_user),
) -> dict:
    """Create a new task in Smartsheet.

    Requires confirmation=True to execute. If not confirmed, returns a preview.
    """
    from daily_task_assistant.smartsheet_client import SmartsheetClient, SmartsheetAPIError

    settings = get_settings()

    # Validate project
    valid_projects = VALID_PROJECTS_PERSONAL if request.source == "personal" else VALID_PROJECTS_WORK
    if request.project not in valid_projects:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid project '{request.project}'. Valid: {valid_projects}"
        )

    # Validate priority
    valid_priorities = VALID_PRIORITIES if request.source == "personal" else VALID_PRIORITIES_WORK
    if request.priority not in valid_priorities:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid priority '{request.priority}'. Valid: {valid_priorities}"
        )

    # Validate estimated hours
    if request.estimated_hours not in VALID_ESTIMATED_HOURS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid estimated_hours '{request.estimated_hours}'. Valid: {VALID_ESTIMATED_HOURS}"
        )

    # Return preview if not confirmed
    if not request.confirmed:
        return {
            "status": "preview",
            "message": f"Will create task: '{request.task}' in {request.project}",
            "task": {
                "task": request.task,
                "project": request.project,
                "due_date": request.due_date,
                "priority": request.priority,
                "status": request.status,
                "assigned_to": request.assigned_to,
                "estimated_hours": request.estimated_hours,
                "notes": request.notes,
            }
        }

    # Execute creation
    try:
        client = SmartsheetClient(settings)
        task_data = {
            "task": request.task,
            "project": request.project,
            "due_date": request.due_date,
            "priority": request.priority,
            "status": request.status,
            "assigned_to": request.assigned_to,
            "estimated_hours": request.estimated_hours,
        }
        if request.notes:
            task_data["notes"] = request.notes

        result = client.create_row(task_data, source=request.source)

        return {
            "status": "created",
            "message": f"Created task: '{request.task}'",
            "result": result,
        }
    except SmartsheetAPIError as exc:
        raise HTTPException(status_code=502, detail=f"Smartsheet error: {exc}")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# =============================================================================
# Firestore Task Endpoints
# =============================================================================

@router.get("/firestore")
def list_firestore_tasks(
    domain: Optional[str] = Query(None, description="Filter by domain"),
    status: Optional[str] = Query(None, description="Filter by status"),
    source: Optional[str] = Query(None, description="Filter by source"),
    limit: int = Query(50, ge=1, le=200, description="Maximum tasks to return"),
    user: str = Depends(get_current_user),
) -> dict:
    """List tasks from the Firestore task store."""
    from daily_task_assistant.task_store import list_tasks, TaskFilters
    
    filters = TaskFilters(
        domain=domain,
        status=[status] if status else None,
        source=source,
    )
    
    tasks = list_tasks(user, filters=filters, limit=limit)
    
    return {
        "count": len(tasks),
        "tasks": [t.to_api_dict() for t in tasks],
    }


@router.post("/firestore")
def create_firestore_task(
    request: FirestoreTaskCreateRequest,
    user: str = Depends(get_current_user),
) -> dict:
    """Create a new task directly in Firestore."""
    from daily_task_assistant.task_store import create_task, TaskStatus, TaskPriority, TaskSource
    
    # Parse dates
    planned_date = None
    target_date = None
    hard_deadline = None
    
    if request.planned_date:
        try:
            planned_date = date.fromisoformat(request.planned_date)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid planned_date format: {request.planned_date}")
    
    if request.target_date:
        try:
            target_date = date.fromisoformat(request.target_date)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid target_date format: {request.target_date}")
    
    if request.hard_deadline:
        try:
            hard_deadline = date.fromisoformat(request.hard_deadline)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid hard_deadline format: {request.hard_deadline}")
    
    status = request.status or TaskStatus.SCHEDULED.value
    priority = request.priority or TaskPriority.STANDARD.value
    
    task = create_task(
        user_id=user,
        title=request.title,
        domain=request.domain,
        status=status,
        priority=priority,
        project=request.project,
        planned_date=planned_date,
        target_date=target_date,
        hard_deadline=hard_deadline,
        notes=request.notes,
        estimated_hours=request.estimated_hours,
        source=TaskSource.MANUAL.value,
        recurring_type=request.recurring_type,
        recurring_days=request.recurring_days,
        recurring_monthly=request.recurring_monthly,
        recurring_interval=request.recurring_interval,
    )
    
    # Auto-sync to Smartsheet if requested
    sync_result = None
    if request.auto_sync:
        try:
            from daily_task_assistant.sync.service import SyncService
            from daily_task_assistant.config import Settings
            
            api_settings = Settings(smartsheet_token=(os.getenv("SMARTSHEET_API_TOKEN", "") or "").strip())
            sync_service = SyncService(api_settings, user_email=user)
            
            result = sync_service.sync_to_smartsheet(task_ids=[task.id])
            sync_result = {
                "synced": result.success,
                "created": result.created,
                "errors": result.errors if result.errors else None,
            }
        except Exception as e:
            sync_result = {"synced": False, "error": str(e)}
    
    return {"task": task.to_api_dict(), "sync": sync_result}


@router.get("/firestore/{task_id}")
def get_firestore_task_by_id(
    task_id: str,
    user: str = Depends(get_current_user),
) -> dict:
    """Get a single task from Firestore."""
    from daily_task_assistant.task_store import get_task
    
    task = get_task(user, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    return {"task": task.to_api_dict()}


@router.patch("/firestore/{task_id}")
def update_firestore_task(
    task_id: str,
    updates: Dict[str, Any],
    user: str = Depends(get_current_user),
) -> dict:
    """Update a task in Firestore."""
    from daily_task_assistant.task_store import update_task
    
    task = update_task(user, task_id, updates)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    return {"task": task.to_api_dict()}


@router.delete("/firestore/{task_id}")
def delete_firestore_task(
    task_id: str,
    user: str = Depends(get_current_user),
    cascade_to_smartsheet: bool = Query(True, description="Also delete from Smartsheet if synced"),
) -> dict:
    """Delete a task from Firestore."""
    from daily_task_assistant.task_store import get_task, delete_task
    from daily_task_assistant.smartsheet_client import SmartsheetClient
    
    task = get_task(user, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    ss_row_id = task.smartsheet_row_id
    ss_sheet = task.smartsheet_sheet or task.domain
    
    deleted = delete_task(user, task_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # Mark as Cancelled + Done in Smartsheet (preserves history)
    ss_updated = False
    if cascade_to_smartsheet and ss_row_id:
        try:
            settings = get_settings()
            client = SmartsheetClient(settings)
            client.update_row(
                ss_row_id,
                {"status": "Cancelled", "done": True},
                source=ss_sheet,
            )
            ss_updated = True
        except Exception as e:
            logger.warning(f"Failed to update Smartsheet row {ss_row_id}: {e}")
    
    return {
        "deleted": True,
        "taskId": task_id,
        "smartsheetUpdated": ss_updated,
    }


# =============================================================================
# Recurring Task Endpoints
# =============================================================================

@router.post("/recurring/reset")
def reset_recurring_tasks(
    user: str = Depends(get_current_user),
) -> dict:
    """Reset recurring tasks that should activate today.
    
    Called by Cloud Scheduler daily at 4:00 AM ET.
    """
    from daily_task_assistant.task_store import list_tasks
    from daily_task_assistant.task_store.recurring import (
        should_reset_today,
        reset_recurring_task,
    )
    
    today = date.today()
    reset_count = 0
    reset_task_ids = []
    errors = []
    
    try:
        all_tasks = list_tasks(user, limit=10000)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch tasks: {e}")
    
    for task in all_tasks:
        try:
            if should_reset_today(task, today):
                updated = reset_recurring_task(user, task)
                if updated:
                    reset_count += 1
                    reset_task_ids.append(task.id)
        except Exception as e:
            errors.append(f"Error resetting task {task.id}: {e}")
    
    return {
        "date": today.isoformat(),
        "resetCount": reset_count,
        "resetTaskIds": reset_task_ids,
        "errors": errors,
    }


@router.get("/recurring/preview")
def preview_recurring_resets(
    target_date: Optional[str] = Query(None, description="Date to preview (YYYY-MM-DD)"),
    user: str = Depends(get_current_user),
) -> dict:
    """Preview which recurring tasks would reset on a given date."""
    from daily_task_assistant.task_store import list_tasks
    from daily_task_assistant.task_store.recurring import (
        should_reset_today,
        get_recurring_display,
        get_next_occurrence,
    )
    
    if target_date:
        try:
            check_date = date.fromisoformat(target_date)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD.")
    else:
        check_date = date.today()
    
    try:
        all_tasks = list_tasks(user, limit=10000)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch tasks: {e}")
    
    would_reset = []
    recurring_tasks = []
    
    for task in all_tasks:
        if task.recurring_type:
            recurring_info = {
                "id": task.id,
                "title": task.title,
                "recurringType": task.recurring_type,
                "recurringDays": task.recurring_days,
                "recurringMonthly": task.recurring_monthly,
                "recurringInterval": task.recurring_interval,
                "pattern": get_recurring_display(task),
                "plannedDate": task.planned_date.isoformat() if task.planned_date else None,
                "done": task.done,
                "nextOccurrence": None,
            }
            
            next_occ = get_next_occurrence(task)
            if next_occ:
                recurring_info["nextOccurrence"] = next_occ.isoformat()
            
            recurring_tasks.append(recurring_info)
            
            if should_reset_today(task, check_date):
                would_reset.append(recurring_info)
    
    return {
        "targetDate": check_date.isoformat(),
        "totalRecurringTasks": len(recurring_tasks),
        "wouldResetCount": len(would_reset),
        "wouldReset": would_reset,
        "allRecurringTasks": recurring_tasks,
    }


# =============================================================================
# Sync Endpoints (mounted at /sync)
# =============================================================================

@sync_router.post("/now", tags=["sync"])
def sync_now(
    request: SyncRequest,
    user: str = Depends(get_current_user),
) -> dict:
    """Trigger a sync between Smartsheet and Firestore."""
    from daily_task_assistant.sync import SyncService, SyncDirection
    from daily_task_assistant.config import Settings
    
    start_time = time.time()
    logger.info(f"[SYNC/NOW] Manual sync triggered for user: {user}, direction: {request.direction}")
    
    try:
        settings = Settings(smartsheet_token=(os.getenv("SMARTSHEET_API_TOKEN", "") or "").strip())
    except Exception as e:
        logger.error(f"[SYNC/NOW] Failed to load settings: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to load settings: {e}")
    
    sync_service = SyncService(settings, user_email=user)
    
    direction_map = {
        "smartsheet_to_firestore": SyncDirection.SMARTSHEET_TO_FIRESTORE,
        "firestore_to_smartsheet": SyncDirection.FIRESTORE_TO_SMARTSHEET,
        "bidirectional": SyncDirection.BIDIRECTIONAL,
    }
    direction = direction_map.get(request.direction, SyncDirection.BIDIRECTIONAL)
    
    try:
        if direction == SyncDirection.SMARTSHEET_TO_FIRESTORE:
            result = sync_service.sync_from_smartsheet(
                sources=request.sources,
                include_work=request.include_work,
            )
        elif direction == SyncDirection.FIRESTORE_TO_SMARTSHEET:
            result = sync_service.sync_to_smartsheet()
        else:
            result = sync_service.sync_bidirectional(
                sources=request.sources,
                include_work=request.include_work,
            )
        
        elapsed = time.time() - start_time
        logger.info(f"[SYNC/NOW] Completed in {elapsed:.2f}s")
    except Exception as e:
        logger.error(f"[SYNC/NOW] Sync failed: {e}")
        raise HTTPException(status_code=500, detail=f"Sync failed: {e}")
    
    return {
        "success": result.success,
        "direction": result.direction.value,
        "created": result.created,
        "updated": result.updated,
        "unchanged": result.unchanged,
        "conflicts": result.conflicts,
        "errors": result.errors,
        "totalProcessed": result.total_processed,
        "syncedAt": result.synced_at.isoformat(),
    }


@sync_router.get("/status", tags=["sync"])
def get_sync_status(
    user: str = Depends(get_current_user),
) -> dict:
    """Get current sync status summary."""
    from daily_task_assistant.sync import SyncService
    from daily_task_assistant.config import Settings
    
    try:
        settings = Settings(smartsheet_token=(os.getenv("SMARTSHEET_API_TOKEN", "") or "").strip())
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load settings: {e}")
    
    sync_service = SyncService(settings, user_email=user)
    status = sync_service.get_sync_status()
    
    return {
        "totalTasks": status["total_tasks"],
        "synced": status["synced"],
        "pending": status["pending"],
        "localOnly": status["local_only"],
        "conflicts": status["conflicts"],
        "orphaned": status.get("orphaned", 0),
    }


@sync_router.post("/scheduled", tags=["sync"])
def sync_scheduled(
    user: str = Depends(get_current_user),
) -> dict:
    """Scheduled sync endpoint for Cloud Scheduler."""
    from daily_task_assistant.settings import (
        get_settings as get_app_settings,
        should_run_scheduled_sync,
        record_sync_result,
    )
    from daily_task_assistant.sync import SyncService
    from daily_task_assistant.config import Settings
    
    logger.info(f"[SYNC] Scheduled sync triggered for user: {user}")
    
    if not should_run_scheduled_sync():
        app_settings = get_app_settings()
        return {
            "skipped": True,
            "reason": "Sync interval not reached or sync disabled",
            "syncEnabled": app_settings.sync.enabled,
            "intervalMinutes": app_settings.sync.interval_minutes,
            "lastSyncAt": app_settings.sync.last_sync_at.isoformat() if app_settings.sync.last_sync_at else None,
        }
    
    try:
        settings = Settings(smartsheet_token=(os.getenv("SMARTSHEET_API_TOKEN", "") or "").strip())
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load settings: {e}")
    
    sync_service = SyncService(settings, user_email=user)
    
    try:
        result = sync_service.sync_bidirectional()
        record_sync_result(result.success)
    except Exception as e:
        record_sync_result(False)
        raise HTTPException(status_code=500, detail=f"Sync failed: {e}")
    
    return {
        "success": result.success,
        "created": result.created,
        "updated": result.updated,
        "unchanged": result.unchanged,
        "errors": result.errors,
    }


# =============================================================================
# Work Badge Endpoint (mounted at /work prefix)
# =============================================================================

work_router = APIRouter()


@work_router.get("/badge")
def get_work_badge(
    user: str = Depends(get_current_user),
) -> dict:
    """Get work task badge/notification counts."""
    from daily_task_assistant.smartsheet_client import SmartsheetClient
    
    settings = get_settings()
    
    try:
        client = SmartsheetClient(settings)
        tasks = client.list_tasks(sources=["work"])
    except Exception:
        return {
            "needsAttention": 0,
            "overdue": 0,
            "dueToday": 0,
            "total": 0,
        }
    
    today = date.today()
    overdue = 0
    due_today = 0
    
    for task in tasks:
        if task.due:
            try:
                if isinstance(task.due, date):
                    due_date = task.due
                elif isinstance(task.due, str):
                    due_date = datetime.fromisoformat(task.due.replace("Z", "+00:00")).date()
                else:
                    continue
                    
                if due_date < today:
                    overdue += 1
                elif due_date == today:
                    due_today += 1
            except (ValueError, AttributeError, TypeError):
                pass
    
    return {
        "needsAttention": overdue + due_today,
        "overdue": overdue,
        "dueToday": due_today,
        "total": len(tasks),
    }
