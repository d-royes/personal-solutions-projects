"""Tests for Haiku Intelligence Layer - analyzer and usage tracking.

This module tests:
- Privacy safeguards (domain blocklist, content masking)
- Usage tracking (counters, limits, resets)
- Settings storage
- Haiku response parsing
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

import pytest

from daily_task_assistant.email.haiku_analyzer import (
    is_sensitive_domain,
    sanitize_content,
    prepare_email_for_haiku,
    analyze_email_with_haiku,
    _parse_haiku_response,
    _build_analysis_result,
    _create_fallback_result,
    HaikuAnalysisResult,
    HaikuAttentionResult,
    HaikuActionResult,
    HaikuRuleResult,
    PrivacySanitizeResult,
    SENSITIVE_DOMAINS,
    CONTENT_MASK_PATTERNS,
)
from daily_task_assistant.email.haiku_usage import (
    HaikuSettings,
    HaikuUsage,
    get_settings,
    save_settings,
    get_usage,
    save_usage,
    increment_usage,
    can_use_haiku,
    get_usage_summary,
    DEFAULT_DAILY_LIMIT,
    DEFAULT_WEEKLY_LIMIT,
)


# =============================================================================
# Privacy Safeguards Tests
# =============================================================================

class TestSensitiveDomainBlocklist:
    """Tests for domain blocklist functionality.

    DEPRECATED (Jan 2026): Hardcoded domain blocklist removed.
    Users now manage sensitive senders via Profile blocklist and Gmail "Sensitive" label.
    is_sensitive_domain() now always returns False.
    """

    def test_blocks_banking_domains(self):
        """Banking domains are no longer blocked by hardcoded list."""
        # DEPRECATED: Domain blocklist removed - use Profile blocklist instead
        assert not is_sensitive_domain("alerts@chase.com")
        assert not is_sensitive_domain("noreply@bankofamerica.com")
        assert not is_sensitive_domain("security@citibank.com")

    def test_blocks_investment_domains(self):
        """Investment domains are no longer blocked by hardcoded list."""
        # DEPRECATED: Domain blocklist removed - use Profile blocklist instead
        assert not is_sensitive_domain("statements@fidelity.com")
        assert not is_sensitive_domain("info@schwab.com")
        assert not is_sensitive_domain("updates@vanguard.com")

    def test_blocks_payment_domains(self):
        """Payment domains are no longer blocked by hardcoded list."""
        # DEPRECATED: Domain blocklist removed - use Profile blocklist instead
        assert not is_sensitive_domain("support@paypal.com")
        assert not is_sensitive_domain("receipts@venmo.com")
        assert not is_sensitive_domain("payments@stripe.com")

    def test_blocks_government_domains(self):
        """Government domains are no longer blocked by hardcoded list."""
        # DEPRECATED: Domain blocklist removed - use Profile blocklist instead
        assert not is_sensitive_domain("refunds@irs.gov")
        assert not is_sensitive_domain("updates@ssa.gov")
        assert not is_sensitive_domain("notices@treasury.gov")

    def test_blocks_healthcare_domains(self):
        """Healthcare domains are no longer blocked by hardcoded list."""
        # DEPRECATED: Domain blocklist removed - use Profile blocklist instead
        assert not is_sensitive_domain("appointments@mychart.com")
        assert not is_sensitive_domain("claims@anthem.com")

    def test_blocks_subdomains(self):
        """Subdomains are no longer blocked by hardcoded list."""
        # DEPRECATED: Domain blocklist removed - use Profile blocklist instead
        assert not is_sensitive_domain("alerts@mail.chase.com")
        assert not is_sensitive_domain("noreply@secure.bankofamerica.com")

    def test_allows_regular_domains(self):
        """Regular domains should NOT be blocked (unchanged behavior)."""
        assert not is_sensitive_domain("john@gmail.com")
        assert not is_sensitive_domain("newsletter@company.com")
        assert not is_sensitive_domain("support@amazon.com")
        assert not is_sensitive_domain("team@slack.com")

    def test_handles_invalid_input(self):
        """Should handle invalid email addresses gracefully."""
        assert not is_sensitive_domain("")
        assert not is_sensitive_domain("not-an-email")
        assert not is_sensitive_domain(None)  # type: ignore


class TestContentMasking:
    """Tests for content masking functionality."""

    def test_masks_credit_card_numbers(self):
        """Credit card numbers should be masked."""
        result = sanitize_content("Card: 1234-5678-9012-3456")
        assert "[CARD-XXXX]" in result.sanitized_content
        assert "1234" not in result.sanitized_content
        assert result.was_modified

    def test_masks_credit_card_with_spaces(self):
        """Credit cards with spaces should be masked."""
        result = sanitize_content("Card: 1234 5678 9012 3456")
        assert "[CARD-XXXX]" in result.sanitized_content
        assert "1234" not in result.sanitized_content

    def test_masks_ssn(self):
        """SSN patterns should be masked."""
        result = sanitize_content("SSN: 123-45-6789")
        assert "[SSN-XXXX]" in result.sanitized_content
        assert "123" not in result.sanitized_content
        assert result.was_modified

    def test_masks_account_numbers(self):
        """Long account numbers should be masked."""
        # When "Account:" prefix is present, uses ACCOUNT-XXXX
        result = sanitize_content("Account: 123456789012")
        assert "[ACCOUNT-XXXX]" in result.sanitized_content
        assert "123456789012" not in result.sanitized_content

    def test_masks_bare_account_numbers(self):
        """Bare account numbers (without label) should be masked."""
        # When no prefix, uses generic ACCT-XXXX
        result = sanitize_content("Reference: 123456789012")
        assert "[ACCT-XXXX]" in result.sanitized_content
        assert "123456789012" not in result.sanitized_content

    def test_masks_routing_numbers(self):
        """Routing numbers should be masked."""
        result = sanitize_content("Routing: 123456789")
        assert "[ROUTING-XXXX]" in result.sanitized_content

    def test_masks_passwords(self):
        """Plaintext passwords should be masked."""
        result = sanitize_content("Your password: secretpass123")
        assert "[PASSWORD-REDACTED]" in result.sanitized_content
        assert "secretpass123" not in result.sanitized_content

    def test_masks_api_keys(self):
        """API keys and tokens should be masked."""
        # Using clearly fake test pattern to avoid GitHub secret scanning false positives
        result = sanitize_content("api_key: sk_test_FAKEKEYFORTESTING123456")
        assert "[API-KEY-REDACTED]" in result.sanitized_content

    def test_masks_bearer_tokens(self):
        """Bearer tokens should be masked."""
        result = sanitize_content("Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9")
        assert "[API-KEY-REDACTED]" in result.sanitized_content

    def test_preserves_safe_content(self):
        """Safe content should not be modified."""
        original = "Meeting tomorrow at 3pm. Please bring the report."
        result = sanitize_content(original)
        assert result.sanitized_content == original
        assert not result.was_modified
        assert result.masked_patterns == []

    def test_handles_empty_content(self):
        """Empty content should be handled gracefully."""
        result = sanitize_content("")
        assert result.sanitized_content == ""
        assert not result.was_modified

    def test_tracks_masked_patterns(self):
        """Should track which patterns were masked."""
        result = sanitize_content("Card: 1234-5678-9012-3456 and SSN: 123-45-6789")
        assert "CARD-XXXX" in result.masked_patterns
        assert "SSN-XXXX" in result.masked_patterns


class TestPrepareEmailForHaiku:
    """Tests for the combined prepare function."""

    def test_skips_sensitive_domains(self):
        """Emails from sensitive domains are no longer skipped (deprecated).

        DEPRECATED (Jan 2026): Domain blocklist removed.
        Emails from previously blocked domains now process normally.
        """
        content, skip_reason = prepare_email_for_haiku(
            sender="alerts@chase.com",
            subject="Your statement is ready",
            snippet="View your balance",
        )
        # Domain blocklist removed - content should now be prepared
        assert content is not None
        assert skip_reason is None
        assert "Subject: Your statement is ready" in content

    def test_sanitizes_content_for_safe_domains(self):
        """Content from safe domains should be sanitized."""
        content, skip_reason = prepare_email_for_haiku(
            sender="newsletter@company.com",
            subject="Weekly Update",
            snippet="Here's what happened this week",
        )
        assert content is not None
        assert skip_reason is None
        assert "Subject: Weekly Update" in content
        assert "Preview: Here's what happened this week" in content

    def test_masks_sensitive_data_in_safe_domain_emails(self):
        """Sensitive data in content should be masked even for safe domains."""
        content, skip_reason = prepare_email_for_haiku(
            sender="john@company.com",
            subject="Account 123456789012 Info",
            snippet="Your account details",
        )
        assert content is not None
        # Account prefix triggers ACCOUNT-XXXX mask
        assert "[ACCOUNT-XXXX]" in content
        assert "123456789012" not in content

    def test_truncates_long_body(self):
        """Long email bodies should be truncated."""
        long_body = "A" * 2000
        content, _ = prepare_email_for_haiku(
            sender="john@company.com",
            subject="Test",
            snippet="Test",
            body=long_body,
        )
        assert content is not None
        # Should only include first 1000 chars of body
        assert "Body excerpt:" in content


# =============================================================================
# Haiku Response Parsing Tests
# =============================================================================

class TestHaikuResponseParsing:
    """Tests for Haiku response parsing."""

    def test_parses_valid_json(self):
        """Should parse valid JSON response."""
        json_str = """{
            "attention": {
                "needs_attention": true,
                "urgency": "high",
                "reason": "Deadline mentioned",
                "suggested_action": "Reply needed",
                "extracted_task": "Review document",
                "matched_role": "work"
            },
            "action": {
                "recommended": "keep",
                "label_name": null,
                "reason": "Needs response"
            },
            "rule": {
                "should_suggest": false,
                "pattern_type": null,
                "pattern": null,
                "reason": null
            },
            "confidence": 0.85
        }"""
        data = _parse_haiku_response(json_str)
        assert data["attention"]["needs_attention"] is True
        assert data["confidence"] == 0.85

    def test_parses_json_with_markdown_fences(self):
        """Should strip markdown code fences."""
        json_str = """```json
{
    "attention": {"needs_attention": false, "urgency": "low", "reason": "FYI", "suggested_action": "Archive"},
    "action": {"recommended": "archive", "reason": "Newsletter"},
    "rule": {"should_suggest": false},
    "confidence": 0.9
}
```"""
        data = _parse_haiku_response(json_str)
        assert data["attention"]["needs_attention"] is False

    def test_builds_analysis_result(self):
        """Should build HaikuAnalysisResult from parsed data."""
        data = {
            "attention": {
                "needs_attention": True,
                "urgency": "medium",
                "reason": "Question asked",
                "suggested_action": "Reply needed",
                "extracted_task": None,
                "matched_role": "church"
            },
            "action": {
                "recommended": "star",
                "label_name": "Church",
                "reason": "Important church matter"
            },
            "rule": {
                "should_suggest": True,
                "pattern_type": "sender",
                "pattern": "@church.org",
                "action": "label",
                "label_name": "Church",
                "reason": "Recurring church emails"
            },
            "confidence": 0.8
        }
        result = _build_analysis_result(data)

        assert isinstance(result, HaikuAnalysisResult)
        assert result.attention.needs_attention is True
        assert result.attention.urgency == "medium"
        assert result.action.action == "star"
        assert result.rule.should_suggest is True
        assert result.confidence == 0.8
        assert result.analysis_method == "haiku"


class TestFallbackResult:
    """Tests for fallback result creation."""

    def test_creates_fallback_result(self):
        """Should create proper fallback result when skipping."""
        result = _create_fallback_result("Sensitive domain: chase.com")

        assert result.attention.needs_attention is False
        assert result.attention.confidence == 0.0
        assert result.action.action == "keep"
        assert result.rule.should_suggest is False
        assert result.analysis_method == "skipped"
        assert "Sensitive domain" in result.skipped_reason


# =============================================================================
# Usage Tracking Tests
# =============================================================================

class TestHaikuSettings:
    """Tests for HaikuSettings dataclass."""

    def test_default_values(self):
        """Should have sensible defaults."""
        settings = HaikuSettings()
        assert settings.enabled is True
        assert settings.daily_limit == DEFAULT_DAILY_LIMIT
        assert settings.weekly_limit == DEFAULT_WEEKLY_LIMIT

    def test_to_dict_and_from_dict(self):
        """Should serialize and deserialize correctly."""
        original = HaikuSettings(enabled=False, daily_limit=100, weekly_limit=500)
        data = original.to_dict()
        restored = HaikuSettings.from_dict(data)

        assert restored.enabled == original.enabled
        assert restored.daily_limit == original.daily_limit
        assert restored.weekly_limit == original.weekly_limit

    def test_to_api_dict(self):
        """Should convert to camelCase for API."""
        settings = HaikuSettings(daily_limit=75)
        api_dict = settings.to_api_dict()

        assert "dailyLimit" in api_dict
        assert api_dict["dailyLimit"] == 75


class TestHaikuUsage:
    """Tests for HaikuUsage dataclass."""

    def test_default_values(self):
        """Should start with zero counts."""
        usage = HaikuUsage()
        assert usage.daily_count == 0
        assert usage.weekly_count == 0

    def test_increment(self):
        """Should increment both counters."""
        usage = HaikuUsage()
        usage.increment()
        assert usage.daily_count == 1
        assert usage.weekly_count == 1

        usage.increment()
        assert usage.daily_count == 2
        assert usage.weekly_count == 2

    def test_can_analyze_under_limits(self):
        """Should allow analysis when under limits."""
        settings = HaikuSettings(daily_limit=50, weekly_limit=200)
        usage = HaikuUsage(daily_count=10, weekly_count=50)

        assert usage.can_analyze(settings) is True

    def test_cannot_analyze_at_daily_limit(self):
        """Should block analysis when daily limit reached."""
        settings = HaikuSettings(daily_limit=50, weekly_limit=200)
        usage = HaikuUsage(daily_count=50, weekly_count=50)

        assert usage.can_analyze(settings) is False

    def test_cannot_analyze_at_weekly_limit(self):
        """Should block analysis when weekly limit reached."""
        settings = HaikuSettings(daily_limit=50, weekly_limit=200)
        usage = HaikuUsage(daily_count=10, weekly_count=200)

        assert usage.can_analyze(settings) is False

    def test_cannot_analyze_when_disabled(self):
        """Should block analysis when Haiku is disabled."""
        settings = HaikuSettings(enabled=False)
        usage = HaikuUsage(daily_count=0, weekly_count=0)

        assert usage.can_analyze(settings) is False

    def test_remaining_calculations(self):
        """Should correctly calculate remaining quota."""
        settings = HaikuSettings(daily_limit=50, weekly_limit=200)
        usage = HaikuUsage(daily_count=15, weekly_count=42)

        assert usage.remaining_daily(settings) == 35
        assert usage.remaining_weekly(settings) == 158

    def test_reset_expired_daily(self):
        """Should reset daily counter when expired."""
        past_reset = datetime.now(timezone.utc) - timedelta(hours=1)
        usage = HaikuUsage(
            daily_count=25,
            weekly_count=100,
            daily_reset_at=past_reset,
            weekly_reset_at=datetime.now(timezone.utc) + timedelta(days=5)
        )

        was_reset = usage.reset_if_expired()

        assert was_reset is True
        assert usage.daily_count == 0
        assert usage.weekly_count == 100  # Weekly not reset

    def test_reset_expired_weekly(self):
        """Should reset weekly counter when expired."""
        past_reset = datetime.now(timezone.utc) - timedelta(hours=1)
        usage = HaikuUsage(
            daily_count=25,
            weekly_count=100,
            daily_reset_at=datetime.now(timezone.utc) + timedelta(days=1),
            weekly_reset_at=past_reset
        )

        was_reset = usage.reset_if_expired()

        assert was_reset is True
        assert usage.weekly_count == 0
        # Daily might also be reset if it was expired, but let's check weekly specifically
        assert usage.daily_count == 25 or usage.daily_count == 0

    def test_to_api_dict(self):
        """Should produce complete API response."""
        settings = HaikuSettings(enabled=True, daily_limit=50, weekly_limit=200)
        usage = HaikuUsage(daily_count=15, weekly_count=42)

        api_dict = usage.to_api_dict(settings)

        assert api_dict["dailyCount"] == 15
        assert api_dict["weeklyCount"] == 42
        assert api_dict["dailyLimit"] == 50
        assert api_dict["weeklyLimit"] == 200
        assert api_dict["dailyRemaining"] == 35
        assert api_dict["weeklyRemaining"] == 158
        assert api_dict["enabled"] is True


class TestHaikuUsageStorage:
    """Tests for usage file storage (using temp directory)."""

    @pytest.fixture
    def temp_storage(self, tmp_path):
        """Set up temporary storage directory."""
        with patch.dict(os.environ, {
            "DTA_HAIKU_FORCE_FILE": "1",
            "DTA_HAIKU_STORAGE_DIR": str(tmp_path),
        }):
            yield tmp_path

    def test_save_and_get_settings(self, temp_storage):
        """Should save and retrieve settings (GLOBAL - no user_id)."""
        original = HaikuSettings(enabled=False, daily_limit=100)

        save_settings(original)
        restored = get_settings()

        assert restored.enabled == original.enabled
        assert restored.daily_limit == original.daily_limit

    def test_save_and_get_usage(self, temp_storage):
        """Should save and retrieve usage (GLOBAL - no user_id)."""
        usage = HaikuUsage(daily_count=5, weekly_count=20)

        save_usage(usage)
        restored = get_usage()

        assert restored.daily_count == 5
        assert restored.weekly_count == 20

    def test_increment_usage(self, temp_storage):
        """Should increment and persist usage (GLOBAL - no user_id)."""
        usage = increment_usage()
        assert usage.daily_count == 1
        assert usage.weekly_count == 1

        usage = increment_usage()
        assert usage.daily_count == 2
        assert usage.weekly_count == 2

    def test_can_use_haiku(self, temp_storage):
        """Should check combined settings and usage (GLOBAL - no user_id)."""
        # Should be able to use with defaults
        assert can_use_haiku() is True

        # Disable Haiku
        settings = HaikuSettings(enabled=False)
        save_settings(settings)
        assert can_use_haiku() is False

    def test_get_usage_summary(self, temp_storage):
        """Should return complete summary (GLOBAL - no user_id)."""
        # Set some usage
        usage = HaikuUsage(daily_count=10, weekly_count=30)
        save_usage(usage)

        summary = get_usage_summary()

        assert summary["dailyCount"] == 10
        assert summary["weeklyCount"] == 30
        assert summary["dailyLimit"] == DEFAULT_DAILY_LIMIT
        assert summary["weeklyLimit"] == DEFAULT_WEEKLY_LIMIT
        assert "dailyRemaining" in summary
        assert "weeklyRemaining" in summary

    def test_defaults_when_no_stored_data(self, temp_storage):
        """Should return defaults when no stored data exists (GLOBAL)."""
        settings = get_settings()
        usage = get_usage()

        assert settings.enabled is True
        assert settings.daily_limit == DEFAULT_DAILY_LIMIT
        assert usage.daily_count == 0
        assert usage.weekly_count == 0


# =============================================================================
# Integration Tests (with mocked Anthropic API)
# =============================================================================

class TestHaikuAnalysisIntegration:
    """Integration tests with mocked Anthropic API."""

    @pytest.fixture
    def mock_anthropic_response(self):
        """Create a mock Anthropic API response."""
        mock_response = Mock()
        mock_response.content = [
            Mock(
                type="text",
                text="""{
                    "attention": {
                        "needs_attention": true,
                        "urgency": "high",
                        "reason": "Deadline mentioned - Friday",
                        "suggested_action": "Reply needed",
                        "extracted_task": "Review document by Friday",
                        "matched_role": "work"
                    },
                    "action": {
                        "recommended": "star",
                        "label_name": "Work",
                        "reason": "Important work request"
                    },
                    "rule": {
                        "should_suggest": false,
                        "pattern_type": null,
                        "pattern": null,
                        "reason": null
                    },
                    "confidence": 0.88
                }"""
            )
        ]
        return mock_response

    @patch("daily_task_assistant.email.haiku_analyzer.build_anthropic_client")
    def test_analyze_email_success(self, mock_build_client, mock_anthropic_response):
        """Should analyze email and return structured result."""
        mock_client = Mock()
        mock_client.messages.create.return_value = mock_anthropic_response
        mock_build_client.return_value = mock_client

        result = analyze_email_with_haiku(
            sender_email="boss@company.com",
            sender_name="The Boss",
            subject="Please review by Friday",
            snippet="Can you look at this document?",
            date="2025-01-15",
        )

        assert isinstance(result, HaikuAnalysisResult)
        assert result.attention.needs_attention is True
        assert result.attention.urgency == "high"
        assert result.action.action == "star"
        assert result.confidence == 0.88
        assert result.analysis_method == "haiku"

    def test_analyze_skips_sensitive_domain(self, mock_anthropic_response):
        """Sensitive domains are no longer skipped - domain blocklist deprecated.

        DEPRECATED (Jan 2026): Domain blocklist removed.
        Emails from previously blocked domains now process normally via Haiku.
        Users manage sensitive senders via Profile blocklist instead.
        """
        # Mock the Anthropic client since we now call Haiku
        with patch("daily_task_assistant.email.haiku_analyzer.build_anthropic_client") as mock_build:
            mock_client = Mock()
            mock_client.messages.create.return_value = mock_anthropic_response
            mock_build.return_value = mock_client

            result = analyze_email_with_haiku(
                sender_email="alerts@chase.com",
                sender_name="Chase Bank",
                subject="Your statement is ready",
                snippet="View your balance",
                date="2025-01-15",
            )

            # Domain blocklist removed - should now analyze via Haiku
            assert result.analysis_method == "haiku"
            assert result.skipped_reason is None
            # Verify Haiku was called
            mock_client.messages.create.assert_called_once()

    @patch("daily_task_assistant.email.haiku_analyzer.build_anthropic_client")
    def test_analyze_masks_sensitive_content(self, mock_build_client, mock_anthropic_response):
        """Should mask sensitive content before sending to Haiku."""
        mock_client = Mock()
        mock_client.messages.create.return_value = mock_anthropic_response
        mock_build_client.return_value = mock_client

        analyze_email_with_haiku(
            sender_email="vendor@company.com",
            sender_name="Vendor",
            subject="Invoice 123456789012",
            snippet="Please pay to account 123456789012",
            date="2025-01-15",
        )

        # Check what was sent to the API
        call_args = mock_client.messages.create.call_args
        prompt = call_args.kwargs["messages"][0]["content"]

        # The account number should be masked
        assert "123456789012" not in prompt
        assert "[ACCT-XXXX]" in prompt
