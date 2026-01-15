"""Email Privacy Controls - 3-tier system for DATA body access.

This module provides privacy controls that determine whether DATA can see
the full body of an email. The 3-tier system provides layered defense:

Tier 1: Sender Blocklist (Immediate block)
    - User-managed list of sender emails in profile
    - Check: sender email in blocklist -> BLOCKED
    - Example: block statements@chase.com, allow promotions@chase.com

Tier 2: Gmail "Sensitive" Label (User-controlled)
    - User applies "Sensitive" label in Gmail
    - Check: email has label -> BLOCKED
    - Can be auto-applied via Gmail filter rules

Tier 3: Haiku Pre-screening (AI detection)
    - During regular analysis, Haiku flags PII
    - Check: content was sanitized -> BLOCKED
    - Suggests adding sender to blocklist

When blocked, DATA still sees:
    - Subject line
    - Sender email and name
    - Date
    - Haiku-generated summary (if available, from attention/suggestion)

The user can grant one-time access via "Share with DATA" button.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Literal, Optional, Tuple

from ..memory.profile import is_sender_blocked, get_sender_blocklist
from .haiku_analyzer import (
    sanitize_content,
    PrivacySanitizeResult,
)
# Note: is_sensitive_domain removed (Jan 2026) - use blocklist instead


# The Gmail label that indicates user-marked sensitive email
SENSITIVE_LABEL_NAME = "Sensitive"

# Alternate label IDs that might be used (case variations)
SENSITIVE_LABEL_VARIANTS = frozenset([
    "Sensitive",
    "SENSITIVE",
    "sensitive",
    "Label_Sensitive",
])


BlockReason = Literal[
    "sender_blocked",      # Tier 1: User blocked this sender
    "label_sensitive",     # Tier 2: Gmail "Sensitive" label
    "domain_sensitive",    # DEPRECATED (Jan 2026): No longer used
    "pii_detected",        # Tier 3b: Haiku detected PII patterns
]


@dataclass
class PrivacyCheckResult:
    """Result of privacy check for an email.

    Attributes:
        can_see_body: Whether DATA is allowed to see the email body
        blocked_reason: Why body access is blocked (if blocked)
        blocked_reason_display: Human-readable reason for UI
        haiku_summary: AI-generated summary if available (for fallback)
        pii_detected: List of PII types detected (if any)
        override_granted: Whether user granted one-time access
    """
    can_see_body: bool
    blocked_reason: Optional[BlockReason] = None
    blocked_reason_display: Optional[str] = None
    haiku_summary: Optional[str] = None
    pii_detected: List[str] = None
    override_granted: bool = False

    def __post_init__(self):
        if self.pii_detected is None:
            self.pii_detected = []

    def to_api_dict(self) -> Dict[str, Any]:
        """Convert to API-friendly dict (camelCase)."""
        return {
            "canSeeBody": self.can_see_body,
            "blockedReason": self.blocked_reason,
            "blockedReasonDisplay": self.blocked_reason_display,
            "haikuSummary": self.haiku_summary,
            "piiDetected": self.pii_detected,
            "overrideGranted": self.override_granted,
        }


def check_email_privacy(
    from_address: str,
    labels: Optional[List[str]] = None,
    body: Optional[str] = None,
    subject: Optional[str] = None,
    snippet: Optional[str] = None,
    haiku_summary: Optional[str] = None,
    override_granted: bool = False,
) -> PrivacyCheckResult:
    """Check if DATA can see the email body.

    Implements the 3-tier privacy system:
    1. Sender blocklist (user-managed in profile)
    2. Gmail "Sensitive" label
    3. Domain/PII detection from Haiku safeguards

    Args:
        from_address: Sender email address
        labels: List of Gmail label names/IDs
        body: Email body (for PII scan if not blocked earlier)
        subject: Email subject (for PII scan)
        snippet: Email snippet (for PII scan)
        haiku_summary: Pre-computed Haiku summary (for fallback display)
        override_granted: User granted one-time access

    Returns:
        PrivacyCheckResult indicating whether DATA can see body
    """
    # If override granted, allow access
    if override_granted:
        return PrivacyCheckResult(
            can_see_body=True,
            override_granted=True,
            haiku_summary=haiku_summary,
        )

    # Tier 1: Check sender blocklist (sender email level)
    if is_sender_blocked(from_address):
        return PrivacyCheckResult(
            can_see_body=False,
            blocked_reason="sender_blocked",
            blocked_reason_display=f"Sender is blocked: {from_address}",
            haiku_summary=haiku_summary,
        )

    # Tier 2: Check Gmail "Sensitive" label
    if labels:
        for label in labels:
            # Check both label name and potential label IDs
            if label in SENSITIVE_LABEL_VARIANTS:
                return PrivacyCheckResult(
                    can_see_body=False,
                    blocked_reason="label_sensitive",
                    blocked_reason_display="Email marked as sensitive",
                    haiku_summary=haiku_summary,
                )
            # Also check if it's a user label containing "sensitive"
            if "sensitive" in label.lower():
                return PrivacyCheckResult(
                    can_see_body=False,
                    blocked_reason="label_sensitive",
                    blocked_reason_display="Email marked as sensitive",
                    haiku_summary=haiku_summary,
                )

    # Tier 3a: Domain blocklist - DEPRECATED (Jan 2026)
    # Hardcoded domain list removed. Users manage sensitive senders via:
    # - Tier 1: Profile blocklist (specific sender emails)
    # - Tier 2: Gmail "Sensitive" label (user-applied or via Gmail filters)
    # is_sensitive_domain() now always returns False, check removed.

    # Tier 3b: Check content for PII patterns
    pii_detected = []
    if body:
        body_result = sanitize_content(body)
        if body_result.was_modified:
            pii_detected.extend(body_result.masked_patterns)

    if subject:
        subject_result = sanitize_content(subject)
        if subject_result.was_modified:
            pii_detected.extend(subject_result.masked_patterns)

    if snippet and not body:  # Only check snippet if no body
        snippet_result = sanitize_content(snippet)
        if snippet_result.was_modified:
            pii_detected.extend(snippet_result.masked_patterns)

    # Deduplicate PII types
    pii_detected = list(set(pii_detected))

    if pii_detected:
        return PrivacyCheckResult(
            can_see_body=False,
            blocked_reason="pii_detected",
            blocked_reason_display="Potential PII detected",
            haiku_summary=haiku_summary,
            pii_detected=pii_detected,
        )

    # All checks passed - DATA can see body
    return PrivacyCheckResult(
        can_see_body=True,
        haiku_summary=haiku_summary,
    )


def can_data_see_email(
    from_address: str,
    labels: Optional[List[str]] = None,
    body: Optional[str] = None,
    subject: Optional[str] = None,
    snippet: Optional[str] = None,
    haiku_summary: Optional[str] = None,
    override_granted: bool = False,
) -> Tuple[bool, str]:
    """Simplified check returning (can_see, reason) tuple.

    Convenience wrapper around check_email_privacy for simple boolean check.

    Args:
        from_address: Sender email address
        labels: List of Gmail label names/IDs
        body: Email body (for PII scan)
        subject: Email subject (for PII scan)
        snippet: Email snippet (for PII scan)
        haiku_summary: Pre-computed Haiku summary
        override_granted: User granted one-time access

    Returns:
        Tuple of (can_see: bool, reason: str)
        If can_see is True, reason will be empty string
    """
    result = check_email_privacy(
        from_address=from_address,
        labels=labels,
        body=body,
        subject=subject,
        snippet=snippet,
        haiku_summary=haiku_summary,
        override_granted=override_granted,
    )

    if result.can_see_body:
        return (True, "")
    return (False, result.blocked_reason_display or "Access blocked")


def build_email_context_for_data(
    email_id: str,
    thread_id: str,
    from_address: str,
    from_name: Optional[str],
    subject: str,
    date: str,
    snippet: str,
    body: Optional[str] = None,
    labels: Optional[List[str]] = None,
    haiku_summary: Optional[str] = None,
    override_granted: bool = False,
) -> Dict[str, Any]:
    """Build context dict for DATA conversation.

    Applies privacy checks and returns appropriate context
    based on whether DATA can see the full body.

    Args:
        email_id: Gmail message ID
        thread_id: Gmail thread ID
        from_address: Sender email
        from_name: Sender display name
        subject: Email subject
        date: Email date string
        snippet: Email preview snippet
        body: Full email body (optional)
        labels: Gmail labels
        haiku_summary: Pre-computed Haiku summary
        override_granted: User granted one-time access

    Returns:
        Context dict with privacy-aware content:
        {
            "emailId": str,
            "threadId": str,
            "subject": str,
            "from": str,
            "date": str,
            "snippet": str,
            "body": Optional[str],  # Only if allowed or override
            "bodyAvailable": bool,
            "blockedReason": Optional[str],
            "haikuSummary": Optional[str],  # Fallback if blocked
        }
    """
    # Run privacy check
    privacy_result = check_email_privacy(
        from_address=from_address,
        labels=labels,
        body=body,
        subject=subject,
        snippet=snippet,
        haiku_summary=haiku_summary,
        override_granted=override_granted,
    )

    # Format "from" field
    from_display = f"{from_name} <{from_address}>" if from_name else from_address

    # Build context
    context = {
        "emailId": email_id,
        "threadId": thread_id,
        "subject": subject,
        "from": from_display,
        "date": date,
        "snippet": snippet,
        "body": body if privacy_result.can_see_body else None,
        "bodyAvailable": privacy_result.can_see_body,
        "blockedReason": privacy_result.blocked_reason_display,
        "haikuSummary": haiku_summary,
        "overrideGranted": privacy_result.override_granted,
    }

    return context


def get_privacy_summary_for_email(
    from_address: str,
    labels: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Get a quick privacy status for an email (without body check).

    Useful for UI display to show privacy indicators before loading body.

    Privacy is now controlled by:
    - Tier 1: User-managed sender blocklist (Profile)
    - Tier 2: Gmail "Sensitive" label (user-applied or via Gmail filters)

    Note: Domain-based blocking was deprecated in Jan 2026.
    Users should add specific senders to blocklist instead.

    Args:
        from_address: Sender email address
        labels: Gmail label names/IDs

    Returns:
        Summary dict with privacy indicators
    """
    sender_blocked = is_sender_blocked(from_address)

    label_sensitive = False
    if labels:
        for label in labels:
            if label in SENSITIVE_LABEL_VARIANTS or "sensitive" in label.lower():
                label_sensitive = True
                break

    # Domain-sensitive removed - user manages via blocklist now
    is_blocked = sender_blocked or label_sensitive

    reason = None
    if sender_blocked:
        reason = "sender_blocked"
    elif label_sensitive:
        reason = "label_sensitive"

    return {
        "isBlocked": is_blocked,
        "reason": reason,
        "senderBlocked": sender_blocked,
        "domainSensitive": False,  # DEPRECATED: Always False, use blocklist instead
        "labelSensitive": label_sensitive,
        "canRequestOverride": is_blocked,  # User can always request override if blocked
    }
