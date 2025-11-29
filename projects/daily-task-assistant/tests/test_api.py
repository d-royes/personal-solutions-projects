import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("SMARTSHEET_API_TOKEN", "test-token")
os.environ.setdefault("DTA_ACTIVITY_LOG", str(Path("test_activity_log.jsonl").resolve()))
os.environ.setdefault("DTA_ACTIVITY_FORCE_FILE", "1")
os.environ.setdefault("DTA_CONVERSATION_FORCE_FILE", "1")
os.environ.setdefault("DTA_CONVERSATION_DIR", str(Path("test_conversations").resolve()))
os.environ.setdefault("DTA_DEV_AUTH_BYPASS", "1")

API_ROOT = Path("projects/daily-task-assistant").resolve()
if str(API_ROOT) not in sys.path:
    sys.path.append(str(API_ROOT))

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
    log_file = tmp_path / "api-log.jsonl"
    monkeypatch.setenv("DTA_ACTIVITY_LOG", str(log_file))
    monkeypatch.setenv("DTA_ACTIVITY_FORCE_FILE", "1")
    monkeypatch.setenv("DTA_CONVERSATION_FORCE_FILE", "1")
    monkeypatch.setenv("DTA_CONVERSATION_DIR", str(tmp_path / "conversations"))
    resp = client.post(
        "/assist/1001",
        json={"source": "stub", "limit": 5},
        headers=USER_HEADERS,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["plan"]["summary"]
    assert not body["plan"]["commentPosted"]
    assert "history" in body
    assert log_file.exists()

    history_resp = client.get("/assist/1001/history", headers=USER_HEADERS)
    assert history_resp.status_code == 200
    assert len(history_resp.json()) >= len(body["history"])

    follow_up = client.post(
        "/assist/1001",
        json={
          "source": "stub",
          "instructions": "Please mention the parking lot detail.",
        },
        headers=USER_HEADERS,
    )
    assert follow_up.status_code == 200
    history = follow_up.json()["history"]
    assert history[-1]["role"] == "assistant"
    assert any(turn["role"] == "user" for turn in history)


def test_activity_endpoint(tmp_path, monkeypatch):
    log_file = tmp_path / "api-log.jsonl"
    log_file.write_text('{"task_id": "1"}\n', encoding="utf-8")
    monkeypatch.setenv("DTA_ACTIVITY_LOG", str(log_file))
    monkeypatch.setenv("DTA_ACTIVITY_FORCE_FILE", "1")

    resp = client.get("/activity?limit=10", headers=USER_HEADERS)
    assert resp.status_code == 200
    assert resp.json()["count"] >= 1

