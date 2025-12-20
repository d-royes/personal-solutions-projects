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
class AttachmentInfo:
    """Represents an email attachment metadata."""
    
    filename: str
    mime_type: str
    size: int  # Size in bytes
    attachment_id: Optional[str] = None


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
    # Full body fields (populated when format="full")
    body: Optional[str] = None  # Plain text body
    body_html: Optional[str] = None  # HTML body for display
    attachment_count: int = 0
    attachments: List[AttachmentInfo] = field(default_factory=list)
    # Additional headers for replies
    cc_address: str = ""
    message_id_header: str = ""  # For In-Reply-To
    references: str = ""  # For References header
    
    @property
    def is_important(self) -> bool:
        """Check if message has IMPORTANT label."""
        return "IMPORTANT" in self.labels
    
    @property
    def is_starred(self) -> bool:
        """Check if message is starred."""
        return "STARRED" in self.labels
    
    def age_hours(self) -> float:
        """Return age of message in hours.

        Handles both timezone-aware and naive datetimes safely.
        """
        now = datetime.now(timezone.utc)
        msg_date = self.date
        # Handle offset-naive datetimes (assume UTC if no timezone)
        if msg_date.tzinfo is None:
            msg_date = msg_date.replace(tzinfo=timezone.utc)
        delta = now - msg_date
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
                Use 'full' to get body content and attachments.
        
    Returns:
        EmailMessage with parsed headers and metadata.
        When format='full', includes body, body_html, and attachments.
    """
    access_token = _fetch_access_token(account)
    
    # Request specific headers we need (for metadata format)
    # For full format, all headers are included automatically
    url = (
        f"{MESSAGES_URL}/{message_id}?format={format}"
        f"&metadataHeaders=Subject&metadataHeaders=From"
        f"&metadataHeaders=To&metadataHeaders=Date"
        f"&metadataHeaders=Cc&metadataHeaders=Message-ID"
        f"&metadataHeaders=References"
    )
    headers = {"Authorization": f"Bearer {access_token}"}
    
    req = urlrequest.Request(url, headers=headers, method="GET")
    
    try:
        with urlrequest.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return _parse_message(data, include_body=(format == "full"))
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
    format: Literal["minimal", "metadata", "full"] = "metadata",
) -> List[EmailMessage]:
    """Search messages using Gmail query syntax.

    Args:
        account: Gmail account configuration.
        query: Gmail search query (e.g., "subject:urgent after:2025/01/01").
        max_results: Maximum results to return.
        format: Response format - 'metadata' (default) or 'full' for body content.

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
            msg = get_message(account, ref["id"], format=format)
            messages.append(msg)
        except GmailError:
            continue

    return messages


def _parse_message(data: dict, include_body: bool = False) -> EmailMessage:
    """Parse Gmail API response into EmailMessage.
    
    Args:
        data: Gmail API message response.
        include_body: If True, extract body and attachments from payload.
        
    Returns:
        EmailMessage with parsed data.
    """
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
    
    # Extract body and attachments if requested
    body = None
    body_html = None
    attachments: List[AttachmentInfo] = []
    
    if include_body:
        body, body_html, attachments = _extract_body_and_attachments(data.get("payload", {}))
    
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
        body=body,
        body_html=body_html,
        attachment_count=len(attachments),
        attachments=attachments,
        cc_address=get_header("Cc"),
        message_id_header=get_header("Message-ID"),
        references=get_header("References"),
    )


def _parse_email_address(raw: str) -> tuple[str, str]:
    """Parse 'Name <email@example.com>' into (name, email)."""
    if "<" in raw and ">" in raw:
        name = raw.split("<")[0].strip().strip('"')
        email = raw.split("<")[1].split(">")[0].strip()
        return name, email
    return "", raw.strip()


def _parse_email_date(date_str: str) -> datetime:
    """Parse email date string to datetime.

    Always returns a timezone-aware datetime (UTC if no timezone in source).
    """
    from email.utils import parsedate_to_datetime
    result = None

    try:
        result = parsedate_to_datetime(date_str)
    except Exception:
        # Fallback: try common formats
        for fmt in [
            "%a, %d %b %Y %H:%M:%S %z",
            "%d %b %Y %H:%M:%S %z",
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%d %H:%M:%S",  # No timezone - will be made aware below
        ]:
            try:
                result = datetime.strptime(date_str, fmt)
                break
            except ValueError:
                continue

    if result is None:
        return datetime.now(timezone.utc)

    # Ensure result is timezone-aware (assume UTC if naive)
    if result.tzinfo is None:
        result = result.replace(tzinfo=timezone.utc)

    return result


def _extract_body_and_attachments(
    payload: dict,
) -> tuple[Optional[str], Optional[str], List[AttachmentInfo]]:
    """Extract body content and attachments from Gmail message payload.
    
    Handles multipart MIME structures recursively.
    
    Args:
        payload: The 'payload' field from Gmail API message response.
        
    Returns:
        Tuple of (plain_text_body, html_body, attachments_list).
    """
    import base64
    
    body_plain: Optional[str] = None
    body_html: Optional[str] = None
    attachments: List[AttachmentInfo] = []
    
    def decode_body(data: str) -> str:
        """Decode base64url encoded body data."""
        # Gmail uses URL-safe base64 encoding
        try:
            decoded = base64.urlsafe_b64decode(data)
            return decoded.decode("utf-8", errors="replace")
        except Exception:
            return ""
    
    def process_part(part: dict) -> None:
        """Process a single MIME part recursively."""
        nonlocal body_plain, body_html
        
        mime_type = part.get("mimeType", "")
        filename = part.get("filename", "")
        
        # Check if this is an attachment
        if filename:
            # This is an attachment
            body_data = part.get("body", {})
            attachments.append(AttachmentInfo(
                filename=filename,
                mime_type=mime_type,
                size=body_data.get("size", 0),
                attachment_id=body_data.get("attachmentId"),
            ))
            return
        
        # Check for nested parts (multipart)
        if "parts" in part:
            for sub_part in part["parts"]:
                process_part(sub_part)
            return
        
        # Extract body content
        body_data = part.get("body", {}).get("data", "")
        if not body_data:
            return
        
        if mime_type == "text/plain" and body_plain is None:
            body_plain = decode_body(body_data)
        elif mime_type == "text/html" and body_html is None:
            body_html = decode_body(body_data)
    
    # Start processing from the root payload
    process_part(payload)
    
    return body_plain, body_html, attachments


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


# =============================================================================
# Custom Label Operations (Phase A2)
# =============================================================================

@dataclass(slots=True)
class GmailLabel:
    """Represents a Gmail label."""
    
    id: str
    name: str
    label_type: str  # "system" or "user"
    messages_total: int = 0
    messages_unread: int = 0
    color: Optional[str] = None


def list_labels(account: GmailAccountConfig) -> List[GmailLabel]:
    """List all Gmail labels for the account.
    
    Args:
        account: Gmail account configuration.
        
    Returns:
        List of GmailLabel objects including both system and user labels.
    """
    access_token = _fetch_access_token(account)
    
    url = "https://gmail.googleapis.com/gmail/v1/users/me/labels"
    headers = {"Authorization": f"Bearer {access_token}"}
    
    req = urlrequest.Request(url, headers=headers, method="GET")
    
    try:
        with urlrequest.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            labels = []
            for label_data in data.get("labels", []):
                label_type = label_data.get("type", "user").lower()
                color = None
                if "color" in label_data:
                    color = label_data["color"].get("backgroundColor")
                
                labels.append(GmailLabel(
                    id=label_data["id"],
                    name=label_data["name"],
                    label_type=label_type,
                    messages_total=label_data.get("messagesTotal", 0),
                    messages_unread=label_data.get("messagesUnread", 0),
                    color=color,
                ))
            return labels
    except urlerror.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise GmailError(f"Gmail labels list failed ({exc.code}): {detail}") from exc
    except urlerror.URLError as exc:
        raise GmailError(f"Gmail network error: {exc}") from exc


def get_label_by_name(
    account: GmailAccountConfig,
    label_name: str,
) -> Optional[GmailLabel]:
    """Find a label by name (case-insensitive).
    
    Args:
        account: Gmail account configuration.
        label_name: The label name to find.
        
    Returns:
        GmailLabel if found, None otherwise.
    """
    labels = list_labels(account)
    label_name_lower = label_name.lower()
    for label in labels:
        if label.name.lower() == label_name_lower:
            return label
    return None


def apply_label(
    account: GmailAccountConfig,
    message_id: str,
    label_id: str,
) -> dict:
    """Apply a label to a message.
    
    Args:
        account: Gmail account configuration.
        message_id: The message ID.
        label_id: The label ID to apply (use list_labels to get IDs).
        
    Returns:
        Updated message data.
    """
    return modify_message_labels(
        account,
        message_id,
        add_labels=[label_id],
    )


def remove_label(
    account: GmailAccountConfig,
    message_id: str,
    label_id: str,
) -> dict:
    """Remove a label from a message.
    
    Args:
        account: Gmail account configuration.
        message_id: The message ID.
        label_id: The label ID to remove.
        
    Returns:
        Updated message data.
    """
    return modify_message_labels(
        account,
        message_id,
        remove_labels=[label_id],
    )


def apply_label_by_name(
    account: GmailAccountConfig,
    message_id: str,
    label_name: str,
) -> dict:
    """Apply a label to a message by label name.
    
    Convenience wrapper that finds the label ID by name first.
    
    Args:
        account: Gmail account configuration.
        message_id: The message ID.
        label_name: The label name to apply (case-insensitive).
        
    Returns:
        Updated message data.
        
    Raises:
        GmailError: If label not found.
    """
    label = get_label_by_name(account, label_name)
    if not label:
        raise GmailError(f"Label not found: {label_name}")
    return apply_label(account, message_id, label.id)


def remove_label_by_name(
    account: GmailAccountConfig,
    message_id: str,
    label_name: str,
) -> dict:
    """Remove a label from a message by label name.
    
    Args:
        account: Gmail account configuration.
        message_id: The message ID.
        label_name: The label name to remove (case-insensitive).
        
    Returns:
        Updated message data.
        
    Raises:
        GmailError: If label not found.
    """
    label = get_label_by_name(account, label_name)
    if not label:
        raise GmailError(f"Label not found: {label_name}")
    return remove_label(account, message_id, label.id)

