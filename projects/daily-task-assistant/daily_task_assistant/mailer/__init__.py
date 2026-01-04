"""Mail helper package."""

from .gmail import (
    GmailAccountConfig,
    GmailError,
    load_account_from_env,
    send_email,
)

from .inbox import (
    AttachmentInfo,
    EmailMessage,
    InboxSummary,
    GmailLabel,
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
    # Custom label operations
    list_labels,
    get_label_by_name,
    apply_label,
    remove_label,
    apply_label_by_name,
    remove_label_by_name,
)

__all__ = [
    # Gmail sending
    "GmailAccountConfig",
    "GmailError",
    "load_account_from_env",
    "send_email",
    # Inbox reading
    "AttachmentInfo",
    "EmailMessage",
    "InboxSummary",
    "GmailLabel",
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
    # Custom label operations
    "list_labels",
    "get_label_by_name",
    "apply_label",
    "remove_label",
    "apply_label_by_name",
    "remove_label_by_name",
]

