"""Task scoring and automation opportunity detection."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable, List, Sequence

from ..tasks import TaskDetail


PRIORITY_WEIGHTS = {
    "Critical": 5.0,
    "Urgent": 4.0,
    "Important": 3.0,
    "Standard": 2.0,
    "Low": 1.0,
}

# Valid Smartsheet statuses:
# Active: Scheduled, Recurring, On Hold, In Progress, Follow-up, Awaiting Reply,
#         Delivered, Create ZD Ticket, Validation, Needs Approval
# Terminal: Ticket Created, Cancelled, Delegated, Completed
STATUS_WEIGHTS = {
    "On Hold": 3.0,           # Needs attention/unblock
    "Awaiting Reply": 2.5,    # Waiting on external response
    "Follow-up": 2.0,         # Needs follow-up action
    "In Progress": 1.5,       # Actively being worked
    "Scheduled": 1.0,         # Planned but not started
    "Recurring": 1.0,         # Regular recurring task
    "Validation": 1.5,        # Needs review/validation
    "Needs Approval": 2.0,    # Waiting for approval
    "Create ZD Ticket": 1.5,  # Action needed
    "Delivered": 0.5,         # Delivered, may need follow-up
}

AUTOMATION_KEYWORDS = {
    "email": "Draft follow-up email",
    "follow up": "Send follow-up",
    "follow-up": "Send follow-up",
    "schedule": "Propose meeting times",
    "calendar": "Send calendar hold",
    "summarize": "Summarize document",
    "summary": "Summarize document",
    "report": "Generate report draft",
    "outline": "Outline response",
    "response": "Draft response",
}


@dataclass(slots=True)
class RankedTask:
    """Task enriched with scoring metadata."""

    task: TaskDetail
    score: float
    labels: List[str] = field(default_factory=list)
    automation_triggers: List[str] = field(default_factory=list)
    reasons: List[str] = field(default_factory=list)


def rank_tasks(
    tasks: Iterable[TaskDetail], *, now: datetime | None = None
) -> List[RankedTask]:
    """Return tasks sorted by score (descending)."""

    ranked = [score_task(task, now=now) for task in tasks]
    ranked.sort(key=lambda rt: rt.score, reverse=True)
    return ranked


def score_task(task: TaskDetail, *, now: datetime | None = None) -> RankedTask:
    now = now or datetime.utcnow()
    score = 0.0
    reasons: List[str] = []
    labels: List[str] = []

    priority_score = PRIORITY_WEIGHTS.get(task.priority, 1.0)
    score += priority_score
    reasons.append(f"Priority weight {priority_score:.1f}")

    status_weight = STATUS_WEIGHTS.get(task.status, 0.5)
    score += status_weight
    if task.status in ("On Hold", "Awaiting Reply", "Needs Approval"):
        labels.append("Needs attention")
    reasons.append(f"Status weight {status_weight:.1f}")

    due_delta_days = (task.due - now).total_seconds() / 86400
    if due_delta_days <= 0:
        due_score = 4.0
        labels.append("Past due")
    elif due_delta_days <= 1:
        due_score = 3.0
        labels.append("Due soon")
    elif due_delta_days <= 3:
        due_score = 2.0
    elif due_delta_days <= 7:
        due_score = 1.0
    else:
        due_score = 0.5
    score += due_score
    reasons.append(f"Due-date urgency {due_score:.1f}")

    if task.estimated_hours is not None:
        if task.estimated_hours <= 2:
            quick_win_bonus = 1.0
            score += quick_win_bonus
            labels.append("Quick win")
            reasons.append(f"Quick win bonus {quick_win_bonus:.1f}")
        elif task.estimated_hours >= 8:
            score += 0.5
            labels.append("Deep work")
            reasons.append("Deep work effort +0.5")

    automation_triggers = list(detect_automation_triggers(task))
    if automation_triggers:
        score += 0.5
        reasons.append("Automation opportunities +0.5")

    return RankedTask(
        task=task,
        score=score,
        labels=labels,
        automation_triggers=automation_triggers,
        reasons=reasons,
    )


def detect_automation_triggers(task: TaskDetail) -> Sequence[str]:
    """Return automation suggestions based on task text."""

    haystacks = [
        task.notes or "",
        task.next_step or "",
        task.automation_hint or "",
    ]
    text = " ".join(haystacks).lower()
    triggers: List[str] = []

    for keyword, suggestion in AUTOMATION_KEYWORDS.items():
        if keyword in text and suggestion not in triggers:
            triggers.append(suggestion)

    return triggers

