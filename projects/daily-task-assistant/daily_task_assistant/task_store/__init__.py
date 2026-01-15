"""Tasks package - task data models and storage.

Enhanced with three-date model for slippage tracking:
- planned_date: When you plan to work on it (auto-rolls)
- target_date: Original goal (never changes)
- hard_deadline: External commitment (triggers alerts)
"""
from __future__ import annotations

from .store import (
    # Data models
    FirestoreTask,
    TaskStatus,
    TaskPriority,
    TaskSource,
    TaskFilters,
    SyncStatus,
    RecurringType,
    # CRUD operations
    create_task,
    get_task,
    list_tasks,
    update_task,
    delete_task,
    # Helper functions
    reschedule_task,
    complete_task,
    get_slippage_info,
    create_task_from_email,
)

__all__ = [
    # Data models
    "FirestoreTask",
    "TaskStatus",
    "TaskPriority",
    "TaskSource",
    "TaskFilters",
    "SyncStatus",
    "RecurringType",
    # CRUD operations
    "create_task",
    "get_task",
    "list_tasks",
    "update_task",
    "delete_task",
    # Helper functions
    "reschedule_task",
    "complete_task",
    "get_slippage_info",
    "create_task_from_email",
]

