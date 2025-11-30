"""Tests for the feedback collection system."""
from __future__ import annotations

import json
import pytest
from pathlib import Path
from datetime import datetime, timezone

from daily_task_assistant.feedback import (
    FeedbackEntry,
    log_feedback,
    fetch_feedback_for_task,
    fetch_feedback_summary,
    fetch_recent_feedback,
)


@pytest.fixture
def feedback_dir(tmp_path, monkeypatch):
    """Set up file-based feedback storage for tests."""
    feedback_path = tmp_path / "feedback"
    monkeypatch.setenv("DTA_FEEDBACK_FORCE_FILE", "1")
    monkeypatch.setenv("DTA_FEEDBACK_DIR", str(feedback_path))
    return feedback_path


class TestFeedbackEntry:
    """Tests for FeedbackEntry dataclass."""

    def test_to_dict(self):
        entry = FeedbackEntry(
            id="test-123",
            task_id="task-456",
            feedback="helpful",
            context="research",
            message_content="Test content",
            timestamp=datetime(2025, 11, 30, 12, 0, 0, tzinfo=timezone.utc),
            user_email="test@example.com",
        )
        
        result = entry.to_dict()
        
        assert result["id"] == "test-123"
        assert result["task_id"] == "task-456"
        assert result["feedback"] == "helpful"
        assert result["context"] == "research"
        assert result["timestamp"] == "2025-11-30T12:00:00+00:00"

    def test_from_dict(self):
        data = {
            "id": "test-123",
            "task_id": "task-456",
            "feedback": "needs_work",
            "context": "chat",
            "message_content": "Test content",
            "timestamp": "2025-11-30T12:00:00+00:00",
            "user_email": "test@example.com",
        }
        
        entry = FeedbackEntry.from_dict(data)
        
        assert entry.id == "test-123"
        assert entry.feedback == "needs_work"
        assert entry.context == "chat"

    def test_message_content_truncation(self):
        long_content = "x" * 1000
        entry = FeedbackEntry(
            id="test",
            task_id="task",
            feedback="helpful",
            context="research",
            message_content=long_content,
            timestamp=datetime.now(timezone.utc),
        )
        
        result = entry.to_dict()
        
        assert len(result["message_content"]) == 500


class TestLogFeedback:
    """Tests for log_feedback function."""

    def test_log_feedback_creates_entry(self, feedback_dir):
        entry = log_feedback(
            task_id="task-123",
            feedback="helpful",
            context="research",
            message_content="Great research results!",
            user_email="david@example.com",
        )
        
        assert entry.task_id == "task-123"
        assert entry.feedback == "helpful"
        assert entry.context == "research"
        assert entry.user_email == "david@example.com"
        assert entry.id is not None

    def test_log_feedback_writes_to_file(self, feedback_dir):
        log_feedback(
            task_id="task-123",
            feedback="needs_work",
            context="chat",
            message_content="Response was too verbose",
        )
        
        feedback_file = feedback_dir / "feedback.jsonl"
        assert feedback_file.exists()
        
        with feedback_file.open() as f:
            line = f.readline()
            data = json.loads(line)
        
        assert data["task_id"] == "task-123"
        assert data["feedback"] == "needs_work"

    def test_log_multiple_feedback_entries(self, feedback_dir):
        log_feedback(task_id="task-1", feedback="helpful", context="research", message_content="Good")
        log_feedback(task_id="task-2", feedback="needs_work", context="chat", message_content="Bad")
        log_feedback(task_id="task-1", feedback="helpful", context="plan", message_content="Great")
        
        feedback_file = feedback_dir / "feedback.jsonl"
        with feedback_file.open() as f:
            lines = f.readlines()
        
        assert len(lines) == 3


class TestFetchFeedback:
    """Tests for fetching feedback."""

    def test_fetch_feedback_for_task(self, feedback_dir):
        # Log feedback for multiple tasks
        log_feedback(task_id="task-A", feedback="helpful", context="research", message_content="A1")
        log_feedback(task_id="task-B", feedback="needs_work", context="chat", message_content="B1")
        log_feedback(task_id="task-A", feedback="needs_work", context="plan", message_content="A2")
        
        # Fetch only task-A feedback
        result = fetch_feedback_for_task("task-A")
        
        assert len(result) == 2
        assert all(e.task_id == "task-A" for e in result)

    def test_fetch_feedback_for_task_sorted_descending(self, feedback_dir):
        log_feedback(task_id="task-A", feedback="helpful", context="research", message_content="First")
        log_feedback(task_id="task-A", feedback="needs_work", context="chat", message_content="Second")
        
        result = fetch_feedback_for_task("task-A")
        
        # Most recent first
        assert result[0].message_content == "Second"
        assert result[1].message_content == "First"

    def test_fetch_recent_feedback(self, feedback_dir):
        log_feedback(task_id="task-1", feedback="helpful", context="research", message_content="1")
        log_feedback(task_id="task-2", feedback="needs_work", context="chat", message_content="2")
        log_feedback(task_id="task-3", feedback="helpful", context="plan", message_content="3")
        
        result = fetch_recent_feedback(limit=10)
        
        assert len(result) == 3

    def test_fetch_recent_feedback_with_limit(self, feedback_dir):
        for i in range(10):
            log_feedback(task_id=f"task-{i}", feedback="helpful", context="chat", message_content=f"msg-{i}")
        
        result = fetch_recent_feedback(limit=5)
        
        assert len(result) == 5


class TestFeedbackSummary:
    """Tests for feedback summary aggregation."""

    def test_feedback_summary_counts(self, feedback_dir):
        log_feedback(task_id="t1", feedback="helpful", context="research", message_content="1")
        log_feedback(task_id="t2", feedback="helpful", context="research", message_content="2")
        log_feedback(task_id="t3", feedback="needs_work", context="chat", message_content="3")
        
        summary = fetch_feedback_summary(days=30)
        
        assert summary.total_helpful == 2
        assert summary.total_needs_work == 1

    def test_feedback_summary_by_context(self, feedback_dir):
        log_feedback(task_id="t1", feedback="helpful", context="research", message_content="1")
        log_feedback(task_id="t2", feedback="needs_work", context="research", message_content="2")
        log_feedback(task_id="t3", feedback="helpful", context="chat", message_content="3")
        
        summary = fetch_feedback_summary(days=30)
        
        assert summary.by_context["research"]["helpful"] == 1
        assert summary.by_context["research"]["needs_work"] == 1
        assert summary.by_context["chat"]["helpful"] == 1

    def test_feedback_summary_helpful_rate(self, feedback_dir):
        log_feedback(task_id="t1", feedback="helpful", context="chat", message_content="1")
        log_feedback(task_id="t2", feedback="helpful", context="chat", message_content="2")
        log_feedback(task_id="t3", feedback="helpful", context="chat", message_content="3")
        log_feedback(task_id="t4", feedback="needs_work", context="chat", message_content="4")
        
        summary = fetch_feedback_summary(days=30)
        
        assert summary.helpful_rate == 0.75  # 3 out of 4

    def test_feedback_summary_recent_issues(self, feedback_dir):
        log_feedback(task_id="t1", feedback="needs_work", context="chat", message_content="Too verbose response")
        log_feedback(task_id="t2", feedback="needs_work", context="research", message_content="Missing contact info")
        
        summary = fetch_feedback_summary(days=30)
        
        assert len(summary.recent_issues) == 2
        assert "Too verbose" in summary.recent_issues[0] or "Too verbose" in summary.recent_issues[1]

    def test_feedback_summary_empty(self, feedback_dir):
        summary = fetch_feedback_summary(days=30)
        
        assert summary.total_helpful == 0
        assert summary.total_needs_work == 0
        assert summary.helpful_rate == 0.0

