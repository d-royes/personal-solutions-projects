"""Email Stale Item Synchronization.

This module validates that emails referenced in attention items and suggestions
still exist in Gmail. When emails are deleted or archived, the corresponding
items become "stale" and should be auto-dismissed.

Sync Strategy: On-Refresh + On-Interaction
    - During analysis refresh: batch validate existing items
    - On user interaction (approve/dismiss): quick existence check
    - No background jobs or extra infrastructure needed

Usage:
    # During refresh cycle
    stale_ids = await validate_attention_items(account, items, gmail_config)
    for email_id in stale_ids:
        dismiss_attention(account, email_id, "handled")

    # On user interaction
    if not await email_exists(gmail_config, email_id):
        # Show toast, auto-dismiss item
        pass
"""
from __future__ import annotations

import logging
from typing import List, Optional, Set, Union

from ..mailer.gmail import GmailAccountConfig, GmailError
from ..mailer.inbox import get_message
from .attention_store import AttentionRecord, dismiss_attention
from .suggestion_store import SuggestionRecord, record_suggestion_decision


logger = logging.getLogger(__name__)


# =============================================================================
# Core Existence Checking
# =============================================================================

def email_exists(config: GmailAccountConfig, email_id: str) -> bool:
    """Check if an email still exists and is accessible in Gmail.

    Uses minimal format for efficiency (just checks existence and labels).
    Emails in TRASH or SPAM are considered "not existing" for attention purposes
    since the user has deliberately removed them from their inbox.

    Args:
        config: Gmail account configuration
        email_id: Gmail message ID

    Returns:
        True if email exists and is accessible, False if deleted/trashed/spam
    """
    try:
        # Use minimal format - fastest way to check existence
        msg = get_message(config, email_id, format="minimal")

        # Check if email is in Trash or Spam - treat as "deleted" for attention purposes
        labels = getattr(msg, "labels", []) or []
        if "TRASH" in labels:
            logger.debug(f"Email {email_id} is in Trash - treating as deleted")
            return False
        if "SPAM" in labels:
            logger.debug(f"Email {email_id} is in Spam - treating as deleted")
            return False

        return True
    except GmailError as e:
        # Check if it's a 404 (not found) vs other error
        error_str = str(e).lower()
        if "404" in error_str or "not found" in error_str:
            logger.debug(f"Email {email_id} no longer exists in Gmail")
            return False
        # For other errors (network, auth), assume email exists
        # to avoid false positives on transient failures
        logger.warning(f"Gmail API error checking email {email_id}: {e}")
        return True


def batch_check_emails(
    config: GmailAccountConfig,
    email_ids: List[str],
) -> Set[str]:
    """Check multiple emails for existence, return set of stale IDs.

    Note: Gmail API doesn't have a batch existence check endpoint,
    so we check individually. For large lists, this may be slow.

    Args:
        config: Gmail account configuration
        email_ids: List of Gmail message IDs to check

    Returns:
        Set of email IDs that no longer exist (stale)
    """
    stale_ids: Set[str] = set()

    for email_id in email_ids:
        if not email_exists(config, email_id):
            stale_ids.add(email_id)

    if stale_ids:
        logger.info(f"Found {len(stale_ids)} stale emails out of {len(email_ids)} checked")

    return stale_ids


# =============================================================================
# Attention Item Validation
# =============================================================================

def validate_attention_items(
    account: str,
    items: List[AttentionRecord],
    config: GmailAccountConfig,
) -> List[str]:
    """Validate attention items against Gmail, return list of stale email IDs.

    Called during analysis refresh to identify items that reference
    emails that no longer exist in Gmail.

    Args:
        account: Email account ("church" or "personal")
        items: List of AttentionRecords to validate
        config: Gmail account configuration

    Returns:
        List of email IDs that are stale (email no longer exists)
    """
    if not items:
        return []

    # Collect unique email IDs
    email_ids = list({item.email_id for item in items})

    logger.debug(f"Validating {len(email_ids)} unique email IDs for {account} account")

    # Check existence
    stale_ids = batch_check_emails(config, email_ids)

    return list(stale_ids)


def dismiss_stale_attention(
    account: str,
    stale_email_ids: List[str],
) -> int:
    """Dismiss attention items for stale emails.

    Args:
        account: Email account ("church" or "personal")
        stale_email_ids: List of email IDs to dismiss

    Returns:
        Count of items dismissed
    """
    count = 0
    for email_id in stale_email_ids:
        if dismiss_attention(account, email_id, "handled"):
            count += 1
            logger.debug(f"Auto-dismissed stale attention item: {email_id}")

    if count:
        logger.info(f"Auto-dismissed {count} stale attention items for {account}")

    return count


# =============================================================================
# Suggestion Item Validation
# =============================================================================

def validate_suggestion_items(
    account: str,
    items: List[SuggestionRecord],
    config: GmailAccountConfig,
) -> List[str]:
    """Validate suggestion items against Gmail, return list of stale suggestion IDs.

    Called during refresh to identify suggestions that reference
    emails that no longer exist in Gmail.

    Args:
        account: Email account ("church" or "personal")
        items: List of SuggestionRecords to validate
        config: Gmail account configuration

    Returns:
        List of suggestion IDs that are stale (email no longer exists)
    """
    if not items:
        return []

    # Build mapping of email_id -> suggestion_ids
    email_to_suggestions: dict[str, List[str]] = {}
    for item in items:
        if item.email_id not in email_to_suggestions:
            email_to_suggestions[item.email_id] = []
        email_to_suggestions[item.email_id].append(item.suggestion_id)

    # Check email existence
    email_ids = list(email_to_suggestions.keys())
    logger.debug(f"Validating {len(email_ids)} unique email IDs for {account} suggestions")

    stale_email_ids = batch_check_emails(config, email_ids)

    # Map back to suggestion IDs
    stale_suggestion_ids: List[str] = []
    for email_id in stale_email_ids:
        stale_suggestion_ids.extend(email_to_suggestions[email_id])

    return stale_suggestion_ids


def expire_stale_suggestions(
    account: str,
    stale_suggestion_ids: List[str],
) -> int:
    """Mark suggestions as expired for stale emails.

    Instead of approving/rejecting (which affects trust metrics),
    we reject with a note that it's due to stale email.

    Args:
        account: Email account ("church" or "personal")
        stale_suggestion_ids: List of suggestion IDs to expire

    Returns:
        Count of suggestions expired
    """
    count = 0
    for suggestion_id in stale_suggestion_ids:
        # Use reject (False) since the email no longer exists
        # This doesn't negatively affect trust since it's not a user decision
        if record_suggestion_decision(account, suggestion_id, approved=False):
            count += 1
            logger.debug(f"Auto-expired stale suggestion: {suggestion_id}")

    if count:
        logger.info(f"Auto-expired {count} stale suggestions for {account}")

    return count


# =============================================================================
# Combined Sync Operation
# =============================================================================

def sync_stale_items(
    account: str,
    attention_items: List[AttentionRecord],
    suggestion_items: List[SuggestionRecord],
    config: GmailAccountConfig,
) -> dict:
    """Full sync operation: validate and dismiss stale items.

    This is the main entry point for refresh-time sync.

    Args:
        account: Email account ("church" or "personal")
        attention_items: List of AttentionRecords to validate
        suggestion_items: List of SuggestionRecords to validate
        config: Gmail account configuration

    Returns:
        Dict with sync results:
        {
            "attention": {
                "checked": int,
                "stale": int,
                "dismissed": int
            },
            "suggestions": {
                "checked": int,
                "stale": int,
                "expired": int
            },
            "stale_email_ids": List[str]
        }
    """
    result = {
        "attention": {"checked": 0, "stale": 0, "dismissed": 0},
        "suggestions": {"checked": 0, "stale": 0, "expired": 0},
        "stale_email_ids": [],
    }

    # Collect all unique email IDs for batch checking
    all_email_ids: Set[str] = set()
    attention_email_ids = {item.email_id for item in attention_items}
    suggestion_email_ids = {item.email_id for item in suggestion_items}
    all_email_ids.update(attention_email_ids)
    all_email_ids.update(suggestion_email_ids)

    if not all_email_ids:
        return result

    logger.info(f"Syncing {len(all_email_ids)} unique emails for {account} account")

    # Single batch check for all emails
    stale_email_ids = batch_check_emails(config, list(all_email_ids))
    result["stale_email_ids"] = list(stale_email_ids)

    # Process attention items
    result["attention"]["checked"] = len(attention_email_ids)
    stale_attention = [eid for eid in stale_email_ids if eid in attention_email_ids]
    result["attention"]["stale"] = len(stale_attention)
    if stale_attention:
        result["attention"]["dismissed"] = dismiss_stale_attention(account, stale_attention)

    # Process suggestions
    result["suggestions"]["checked"] = len(suggestion_email_ids)
    stale_suggestion_ids: List[str] = []
    for item in suggestion_items:
        if item.email_id in stale_email_ids:
            stale_suggestion_ids.append(item.suggestion_id)
    result["suggestions"]["stale"] = len(stale_suggestion_ids)
    if stale_suggestion_ids:
        result["suggestions"]["expired"] = expire_stale_suggestions(account, stale_suggestion_ids)

    if stale_email_ids:
        logger.info(
            f"Sync complete for {account}: "
            f"{result['attention']['dismissed']} attention items dismissed, "
            f"{result['suggestions']['expired']} suggestions expired"
        )

    return result


# =============================================================================
# Quick Interaction Check
# =============================================================================

def verify_email_for_interaction(
    config: GmailAccountConfig,
    email_id: str,
) -> tuple[bool, Optional[str]]:
    """Quick existence check for user interactions.

    Called when user clicks approve/dismiss/view on an item.
    If email no longer exists, returns False with a reason message.

    Args:
        config: Gmail account configuration
        email_id: Gmail message ID

    Returns:
        Tuple of (exists: bool, message: Optional[str])
        If exists is False, message explains why for toast display
    """
    if email_exists(config, email_id):
        return (True, None)

    return (False, "This email has been deleted or archived. The item will be dismissed.")
