"""Helpers for sending email through Gmail API."""
from __future__ import annotations

import base64
from dataclasses import dataclass
import json
import os
from typing import Optional
from urllib import error as urlerror
from urllib import parse as urlparse
from urllib import request as urlrequest
from email.message import EmailMessage


TOKEN_URL = "https://oauth2.googleapis.com/token"
SEND_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"


class GmailError(RuntimeError):
    """Raised when Gmail sending fails."""


@dataclass(slots=True)
class GmailAccountConfig:
    """Gmail OAuth configuration."""

    name: str
    client_id: str
    client_secret: str
    refresh_token: str
    from_address: str
    default_to: Optional[str] = None


def load_account_from_env(name: str) -> GmailAccountConfig:
    """Load Gmail account credentials from environment variables."""

    prefix = name.upper()
    client_id = os.getenv(f"{prefix}_GMAIL_CLIENT_ID")
    client_secret = os.getenv(f"{prefix}_GMAIL_CLIENT_SECRET")
    refresh_token = os.getenv(f"{prefix}_GMAIL_REFRESH_TOKEN")
    from_address = os.getenv(f"{prefix}_GMAIL_ADDRESS")
    default_to = os.getenv(f"{prefix}_GMAIL_DEFAULT_TO")

    missing = [
        label
        for label, value in [
            ("CLIENT_ID", client_id),
            ("CLIENT_SECRET", client_secret),
            ("REFRESH_TOKEN", refresh_token),
            ("ADDRESS", from_address),
        ]
        if not value
    ]
    if missing:
        raise GmailError(
            f"Missing Gmail env vars for account '{name}': {', '.join(missing)}"
        )

    return GmailAccountConfig(
        name=name,
        client_id=client_id,
        client_secret=client_secret,
        refresh_token=refresh_token,
        from_address=from_address,
        default_to=default_to,
    )


def send_email(
    account: GmailAccountConfig,
    *,
    to_address: Optional[str],
    subject: str,
    body: str,
    cc_address: Optional[str] = None,
    in_reply_to: Optional[str] = None,
    references: Optional[str] = None,
    thread_id: Optional[str] = None,
) -> str:
    """Send an email using the Gmail API and return the message ID.
    
    Args:
        account: Gmail account configuration.
        to_address: Primary recipient(s), comma-separated if multiple.
        subject: Email subject line.
        body: Email body text.
        cc_address: Optional CC recipient(s), comma-separated if multiple.
        in_reply_to: Message-ID header of the email being replied to.
        references: References header for threading (space-separated Message-IDs).
        thread_id: Gmail thread ID to keep the reply in the same thread.
    
    Returns:
        Gmail message ID.
    """

    to_addr = to_address or account.default_to or account.from_address
    if not to_addr:
        raise GmailError("No recipient email available for Gmail send.")

    access_token = _fetch_access_token(account)
    raw_message = _build_raw_message(
        from_address=account.from_address,
        to_address=to_addr,
        subject=subject,
        body=body,
        cc_address=cc_address,
        in_reply_to=in_reply_to,
        references=references,
    )

    # Build payload - include threadId to keep reply in same thread
    payload_data = {"raw": raw_message}
    if thread_id:
        payload_data["threadId"] = thread_id
    
    payload = json.dumps(payload_data).encode("utf-8")
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    req = urlrequest.Request(SEND_URL, data=payload, headers=headers, method="POST")
    try:
        with urlrequest.urlopen(req, timeout=15) as resp:
            response = json.loads(resp.read().decode("utf-8"))
    except urlerror.HTTPError as exc:  # pragma: no cover - network path
        detail = exc.read().decode("utf-8", errors="ignore")
        raise GmailError(
            f"Gmail send failed with status {exc.code}: {detail}"
        ) from exc
    except urlerror.URLError as exc:  # pragma: no cover - network path
        raise GmailError(f"Gmail network error: {exc}") from exc

    return response.get("id", "")


def _fetch_access_token(account: GmailAccountConfig) -> str:
    payload = urlparse.urlencode(
        {
            "client_id": account.client_id,
            "client_secret": account.client_secret,
            "refresh_token": account.refresh_token,
            "grant_type": "refresh_token",
        }
    ).encode("utf-8")
    req = urlrequest.Request(
        TOKEN_URL,
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urlrequest.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urlerror.HTTPError as exc:  # pragma: no cover - network path
        detail = exc.read().decode("utf-8", errors="ignore")
        raise GmailError(f"Gmail token request failed ({exc.code}): {detail}") from exc
    except urlerror.URLError as exc:  # pragma: no cover - network path
        raise GmailError(f"Gmail token network error: {exc}") from exc

    token = data.get("access_token")
    if not token:
        raise GmailError("Gmail token response missing access_token.")
    return str(token)


def _build_raw_message(
    *,
    from_address: str,
    to_address: str,
    subject: str,
    body: str,
    cc_address: Optional[str] = None,
    in_reply_to: Optional[str] = None,
    references: Optional[str] = None,
) -> str:
    message = EmailMessage()
    message["To"] = to_address
    message["From"] = from_address
    message["Subject"] = subject
    if cc_address:
        message["Cc"] = cc_address
    
    # Add threading headers for replies
    if in_reply_to:
        message["In-Reply-To"] = in_reply_to
    if references:
        message["References"] = references
    
    message.set_content(body)
    encoded = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
    return encoded

