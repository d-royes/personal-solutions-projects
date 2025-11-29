from datetime import datetime, timedelta

from daily_task_assistant.actions import plan_assist
from daily_task_assistant.tasks import TaskDetail


def _sample_task() -> TaskDetail:
    now = datetime.utcnow()
    return TaskDetail(
        row_id="1234",
        title="Prepare onboarding email",
        status="Blocked",
        due=now + timedelta(days=2),
        priority="Urgent",
        project="Zendesk Ticket",
        assigned_to="owner@example.com",
        estimated_hours=1.5,
        notes="Need to summarize decisions and email the vendor.",
        next_step="Draft email with next steps",
        automation_hint="Draft follow-up email",
    )


def test_plan_assist_returns_email_and_recommendations():
    plan = plan_assist(_sample_task())

    assert "Subject:" in plan.email_draft
    assert plan.next_steps, "Next steps should not be empty"
    assert plan.efficiency_tips, "Efficiency tips should not be empty"
    assert plan.score > 0
    assert "Draft follow-up email" in (plan.automation_triggers or [])

