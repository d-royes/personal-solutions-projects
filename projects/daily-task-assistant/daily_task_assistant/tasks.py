"""Stubbed task ingestion/prioritization logic."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterable, List, Optional


@dataclass(slots=True)
class TaskDetail:
    """Normalized representation of a Smartsheet task row."""

    row_id: str
    title: str
    status: str
    due: datetime
    priority: str
    project: str
    assigned_to: Optional[str]
    estimated_hours: Optional[float]
    notes: Optional[str]
    next_step: str
    automation_hint: str
    source: str = "personal"  # "personal" or "work" - identifies which sheet
    done: bool = False  # True if Done checkbox is checked
    number: Optional[float] = None  # # field for ordering: 0.1-0.9 for recurring (early AM), 1+ for regular tasks


def fetch_stubbed_tasks(*, limit: Optional[int] = None) -> List[TaskDetail]:
    """Return a deterministic list of placeholder tasks."""

    now = datetime.utcnow()
    sample: List[TaskDetail] = [
        TaskDetail(
            row_id="1001",
            title="Prepare Q4 client recap",
            status="In Progress",
            due=now + timedelta(days=1),
            priority="Critical",
            project="Sm. Projects & Tasks",
            assigned_to="david.a.royes@gmail.com",
            estimated_hours=3.0,
            notes="Need to summarize metrics, draft recap email, attach charts.",
            next_step="Draft email summary and attach metrics",
            automation_hint="Use LLM to summarize metrics doc",
        ),
        TaskDetail(
            row_id="1002",
            title="Schedule onboarding with vendor",
            status="Awaiting Reply",
            due=now + timedelta(days=3),
            priority="Urgent",
            project="Zendesk Ticket",
            assigned_to="vendor-success@acme.com",
            estimated_hours=1.0,
            notes="Waiting on vendor availability; requires follow-up email plus calendar hold.",
            next_step="Email vendor with availability",
            automation_hint="Generate calendar poll + email",
        ),
        TaskDetail(
            row_id="1003",
            title="Review security questionnaire",
            status="Scheduled",
            due=now + timedelta(days=5),
            priority="Important",
            project="Around The House",
            assigned_to=None,
            estimated_hours=5.0,
            notes="Large questionnaire; reuse previous responses where possible.",
            next_step="Outline responses, flag gaps",
            automation_hint="Suggest response drafts from previous forms",
        ),
    ]

    if limit is None:
        return sample[:]
    return sample[:limit]


def format_task_rows(tasks: Iterable[TaskDetail]) -> str:
    """Return a human-friendly summary table string."""

    lines = ["ID | Title | Status | Priority | Due | Next Step"]
    for task in tasks:
        lines.append(
            f"{task.row_id} | {task.title} | {task.status} | {task.priority} | "
            f"{task.due:%Y-%m-%d} | {task.next_step}"
        )
    return "\n".join(lines)
