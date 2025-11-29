import json
from pathlib import Path

from daily_task_assistant.actions import AssistPlan
from daily_task_assistant.logs import activity as activity_log
from daily_task_assistant.logs.activity import log_assist_event
from daily_task_assistant.tasks import TaskDetail


def _sample_plan(tmp_path: Path) -> AssistPlan:
    task = TaskDetail(
        row_id="123",
        title="Test Task",
        status="In Progress",
        due=__import__("datetime").datetime.utcnow(),
        priority="Urgent",
        project="Demo",
        assigned_to="user@example.com",
        estimated_hours=1.0,
        notes="notes",
        next_step="Do the thing",
        automation_hint="Send email",
    )
    return AssistPlan(
        task=task,
        summary="summary",
        score=1.0,
        labels=["Due soon"],
        automation_triggers=["Draft email"],
        reasons=[],
        next_steps=["Next"],
        efficiency_tips=["Tip"],
        email_draft="Hello",
        generator="templates",
        generator_notes=[],
    )


def test_log_assist_event_writes_jsonl(tmp_path, monkeypatch):
    log_file = tmp_path / "log.jsonl"
    monkeypatch.setenv("DTA_ACTIVITY_LOG", str(log_file))
    monkeypatch.setenv("DTA_ACTIVITY_FORCE_FILE", "1")
    plan = _sample_plan(tmp_path)

    log_assist_event(
        plan=plan,
        account_name="church",
        message_id="abc123",
        anthropic_model="claude",
        environment="local",
        source="stub",
    )

    assert log_file.exists()
    lines = log_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["task_id"] == "123"
    assert record["account"] == "church"
    assert record["source"] == "stub"


def test_log_assist_event_calls_firestore(monkeypatch, tmp_path):
    captured = {}

    class FakeCollection:
        def add(self, payload):
            captured["payload"] = payload

    class FakeClient:
        def collection(self, name):
            captured["collection"] = name
            return FakeCollection()

    plan = _sample_plan(tmp_path)
    monkeypatch.delenv("DTA_ACTIVITY_FORCE_FILE", raising=False)
    monkeypatch.delenv("DTA_ACTIVITY_LOG", raising=False)
    monkeypatch.setenv("DTA_ACTIVITY_COLLECTION", "activity_log")
    monkeypatch.setattr(activity_log, "_firestore_client", FakeClient())

    log_assist_event(
        plan=plan,
        account_name="personal",
        message_id="id-456",
        anthropic_model="opus",
        environment="prod",
        source="live",
    )

    assert captured["collection"] == "activity_log"
    assert captured["payload"]["task_id"] == "123"
    assert captured["payload"]["account"] == "personal"