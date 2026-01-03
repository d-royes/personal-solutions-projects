"""Calendar Chat Handler - orchestrates DATA chat for calendar mode.

This module handles the chat flow for calendar mode, including:
- Building calendar context for DATA
- Managing conversation persistence
- Calling the LLM
- Processing pending actions

No privacy tiers like email - calendar is fully visible to DATA.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from .types import CalendarEvent, CalendarAttentionRecord
from .context import build_calendar_context, DomainType
from ..conversations.calendar_history import (
    log_calendar_message,
    fetch_calendar_conversation,
    get_calendar_conversation_metadata,
)


@dataclass
class CalendarChatRequest:
    """Request to chat with DATA about calendar.

    Attributes:
        message: User's message
        domain: Calendar domain (personal, church, work, combined)
        selected_event_id: Event being discussed (optional)
        date_range_start: Start of visible date range (optional)
        date_range_end: End of visible date range (optional)
        events: Events in current view
        attention_items: Active attention items
        tasks: Tasks from Task tab
    """
    message: str
    domain: DomainType
    selected_event_id: Optional[str] = None
    date_range_start: Optional[datetime] = None
    date_range_end: Optional[datetime] = None
    events: List[CalendarEvent] = field(default_factory=list)
    attention_items: List[CalendarAttentionRecord] = field(default_factory=list)
    tasks: List[Dict[str, Any]] = field(default_factory=list)
    history: Optional[List[Dict[str, str]]] = None


@dataclass
class CalendarChatResponse:
    """Response from calendar chat.

    Attributes:
        response: DATA's message
        domain: Calendar domain
        pending_calendar_action: Event creation/update/delete action
        pending_task_creation: New task to create
        pending_task_update: Task update action
    """
    response: str
    domain: DomainType
    pending_calendar_action: Optional[Dict[str, Any]] = None
    pending_task_creation: Optional[Dict[str, Any]] = None
    pending_task_update: Optional[Dict[str, Any]] = None


def handle_calendar_chat(
    request: CalendarChatRequest,
    user_email: Optional[str] = None,
) -> CalendarChatResponse:
    """Process a calendar chat request.

    This is the main entry point for calendar chat. It:
    1. Finds the selected event if specified
    2. Builds context for DATA
    3. Loads conversation history
    4. Calls the LLM
    5. Persists messages
    6. Returns response with any pending actions

    Args:
        request: CalendarChatRequest with all context
        user_email: User's email for logging

    Returns:
        CalendarChatResponse with DATA's message and pending actions
    """
    from ..llm.anthropic_client import (
        chat_with_calendar,
        AnthropicError,
    )

    # Find selected event if specified
    selected_event = None
    if request.selected_event_id:
        for event in request.events:
            if event.id == request.selected_event_id:
                selected_event = event
                break

    # Build context string for DATA
    context = build_calendar_context(
        domain=request.domain,
        events=request.events,
        attention_items=request.attention_items,
        tasks=request.tasks,
        selected_event=selected_event,
        date_range_start=request.date_range_start,
        date_range_end=request.date_range_end,
    )

    # Load conversation history
    history = request.history
    if not history:
        # Try loading persisted conversation
        persisted_msgs = fetch_calendar_conversation(request.domain, limit=20)
        if persisted_msgs:
            history = [{"role": m.role, "content": m.content} for m in persisted_msgs]

    # Call DATA
    try:
        llm_response = chat_with_calendar(
            calendar_context=context,
            user_message=request.message,
            history=history,
        )
    except AnthropicError as exc:
        raise CalendarChatError(f"AI service error: {exc}") from exc

    # Persist messages
    log_calendar_message(
        domain=request.domain,
        role="user",
        content=request.message,
        event_context=request.selected_event_id,
        user_email=user_email,
    )
    log_calendar_message(
        domain=request.domain,
        role="assistant",
        content=llm_response.message,
        event_context=request.selected_event_id,
    )

    # Build response with pending actions
    response = CalendarChatResponse(
        response=llm_response.message,
        domain=request.domain,
    )

    # Convert pending actions to API-friendly dicts
    if llm_response.pending_calendar_action:
        action = llm_response.pending_calendar_action
        response.pending_calendar_action = {
            "action": action.action,
            "domain": action.domain,
            "reason": action.reason,
        }
        if action.event_id:
            response.pending_calendar_action["eventId"] = action.event_id
        if action.summary:
            response.pending_calendar_action["summary"] = action.summary
        if action.start_datetime:
            response.pending_calendar_action["startDatetime"] = action.start_datetime
        if action.end_datetime:
            response.pending_calendar_action["endDatetime"] = action.end_datetime
        if action.location:
            response.pending_calendar_action["location"] = action.location
        if action.description:
            response.pending_calendar_action["description"] = action.description

    if llm_response.pending_task_creation:
        task = llm_response.pending_task_creation
        response.pending_task_creation = {
            "taskTitle": task.task_title,
            "reason": task.reason,
        }
        if task.due_date:
            response.pending_task_creation["dueDate"] = task.due_date
        if task.priority:
            response.pending_task_creation["priority"] = task.priority
        if task.domain:
            response.pending_task_creation["domain"] = task.domain
        if task.project:
            response.pending_task_creation["project"] = task.project
        if task.notes:
            response.pending_task_creation["notes"] = task.notes
        if task.related_event_id:
            response.pending_task_creation["relatedEventId"] = task.related_event_id

    if llm_response.pending_task_update:
        update = llm_response.pending_task_update
        response.pending_task_update = {
            "action": update.action,
            "reason": update.reason,
        }
        if update.row_id:
            response.pending_task_update["rowId"] = update.row_id
        if update.status:
            response.pending_task_update["status"] = update.status
        if update.priority:
            response.pending_task_update["priority"] = update.priority
        if update.due_date:
            response.pending_task_update["dueDate"] = update.due_date
        if update.comment:
            response.pending_task_update["comment"] = update.comment
        if update.number is not None:
            response.pending_task_update["number"] = update.number
        if update.contact_flag is not None:
            response.pending_task_update["contactFlag"] = update.contact_flag
        if update.recurring:
            response.pending_task_update["recurring"] = update.recurring
        if update.project:
            response.pending_task_update["project"] = update.project
        if update.task_title:
            response.pending_task_update["taskTitle"] = update.task_title
        if update.assigned_to:
            response.pending_task_update["assignedTo"] = update.assigned_to
        if update.notes:
            response.pending_task_update["notes"] = update.notes
        if update.estimated_hours:
            response.pending_task_update["estimatedHours"] = update.estimated_hours

    return response


class CalendarChatError(Exception):
    """Error during calendar chat processing."""
    pass
