"""Shared Pydantic models for API routers.

This module extracts common request/response models from main.py.
Domain-specific models can remain in their respective router files.

Usage in routers:
    from api.models import AssistRequest, ChatRequest, ConversationMessageModel
"""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field


# =============================================================================
# Base Request Models (used across multiple routers)
# =============================================================================

class AssistRequest(BaseModel):
    """Request model for assist endpoints."""
    source: Literal["auto", "live", "stub"] = "auto"
    anthropic_model: Optional[str] = Field(
        None, alias="anthropicModel", description="Override Anthropic model name."
    )
    send_email_account: Optional[str] = Field(
        None,
        alias="sendEmailAccount",
        description="Gmail account prefix to send email (e.g., 'church').",
    )
    instructions: Optional[str] = None
    reset_conversation: bool = Field(
        False,
        alias="resetConversation",
        description="If true, clears stored conversation history before running assist.",
    )


class ChatRequest(BaseModel):
    """Request model for chat endpoints."""
    message: str
    source: Literal["auto", "live", "stub"] = "auto"
    attachments: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="Optional file attachments for the message.",
    )


class ConversationMessageModel(BaseModel):
    """Model for conversation history messages."""
    role: Literal["user", "assistant", "tool"]
    content: str
    timestamp: Optional[str] = None
    message_id: Optional[str] = Field(None, alias="messageId")
    struck: bool = False


# =============================================================================
# Task Models
# =============================================================================

class TaskCreateRequest(BaseModel):
    """Request model for creating tasks."""
    title: str
    due_date: Optional[str] = Field(None, alias="dueDate")
    priority: str = "Standard"
    domain: str = "personal"
    project: Optional[str] = None
    notes: Optional[str] = None
    estimated_hours: Optional[float] = Field(None, alias="estimatedHours")


class TaskUpdateRequest(BaseModel):
    """Request model for updating tasks."""
    action: str
    status: Optional[str] = None
    priority: Optional[str] = None
    due_date: Optional[str] = Field(None, alias="dueDate")
    comment: Optional[str] = None
    confirmed: bool = False


class BulkTaskUpdate(BaseModel):
    """Single task update in a bulk operation."""
    row_id: str = Field(..., alias="rowId")
    updates: Dict[str, Any]


class BulkUpdateRequest(BaseModel):
    """Request model for bulk task updates."""
    tasks: List[BulkTaskUpdate]
    source: Literal["auto", "live", "stub"] = "auto"


class BulkUpdateResult(BaseModel):
    """Result of a bulk update operation."""
    success: bool
    row_id: str = Field(..., alias="rowId")
    error: Optional[str] = None


# =============================================================================
# Email Models
# =============================================================================

class EmailChatRequest(BaseModel):
    """Request model for email chat."""
    message: str
    email_context: Optional[Dict[str, Any]] = Field(None, alias="emailContext")


class EmailDraftRequest(BaseModel):
    """Request model for creating email drafts."""
    to: List[str]
    subject: str
    body: str
    cc: Optional[List[str]] = None
    bcc: Optional[List[str]] = None


class EmailDraftResponse(BaseModel):
    """Response model for email draft operations."""
    draft_id: str = Field(..., alias="draftId")
    message_id: Optional[str] = Field(None, alias="messageId")
    thread_id: Optional[str] = Field(None, alias="threadId")


# =============================================================================
# Calendar Models
# =============================================================================

class CreateEventRequest(BaseModel):
    """Request model for creating calendar events."""
    summary: str
    start_datetime: str = Field(..., alias="startDatetime")
    end_datetime: str = Field(..., alias="endDatetime")
    description: Optional[str] = None
    location: Optional[str] = None


class UpdateEventRequest(BaseModel):
    """Request model for updating calendar events."""
    summary: Optional[str] = None
    start_datetime: Optional[str] = Field(None, alias="startDatetime")
    end_datetime: Optional[str] = Field(None, alias="endDatetime")
    description: Optional[str] = None
    location: Optional[str] = None


class QuickAddEventRequest(BaseModel):
    """Request model for quick-add calendar events."""
    text: str


class CalendarChatRequestModel(BaseModel):
    """Request model for calendar chat."""
    message: str
    event_context: Optional[Dict[str, Any]] = Field(None, alias="eventContext")


# =============================================================================
# Feedback Models
# =============================================================================

class FeedbackRequest(BaseModel):
    """Request model for submitting feedback."""
    task_id: str = Field(..., alias="taskId")
    rating: int
    comment: Optional[str] = None
    feedback_type: str = Field("general", alias="feedbackType")


# =============================================================================
# Sync Models
# =============================================================================

class SyncRequest(BaseModel):
    """Request model for sync operations."""
    full_sync: bool = Field(False, alias="fullSync")
    force: bool = False


# =============================================================================
# Settings Models
# =============================================================================

class UpdateSettingsRequest(BaseModel):
    """Request model for updating settings."""
    settings: Dict[str, Any]


# =============================================================================
# Attachment Models
# =============================================================================

class AttachmentResponse(BaseModel):
    """Response model for attachment metadata."""
    attachment_id: str = Field(..., alias="attachmentId")
    name: str
    mime_type: Optional[str] = Field(None, alias="mimeType")
    size_in_kb: Optional[float] = Field(None, alias="sizeInKB")
    created_at: Optional[str] = Field(None, alias="createdAt")


class AttachmentsListResponse(BaseModel):
    """Response model for attachment list."""
    attachments: List[AttachmentResponse]
    total_size_kb: float = Field(..., alias="totalSizeKB")
