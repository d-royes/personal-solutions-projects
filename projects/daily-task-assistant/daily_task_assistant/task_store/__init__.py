"""Tasks package - task data models and storage.

Enhanced with three-date model for slippage tracking:
- planned_date: When you plan to work on it (auto-rolls)
- target_date: Original goal (never changes)
- hard_deadline: External commitment (triggers alerts)

Recurring task support:
- Weekly: M, T, W, H, F, Sa, Su
- Monthly: 1st, 15th, last, first_monday, etc.
- Bi-weekly: Every 2 weeks on specified days
- Custom: Every N days
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

from .recurring import (
    # Recurring task utilities
    get_next_occurrence,
    should_reset_today,
    reset_recurring_task,
    get_recurring_display,
    DAY_CODES,
    DAY_NAMES,
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
    # Recurring task utilities
    "get_next_occurrence",
    "should_reset_today",
    "reset_recurring_task",
    "get_recurring_display",
    "DAY_CODES",
    "DAY_NAMES",
]

