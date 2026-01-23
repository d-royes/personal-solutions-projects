"""Shared dependencies and helper functions for API routers.

This module extracts common utilities from main.py to enable code reuse
across the modular routers. Import these in routers instead of duplicating code.

Usage in routers:
    from api.dependencies import get_current_user, serialize_task, get_task_by_id
"""
from __future__ import annotations

import os
from functools import lru_cache
from datetime import datetime
from typing import Optional

from fastapi import HTTPException

from daily_task_assistant.api.auth import get_current_user  # noqa: F401 - re-export
from daily_task_assistant.config import load_settings
from daily_task_assistant.dataset import fetch_tasks as fetch_task_dataset
from daily_task_assistant.tasks import TaskDetail


# =============================================================================
# Configuration Constants
# =============================================================================

ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:5174",
    "http://127.0.0.1:5174",
    os.getenv("DTA_ALLOWED_FRONTEND", "").strip(),
    # Custom domains
    "https://staging.dailytaskassistant.ai",
    "https://dailytaskassistant.ai",
    "https://www.dailytaskassistant.ai",
]

# Account-specific labels to include in attention scanning
ATTENTION_SCAN_CONFIG = {
    "church": {
        "include": ["Admin", "Ministry Comms", "Personal", "Unknown"],
        "exclude": ["Junk", "Promotional", "Trash"],
    },
    "personal": {
        "include": ["1 Week Hold", "Admin", "Transactional", "Personal"],
        "exclude": ["Junk", "Promotional", "Trash"],
    },
}

# Labels that DATA is allowed to suggest for rule creation (per account)
ALLOWED_SUGGESTION_LABELS = {
    "church": {
        "1 Week Hold",
        "Admin",
        "Junk",
        "Ministry Comms",
        "Personal",
        "Promotional",
        "Risk Management Forms",
        "Transactional",
        "Unknown",
    },
    "personal": {
        "1 Week Hold",
        "Admin",
        "Junk",
        "Personal",
        "Promotional",
        "Transactional",
    },
}


# =============================================================================
# Cached Functions
# =============================================================================

@lru_cache
def get_settings():
    """Get application settings (cached)."""
    return load_settings()


# =============================================================================
# Serialization Helpers
# =============================================================================

def serialize_task(task: TaskDetail) -> dict:
    """Serialize a Smartsheet TaskDetail to API response format."""
    return {
        "rowId": task.row_id,
        "title": task.title,
        "status": task.status,
        "due": task.due.isoformat(),
        "priority": task.priority,
        "project": task.project,
        "assignedTo": task.assigned_to,
        "estimatedHours": task.estimated_hours,
        "notes": task.notes,
        "nextStep": task.next_step,
        "automationHint": task.automation_hint,
        "source": task.source,
        "done": task.done,
    }


def serialize_firestore_task(task) -> dict:
    """Serialize a FirestoreTask to API response format.
    
    Maps Firestore task fields to match the Smartsheet task format for 
    compatibility with existing LLM prompts and context assembly.
    """
    due_str = None
    if task.planned_date:
        due_str = task.planned_date.isoformat() if hasattr(task.planned_date, 'isoformat') else str(task.planned_date)
    elif task.due_date:
        due_str = task.due_date.isoformat() if hasattr(task.due_date, 'isoformat') else str(task.due_date)
    
    return {
        "rowId": f"fs:{task.id}",
        "title": task.title,
        "status": task.status or "scheduled",
        "due": due_str,
        "priority": task.priority or "Standard",
        "project": task.project,
        "assignedTo": task.assigned_to,
        "estimatedHours": task.estimated_hours,
        "notes": task.notes,
        "nextStep": task.next_step,
        "automationHint": None,
        "source": task.domain or "personal",
        "done": task.done,
        # Firestore-specific fields
        "firestoreId": task.id,
        "isFirestoreTask": True,
        "targetDate": task.target_date.isoformat() if task.target_date else None,
        "hardDeadline": task.hard_deadline.isoformat() if task.hard_deadline else None,
        "timesRescheduled": task.times_rescheduled,
        "recurringType": task.recurring_type,
    }


def serialize_plan(result) -> dict:
    """Serialize an AssistExecutionResult to API response format."""
    plan = result.plan
    return {
        "summary": plan.summary,
        "score": plan.score,
        "labels": plan.labels,
        "automationTriggers": plan.automation_triggers,
        "nextSteps": plan.next_steps,
        "efficiencyTips": plan.efficiency_tips,
        "suggestedActions": plan.suggested_actions,
        "task": serialize_task(plan.task),
        "generator": plan.generator,
        "generatorNotes": plan.generator_notes,
        "messageId": result.message_id,
        "commentPosted": result.comment_posted,
        "warnings": result.warnings,
        # Task Planning Skill fields
        "complexity": plan.complexity,
        "crux": plan.crux,
        "approachOptions": plan.approach_options,
        "recommendedPath": plan.recommended_path,
        "openQuestions": plan.open_questions,
        "doneWhen": plan.done_when,
    }


# =============================================================================
# Task Lookup Helpers
# =============================================================================

def get_task_by_id(task_id: str, user: str, source: str = "auto") -> tuple:
    """Fetch a task by ID, handling both Smartsheet and Firestore tasks.
    
    Args:
        task_id: Task ID, optionally prefixed with 'fs:' for Firestore tasks
        user: User email for Firestore lookups
        source: Data source for Smartsheet lookups
        
    Returns:
        Tuple of (TaskDetail, is_firestore_task, settings, live_tasks, warning)
        
    Raises:
        HTTPException: If task not found
    """
    from daily_task_assistant.task_store import get_task as get_firestore_task
    
    # Check if this is a Firestore task (prefixed with 'fs:')
    if task_id.startswith("fs:"):
        firestore_id = task_id[3:]
        fs_task = get_firestore_task(user, firestore_id)
        if not fs_task:
            raise HTTPException(status_code=404, detail="Firestore task not found.")
        
        # Convert to TaskDetail-compatible object
        due_datetime = datetime.combine(
            fs_task.planned_date or fs_task.due_date or datetime.now().date(),
            datetime.min.time()
        )
        
        task_detail = TaskDetail(
            row_id=task_id,
            title=fs_task.title,
            status=fs_task.status or "scheduled",
            due=due_datetime,
            priority=fs_task.priority or "Standard",
            project=fs_task.project or "",
            assigned_to=fs_task.assigned_to,
            estimated_hours=fs_task.estimated_hours,
            notes=fs_task.notes,
            next_step=fs_task.next_step,
            automation_hint=None,
            source=fs_task.domain or "personal",
            done=fs_task.done,
        )
        
        settings = get_settings()
        return (task_detail, True, settings, True, None)
    
    # Smartsheet task - use existing logic
    tasks, live_tasks, settings, warning = fetch_task_dataset(
        limit=None, source=source, include_work_in_all=True
    )
    target = next((task for task in tasks if task.row_id == task_id), None)
    if not target:
        raise HTTPException(status_code=404, detail="Task not found.")
    
    return (target, False, settings, live_tasks, warning)


def get_environment_info() -> tuple[str, bool]:
    """Get environment identifier and live tasks flag.
    
    Returns:
        Tuple of (environment_name, is_dev_bypass)
    """
    env = os.getenv("DTA_ENV", "local")
    is_dev = os.getenv("DTA_DEV_AUTH_BYPASS") == "1"
    return env, is_dev
