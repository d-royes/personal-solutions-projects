"""Stubbed task ingestion/prioritization logic."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterable, List


@dataclass(slots=True)
class TaskSummary:
    """Lightweight representation of a Smartsheet row."""

    row_id: str
    title: str
    status: str
    due: datetime
    next_step: str
    automation_hint: str


def fetch_stubbed_tasks(*, limit: int = 5) -> List[TaskSummary]:
    """Return a deterministic list of placeholder tasks.

    The stub lets us validate CLI flows before wiring the real Smartsheet API.
    """

    now = datetime.utcnow()
    sample = [
        TaskSummary(
            row_id="1001",
            title="Prepare Q4 client recap",
            status="In Progress",
            due=now + timedelta(days=1),
            next_step="Draft email summary and attach metrics",
            automation_hint="Use LLM to summarize metrics doc",
        ),
        TaskSummary(
            row_id="1002",
            title="Schedule onboarding with vendor",
            status="Blocked",
            due=now + timedelta(days=3),
            next_step="Email vendor with availability",
            automation_hint="Generate calendar poll + email",
        ),
        TaskSummary(
            row_id="1003",
            title="Review security questionnaire",
            status="Not Started",
            due=now + timedelta(days=5),
            next_step="Outline responses, flag gaps",
            automation_hint="Suggest response drafts from previous forms",
        ),
    ]

    return sample[:limit]


def format_task_rows(tasks: Iterable[TaskSummary]) -> str:
    """Return a human-friendly summary table string."""

    lines = ["ID | Title | Status | Due | Next Step"]
    for task in tasks:
        lines.append(
            f"{task.row_id} | {task.title} | {task.status} | "
            f"{task.due:%Y-%m-%d} | {task.next_step}"
        )
    return "\n".join(lines)
