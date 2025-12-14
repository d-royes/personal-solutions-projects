#!/usr/bin/env python3
"""
Diagnostic script to test email sending via Gmail API.

This script tests the email send functionality directly, bypassing the API layer,
to help diagnose issues with email delivery.

Usage:
    cd projects/daily-task-assistant
    python scripts/test_email_send.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

# Load environment variables
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

from daily_task_assistant.mailer import (
    GmailError,
    load_account_from_env,
    send_email,
)


def test_email_send(account_name: str = "personal"):
    """Test sending an email and report detailed results."""

    print(f"\n{'='*60}")
    print(f"EMAIL SEND DIAGNOSTIC TEST")
    print(f"{'='*60}\n")

    # Step 1: Load account config
    print(f"[1/4] Loading Gmail config for '{account_name}'...")
    try:
        config = load_account_from_env(account_name)
        print(f"      [OK] Loaded config for: {config.from_address}")
    except GmailError as e:
        print(f"      [FAIL] Failed to load config: {e}")
        return False

    # Step 2: Prepare test email
    print(f"\n[2/4] Preparing test email...")
    test_subject = "DATA Email Test - Please Confirm Receipt"
    test_body = f"""This is a test email from DATA's diagnostic script.

If you received this email, the Gmail API integration is working correctly.

Test Details:
- Account: {account_name}
- From: {config.from_address}
- Sent via: Gmail API (OAuth2)

Please reply or let me know if you received this.

-- DATA Diagnostic Script
"""

    # Send to self for testing
    to_address = config.from_address
    print(f"      To: {to_address}")
    print(f"      Subject: {test_subject}")
    print(f"      Body length: {len(test_body)} chars")

    # Step 3: Send the email
    print(f"\n[3/4] Sending email via Gmail API...")
    try:
        message_id = send_email(
            config,
            to_address=to_address,
            subject=test_subject,
            body=test_body,
        )
        print(f"      [OK] Email sent successfully!")
        print(f"      Message ID: {message_id}")
    except GmailError as e:
        print(f"      [FAIL] Send failed: {e}")
        return False

    # Step 4: Verify in Sent folder
    print(f"\n[4/4] Verification steps:")
    print(f"      1. Check your Gmail Sent folder for message ID: {message_id}")
    print(f"      2. Check your Inbox for the test email")
    print(f"      3. Check Spam/Junk folder if not in Inbox")

    print(f"\n{'='*60}")
    print(f"TEST COMPLETE - Check Gmail for results")
    print(f"{'='*60}\n")

    return True


def check_sent_folder(account_name: str, message_id: str):
    """Check if a message exists in the Sent folder."""
    from daily_task_assistant.mailer.inbox import get_message

    print(f"\nChecking sent message {message_id}...")
    try:
        config = load_account_from_env(account_name)
        msg = get_message(config, message_id, format="metadata")
        print(f"  [OK] Message found in Gmail!")
        print(f"    Subject: {msg.subject}")
        print(f"    To: {msg.to_address}")
        print(f"    Labels: {msg.labels}")
        return True
    except GmailError as e:
        print(f"  [FAIL] Could not find message: {e}")
        return False


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Test Gmail email sending")
    parser.add_argument(
        "--account",
        choices=["personal", "church"],
        default="personal",
        help="Gmail account to test (default: personal)"
    )
    parser.add_argument(
        "--verify",
        metavar="MESSAGE_ID",
        help="Verify a specific message ID exists"
    )

    args = parser.parse_args()

    if args.verify:
        check_sent_folder(args.account, args.verify)
    else:
        test_email_send(args.account)
