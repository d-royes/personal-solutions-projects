"""Calendar integration module for DATA.

This module provides Google Calendar integration, including:
- Calendar list and event operations
- Calendar settings persistence
- View filtering (Personal, Work, Church, Combined)

Storage follows ACCOUNT-based keying (church/personal) to prevent
data fragmentation across David's two Google accounts.
"""
from __future__ import annotations

from .types import (
    CalendarInfo,
    CalendarEvent,
    EventAttendee,
    CalendarSettings,
    CalendarListResponse,
    EventListResponse,
)

from .google_calendar import (
    CalendarError,
    CalendarAccountConfig,
    load_account_from_env,
    list_calendars,
    get_calendar,
    list_events,
    get_event,
    create_event,
    update_event,
    delete_event,
    quick_add_event,
)

from .calendar_store import (
    get_calendar_settings,
    save_calendar_settings,
    DEFAULT_CALENDAR_SETTINGS,
)


__all__ = [
    # Types
    "CalendarInfo",
    "CalendarEvent",
    "EventAttendee",
    "CalendarSettings",
    "CalendarListResponse",
    "EventListResponse",
    # API Client
    "CalendarError",
    "CalendarAccountConfig",
    "load_account_from_env",
    "list_calendars",
    "get_calendar",
    "list_events",
    "get_event",
    "create_event",
    "update_event",
    "delete_event",
    "quick_add_event",
    # Settings Store
    "get_calendar_settings",
    "save_calendar_settings",
    "DEFAULT_CALENDAR_SETTINGS",
]
