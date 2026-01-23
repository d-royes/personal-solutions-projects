"""Calendar Router - Calendar events, attention, and chat.

Handles:
- Calendar listing and event CRUD
- Calendar attention items (need action)
- Calendar settings
- Calendar chat with DATA

Migrated from api/main.py as part of the API refactoring initiative.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from api.dependencies import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter()

_LOCAL_TZ = ZoneInfo("America/New_York")


# =============================================================================
# Pydantic Models
# =============================================================================

class CreateEventRequest(BaseModel):
    """Request body for creating a calendar event."""
    summary: str = Field(..., description="Event title")
    start: str = Field(..., description="Start time (ISO format)")
    end: str = Field(..., description="End time (ISO format)")
    description: Optional[str] = Field(None, description="Event description")
    location: Optional[str] = Field(None, description="Event location")
    attendees: Optional[List[str]] = Field(None, description="List of attendee email addresses")
    is_all_day: bool = Field(False, alias="isAllDay", description="Whether this is an all-day event")
    send_notifications: bool = Field(True, alias="sendNotifications", description="Whether to send notifications")
    calendar_id: str = Field("primary", alias="calendarId", description="Calendar ID (defaults to primary)")

    model_config = ConfigDict(populate_by_name=True)


class UpdateEventRequest(BaseModel):
    """Request body for updating a calendar event."""
    summary: Optional[str] = Field(None, description="New event title")
    start: Optional[str] = Field(None, description="New start time (ISO format)")
    end: Optional[str] = Field(None, description="New end time (ISO format)")
    description: Optional[str] = Field(None, description="New event description")
    location: Optional[str] = Field(None, description="New event location")
    attendees: Optional[list[str]] = Field(None, description="List of attendee email addresses")
    send_notifications: bool = Field(True, alias="sendNotifications", description="Whether to send notifications")
    calendar_id: str = Field("primary", alias="calendarId", description="Calendar ID")

    model_config = ConfigDict(populate_by_name=True)


class QuickAddEventRequest(BaseModel):
    """Request body for quick-add event using natural language."""
    text: str = Field(..., description="Natural language description")
    calendar_id: str = Field("primary", alias="calendarId", description="Calendar ID")
    send_notifications: bool = Field(True, alias="sendNotifications", description="Whether to send notifications")

    model_config = ConfigDict(populate_by_name=True)


class UpdateCalendarSettingsRequest(BaseModel):
    """Request body for updating calendar settings."""
    enabled_calendars: Optional[List[str]] = Field(None, alias="enabledCalendars")
    work_calendar_id: Optional[str] = Field(None, alias="workCalendarId")
    show_declined_events: Optional[bool] = Field(None, alias="showDeclinedEvents")
    show_all_day_events: Optional[bool] = Field(None, alias="showAllDayEvents")
    default_days_ahead: Optional[int] = Field(None, alias="defaultDaysAhead")

    model_config = ConfigDict(populate_by_name=True)


class CalendarEventContext(BaseModel):
    """Event data passed from frontend for chat context."""
    id: str
    summary: str
    start: str
    end: str
    location: Optional[str] = None
    attendees: Optional[List[Dict[str, Any]]] = None
    description: Optional[str] = None
    htmlLink: Optional[str] = None
    isMeeting: bool = False
    sourceDomain: Optional[str] = None


class CalendarAttentionContext(BaseModel):
    """Attention item passed from frontend for chat context."""
    eventId: str
    summary: str
    start: str
    attentionType: str
    reason: str
    matchedVip: Optional[str] = None


class CalendarChatRequestModel(BaseModel):
    """Request body for calendar chat."""
    message: str
    selectedEventId: Optional[str] = None
    selectedTaskId: Optional[str] = None
    dateRangeStart: Optional[str] = None
    dateRangeEnd: Optional[str] = None
    events: Optional[List[CalendarEventContext]] = None
    attentionItems: Optional[List[CalendarAttentionContext]] = None
    tasks: Optional[List[Dict[str, Any]]] = None
    history: Optional[List[Dict[str, str]]] = None


class UpdateCalendarConversationRequest(BaseModel):
    """Request body for updating conversation history."""
    history: List[Dict[str, str]]


# =============================================================================
# Serialization Helpers
# =============================================================================

def _serialize_calendar_event(event) -> dict:
    """Serialize a CalendarEvent to API response format."""
    return {
        "id": event.id,
        "calendarId": event.calendar_id,
        "summary": event.summary,
        "start": event.start.isoformat(),
        "end": event.end.isoformat(),
        "description": event.description,
        "location": event.location,
        "colorId": event.color_id,
        "startTimezone": event.start_timezone,
        "endTimezone": event.end_timezone,
        "isAllDay": event.is_all_day,
        "status": event.status,
        "attendees": [
            {
                "email": a.email,
                "displayName": a.display_name,
                "responseStatus": a.response_status,
                "isOrganizer": a.is_organizer,
                "isSelf": a.is_self,
            }
            for a in event.attendees
        ],
        "organizerEmail": event.organizer_email,
        "creatorEmail": event.creator_email,
        "recurringEventId": event.recurring_event_id,
        "recurrence": event.recurrence,
        "htmlLink": event.html_link,
        "hangoutLink": event.hangout_link,
        "created": event.created.isoformat() if event.created else None,
        "updated": event.updated.isoformat() if event.updated else None,
        "sourceDomain": event.source_domain,
        "isMeeting": event.is_meeting,
        "attendeeCount": event.attendee_count,
        "durationMinutes": event.duration_minutes,
    }


def _serialize_calendar_info(cal) -> dict:
    """Serialize a CalendarInfo to API response format."""
    return {
        "id": cal.id,
        "summary": cal.summary,
        "description": cal.description,
        "colorId": cal.color_id,
        "backgroundColor": cal.background_color,
        "foregroundColor": cal.foreground_color,
        "isPrimary": cal.is_primary,
        "accessRole": cal.access_role,
        "isWritable": cal.is_writable,
    }


# =============================================================================
# Calendar Endpoints
# =============================================================================

@router.get("/{account}/calendars")
def list_calendars_endpoint(
    account: Literal["church", "personal"],
    show_hidden: bool = Query(False, alias="showHidden"),
    user: str = Depends(get_current_user),
) -> dict:
    """List all calendars accessible by this account."""
    from daily_task_assistant.calendar import (
        CalendarError,
        load_account_from_env,
        list_calendars,
    )

    try:
        config = load_account_from_env(account)
        response = list_calendars(config, show_hidden=show_hidden)
    except CalendarError as e:
        raise HTTPException(status_code=502, detail=str(e))

    return {
        "calendars": [_serialize_calendar_info(c) for c in response.calendars],
        "count": response.count,
    }


@router.get("/{account}/events")
def list_events_endpoint(
    account: Literal["church", "personal"],
    start: Optional[str] = Query(None, description="Start of date range (ISO format)"),
    end: Optional[str] = Query(None, description="End of date range (ISO format)"),
    calendar_id: str = Query("primary", alias="calendarId"),
    max_results: int = Query(100, alias="maxResults", ge=1, le=250),
    user: str = Depends(get_current_user),
) -> dict:
    """List events from a calendar."""
    from daily_task_assistant.calendar import (
        CalendarError,
        load_account_from_env,
        list_events,
    )

    try:
        config = load_account_from_env(account)
        
        # Parse dates
        start_dt = None
        end_dt = None
        if start:
            start_dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
        if end:
            end_dt = datetime.fromisoformat(end.replace("Z", "+00:00"))
        
        response = list_events(
            config,
            calendar_id=calendar_id,
            start=start_dt,
            end=end_dt,
            max_results=max_results,
        )
    except CalendarError as e:
        raise HTTPException(status_code=502, detail=str(e))

    return {
        "events": [_serialize_calendar_event(e) for e in response.events],
        "count": response.count,
    }


@router.get("/{account}/events/{event_id}")
def get_event_endpoint(
    account: Literal["church", "personal"],
    event_id: str,
    calendar_id: str = Query("primary", alias="calendarId"),
    user: str = Depends(get_current_user),
) -> dict:
    """Get a single event by ID."""
    from daily_task_assistant.calendar import (
        CalendarError,
        load_account_from_env,
        get_event,
    )

    try:
        config = load_account_from_env(account)
        event = get_event(config, event_id, calendar_id=calendar_id)
    except CalendarError as e:
        raise HTTPException(status_code=502, detail=str(e))

    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    return {"event": _serialize_calendar_event(event)}


@router.post("/{account}/events")
def create_event_endpoint(
    account: Literal["church", "personal"],
    request: CreateEventRequest,
    user: str = Depends(get_current_user),
) -> dict:
    """Create a new calendar event."""
    from daily_task_assistant.calendar import (
        CalendarError,
        load_account_from_env,
        create_event,
    )

    try:
        config = load_account_from_env(account)
        event = create_event(
            config,
            summary=request.summary,
            start=request.start,
            end=request.end,
            description=request.description,
            location=request.location,
            attendees=request.attendees,
            is_all_day=request.is_all_day,
            send_notifications=request.send_notifications,
            calendar_id=request.calendar_id,
        )
    except CalendarError as e:
        raise HTTPException(status_code=502, detail=str(e))

    return {"event": _serialize_calendar_event(event), "created": True}


@router.put("/{account}/events/{event_id}")
def update_event_endpoint(
    account: Literal["church", "personal"],
    event_id: str,
    request: UpdateEventRequest,
    user: str = Depends(get_current_user),
) -> dict:
    """Update an existing calendar event."""
    from daily_task_assistant.calendar import (
        CalendarError,
        load_account_from_env,
        update_event,
    )

    try:
        config = load_account_from_env(account)
        event = update_event(
            config,
            event_id,
            summary=request.summary,
            start=request.start,
            end=request.end,
            description=request.description,
            location=request.location,
            attendees=request.attendees,
            send_notifications=request.send_notifications,
            calendar_id=request.calendar_id,
        )
    except CalendarError as e:
        raise HTTPException(status_code=502, detail=str(e))

    return {"event": _serialize_calendar_event(event), "updated": True}


@router.delete("/{account}/events/{event_id}")
def delete_event_endpoint(
    account: Literal["church", "personal"],
    event_id: str,
    calendar_id: str = Query("primary", alias="calendarId"),
    send_notifications: bool = Query(True, alias="sendNotifications"),
    user: str = Depends(get_current_user),
) -> dict:
    """Delete a calendar event."""
    from daily_task_assistant.calendar import (
        CalendarError,
        load_account_from_env,
        delete_event,
    )

    try:
        config = load_account_from_env(account)
        delete_event(
            config,
            event_id,
            calendar_id=calendar_id,
            send_notifications=send_notifications,
        )
    except CalendarError as e:
        raise HTTPException(status_code=502, detail=str(e))

    return {"deleted": True, "eventId": event_id}


@router.post("/{account}/quick-add")
def quick_add_event_endpoint(
    account: Literal["church", "personal"],
    request: QuickAddEventRequest,
    user: str = Depends(get_current_user),
) -> dict:
    """Create an event using natural language."""
    from daily_task_assistant.calendar import (
        CalendarError,
        load_account_from_env,
        quick_add_event,
    )

    try:
        config = load_account_from_env(account)
        event = quick_add_event(
            config,
            text=request.text,
            calendar_id=request.calendar_id,
            send_notifications=request.send_notifications,
        )
    except CalendarError as e:
        raise HTTPException(status_code=502, detail=str(e))

    return {"event": _serialize_calendar_event(event), "created": True}


# =============================================================================
# Calendar Settings Endpoints
# =============================================================================

@router.get("/{account}/settings")
def get_calendar_settings_endpoint(
    account: Literal["church", "personal"],
    user: str = Depends(get_current_user),
) -> dict:
    """Get calendar settings for an account."""
    from daily_task_assistant.calendar import get_calendar_settings

    settings = get_calendar_settings(account)
    return {
        "enabledCalendars": settings.enabled_calendars,
        "workCalendarId": settings.work_calendar_id,
        "showDeclinedEvents": settings.show_declined_events,
        "showAllDayEvents": settings.show_all_day_events,
        "defaultDaysAhead": settings.default_days_ahead,
    }


@router.put("/{account}/settings")
def update_calendar_settings_endpoint(
    account: Literal["church", "personal"],
    request: UpdateCalendarSettingsRequest,
    user: str = Depends(get_current_user),
) -> dict:
    """Update calendar settings for an account."""
    from daily_task_assistant.calendar import update_calendar_settings

    updates = {}
    if request.enabled_calendars is not None:
        updates["enabled_calendars"] = request.enabled_calendars
    if request.work_calendar_id is not None:
        updates["work_calendar_id"] = request.work_calendar_id
    if request.show_declined_events is not None:
        updates["show_declined_events"] = request.show_declined_events
    if request.show_all_day_events is not None:
        updates["show_all_day_events"] = request.show_all_day_events
    if request.default_days_ahead is not None:
        updates["default_days_ahead"] = request.default_days_ahead

    settings = update_calendar_settings(account, updates)
    return {
        "enabledCalendars": settings.enabled_calendars,
        "workCalendarId": settings.work_calendar_id,
        "showDeclinedEvents": settings.show_declined_events,
        "showAllDayEvents": settings.show_all_day_events,
        "defaultDaysAhead": settings.default_days_ahead,
        "updated": True,
    }


# =============================================================================
# Calendar Attention Endpoints
# =============================================================================

@router.get("/{account}/attention")
def get_calendar_attention_endpoint(
    account: Literal["church", "personal"],
    user: str = Depends(get_current_user),
) -> dict:
    """Get calendar attention items that need action."""
    from daily_task_assistant.calendar import get_calendar_attention

    items = get_calendar_attention(account)
    return {
        "items": [item.to_api_dict() for item in items],
        "count": len(items),
    }


@router.post("/{account}/attention/{event_id}/viewed")
def mark_attention_viewed_endpoint(
    account: Literal["church", "personal"],
    event_id: str,
    user: str = Depends(get_current_user),
) -> dict:
    """Mark a calendar attention item as viewed."""
    from daily_task_assistant.calendar import mark_attention_viewed

    mark_attention_viewed(account, event_id)
    return {"viewed": True, "eventId": event_id}


@router.post("/{account}/attention/{event_id}/dismiss")
def dismiss_attention_endpoint(
    account: Literal["church", "personal"],
    event_id: str,
    user: str = Depends(get_current_user),
) -> dict:
    """Dismiss a calendar attention item."""
    from daily_task_assistant.calendar import dismiss_attention

    dismiss_attention(account, event_id)
    return {"dismissed": True, "eventId": event_id}


@router.post("/{account}/attention/{event_id}/act")
def act_on_attention_endpoint(
    account: Literal["church", "personal"],
    event_id: str,
    user: str = Depends(get_current_user),
) -> dict:
    """Record that action was taken on a calendar attention item."""
    from daily_task_assistant.calendar import act_on_attention

    act_on_attention(account, event_id)
    return {"acted": True, "eventId": event_id}


@router.get("/{account}/attention/quality-metrics")
def get_attention_quality_metrics_endpoint(
    account: Literal["church", "personal"],
    user: str = Depends(get_current_user),
) -> dict:
    """Get quality metrics for calendar attention analysis."""
    from daily_task_assistant.calendar import get_attention_quality_metrics

    metrics = get_attention_quality_metrics(account)
    return metrics


@router.post("/{account}/attention/analyze")
def analyze_calendar_attention_endpoint(
    account: Literal["church", "personal"],
    user: str = Depends(get_current_user),
) -> dict:
    """Run attention analysis on calendar events."""
    from daily_task_assistant.calendar import analyze_calendar_attention

    result = analyze_calendar_attention(account)
    return result


# =============================================================================
# Calendar Chat Endpoints
# =============================================================================

@router.post("/{domain}/chat")
def chat_about_calendar(
    domain: Literal["personal", "church", "work", "combined"],
    request: CalendarChatRequestModel,
    user: str = Depends(get_current_user),
) -> dict:
    """Chat with DATA about calendar and tasks."""
    from daily_task_assistant.calendar.chat import (
        handle_calendar_chat,
        CalendarChatRequest,
        CalendarChatError,
    )
    from daily_task_assistant.calendar.types import (
        CalendarEvent,
        CalendarAttentionRecord,
        EventAttendee,
    )

    # Convert frontend events to CalendarEvent objects
    events = []
    if request.events:
        for evt in request.events:
            try:
                start_dt = datetime.fromisoformat(evt.start.replace("Z", "+00:00"))
                end_dt = datetime.fromisoformat(evt.end.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                start_dt = datetime.now(timezone.utc)
                end_dt = datetime.now(timezone.utc)

            attendees = []
            if evt.attendees:
                for att in evt.attendees:
                    attendees.append(EventAttendee(
                        email=att.get("email", ""),
                        display_name=att.get("displayName"),
                        response_status=att.get("responseStatus"),
                        is_self=att.get("isSelf", False),
                    ))

            events.append(CalendarEvent(
                id=evt.id,
                calendar_id="primary",
                summary=evt.summary,
                start=start_dt,
                end=end_dt,
                location=evt.location,
                attendees=attendees,
                description=evt.description,
                html_link=evt.htmlLink,
                source_domain=evt.sourceDomain or domain,
            ))

    # Convert frontend attention items
    attention_items = []
    if request.attentionItems:
        for item in request.attentionItems:
            try:
                start_dt = datetime.fromisoformat(item.start.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                start_dt = datetime.now(timezone.utc)

            attention_items.append(CalendarAttentionRecord(
                event_id=item.eventId,
                calendar_account=domain if domain != "combined" else "personal",
                calendar_id="primary",
                summary=item.summary,
                start=start_dt,
                end=start_dt,
                attendees=[],
                attention_type=item.attentionType,
                reason=item.reason,
                matched_vip=item.matchedVip,
            ))

    # Parse date range
    date_range_start = None
    date_range_end = None
    if request.dateRangeStart:
        try:
            date_range_start = datetime.fromisoformat(request.dateRangeStart.replace("Z", "+00:00"))
        except ValueError:
            pass
    if request.dateRangeEnd:
        try:
            date_range_end = datetime.fromisoformat(request.dateRangeEnd.replace("Z", "+00:00"))
        except ValueError:
            pass

    # Filter tasks by date range
    filtered_tasks = []
    if request.tasks and date_range_start and date_range_end:
        local_range_start = date_range_start.astimezone(_LOCAL_TZ).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        local_range_end = date_range_end.astimezone(_LOCAL_TZ).replace(
            hour=23, minute=59, second=59, microsecond=999999
        )

        for task in request.tasks:
            due_date_str = task.get("due") or task.get("due_date") or task.get("dueDate")
            if not due_date_str:
                continue
            try:
                if isinstance(due_date_str, str):
                    if "T" in due_date_str:
                        date_part = due_date_str.split("T")[0]
                        task_due = datetime.strptime(date_part, "%Y-%m-%d")
                    else:
                        task_due = datetime.strptime(due_date_str, "%Y-%m-%d")
                    task_due = task_due.replace(tzinfo=_LOCAL_TZ)
                else:
                    continue

                if local_range_start <= task_due <= local_range_end:
                    filtered_tasks.append(task)
            except (ValueError, TypeError):
                continue
    elif request.tasks:
        filtered_tasks = request.tasks

    # Build chat request
    chat_request = CalendarChatRequest(
        message=request.message,
        domain=domain,  # type: ignore
        selected_event_id=request.selectedEventId,
        selected_task_id=request.selectedTaskId,
        date_range_start=date_range_start,
        date_range_end=date_range_end,
        events=events,
        attention_items=attention_items,
        tasks=filtered_tasks,
        history=request.history,
    )

    try:
        response = handle_calendar_chat(chat_request, user_email=user)
    except CalendarChatError as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {
        "response": response.message,
        "toolResults": response.tool_results,
        "tasksUpdated": response.tasks_updated,
        "eventsCreated": response.events_created,
        "eventsUpdated": response.events_updated,
        "eventsDeleted": response.events_deleted,
    }


@router.get("/{domain}/conversation")
def get_calendar_conversation(
    domain: Literal["personal", "church", "work", "combined"],
    user: str = Depends(get_current_user),
) -> dict:
    """Get conversation history for a calendar domain."""
    from daily_task_assistant.conversations.calendar_history import get_conversation

    history = get_conversation(domain)
    return {
        "history": history,
        "domain": domain,
    }


@router.delete("/{domain}/conversation")
def clear_calendar_conversation(
    domain: Literal["personal", "church", "work", "combined"],
    user: str = Depends(get_current_user),
) -> dict:
    """Clear conversation history for a calendar domain."""
    from daily_task_assistant.conversations.calendar_history import clear_conversation

    clear_conversation(domain)
    return {"cleared": True, "domain": domain}


@router.put("/{domain}/conversation")
def update_calendar_conversation(
    domain: Literal["personal", "church", "work", "combined"],
    request: UpdateCalendarConversationRequest,
    user: str = Depends(get_current_user),
) -> dict:
    """Update conversation history for a calendar domain."""
    from daily_task_assistant.conversations.calendar_history import save_conversation

    save_conversation(domain, request.history)
    return {"updated": True, "domain": domain, "messageCount": len(request.history)}
