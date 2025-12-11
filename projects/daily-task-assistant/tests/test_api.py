import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# Set env vars BEFORE any imports that might cache them
os.environ["SMARTSHEET_API_TOKEN"] = "test-token"
os.environ["DTA_ACTIVITY_LOG"] = str(Path("test_activity_log.jsonl").resolve())
os.environ["DTA_ACTIVITY_FORCE_FILE"] = "1"
os.environ["DTA_CONVERSATION_FORCE_FILE"] = "1"
os.environ["DTA_CONVERSATION_DIR"] = str(Path("test_conversations").resolve())
os.environ["DTA_DEV_AUTH_BYPASS"] = "1"
os.environ["DTA_ALLOWED_EMAILS"] = "tester@example.com,david.a.royes@gmail.com"

API_ROOT = Path("projects/daily-task-assistant").resolve()
if str(API_ROOT) not in sys.path:
    sys.path.append(str(API_ROOT))

# Clear any cached auth functions before importing app
from daily_task_assistant.api import auth as auth_module  # noqa: E402
auth_module._allowed_emails.cache_clear()

from api.main import app  # type: ignore  # noqa: E402


client = TestClient(app)
USER_HEADERS = {"X-User-Email": "tester@example.com"}


def test_health_check():
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"


def test_list_tasks_stub_source():
    resp = client.get("/tasks?source=stub&limit=2", headers=USER_HEADERS)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["tasks"]) <= 2


def test_assist_stub_flow(tmp_path, monkeypatch):
    from daily_task_assistant.logs import activity as activity_log
    
    log_file = tmp_path / "api-log.jsonl"
    monkeypatch.setenv("DTA_ACTIVITY_LOG", str(log_file))
    monkeypatch.setattr(activity_log, "FORCE_FILE_FALLBACK", True)
    monkeypatch.setenv("DTA_CONVERSATION_FORCE_FILE", "1")
    monkeypatch.setenv("DTA_CONVERSATION_DIR", str(tmp_path / "conversations"))
    
    # First engage the task (loads context, no plan yet)
    engage_resp = client.post(
        "/assist/1001",
        json={"source": "stub"},
        headers=USER_HEADERS,
    )
    assert engage_resp.status_code == 200
    engage_body = engage_resp.json()
    assert "history" in engage_body
    # Plan may be None if no prior plan exists
    
    # Then generate a plan
    resp = client.post(
        "/assist/1001/plan",
        json={"source": "stub"},
        headers=USER_HEADERS,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["plan"]["summary"]
    assert log_file.exists()

    history_resp = client.get("/assist/1001/history", headers=USER_HEADERS)
    assert history_resp.status_code == 200
    # Plan endpoint logs the plan to history, so there should be at least 1 entry
    assert len(history_resp.json()) >= 1

    # Re-engage the task to verify context loading works
    follow_up = client.post(
        "/assist/1001",
        json={"source": "stub"},
        headers=USER_HEADERS,
    )
    assert follow_up.status_code == 200
    # History should include the plan that was logged
    history = follow_up.json()["history"]
    assert len(history) >= 1


def test_activity_endpoint(tmp_path, monkeypatch):
    log_file = tmp_path / "api-log.jsonl"
    log_file.write_text('{"task_id": "1"}\n', encoding="utf-8")
    monkeypatch.setenv("DTA_ACTIVITY_LOG", str(log_file))
    monkeypatch.setenv("DTA_ACTIVITY_FORCE_FILE", "1")

    resp = client.get("/activity?limit=10", headers=USER_HEADERS)
    assert resp.status_code == 200
    assert resp.json()["count"] >= 1


class TestTaskUpdateEndpoint:
    """Tests for the /assist/{task_id}/update endpoint."""

    def test_mark_complete_requires_confirmation(self):
        """Test that mark_complete returns preview when not confirmed."""
        resp = client.post(
            "/assist/1001/update",
            json={"action": "mark_complete", "confirmed": False},
            headers=USER_HEADERS,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "pending_confirmation"
        assert body["preview"]["action"] == "mark_complete"
        # Preview shows done checkbox will be checked
        # (status change depends on whether task is recurring - handled at execution time)
        assert body["preview"]["changes"]["done"] is True

    def test_update_status_requires_status_field(self):
        """Test that update_status requires status field."""
        resp = client.post(
            "/assist/1001/update",
            json={"action": "update_status", "confirmed": True},
            headers=USER_HEADERS,
        )
        assert resp.status_code == 400
        assert "status field required" in resp.json()["detail"]

    def test_update_status_validates_status_value(self):
        """Test that invalid status values are rejected."""
        resp = client.post(
            "/assist/1001/update",
            json={"action": "update_status", "status": "InvalidStatus", "confirmed": True},
            headers=USER_HEADERS,
        )
        assert resp.status_code == 400
        assert "Invalid status" in resp.json()["detail"]

    def test_update_status_preview(self):
        """Test status update preview."""
        resp = client.post(
            "/assist/1001/update",
            json={"action": "update_status", "status": "On Hold", "confirmed": False},
            headers=USER_HEADERS,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "pending_confirmation"
        assert body["preview"]["changes"]["status"] == "On Hold"

    def test_update_priority_validates_value(self):
        """Test that invalid priority values are rejected."""
        resp = client.post(
            "/assist/1001/update",
            json={"action": "update_priority", "priority": "Super High", "confirmed": True},
            headers=USER_HEADERS,
        )
        assert resp.status_code == 400
        assert "Invalid priority" in resp.json()["detail"]

    def test_update_priority_preview(self):
        """Test priority update preview."""
        resp = client.post(
            "/assist/1001/update",
            json={"action": "update_priority", "priority": "Urgent", "confirmed": False},
            headers=USER_HEADERS,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["preview"]["changes"]["priority"] == "Urgent"

    def test_update_due_date_validates_format(self):
        """Test that invalid date format is rejected."""
        resp = client.post(
            "/assist/1001/update",
            json={"action": "update_due_date", "due_date": "12/25/2025", "confirmed": True},
            headers=USER_HEADERS,
        )
        assert resp.status_code == 400
        assert "YYYY-MM-DD" in resp.json()["detail"]

    def test_update_due_date_preview(self):
        """Test due date update preview."""
        resp = client.post(
            "/assist/1001/update",
            json={"action": "update_due_date", "due_date": "2025-12-25", "confirmed": False},
            headers=USER_HEADERS,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["preview"]["changes"]["due_date"] == "2025-12-25"

    def test_add_comment_requires_comment_field(self):
        """Test that add_comment requires comment field."""
        resp = client.post(
            "/assist/1001/update",
            json={"action": "add_comment", "confirmed": True},
            headers=USER_HEADERS,
        )
        assert resp.status_code == 400
        assert "comment field required" in resp.json()["detail"]

    def test_add_comment_preview(self):
        """Test comment add preview."""
        resp = client.post(
            "/assist/1001/update",
            json={"action": "add_comment", "comment": "Test comment", "confirmed": False},
            headers=USER_HEADERS,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["preview"]["changes"]["comment"] == "Test comment"

