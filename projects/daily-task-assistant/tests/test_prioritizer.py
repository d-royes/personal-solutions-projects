from datetime import datetime, timedelta

from daily_task_assistant.analysis.prioritizer import (
    detect_automation_triggers,
    rank_tasks,
)
from daily_task_assistant.tasks import TaskDetail


def _task(
    *,
    row_id: str,
    priority: str,
    status: str,
    due_offset_days: int,
    notes: str = "",
) -> TaskDetail:
    now = datetime.utcnow()
    return TaskDetail(
        row_id=row_id,
        title=f"Task {row_id}",
        status=status,
        due=now + timedelta(days=due_offset_days),
        priority=priority,
        project="Sm. Projects & Tasks",
        assigned_to="owner@example.com",
        estimated_hours=1.0,
        notes=notes or "General work",
        next_step="Follow up with stakeholder",
        automation_hint="",
    )


def test_rank_tasks_orders_by_priority_and_due():
    tasks = [
        _task(row_id="low", priority="Low", status="Scheduled", due_offset_days=1),
        _task(row_id="urgent", priority="Critical", status="On Hold", due_offset_days=3),
        _task(row_id="due_soon", priority="Important", status="In Progress", due_offset_days=0),
    ]

    ranked = rank_tasks(tasks, now=datetime.utcnow())
    assert [rt.task.row_id for rt in ranked] == ["urgent", "due_soon", "low"]
    assert ranked[0].labels  # should contain urgency labels


def test_detect_automation_triggers_finds_keywords():
    task = _task(
        row_id="auto",
        priority="Standard",
        status="In Progress",
        due_offset_days=5,
        notes="Need to email vendor and schedule follow up call.",
    )

    triggers = detect_automation_triggers(task)
    assert "Draft follow-up email" in triggers
    assert "Send follow-up" in triggers

