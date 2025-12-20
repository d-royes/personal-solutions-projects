"""Tests for Rule Store - persistent storage for email rule suggestions.

This module tests:
- RuleSuggestionRecord dataclass and serialization
- CRUD operations (create, read, update, delete)
- TTL expiration by status (Trust Gradient policy)
- Approval stats for Trust Gradient
- Duplicate detection
"""
from __future__ import annotations

import json
import os
import shutil
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from daily_task_assistant.email.rule_store import (
    RuleSuggestionRecord,
    save_rule_suggestion,
    get_rule_suggestion,
    list_pending_rules,
    decide_rule_suggestion,
    create_rule_suggestion,
    get_rule_approval_stats,
    purge_expired_rules,
    has_pending_rule_for_pattern,
    _rule_dir,
    _now,
)


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def temp_rule_dir(tmp_path):
    """Create temporary rule store directory."""
    rule_dir = tmp_path / "rule_store"
    rule_dir.mkdir()

    with patch.dict(os.environ, {
        "DTA_RULE_FORCE_FILE": "1",
        "DTA_RULE_DIR": str(rule_dir),
    }):
        yield rule_dir

    # Cleanup
    if rule_dir.exists():
        shutil.rmtree(rule_dir)


@pytest.fixture
def sample_rule():
    """Create a sample filter rule dict."""
    return {
        "field": "from",
        "operator": "contains",
        "value": "@newsletter.example.com",
        "action": "Add",
        "label_name": "Promotional",
    }


@pytest.fixture
def sample_record(sample_rule):
    """Create a sample RuleSuggestionRecord."""
    return RuleSuggestionRecord(
        rule_id="test-rule-123",
        email_account="church",
        user_id="david.a.royes@gmail.com",
        suggestion_type="new_label",
        suggested_rule=sample_rule,
        reason="Emails from this sender appear to be promotional newsletters",
        examples=["Weekly Newsletter", "Special Offer!"],
        email_count=5,
        confidence=0.85,
        analysis_method="haiku",
        category="Promotional",
    )


# =============================================================================
# RuleSuggestionRecord Tests
# =============================================================================

class TestRuleSuggestionRecord:
    """Tests for RuleSuggestionRecord dataclass."""

    def test_create_record(self, sample_record):
        """Should create record with all fields."""
        assert sample_record.rule_id == "test-rule-123"
        assert sample_record.email_account == "church"
        assert sample_record.status == "pending"
        assert sample_record.confidence == 0.85
        assert sample_record.analysis_method == "haiku"

    def test_default_status_is_pending(self, sample_rule):
        """New records should default to pending status."""
        record = RuleSuggestionRecord(
            rule_id="test",
            email_account="personal",
            user_id="test@test.com",
            suggestion_type="new_label",
            suggested_rule=sample_rule,
            reason="Test reason",
        )
        assert record.status == "pending"

    def test_expires_at_set_on_creation(self, sample_record):
        """Should set expires_at based on status."""
        assert sample_record.expires_at is not None
        # Pending = 30 days
        expected = sample_record.created_at + timedelta(days=30)
        assert abs((sample_record.expires_at - expected).total_seconds()) < 1

    def test_to_dict_serialization(self, sample_record):
        """Should serialize to dict correctly."""
        data = sample_record.to_dict()

        assert data["rule_id"] == "test-rule-123"
        assert data["email_account"] == "church"
        assert data["suggestion_type"] == "new_label"
        assert data["confidence"] == 0.85
        assert data["status"] == "pending"
        assert isinstance(data["created_at"], str)
        assert isinstance(data["expires_at"], str)

    def test_to_api_dict_camelcase(self, sample_record):
        """Should serialize to camelCase for API."""
        data = sample_record.to_api_dict()

        assert "ruleId" in data
        assert "emailAccount" in data
        assert "suggestionType" in data
        assert "analysisMethod" in data
        assert "createdAt" in data
        # snake_case keys should not be present
        assert "rule_id" not in data
        assert "email_account" not in data

    def test_from_dict_deserialization(self, sample_record):
        """Should deserialize from dict correctly."""
        data = sample_record.to_dict()
        restored = RuleSuggestionRecord.from_dict(data)

        assert restored.rule_id == sample_record.rule_id
        assert restored.email_account == sample_record.email_account
        assert restored.confidence == sample_record.confidence
        assert restored.status == sample_record.status

    def test_is_expired_false_for_new_record(self, sample_record):
        """New records should not be expired."""
        assert not sample_record.is_expired()

    def test_is_expired_true_for_old_record(self, sample_rule):
        """Records past expires_at should be expired."""
        record = RuleSuggestionRecord(
            rule_id="test",
            email_account="personal",
            user_id="test@test.com",
            suggestion_type="new_label",
            suggested_rule=sample_rule,
            reason="Test",
            expires_at=datetime.now(timezone.utc) - timedelta(days=1),
        )
        assert record.is_expired()


# =============================================================================
# TTL Tests (Trust Gradient Policy)
# =============================================================================

class TestTTLPolicy:
    """Tests for TTL expiration by status."""

    def test_pending_ttl_30_days(self, sample_rule):
        """Pending rules should have 30-day TTL."""
        record = RuleSuggestionRecord(
            rule_id="test",
            email_account="church",
            user_id="test@test.com",
            suggestion_type="new_label",
            suggested_rule=sample_rule,
            reason="Test",
            status="pending",
        )

        expected = record.created_at + timedelta(days=30)
        assert abs((record.expires_at - expected).total_seconds()) < 1

    def test_approved_ttl_30_days(self, sample_record):
        """Approved rules should have 30-day TTL from decision."""
        sample_record.status = "approved"
        sample_record.decided_at = _now()
        sample_record._update_expiration()

        expected = sample_record.decided_at + timedelta(days=30)
        assert abs((sample_record.expires_at - expected).total_seconds()) < 1

    def test_rejected_ttl_7_days(self, sample_record):
        """Rejected rules should have 7-day TTL from decision."""
        sample_record.status = "rejected"
        sample_record.decided_at = _now()
        sample_record._update_expiration()

        expected = sample_record.decided_at + timedelta(days=7)
        assert abs((sample_record.expires_at - expected).total_seconds()) < 1


# =============================================================================
# CRUD Operation Tests
# =============================================================================

class TestCRUDOperations:
    """Tests for CRUD operations."""

    def test_save_and_get_rule(self, temp_rule_dir, sample_record):
        """Should save and retrieve rule suggestion."""
        save_rule_suggestion("church", sample_record)

        retrieved = get_rule_suggestion("church", sample_record.rule_id)

        assert retrieved is not None
        assert retrieved.rule_id == sample_record.rule_id
        assert retrieved.confidence == sample_record.confidence

    def test_get_nonexistent_rule(self, temp_rule_dir):
        """Should return None for non-existent rule."""
        result = get_rule_suggestion("church", "nonexistent-id")
        assert result is None

    def test_get_expired_rule_returns_none(self, temp_rule_dir, sample_rule):
        """Should return None for expired rules and delete them."""
        record = RuleSuggestionRecord(
            rule_id="expired-rule",
            email_account="church",
            user_id="test@test.com",
            suggestion_type="new_label",
            suggested_rule=sample_rule,
            reason="Test",
            expires_at=datetime.now(timezone.utc) - timedelta(days=1),
        )

        # Manually save expired record
        store_dir = temp_rule_dir / "church"
        store_dir.mkdir(exist_ok=True)
        file_path = store_dir / f"{record.rule_id}.json"
        with open(file_path, "w") as f:
            json.dump(record.to_dict(), f)

        # Get should return None and delete the file
        result = get_rule_suggestion("church", record.rule_id)
        assert result is None
        assert not file_path.exists()

    def test_list_pending_rules(self, temp_rule_dir, sample_rule):
        """Should list all pending rules."""
        # Create multiple rules
        for i in range(3):
            record = RuleSuggestionRecord(
                rule_id=f"rule-{i}",
                email_account="church",
                user_id="test@test.com",
                suggestion_type="new_label",
                suggested_rule=sample_rule,
                reason=f"Test reason {i}",
                confidence=0.9 - (i * 0.1),
            )
            save_rule_suggestion("church", record)

        # Add one approved rule (should not appear)
        approved = RuleSuggestionRecord(
            rule_id="approved-rule",
            email_account="church",
            user_id="test@test.com",
            suggestion_type="new_label",
            suggested_rule=sample_rule,
            reason="Approved",
            status="approved",
        )
        save_rule_suggestion("church", approved)

        pending = list_pending_rules("church")

        assert len(pending) == 3
        # Should be sorted by confidence descending
        assert pending[0].confidence >= pending[1].confidence
        assert pending[1].confidence >= pending[2].confidence

    def test_list_pending_rules_empty(self, temp_rule_dir):
        """Should return empty list when no pending rules."""
        result = list_pending_rules("personal")
        assert result == []


# =============================================================================
# Decision Tests
# =============================================================================

class TestDecisionTracking:
    """Tests for rule decision tracking."""

    def test_approve_rule(self, temp_rule_dir, sample_record):
        """Should mark rule as approved."""
        save_rule_suggestion("church", sample_record)

        result = decide_rule_suggestion("church", sample_record.rule_id, approved=True)

        assert result is True
        updated = get_rule_suggestion("church", sample_record.rule_id)
        assert updated.status == "approved"
        assert updated.decided_at is not None

    def test_reject_rule_with_reason(self, temp_rule_dir, sample_record):
        """Should mark rule as rejected with reason."""
        save_rule_suggestion("church", sample_record)

        result = decide_rule_suggestion(
            "church",
            sample_record.rule_id,
            approved=False,
            rejection_reason="Too broad, would catch important emails"
        )

        assert result is True
        updated = get_rule_suggestion("church", sample_record.rule_id)
        assert updated.status == "rejected"
        assert updated.rejection_reason == "Too broad, would catch important emails"

    def test_decide_nonexistent_rule(self, temp_rule_dir):
        """Should return False for non-existent rule."""
        result = decide_rule_suggestion("church", "nonexistent", approved=True)
        assert result is False


# =============================================================================
# Create Suggestion Tests
# =============================================================================

class TestCreateSuggestion:
    """Tests for create_rule_suggestion helper."""

    def test_create_generates_uuid(self, temp_rule_dir, sample_rule):
        """Should generate UUID for new suggestion."""
        record = create_rule_suggestion(
            account="church",
            user_id="test@test.com",
            suggestion_type="new_label",
            suggested_rule=sample_rule,
            reason="Test reason",
            confidence=0.8,
        )

        assert record.rule_id is not None
        assert len(record.rule_id) == 36  # UUID format

    def test_create_saves_to_storage(self, temp_rule_dir, sample_rule):
        """Should persist the created suggestion."""
        record = create_rule_suggestion(
            account="personal",
            user_id="test@test.com",
            suggestion_type="new_label",
            suggested_rule=sample_rule,
            reason="Test",
        )

        retrieved = get_rule_suggestion("personal", record.rule_id)
        assert retrieved is not None
        assert retrieved.rule_id == record.rule_id


# =============================================================================
# Approval Stats Tests
# =============================================================================

class TestApprovalStats:
    """Tests for approval statistics."""

    def test_empty_stats(self, temp_rule_dir):
        """Should return empty stats when no rules."""
        stats = get_rule_approval_stats("church")

        assert stats["total"] == 0
        assert stats["approved"] == 0
        assert stats["rejected"] == 0
        assert stats["approvalRate"] == 0.0

    def test_stats_by_method(self, temp_rule_dir, sample_rule):
        """Should group stats by analysis method."""
        # Create haiku suggestions
        for i in range(3):
            record = create_rule_suggestion(
                account="church",
                user_id="test@test.com",
                suggestion_type="new_label",
                suggested_rule=sample_rule,
                reason="Haiku suggestion",
                analysis_method="haiku",
            )
            decide_rule_suggestion("church", record.rule_id, approved=(i < 2))

        # Create regex suggestions
        for i in range(2):
            record = create_rule_suggestion(
                account="church",
                user_id="test@test.com",
                suggestion_type="new_label",
                suggested_rule=sample_rule,
                reason="Regex suggestion",
                analysis_method="regex",
            )
            decide_rule_suggestion("church", record.rule_id, approved=(i < 1))

        stats = get_rule_approval_stats("church")

        assert stats["byMethod"]["haiku"]["approved"] == 2
        assert stats["byMethod"]["haiku"]["rejected"] == 1
        assert stats["byMethod"]["regex"]["approved"] == 1
        assert stats["byMethod"]["regex"]["rejected"] == 1

    def test_stats_by_category(self, temp_rule_dir, sample_rule):
        """Should group stats by category."""
        categories = ["Promotional", "Promotional", "Personal"]
        approvals = [True, False, True]

        for cat, approved in zip(categories, approvals):
            record = create_rule_suggestion(
                account="church",
                user_id="test@test.com",
                suggestion_type="new_label",
                suggested_rule=sample_rule,
                reason="Test",
                category=cat,
            )
            decide_rule_suggestion("church", record.rule_id, approved=approved)

        stats = get_rule_approval_stats("church")

        assert stats["byCategory"]["Promotional"]["approved"] == 1
        assert stats["byCategory"]["Promotional"]["rejected"] == 1
        assert stats["byCategory"]["Personal"]["approved"] == 1


# =============================================================================
# Duplicate Detection Tests
# =============================================================================

class TestDuplicateDetection:
    """Tests for duplicate rule pattern detection."""

    def test_has_pending_rule_for_pattern(self, temp_rule_dir, sample_rule):
        """Should detect existing pending rule for pattern."""
        create_rule_suggestion(
            account="church",
            user_id="test@test.com",
            suggestion_type="new_label",
            suggested_rule=sample_rule,
            reason="Test",
        )

        # Same pattern should be detected
        assert has_pending_rule_for_pattern(
            "church",
            field="from",
            value="@newsletter.example.com",
        )

    def test_no_pending_rule_for_different_pattern(self, temp_rule_dir, sample_rule):
        """Should not detect rule for different pattern."""
        create_rule_suggestion(
            account="church",
            user_id="test@test.com",
            suggestion_type="new_label",
            suggested_rule=sample_rule,
            reason="Test",
        )

        # Different pattern should not be detected
        assert not has_pending_rule_for_pattern(
            "church",
            field="from",
            value="@different.com",
        )

    def test_approved_rule_not_detected(self, temp_rule_dir, sample_rule):
        """Should not detect approved rules as pending."""
        record = create_rule_suggestion(
            account="church",
            user_id="test@test.com",
            suggestion_type="new_label",
            suggested_rule=sample_rule,
            reason="Test",
        )
        decide_rule_suggestion("church", record.rule_id, approved=True)

        # Approved rule should not block new suggestion
        assert not has_pending_rule_for_pattern(
            "church",
            field="from",
            value="@newsletter.example.com",
        )


# =============================================================================
# Purge Tests
# =============================================================================

class TestPurgeExpiredRules:
    """Tests for purging expired rules."""

    def test_purge_expired_rules(self, temp_rule_dir, sample_rule):
        """Should purge expired rules."""
        # Create expired rule
        expired = RuleSuggestionRecord(
            rule_id="expired",
            email_account="church",
            user_id="test@test.com",
            suggestion_type="new_label",
            suggested_rule=sample_rule,
            reason="Expired",
            expires_at=datetime.now(timezone.utc) - timedelta(days=1),
        )

        # Create active rule
        active = RuleSuggestionRecord(
            rule_id="active",
            email_account="church",
            user_id="test@test.com",
            suggestion_type="new_label",
            suggested_rule=sample_rule,
            reason="Active",
        )

        save_rule_suggestion("church", expired)
        save_rule_suggestion("church", active)

        count = purge_expired_rules("church")

        assert count == 1
        assert get_rule_suggestion("church", "expired") is None
        assert get_rule_suggestion("church", "active") is not None
