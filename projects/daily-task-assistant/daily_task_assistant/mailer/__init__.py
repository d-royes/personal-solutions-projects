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
    count_messages,
    get_inbox_summary,
    get_label_counts,
    get_message,
    get_unread_messages,
    list_messages,
    search_messages,
    # Email actions
    archive_message,
    delete_message,
    star_message,
    mark_important,
    mark_read,
    mark_unread,
    modify_message_labels,
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
    "count_messages",
    "get_inbox_summary",
    "get_label_counts",
    "get_message",
    "get_unread_messages",
    "list_messages",
    "search_messages",
    # Email actions
    "archive_message",
    "delete_message",
    "star_message",
    "mark_important",
    "mark_read",
    "mark_unread",
    "modify_message_labels",
]

