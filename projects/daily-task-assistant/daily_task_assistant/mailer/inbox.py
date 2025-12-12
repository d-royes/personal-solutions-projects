"""Gmail inbox reading capabilities.

This module provides functions to read and search emails from Gmail accounts
using the existing OAuth credentials.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional, Literal
from urllib import request as urlrequest
from urllib import error as urlerror

from .gmail import GmailAccountConfig, GmailError, _fetch_access_token


MESSAGES_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages"


@dataclass(slots=True)
class EmailMessage:
    """Represents an email message from the inbox."""
    
    id: str
    thread_id: str
    from_address: str
    from_name: str
    to_address: str
    subject: str
    snippet: str  # Preview text
    date: datetime
    is_unread: bool
    labels: List[str] = field(default_factory=list)
    
    @property
    def is_important(self) -> bool:
        """Check if message has IMPORTANT label."""
        return "IMPORTANT" in self.labels
    
    @property
    def is_starred(self) -> bool:
        """Check if message is starred."""
        return "STARRED" in self.labels
    
    def age_hours(self) -> float:
        """Return age of message in hours."""
        now = datetime.now(timezone.utc)
        delta = now - self.date
        return delta.total_seconds() / 3600


@dataclass(slots=True)
class InboxSummary:
    """Summary of inbox state."""
    
    total_unread: int
    unread_important: int
    unread_from_vips: int
    recent_messages: List[EmailMessage]
    vip_messages: List[EmailMessage]


def list_messages(
    account: GmailAccountConfig,
    *,
    max_results: int = 20,
    label_ids: Optional[List[str]] = None,
    query: Optional[str] = None,
    include_spam_trash: bool = False,
) -> List[dict]:
    """List message IDs from the inbox.
    
    Args:
        account: Gmail account configuration.
        max_results: Maximum number of messages to return (default 20).
        label_ids: Filter by label IDs (e.g., ["UNREAD", "INBOX"]).
        query: Gmail search query (e.g., "is:unread from:boss@company.com").
        include_spam_trash: Whether to include spam and trash.
        
    Returns:
        List of message dicts with 'id' and 'threadId'.
    """
    access_token = _fetch_access_token(account)
    
    params = [f"maxResults={max_results}"]
    if label_ids:
        for label in label_ids:
            params.append(f"labelIds={label}")
    if query:
        params.append(f"q={urlrequest.quote(query)}")
    if include_spam_trash:
        params.append("includeSpamTrash=true")
    
    url = f"{MESSAGES_URL}?{'&'.join(params)}"
    headers = {"Authorization": f"Bearer {access_token}"}
    
    req = urlrequest.Request(url, headers=headers, method="GET")
    
    try:
        with urlrequest.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("messages", [])
    except urlerror.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise GmailError(f"Gmail list failed ({exc.code}): {detail}") from exc
    except urlerror.URLError as exc:
        raise GmailError(f"Gmail network error: {exc}") from exc


def count_messages(
    account: GmailAccountConfig,
    *,
    query: str,
) -> int:
    """Get count of messages matching a query.
    
    Note: Uses Gmail's resultSizeEstimate which is approximate.
    For exact counts, use get_label_counts() instead.
    
    Args:
        account: Gmail account configuration.
        query: Gmail search query (e.g., "is:unread in:inbox").
        
    Returns:
        Estimated count of matching messages.
    """
    access_token = _fetch_access_token(account)
    
    # Request minimal results, we only need the count estimate
    params = [
        "maxResults=1",
        f"q={urlrequest.quote(query)}",
    ]
    
    url = f"{MESSAGES_URL}?{'&'.join(params)}"
    headers = {"Authorization": f"Bearer {access_token}"}
    
    req = urlrequest.Request(url, headers=headers, method="GET")
    
    try:
        with urlrequest.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("resultSizeEstimate", 0)
    except urlerror.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise GmailError(f"Gmail count failed ({exc.code}): {detail}") from exc
    except urlerror.URLError as exc:
        raise GmailError(f"Gmail network error: {exc}") from exc


def get_label_counts(
    account: GmailAccountConfig,
    label_id: str,
) -> dict:
    """Get exact message counts for a Gmail label.
    
    Args:
        account: Gmail account configuration.
        label_id: Gmail label ID (e.g., "INBOX", "UNREAD", "IMPORTANT").
        
    Returns:
        Dict with 'messagesTotal', 'messagesUnread', 'threadsTotal', 'threadsUnread'.
    """
    access_token = _fetch_access_token(account)
    
    url = f"https://gmail.googleapis.com/gmail/v1/users/me/labels/{label_id}"
    headers = {"Authorization": f"Bearer {access_token}"}
    
    req = urlrequest.Request(url, headers=headers, method="GET")
    
    try:
        with urlrequest.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return {
                "messagesTotal": data.get("messagesTotal", 0),
                "messagesUnread": data.get("messagesUnread", 0),
                "threadsTotal": data.get("threadsTotal", 0),
                "threadsUnread": data.get("threadsUnread", 0),
            }
    except urlerror.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise GmailError(f"Gmail label info failed ({exc.code}): {detail}") from exc
    except urlerror.URLError as exc:
        raise GmailError(f"Gmail network error: {exc}") from exc


def get_message(
    account: GmailAccountConfig,
    message_id: str,
    *,
    format: Literal["minimal", "metadata", "full"] = "metadata",
) -> EmailMessage:
    """Get a single message by ID.
    
    Args:
        account: Gmail account configuration.
        message_id: The message ID to fetch.
        format: Response format - 'minimal', 'metadata', or 'full'.
        
    Returns:
        EmailMessage with parsed headers and metadata.
    """
    access_token = _fetch_access_token(account)
    
    # Request specific headers we need
    url = (
        f"{MESSAGES_URL}/{message_id}?format={format}"
        f"&metadataHeaders=Subject&metadataHeaders=From"
        f"&metadataHeaders=To&metadataHeaders=Date"
    )
    headers = {"Authorization": f"Bearer {access_token}"}
    
    req = urlrequest.Request(url, headers=headers, method="GET")
    
    try:
        with urlrequest.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return _parse_message(data)
    except urlerror.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise GmailError(f"Gmail get failed ({exc.code}): {detail}") from exc
    except urlerror.URLError as exc:
        raise GmailError(f"Gmail network error: {exc}") from exc


def get_unread_messages(
    account: GmailAccountConfig,
    *,
    max_results: int = 20,
    from_filter: Optional[str] = None,
) -> List[EmailMessage]:
    """Get unread messages from inbox.
    
    Args:
        account: Gmail account configuration.
        max_results: Maximum number of messages.
        from_filter: Optional filter for sender (e.g., "@company.com").
        
    Returns:
        List of unread EmailMessage objects.
    """
    query = "is:unread"
    if from_filter:
        query += f" from:{from_filter}"
    
    message_refs = list_messages(
        account,
        max_results=max_results,
        label_ids=["INBOX"],
        query=query,
    )
    
    messages = []
    for ref in message_refs:
        try:
            msg = get_message(account, ref["id"])
            messages.append(msg)
        except GmailError:
            # Skip messages that fail to load
            continue
    
    return messages


def get_inbox_summary(
    account: GmailAccountConfig,
    *,
    vip_senders: Optional[List[str]] = None,
    max_recent: int = 10,
) -> InboxSummary:
    """Get a summary of the inbox state.
    
    Args:
        account: Gmail account configuration.
        vip_senders: List of important sender patterns (e.g., ["boss@", "@company.com"]).
        max_recent: Number of recent messages to include.
        
    Returns:
        InboxSummary with counts and recent/VIP messages.
    """
    vip_senders = vip_senders or []
    
    # Get exact counts from Gmail Labels API
    inbox_counts = get_label_counts(account, "INBOX")
    important_counts = get_label_counts(account, "IMPORTANT")
    
    total_unread = inbox_counts["messagesUnread"]
    unread_important = important_counts["messagesUnread"]
    
    # Get recent messages with full details
    recent_refs = list_messages(account, max_results=max_recent, label_ids=["INBOX"])
    recent_messages = []
    for ref in recent_refs:
        try:
            msg = get_message(account, ref["id"])
            recent_messages.append(msg)
        except GmailError:
            continue
    
    # Filter VIP messages
    vip_messages = []
    unread_from_vips = 0
    
    if vip_senders:
        for msg in recent_messages:
            sender = msg.from_address.lower()
            for vip in vip_senders:
                if vip.lower() in sender:
                    vip_messages.append(msg)
                    if msg.is_unread:
                        unread_from_vips += 1
                    break
    
    return InboxSummary(
        total_unread=total_unread,
        unread_important=unread_important,
        unread_from_vips=unread_from_vips,
        recent_messages=recent_messages,
        vip_messages=vip_messages,
    )


def search_messages(
    account: GmailAccountConfig,
    query: str,
    *,
    max_results: int = 20,
) -> List[EmailMessage]:
    """Search messages using Gmail query syntax.
    
    Args:
        account: Gmail account configuration.
        query: Gmail search query (e.g., "subject:urgent after:2025/01/01").
        max_results: Maximum results to return.
        
    Returns:
        List of matching EmailMessage objects.
        
    Examples:
        - "is:unread from:boss@company.com"
        - "subject:urgent OR subject:asap"
        - "after:2025/12/01 has:attachment"
        - "in:inbox is:important"
    """
    message_refs = list_messages(account, max_results=max_results, query=query)
    
    messages = []
    for ref in message_refs:
        try:
            msg = get_message(account, ref["id"])
            messages.append(msg)
        except GmailError:
            continue
    
    return messages


def _parse_message(data: dict) -> EmailMessage:
    """Parse Gmail API response into EmailMessage."""
    headers = data.get("payload", {}).get("headers", [])
    
    def get_header(name: str) -> str:
        return next(
            (h["value"] for h in headers if h["name"].lower() == name.lower()),
            ""
        )
    
    # Parse From header (e.g., "John Doe <john@example.com>")
    from_raw = get_header("From")
    from_name, from_address = _parse_email_address(from_raw)
    
    # Parse date
    date_str = get_header("Date")
    try:
        # Handle various date formats
        date = _parse_email_date(date_str)
    except Exception:
        date = datetime.now(timezone.utc)
    
    labels = data.get("labelIds", [])
    is_unread = "UNREAD" in labels
    
    return EmailMessage(
        id=data["id"],
        thread_id=data.get("threadId", data["id"]),
        from_address=from_address,
        from_name=from_name,
        to_address=get_header("To"),
        subject=get_header("Subject"),
        snippet=data.get("snippet", ""),
        date=date,
        is_unread=is_unread,
        labels=labels,
    )


def _parse_email_address(raw: str) -> tuple[str, str]:
    """Parse 'Name <email@example.com>' into (name, email)."""
    if "<" in raw and ">" in raw:
        name = raw.split("<")[0].strip().strip('"')
        email = raw.split("<")[1].split(">")[0].strip()
        return name, email
    return "", raw.strip()


def _parse_email_date(date_str: str) -> datetime:
    """Parse email date string to datetime."""
    from email.utils import parsedate_to_datetime
    try:
        return parsedate_to_datetime(date_str)
    except Exception:
        # Fallback: try common formats
        for fmt in [
            "%a, %d %b %Y %H:%M:%S %z",
            "%d %b %Y %H:%M:%S %z",
            "%Y-%m-%dT%H:%M:%S%z",
        ]:
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue
        return datetime.now(timezone.utc)


# =============================================================================
# Email Actions (Phase 3)
# =============================================================================

def modify_message_labels(
    account: GmailAccountConfig,
    message_id: str,
    *,
    add_labels: Optional[List[str]] = None,
    remove_labels: Optional[List[str]] = None,
) -> dict:
    """Modify labels on a message.
    
    Args:
        account: Gmail account configuration.
        message_id: The message ID to modify.
        add_labels: Labels to add (e.g., ["STARRED", "IMPORTANT"]).
        remove_labels: Labels to remove (e.g., ["INBOX", "UNREAD"]).
        
    Returns:
        Updated message data.
    """
    access_token = _fetch_access_token(account)
    
    url = f"{MESSAGES_URL}/{message_id}/modify"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    
    body = {}
    if add_labels:
        body["addLabelIds"] = add_labels
    if remove_labels:
        body["removeLabelIds"] = remove_labels
    
    req = urlrequest.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    
    try:
        with urlrequest.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urlerror.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise GmailError(f"Gmail modify failed ({exc.code}): {detail}") from exc
    except urlerror.URLError as exc:
        raise GmailError(f"Gmail network error: {exc}") from exc


def archive_message(account: GmailAccountConfig, message_id: str) -> dict:
    """Archive a message (remove from INBOX, keep in All Mail).
    
    Args:
        account: Gmail account configuration.
        message_id: The message ID to archive.
        
    Returns:
        Updated message data.
    """
    return modify_message_labels(
        account,
        message_id,
        remove_labels=["INBOX"],
    )


def delete_message(account: GmailAccountConfig, message_id: str) -> dict:
    """Move a message to trash.
    
    Args:
        account: Gmail account configuration.
        message_id: The message ID to delete.
        
    Returns:
        Updated message data.
    """
    access_token = _fetch_access_token(account)
    
    url = f"{MESSAGES_URL}/{message_id}/trash"
    headers = {"Authorization": f"Bearer {access_token}"}
    
    req = urlrequest.Request(url, headers=headers, method="POST")
    
    try:
        with urlrequest.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urlerror.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise GmailError(f"Gmail trash failed ({exc.code}): {detail}") from exc
    except urlerror.URLError as exc:
        raise GmailError(f"Gmail network error: {exc}") from exc


def star_message(account: GmailAccountConfig, message_id: str, starred: bool = True) -> dict:
    """Star or unstar a message.
    
    Args:
        account: Gmail account configuration.
        message_id: The message ID to star/unstar.
        starred: True to star, False to unstar.
        
    Returns:
        Updated message data.
    """
    if starred:
        return modify_message_labels(
            account,
            message_id,
            add_labels=["STARRED"],
        )
    else:
        return modify_message_labels(
            account,
            message_id,
            remove_labels=["STARRED"],
        )


def mark_important(account: GmailAccountConfig, message_id: str, important: bool = True) -> dict:
    """Mark a message as important or not important.
    
    Args:
        account: Gmail account configuration.
        message_id: The message ID.
        important: True to mark important, False to remove.
        
    Returns:
        Updated message data.
    """
    if important:
        return modify_message_labels(
            account,
            message_id,
            add_labels=["IMPORTANT"],
        )
    else:
        return modify_message_labels(
            account,
            message_id,
            remove_labels=["IMPORTANT"],
        )


def mark_read(account: GmailAccountConfig, message_id: str) -> dict:
    """Mark a message as read (remove UNREAD label).
    
    Args:
        account: Gmail account configuration.
        message_id: The message ID.
        
    Returns:
        Updated message data.
    """
    return modify_message_labels(
        account,
        message_id,
        remove_labels=["UNREAD"],
    )


def mark_unread(account: GmailAccountConfig, message_id: str) -> dict:
    """Mark a message as unread (add UNREAD label).
    
    Args:
        account: Gmail account configuration.
        message_id: The message ID.
        
    Returns:
        Updated message data.
    """
    return modify_message_labels(
        account,
        message_id,
        add_labels=["UNREAD"],
    )

