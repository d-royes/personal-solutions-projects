"""Conversation history helpers."""

from .history import (
    ConversationMessage,
    build_plan_summary,
    clear_conversation,
    delete_message,
    fetch_conversation,
    fetch_conversation_for_llm,
    log_assistant_message,
    log_user_message,
    strike_message,
    unstrike_message,
)

from .email_history import (
    EmailConversationMessage,
    EmailThreadMetadata,
    clear_email_conversation,
    fetch_email_conversation,
    get_conversation_metadata,
    has_conversation,
    list_recent_conversations,
    log_email_message,
    purge_expired_conversations,
    update_conversation_metadata,
)

__all__ = [
    # Task conversation history
    "ConversationMessage",
    "build_plan_summary",
    "clear_conversation",
    "delete_message",
    "fetch_conversation",
    "fetch_conversation_for_llm",
    "log_assistant_message",
    "log_user_message",
    "strike_message",
    "unstrike_message",
    # Email conversation history
    "EmailConversationMessage",
    "EmailThreadMetadata",
    "clear_email_conversation",
    "fetch_email_conversation",
    "get_conversation_metadata",
    "has_conversation",
    "list_recent_conversations",
    "log_email_message",
    "purge_expired_conversations",
    "update_conversation_metadata",
]

