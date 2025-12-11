"""Mail helper package."""

from .gmail import (
    GmailAccountConfig,
    GmailError,
    load_account_from_env,
    send_email,
)

from .inbox import (
    EmailMessage,
    InboxSummary,
    get_inbox_summary,
    get_message,
    get_unread_messages,
    list_messages,
    search_messages,
)

__all__ = [
    # Gmail sending
    "GmailAccountConfig",
    "GmailError",
    "load_account_from_env",
    "send_email",
    # Inbox reading
    "EmailMessage",
    "InboxSummary",
    "get_inbox_summary",
    "get_message",
    "get_unread_messages",
    "list_messages",
    "search_messages",
]

