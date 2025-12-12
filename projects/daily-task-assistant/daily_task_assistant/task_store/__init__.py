"""Tasks package - task data models and storage."""
from __future__ import annotations

from .store import (
    FirestoreTask,
    TaskStatus,
    TaskPriority,
    TaskSource,
    TaskFilters,
    create_task,
    get_task,
    list_tasks,
    update_task,
    delete_task,
    create_task_from_email,
)

__all__ = [
    "FirestoreTask",
    "TaskStatus",
    "TaskPriority",
    "TaskSource",
    "TaskFilters",
    "create_task",
    "get_task",
    "list_tasks",
    "update_task",
    "delete_task",
    "create_task_from_email",
]

