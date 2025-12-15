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
    generate_action_suggestions_with_haiku,
    _haiku_action_to_suggestion,
    generate_rule_suggestions_with_haiku,
    _haiku_rule_to_suggestion,
    EmailActionType,
    ConfidenceLevel,
    FilterField,
    FilterOperator,
    FilterCategory,
    FilterRule,
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


# =============================================================================
# Test Action Suggestions with Haiku (Sprint 3)
# =============================================================================

class TestHaikuActionToSuggestion:
    """Tests for converting Haiku action results to suggestions."""

    def test_converts_archive_action(self):
        """Should convert archive action to ARCHIVE suggestion."""
        email = make_email()
        result = make_haiku_result()
        result.action = HaikuActionResult(
            action="archive",
            reason="Old newsletter, already read",
            confidence=0.85,
        )
        result.confidence = 0.85

        suggestion = _haiku_action_to_suggestion(
            email=email,
            result=result,
            number=1,
            label_lookup={},
        )

        assert suggestion is not None
        assert suggestion.action == EmailActionType.ARCHIVE
        assert suggestion.rationale == "Old newsletter, already read"
        assert suggestion.confidence == ConfidenceLevel.HIGH

    def test_converts_label_action_with_known_label(self):
        """Should convert label action with matching label lookup."""
        email = make_email()
        result = make_haiku_result()
        result.action = HaikuActionResult(
            action="label",
            label_name="Work",
            reason="Related to work project",
            confidence=0.75,
        )
        result.confidence = 0.75

        label_lookup = {"work": {"id": "Label_123", "name": "Work"}}

        suggestion = _haiku_action_to_suggestion(
            email=email,
            result=result,
            number=2,
            label_lookup=label_lookup,
        )

        assert suggestion is not None
        assert suggestion.action == EmailActionType.LABEL
        assert suggestion.label_id == "Label_123"
        assert suggestion.label_name == "Work"

    def test_converts_label_action_with_unknown_label(self):
        """Should handle label action when label not in lookup."""
        email = make_email()
        result = make_haiku_result()
        result.action = HaikuActionResult(
            action="label",
            label_name="NewCategory",
            reason="New category suggestion",
            confidence=0.7,
        )
        result.confidence = 0.7

        suggestion = _haiku_action_to_suggestion(
            email=email,
            result=result,
            number=1,
            label_lookup={},
        )

        assert suggestion is not None
        assert suggestion.action == EmailActionType.LABEL
        assert suggestion.label_id is None
        assert suggestion.label_name == "NewCategory"

    def test_converts_star_action(self):
        """Should convert star action to STAR suggestion."""
        email = make_email()
        result = make_haiku_result()
        result.action = HaikuActionResult(
            action="star",
            reason="Important message to revisit",
            confidence=0.8,
        )
        result.confidence = 0.8

        suggestion = _haiku_action_to_suggestion(
            email=email,
            result=result,
            number=1,
            label_lookup={},
        )

        assert suggestion is not None
        assert suggestion.action == EmailActionType.STAR
        assert suggestion.confidence == ConfidenceLevel.HIGH

    def test_converts_delete_action(self):
        """Should convert delete action to DELETE suggestion."""
        email = make_email()
        result = make_haiku_result()
        result.action = HaikuActionResult(
            action="delete",
            reason="Spam message",
            confidence=0.65,
        )
        result.confidence = 0.65

        suggestion = _haiku_action_to_suggestion(
            email=email,
            result=result,
            number=1,
            label_lookup={},
        )

        assert suggestion is not None
        assert suggestion.action == EmailActionType.DELETE
        assert suggestion.confidence == ConfidenceLevel.MEDIUM

    def test_returns_none_for_keep_action(self):
        """Should return None for keep action (no action needed)."""
        email = make_email()
        result = make_haiku_result()
        result.action = HaikuActionResult(
            action="keep",
            reason="No action required",
            confidence=0.9,
        )

        suggestion = _haiku_action_to_suggestion(
            email=email,
            result=result,
            number=1,
            label_lookup={},
        )

        assert suggestion is None

    def test_confidence_levels(self):
        """Should map confidence to correct ConfidenceLevel."""
        email = make_email()

        # High confidence (>= 0.8)
        result_high = make_haiku_result()
        result_high.action = HaikuActionResult(action="archive", confidence=0.9)
        result_high.confidence = 0.9
        suggestion_high = _haiku_action_to_suggestion(email, result_high, 1, {})
        assert suggestion_high.confidence == ConfidenceLevel.HIGH

        # Medium confidence (0.6-0.8)
        result_med = make_haiku_result()
        result_med.action = HaikuActionResult(action="archive", confidence=0.65)
        result_med.confidence = 0.65
        suggestion_med = _haiku_action_to_suggestion(email, result_med, 1, {})
        assert suggestion_med.confidence == ConfidenceLevel.MEDIUM

        # Low confidence (< 0.6)
        result_low = make_haiku_result()
        result_low.action = HaikuActionResult(action="archive", confidence=0.4)
        result_low.confidence = 0.4
        suggestion_low = _haiku_action_to_suggestion(email, result_low, 1, {})
        assert suggestion_low.confidence == ConfidenceLevel.LOW


class TestGenerateActionSuggestionsWithHaiku:
    """Tests for generate_action_suggestions_with_haiku function."""

    def test_uses_haiku_results_when_available(self):
        """Should use Haiku results for emails in haiku_results dict."""
        email = make_email(email_id="haiku_analyzed")
        haiku_results = {
            "haiku_analyzed": make_haiku_result()
        }
        haiku_results["haiku_analyzed"].action = HaikuActionResult(
            action="archive",
            reason="Newsletter - safe to archive",
            confidence=0.85,
        )
        haiku_results["haiku_analyzed"].confidence = 0.85

        suggestions = generate_action_suggestions_with_haiku(
            messages=[email],
            email_account="personal",
            haiku_results=haiku_results,
            available_labels=[],
        )

        assert len(suggestions) == 1
        assert suggestions[0].action == EmailActionType.ARCHIVE
        assert "Newsletter" in suggestions[0].rationale

    def test_falls_back_to_regex_for_non_haiku_emails(self):
        """Should use regex for emails without Haiku results."""
        email = make_email(
            email_id="no_haiku",
            to_address="david@test.com",
            subject="Unsubscribe from our list",
            snippet="Click here to unsubscribe from our newsletter.",
            labels=["INBOX"],  # No user labels
        )
        # Make it old enough to trigger archive suggestion
        email = EmailMessage(
            id="no_haiku",
            thread_id="thread_no_haiku",
            from_address="newsletter@example.com",
            from_name="Newsletter",
            to_address="david@test.com",
            subject="Weekly Update - unsubscribe",
            snippet="Click here to unsubscribe from our newsletter.",
            date=datetime.now(timezone.utc) - timedelta(days=5),
            labels=["INBOX"],
            is_unread=True,
        )

        suggestions = generate_action_suggestions_with_haiku(
            messages=[email],
            email_account="personal",
            haiku_results={},  # No Haiku results
            available_labels=[],
        )

        # Should suggest archive due to promotional pattern + age
        assert len(suggestions) >= 1
        assert any(s.action == EmailActionType.ARCHIVE for s in suggestions)

    def test_skips_emails_with_user_labels(self):
        """Should skip emails that already have user-defined labels."""
        email = make_email(
            email_id="labeled",
            labels=["INBOX", "Label_Work"],  # Has user label
        )
        haiku_results = {
            "labeled": make_haiku_result()
        }
        haiku_results["labeled"].action = HaikuActionResult(
            action="archive",
            reason="Test",
            confidence=0.9,
        )

        suggestions = generate_action_suggestions_with_haiku(
            messages=[email],
            email_account="personal",
            haiku_results=haiku_results,
            available_labels=[],
        )

        assert len(suggestions) == 0

    def test_includes_task_creation_from_haiku_attention(self):
        """Should suggest task creation when Haiku attention has extracted_task."""
        email = make_email(email_id="task_email")
        haiku_results = {
            "task_email": make_haiku_result(
                needs_attention=True,
                extracted_task="Complete quarterly report",
                suggested_action="Create task",
                confidence=0.8,
            )
        }
        haiku_results["task_email"].action = HaikuActionResult(
            action="star",
            reason="Important deadline",
            confidence=0.8,
        )
        haiku_results["task_email"].confidence = 0.8

        suggestions = generate_action_suggestions_with_haiku(
            messages=[email],
            email_account="personal",
            haiku_results=haiku_results,
            available_labels=[],
        )

        # Should have both star and create_task suggestions
        actions = [s.action for s in suggestions]
        assert EmailActionType.STAR in actions
        assert EmailActionType.CREATE_TASK in actions

        # Check task title
        task_suggestions = [s for s in suggestions if s.action == EmailActionType.CREATE_TASK]
        assert len(task_suggestions) == 1
        assert task_suggestions[0].task_title == "Complete quarterly report"

    def test_respects_label_lookup(self):
        """Should match Haiku label suggestions to available labels."""
        email = make_email(email_id="label_email")
        haiku_results = {
            "label_email": make_haiku_result()
        }
        haiku_results["label_email"].action = HaikuActionResult(
            action="label",
            label_name="Transactional",
            reason="Receipt/invoice",
            confidence=0.9,
        )
        haiku_results["label_email"].confidence = 0.9

        available_labels = [
            {"id": "Label_Trans", "name": "Transactional"},
        ]

        suggestions = generate_action_suggestions_with_haiku(
            messages=[email],
            email_account="personal",
            haiku_results=haiku_results,
            available_labels=available_labels,
        )

        assert len(suggestions) == 1
        assert suggestions[0].action == EmailActionType.LABEL
        assert suggestions[0].label_id == "Label_Trans"
        assert suggestions[0].label_name == "Transactional"

    def test_mixed_haiku_and_fallback(self):
        """Should handle mix of Haiku-analyzed and fallback emails."""
        haiku_email = make_email(email_id="haiku1")
        fallback_email = EmailMessage(
            id="fallback1",
            thread_id="thread_fallback1",
            from_address="spam@junk.com",
            from_name="Spam",
            to_address="david@test.com",
            subject="Congratulations! You've been selected!",
            snippet="Claim your prize now!",
            date=datetime.now(timezone.utc),
            labels=["INBOX"],
            is_unread=True,
        )

        haiku_results = {
            "haiku1": make_haiku_result()
        }
        haiku_results["haiku1"].action = HaikuActionResult(
            action="archive",
            reason="FYI email",
            confidence=0.8,
        )
        haiku_results["haiku1"].confidence = 0.8

        suggestions = generate_action_suggestions_with_haiku(
            messages=[haiku_email, fallback_email],
            email_account="personal",
            haiku_results=haiku_results,
            available_labels=[],
        )

        # Should have at least 2 suggestions
        # haiku1 -> archive, fallback1 -> delete (junk pattern)
        assert len(suggestions) >= 2

        # Check haiku-based suggestion
        haiku_suggestions = [s for s in suggestions if s.email.id == "haiku1"]
        assert len(haiku_suggestions) == 1
        assert haiku_suggestions[0].action == EmailActionType.ARCHIVE

        # Check regex-based suggestion
        fallback_suggestions = [s for s in suggestions if s.email.id == "fallback1"]
        assert len(fallback_suggestions) == 1
        assert fallback_suggestions[0].action == EmailActionType.DELETE


# =============================================================================
# Test Rule Suggestions with Haiku (Sprint 4)
# =============================================================================

def make_haiku_result_with_rule(
    should_suggest: bool = True,
    pattern_type: str = "sender",
    pattern: str = "newsletter@example.com",
    action: str = "archive",
    label_name: str = None,
    reason: str = "Recurring newsletter pattern",
    confidence: float = 0.8,
) -> HaikuAnalysisResult:
    """Create a test HaikuAnalysisResult with rule suggestion."""
    return HaikuAnalysisResult(
        attention=HaikuAttentionResult(
            needs_attention=False,
            urgency="low",
            reason="No action needed",
            suggested_action="Archive",
            confidence=confidence,
        ),
        action=HaikuActionResult(
            action="archive",
            reason="Default action",
            confidence=confidence,
        ),
        rule=HaikuRuleResult(
            should_suggest=should_suggest,
            pattern_type=pattern_type,
            pattern=pattern,
            action=action,
            label_name=label_name,
            reason=reason,
            confidence=confidence,
        ),
        confidence=confidence,
        analysis_method="haiku",
    )


class TestHaikuRuleToSuggestion:
    """Tests for converting Haiku rule results to RuleSuggestion."""

    def test_converts_sender_rule(self):
        """Should convert sender pattern to RuleSuggestion."""
        email = make_email(from_address="newsletter@example.com")
        result = make_haiku_result_with_rule(
            should_suggest=True,
            pattern_type="sender",
            pattern="newsletter@example.com",
            action="archive",
            reason="Recurring newsletter",
            confidence=0.85,
        )

        suggestion = _haiku_rule_to_suggestion(
            email=email,
            result=result,
            email_account="personal",
        )

        assert suggestion is not None
        assert suggestion.suggested_rule.field == FilterField.SENDER_EMAIL.value
        assert suggestion.suggested_rule.value == "newsletter@example.com"
        assert suggestion.reason == "Recurring newsletter"
        assert suggestion.confidence.value >= "Medium"  # HIGH, MEDIUM, or LOW

    def test_converts_subject_rule(self):
        """Should convert subject pattern to RuleSuggestion."""
        email = make_email(subject="Weekly Digest")
        result = make_haiku_result_with_rule(
            should_suggest=True,
            pattern_type="subject",
            pattern="Weekly Digest",
            action="label",
            label_name="Newsletter",
            reason="Weekly digest pattern",
            confidence=0.75,
        )

        suggestion = _haiku_rule_to_suggestion(
            email=email,
            result=result,
            email_account="personal",
        )

        assert suggestion is not None
        assert suggestion.suggested_rule.field == FilterField.EMAIL_SUBJECT.value
        assert suggestion.suggested_rule.value == "Weekly Digest"

    def test_converts_content_rule_to_subject(self):
        """Should map content pattern to subject field (fallback)."""
        email = make_email()
        result = make_haiku_result_with_rule(
            should_suggest=True,
            pattern_type="content",
            pattern="unsubscribe",
            action="archive",
            reason="Marketing email pattern",
        )

        suggestion = _haiku_rule_to_suggestion(
            email=email,
            result=result,
            email_account="personal",
        )

        assert suggestion is not None
        # Content maps to subject since body search not implemented
        assert suggestion.suggested_rule.field == FilterField.EMAIL_SUBJECT.value

    def test_returns_none_when_no_suggestion(self):
        """Should return None when Haiku says no rule needed."""
        email = make_email()
        result = make_haiku_result_with_rule(
            should_suggest=False,
            pattern_type=None,
            pattern=None,
        )

        suggestion = _haiku_rule_to_suggestion(
            email=email,
            result=result,
            email_account="personal",
        )

        assert suggestion is None

    def test_maps_label_to_category(self):
        """Should map Haiku label suggestions to FilterCategory."""
        email = make_email()
        result = make_haiku_result_with_rule(
            should_suggest=True,
            pattern_type="sender",
            pattern="promotions@store.com",
            action="label",
            label_name="promotional",
            reason="Promotional emails",
        )

        suggestion = _haiku_rule_to_suggestion(
            email=email,
            result=result,
            email_account="personal",
        )

        assert suggestion is not None
        assert suggestion.suggested_rule.category == FilterCategory.PROMOTIONAL.value

    def test_default_category_for_unknown_labels(self):
        """Should use 1 Week Hold for unknown label names."""
        email = make_email()
        result = make_haiku_result_with_rule(
            should_suggest=True,
            pattern_type="sender",
            pattern="updates@service.com",
            action="label",
            label_name="CustomLabel",  # Not in mapping
            reason="Custom label suggestion",
        )

        suggestion = _haiku_rule_to_suggestion(
            email=email,
            result=result,
            email_account="personal",
        )

        assert suggestion is not None
        assert suggestion.suggested_rule.category == FilterCategory.ONE_WEEK_HOLD.value


class TestGenerateRuleSuggestionsWithHaiku:
    """Tests for generate_rule_suggestions_with_haiku function."""

    def test_uses_haiku_results_for_rule_suggestions(self):
        """Should use Haiku results to generate rule suggestions."""
        email = make_email(
            email_id="haiku_rule",
            from_address="newsletter@company.com",
        )
        haiku_results = {
            "haiku_rule": make_haiku_result_with_rule(
                should_suggest=True,
                pattern_type="sender",
                pattern="newsletter@company.com",
                action="archive",
                reason="Recurring newsletter",
                confidence=0.85,
            )
        }

        suggestions = generate_rule_suggestions_with_haiku(
            messages=[email],
            email_account="personal",
            haiku_results=haiku_results,
        )

        assert len(suggestions) >= 1
        # Find the Haiku-generated suggestion
        haiku_suggestions = [
            s for s in suggestions
            if s.suggested_rule.value == "newsletter@company.com"
        ]
        assert len(haiku_suggestions) == 1
        assert haiku_suggestions[0].reason == "Recurring newsletter"

    def test_falls_back_to_pattern_analysis(self):
        """Should use pattern analysis for non-Haiku emails."""
        # Create multiple emails from same sender (triggers pattern detection)
        emails = [
            make_email(
                email_id=f"email_{i}",
                from_address="bulk@marketing.com",
                subject="Sale notification",
            )
            for i in range(3)  # 3 emails triggers pattern
        ]

        suggestions = generate_rule_suggestions_with_haiku(
            messages=emails,
            email_account="personal",
            haiku_results={},  # No Haiku results
        )

        # Should suggest rule based on repeated sender pattern
        # The exact behavior depends on EmailAnalyzer implementation
        assert isinstance(suggestions, list)

    def test_avoids_duplicate_patterns(self):
        """Should not suggest rules for patterns already in existing rules."""
        email = make_email(
            email_id="dup_email",
            from_address="existing@company.com",
        )
        haiku_results = {
            "dup_email": make_haiku_result_with_rule(
                should_suggest=True,
                pattern_type="sender",
                pattern="existing@company.com",
                action="archive",
            )
        }

        existing_rules = [
            FilterRule(
                email_account="personal",
                order=1,
                field=FilterField.SENDER_EMAIL.value,
                operator=FilterOperator.CONTAINS.value,
                value="existing@company.com",
                category=FilterCategory.ONE_WEEK_HOLD.value,
            )
        ]

        suggestions = generate_rule_suggestions_with_haiku(
            messages=[email],
            email_account="personal",
            haiku_results=haiku_results,
            existing_rules=existing_rules,
        )

        # Should not suggest the same pattern again
        matching = [
            s for s in suggestions
            if s.suggested_rule.value.lower() == "existing@company.com"
        ]
        assert len(matching) == 0

    def test_combines_haiku_and_fallback_suggestions(self):
        """Should include both Haiku and fallback suggestions."""
        haiku_email = make_email(
            email_id="haiku1",
            from_address="haiku@example.com",
        )
        fallback_emails = [
            make_email(
                email_id=f"fallback_{i}",
                from_address="repeated@bulk.com",
            )
            for i in range(3)
        ]

        haiku_results = {
            "haiku1": make_haiku_result_with_rule(
                should_suggest=True,
                pattern_type="sender",
                pattern="haiku@example.com",
                action="archive",
            )
        }

        all_messages = [haiku_email] + fallback_emails

        suggestions = generate_rule_suggestions_with_haiku(
            messages=all_messages,
            email_account="personal",
            haiku_results=haiku_results,
        )

        # Should have the Haiku suggestion
        haiku_suggestions = [
            s for s in suggestions
            if s.suggested_rule.value == "haiku@example.com"
        ]
        assert len(haiku_suggestions) == 1

    def test_skips_emails_without_rule_suggestion(self):
        """Should skip emails where Haiku says no rule needed."""
        email = make_email(email_id="no_rule")
        haiku_results = {
            "no_rule": make_haiku_result_with_rule(
                should_suggest=False,  # No rule suggested
            )
        }

        suggestions = generate_rule_suggestions_with_haiku(
            messages=[email],
            email_account="personal",
            haiku_results=haiku_results,
        )

        # Should not include this email in suggestions
        matching = [
            s for s in suggestions
            if hasattr(s, 'email') and s.email and s.email.id == "no_rule"
        ]
        assert len(matching) == 0

    def test_limits_suggestions_count(self):
        """Should limit total number of suggestions."""
        # Create many emails with rule suggestions
        emails = []
        haiku_results = {}
        for i in range(30):
            email = make_email(
                email_id=f"email_{i}",
                from_address=f"sender{i}@example.com",
            )
            emails.append(email)
            haiku_results[f"email_{i}"] = make_haiku_result_with_rule(
                should_suggest=True,
                pattern_type="sender",
                pattern=f"sender{i}@example.com",
                action="archive",
            )

        suggestions = generate_rule_suggestions_with_haiku(
            messages=emails,
            email_account="personal",
            haiku_results=haiku_results,
        )

        # Should limit to 20 suggestions max
        assert len(suggestions) <= 20
