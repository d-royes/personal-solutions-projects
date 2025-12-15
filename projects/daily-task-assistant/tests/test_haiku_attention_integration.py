"""Tests for Haiku integration with attention detection.

Tests the detect_attention_with_haiku function which integrates
Claude 3.5 Haiku analysis with VIP detection and profile/regex fallback.
"""
from __future__ import annotations

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

from daily_task_assistant.mailer.inbox import EmailMessage
from daily_task_assistant.email.analyzer import (
    detect_attention_with_haiku,
    _haiku_result_to_attention_item,
    analyze_email_with_haiku_safe,
)
from daily_task_assistant.email.haiku_analyzer import (
    HaikuAnalysisResult,
    HaikuAttentionResult,
    HaikuActionResult,
    HaikuRuleResult,
)


# =============================================================================
# Test Fixtures
# =============================================================================

def make_email(
    email_id: str = "test123",
    from_address: str = "sender@example.com",
    from_name: str = "Test Sender",
    to_address: str = "david@test.com",
    subject: str = "Test Email",
    snippet: str = "This is a test email.",
    labels: list = None,
    is_unread: bool = True,
    date: datetime = None,
) -> EmailMessage:
    """Create a test EmailMessage.

    Note: is_starred and is_important are properties derived from labels,
    not constructor arguments.
    """
    return EmailMessage(
        id=email_id,
        thread_id=f"thread_{email_id}",
        from_address=from_address,
        from_name=from_name,
        to_address=to_address,
        subject=subject,
        snippet=snippet,
        date=date or datetime.now(timezone.utc),
        labels=labels or ["INBOX", "UNREAD"],
        is_unread=is_unread,
    )


def make_haiku_result(
    needs_attention: bool = True,
    urgency: str = "medium",
    reason: str = "Test reason",
    suggested_action: str = "Review needed",
    extracted_task: str = None,
    matched_role: str = None,
    confidence: float = 0.8,
    analysis_method: str = "haiku",
    skipped_reason: str = None,
) -> HaikuAnalysisResult:
    """Create a test HaikuAnalysisResult."""
    return HaikuAnalysisResult(
        attention=HaikuAttentionResult(
            needs_attention=needs_attention,
            urgency=urgency,
            reason=reason,
            suggested_action=suggested_action,
            extracted_task=extracted_task,
            matched_role=matched_role,
            confidence=confidence,
        ),
        action=HaikuActionResult(
            action="keep",
            reason="Default action",
            confidence=confidence,
        ),
        rule=HaikuRuleResult(
            should_suggest=False,
            confidence=confidence,
        ),
        confidence=confidence,
        analysis_method=analysis_method,
        skipped_reason=skipped_reason,
    )


# Default profile data for tests
DEFAULT_VIP_SENDERS = {
    "church": ["Pastor Smith", "Elder Johnson"],
    "personal": ["Mom", "Esther"],
}

DEFAULT_NOT_ACTIONABLE = {
    "church": ["prayer request", "newsletter"],
    "personal": ["marketing", "promotional"],
}

DEFAULT_CHURCH_ROLES = ["Treasurer", "IT Lead"]
DEFAULT_PERSONAL_CONTEXTS = ["Parent", "Homeowner"]

DEFAULT_CHURCH_PATTERNS = {
    "Treasurer": ["deposit", "check request", "invoice"],
    "IT Lead": ["server", "network", "password reset"],
}

DEFAULT_PERSONAL_PATTERNS = {
    "Parent": ["school", "teacher", "homework"],
    "Homeowner": ["HOA", "maintenance", "repair"],
}


# =============================================================================
# Test _haiku_result_to_attention_item
# =============================================================================

class TestHaikuResultToAttentionItem:
    """Tests for converting HaikuAnalysisResult to AttentionItem."""

    def test_converts_needs_attention_true(self):
        """Should create AttentionItem when needs_attention is True."""
        email = make_email()
        result = make_haiku_result(
            needs_attention=True,
            urgency="high",
            reason="Urgent request",
            suggested_action="Reply needed",
            extracted_task="Reply to urgent request",
            matched_role="Work",
            confidence=0.9,
        )

        item = _haiku_result_to_attention_item(email, result)

        assert item is not None
        assert item.email == email
        assert item.reason == "Urgent request"
        assert item.urgency == "high"
        assert item.suggested_action == "Reply needed"
        assert item.extracted_task == "Reply to urgent request"
        assert item.matched_role == "Work"
        assert item.confidence == 0.9
        assert item.analysis_method == "haiku"

    def test_returns_none_when_no_attention_needed(self):
        """Should return None when needs_attention is False."""
        email = make_email()
        result = make_haiku_result(needs_attention=False)

        item = _haiku_result_to_attention_item(email, result)

        assert item is None


# =============================================================================
# Test analyze_email_with_haiku_safe
# =============================================================================

class TestAnalyzeEmailWithHaikuSafe:
    """Tests for the safe Haiku analysis wrapper."""

    @patch("daily_task_assistant.email.analyzer.analyze_email_with_haiku")
    @patch("daily_task_assistant.email.analyzer.increment_haiku_usage")
    def test_successful_analysis_increments_usage(
        self, mock_increment, mock_analyze
    ):
        """Should increment usage on successful Haiku analysis."""
        email = make_email()
        mock_analyze.return_value = make_haiku_result(analysis_method="haiku")

        result = analyze_email_with_haiku_safe(email, "user@test.com")

        assert result is not None
        assert result.analysis_method == "haiku"
        mock_increment.assert_called_once_with("user@test.com")

    @patch("daily_task_assistant.email.analyzer.analyze_email_with_haiku")
    @patch("daily_task_assistant.email.analyzer.increment_haiku_usage")
    def test_skipped_analysis_no_usage_increment(
        self, mock_increment, mock_analyze
    ):
        """Should NOT increment usage when analysis is skipped."""
        email = make_email()
        mock_analyze.return_value = make_haiku_result(
            analysis_method="skipped",
            skipped_reason="Sensitive domain",
        )

        result = analyze_email_with_haiku_safe(email, "user@test.com")

        assert result is not None
        assert result.analysis_method == "skipped"
        mock_increment.assert_not_called()

    @patch("daily_task_assistant.email.analyzer.analyze_email_with_haiku")
    def test_handles_api_errors_gracefully(self, mock_analyze):
        """Should return None on API errors."""
        from daily_task_assistant.llm.anthropic_client import AnthropicError

        email = make_email()
        mock_analyze.side_effect = AnthropicError("API error")

        result = analyze_email_with_haiku_safe(email, "user@test.com")

        assert result is None

    @patch("daily_task_assistant.email.analyzer.analyze_email_with_haiku")
    def test_handles_unexpected_errors(self, mock_analyze):
        """Should return None on unexpected errors."""
        email = make_email()
        mock_analyze.side_effect = ValueError("Unexpected error")

        result = analyze_email_with_haiku_safe(email, "user@test.com")

        assert result is None


# =============================================================================
# Test detect_attention_with_haiku
# =============================================================================

class TestDetectAttentionWithHaiku:
    """Tests for the main Haiku-enhanced attention detection."""

    @patch("daily_task_assistant.email.analyzer.can_use_haiku")
    @patch("daily_task_assistant.email.analyzer.analyze_email_with_haiku_safe")
    def test_vip_senders_bypass_haiku(self, mock_haiku_safe, mock_can_use):
        """VIP senders should be detected without using Haiku."""
        mock_can_use.return_value = True

        email = make_email(
            from_address="pastor.smith@church.org",
            from_name="Pastor Smith",
        )

        items, results = detect_attention_with_haiku(
            messages=[email],
            email_account="church",
            user_id="user@test.com",
            church_roles=DEFAULT_CHURCH_ROLES,
            personal_contexts=DEFAULT_PERSONAL_CONTEXTS,
            vip_senders=DEFAULT_VIP_SENDERS,
            church_attention_patterns=DEFAULT_CHURCH_PATTERNS,
            personal_attention_patterns=DEFAULT_PERSONAL_PATTERNS,
            not_actionable_patterns=DEFAULT_NOT_ACTIONABLE,
        )

        assert len(items) == 1
        assert items[0].analysis_method == "vip"
        assert items[0].urgency == "high"
        assert "Pastor Smith" in items[0].reason
        # Haiku should NOT be called for VIP senders
        mock_haiku_safe.assert_not_called()

    @patch("daily_task_assistant.email.analyzer.can_use_haiku")
    def test_not_actionable_skipped(self, mock_can_use):
        """Not-actionable emails should be skipped entirely."""
        mock_can_use.return_value = True

        email = make_email(
            subject="Weekly Newsletter",
            snippet="Check out our newsletter for this week!",
        )

        items, results = detect_attention_with_haiku(
            messages=[email],
            email_account="church",
            user_id="user@test.com",
            church_roles=DEFAULT_CHURCH_ROLES,
            personal_contexts=DEFAULT_PERSONAL_CONTEXTS,
            vip_senders=DEFAULT_VIP_SENDERS,
            church_attention_patterns=DEFAULT_CHURCH_PATTERNS,
            personal_attention_patterns=DEFAULT_PERSONAL_PATTERNS,
            not_actionable_patterns=DEFAULT_NOT_ACTIONABLE,
        )

        assert len(items) == 0

    @patch("daily_task_assistant.email.analyzer.can_use_haiku")
    @patch("daily_task_assistant.email.analyzer.analyze_email_with_haiku_safe")
    def test_haiku_analysis_when_available(self, mock_haiku_safe, mock_can_use):
        """Should use Haiku when available and under limits."""
        mock_can_use.return_value = True
        mock_haiku_safe.return_value = make_haiku_result(
            needs_attention=True,
            urgency="high",
            reason="Deadline mentioned - action required",
            suggested_action="Create task",
            extracted_task="Complete quarterly report",
            matched_role="Work",
            confidence=0.85,
        )

        email = make_email(
            subject="Quarterly report due Friday",
            snippet="Please complete the quarterly report by end of day Friday.",
        )

        items, results = detect_attention_with_haiku(
            messages=[email],
            email_account="church",
            user_id="user@test.com",
            church_roles=DEFAULT_CHURCH_ROLES,
            personal_contexts=DEFAULT_PERSONAL_CONTEXTS,
            vip_senders=DEFAULT_VIP_SENDERS,
            church_attention_patterns=DEFAULT_CHURCH_PATTERNS,
            personal_attention_patterns=DEFAULT_PERSONAL_PATTERNS,
            not_actionable_patterns=DEFAULT_NOT_ACTIONABLE,
        )

        assert len(items) == 1
        assert items[0].analysis_method == "haiku"
        assert items[0].urgency == "high"
        assert items[0].extracted_task == "Complete quarterly report"
        # Haiku result should be stored
        assert email.id in results

    @patch("daily_task_assistant.email.analyzer.can_use_haiku")
    def test_fallback_to_profile_when_haiku_unavailable(self, mock_can_use):
        """Should fall back to profile analysis when Haiku is unavailable."""
        mock_can_use.return_value = False

        email = make_email(
            subject="Check request for church supplies",
            snippet="Please approve the check request for new supplies.",
        )

        items, results = detect_attention_with_haiku(
            messages=[email],
            email_account="church",
            user_id="user@test.com",
            church_roles=DEFAULT_CHURCH_ROLES,
            personal_contexts=DEFAULT_PERSONAL_CONTEXTS,
            vip_senders=DEFAULT_VIP_SENDERS,
            church_attention_patterns=DEFAULT_CHURCH_PATTERNS,
            personal_attention_patterns=DEFAULT_PERSONAL_PATTERNS,
            not_actionable_patterns=DEFAULT_NOT_ACTIONABLE,
        )

        assert len(items) == 1
        assert items[0].analysis_method == "profile"
        assert items[0].matched_role == "Treasurer"
        # No Haiku results since it was unavailable
        assert len(results) == 0

    @patch("daily_task_assistant.email.analyzer.can_use_haiku")
    def test_fallback_to_regex_when_no_profile_match(self, mock_can_use):
        """Should fall back to regex when no profile match."""
        mock_can_use.return_value = False

        email = make_email(
            to_address="david@test.com",
            subject="Can you review this?",
            snippet="Please review this document when you have a chance.",
        )

        items, results = detect_attention_with_haiku(
            messages=[email],
            email_account="church",
            user_id="user@test.com",
            church_roles=DEFAULT_CHURCH_ROLES,
            personal_contexts=DEFAULT_PERSONAL_CONTEXTS,
            vip_senders=DEFAULT_VIP_SENDERS,
            church_attention_patterns=DEFAULT_CHURCH_PATTERNS,
            personal_attention_patterns=DEFAULT_PERSONAL_PATTERNS,
            not_actionable_patterns=DEFAULT_NOT_ACTIONABLE,
        )

        # Should match regex pattern for "please review"
        assert len(items) == 1
        assert items[0].analysis_method == "regex"

    @patch("daily_task_assistant.email.analyzer.can_use_haiku")
    @patch("daily_task_assistant.email.analyzer.analyze_email_with_haiku_safe")
    def test_skips_already_analyzed_emails(self, mock_haiku_safe, mock_can_use):
        """Should skip emails already analyzed by Haiku."""
        mock_can_use.return_value = True

        email = make_email(email_id="already_done")
        already_analyzed = {"already_done"}

        items, results = detect_attention_with_haiku(
            messages=[email],
            email_account="church",
            user_id="user@test.com",
            church_roles=DEFAULT_CHURCH_ROLES,
            personal_contexts=DEFAULT_PERSONAL_CONTEXTS,
            vip_senders=DEFAULT_VIP_SENDERS,
            church_attention_patterns=DEFAULT_CHURCH_PATTERNS,
            personal_attention_patterns=DEFAULT_PERSONAL_PATTERNS,
            not_actionable_patterns=DEFAULT_NOT_ACTIONABLE,
            already_analyzed_ids=already_analyzed,
        )

        # Haiku should NOT be called for already-analyzed emails
        mock_haiku_safe.assert_not_called()

    @patch("daily_task_assistant.email.analyzer.can_use_haiku")
    @patch("daily_task_assistant.email.analyzer.analyze_email_with_haiku_safe")
    def test_handles_haiku_skipped_due_to_privacy(
        self, mock_haiku_safe, mock_can_use
    ):
        """Should fall back when Haiku skips due to privacy."""
        mock_can_use.return_value = True
        mock_haiku_safe.return_value = make_haiku_result(
            analysis_method="skipped",
            skipped_reason="Sensitive domain: chase.com",
        )

        email = make_email(
            from_address="alerts@chase.com",
            subject="Account Alert",
            snippet="Your payment has been processed.",
        )

        items, results = detect_attention_with_haiku(
            messages=[email],
            email_account="personal",
            user_id="user@test.com",
            church_roles=DEFAULT_CHURCH_ROLES,
            personal_contexts=DEFAULT_PERSONAL_CONTEXTS,
            vip_senders=DEFAULT_VIP_SENDERS,
            church_attention_patterns=DEFAULT_CHURCH_PATTERNS,
            personal_attention_patterns=DEFAULT_PERSONAL_PATTERNS,
            not_actionable_patterns=DEFAULT_NOT_ACTIONABLE,
        )

        # Should fall back to regex (payment pattern)
        # No Haiku results stored since it was skipped
        assert email.id not in results

    @patch("daily_task_assistant.email.analyzer.can_use_haiku")
    @patch("daily_task_assistant.email.analyzer.analyze_email_with_haiku_safe")
    def test_haiku_no_attention_needed_not_returned(
        self, mock_haiku_safe, mock_can_use
    ):
        """Should not return items when Haiku says no attention needed."""
        mock_can_use.return_value = True
        mock_haiku_safe.return_value = make_haiku_result(
            needs_attention=False,
            reason="Newsletter, no action required",
        )

        email = make_email(
            subject="Weekly Update",
            snippet="Here's what's new this week.",
        )

        items, results = detect_attention_with_haiku(
            messages=[email],
            email_account="personal",
            user_id="user@test.com",
            church_roles=DEFAULT_CHURCH_ROLES,
            personal_contexts=DEFAULT_PERSONAL_CONTEXTS,
            vip_senders=DEFAULT_VIP_SENDERS,
            church_attention_patterns=DEFAULT_CHURCH_PATTERNS,
            personal_attention_patterns=DEFAULT_PERSONAL_PATTERNS,
            not_actionable_patterns=DEFAULT_NOT_ACTIONABLE,
        )

        # No attention items but result is still stored for action/rule suggestions
        assert len(items) == 0
        assert email.id in results

    @patch("daily_task_assistant.email.analyzer.can_use_haiku")
    @patch("daily_task_assistant.email.analyzer.analyze_email_with_haiku_safe")
    def test_multiple_emails_mixed_analysis(self, mock_haiku_safe, mock_can_use):
        """Should handle multiple emails with different analysis methods."""
        mock_can_use.return_value = True
        mock_haiku_safe.return_value = make_haiku_result(
            needs_attention=True,
            urgency="medium",
            reason="Question asked",
        )

        vip_email = make_email(
            email_id="vip1",
            from_name="Pastor Smith",
            subject="Meeting update",
        )

        regular_email = make_email(
            email_id="reg1",
            from_name="Random Person",
            subject="Question about the event",
        )

        not_actionable_email = make_email(
            email_id="skip1",
            subject="Prayer request from John",
        )

        items, results = detect_attention_with_haiku(
            messages=[vip_email, regular_email, not_actionable_email],
            email_account="church",
            user_id="user@test.com",
            church_roles=DEFAULT_CHURCH_ROLES,
            personal_contexts=DEFAULT_PERSONAL_CONTEXTS,
            vip_senders=DEFAULT_VIP_SENDERS,
            church_attention_patterns=DEFAULT_CHURCH_PATTERNS,
            personal_attention_patterns=DEFAULT_PERSONAL_PATTERNS,
            not_actionable_patterns=DEFAULT_NOT_ACTIONABLE,
        )

        # Should have 2 items: VIP + Haiku analyzed
        assert len(items) == 2

        # Verify VIP was detected
        vip_items = [i for i in items if i.analysis_method == "vip"]
        assert len(vip_items) == 1

        # Verify Haiku was used
        haiku_items = [i for i in items if i.analysis_method == "haiku"]
        assert len(haiku_items) == 1

        # Only regular email should have Haiku result stored
        assert "reg1" in results
        assert "vip1" not in results  # VIP doesn't need Haiku
        assert "skip1" not in results  # Not actionable was skipped
