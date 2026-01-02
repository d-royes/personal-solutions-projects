"""Calendar data types."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List


@dataclass(slots=True)
class CalendarInfo:
    """Google Calendar metadata."""

    id: str
    summary: str  # Display name
    description: Optional[str] = None
    color_id: Optional[str] = None
    background_color: Optional[str] = None
    foreground_color: Optional[str] = None
    is_primary: bool = False
    access_role: str = "reader"  # "owner", "writer", "reader", "freeBusyReader"

    @property
    def is_writable(self) -> bool:
        """Check if calendar can be modified."""
        return self.access_role in ("owner", "writer")


@dataclass(slots=True)
class EventAttendee:
    """Calendar event attendee."""

    email: str
    display_name: Optional[str] = None
    response_status: str = "needsAction"  # "needsAction", "declined", "tentative", "accepted"
    is_organizer: bool = False
    is_self: bool = False


@dataclass(slots=True)
class CalendarEvent:
    """Google Calendar event."""

    id: str
    calendar_id: str
    summary: str  # Event title
    start: datetime
    end: datetime

    # Optional fields
    description: Optional[str] = None
    location: Optional[str] = None
    color_id: Optional[str] = None

    # Time zone info
    start_timezone: Optional[str] = None
    end_timezone: Optional[str] = None
    is_all_day: bool = False

    # Status
    status: str = "confirmed"  # "confirmed", "tentative", "cancelled"

    # Attendees
    attendees: List[EventAttendee] = field(default_factory=list)
    organizer_email: Optional[str] = None
    creator_email: Optional[str] = None

    # Recurrence
    recurring_event_id: Optional[str] = None
    recurrence: Optional[List[str]] = None  # RRULE strings

    # Links
    html_link: Optional[str] = None
    hangout_link: Optional[str] = None

    # Metadata
    created: Optional[datetime] = None
    updated: Optional[datetime] = None

    # DATA-specific fields
    source_domain: str = "personal"  # "personal", "work", "church"

    @property
    def is_meeting(self) -> bool:
        """Check if event is a meeting.

        Detection methods:
        1. Has multiple attendees (native Google Calendar events)
        2. Has meeting indicators in description/location (for imported calendars
           like O365 that don't include attendee data when shared)
        """
        # Method 1: Multiple attendees (most reliable)
        if len(self.attendees) > 1:
            return True

        # Exclusions: Known non-meeting event types that may contain meeting links
        exclusion_patterns = [
            "focus time",
            "viva insights",
            "out of office",
        ]
        summary_lower = (self.summary or "").lower()
        desc_lower = (self.description or "").lower()
        for pattern in exclusion_patterns:
            if pattern in summary_lower or pattern in desc_lower:
                return False

        # Method 2: Meeting indicators for imported calendars (O365 -> Google)
        # These events lose attendee data but retain meeting links/descriptions
        meeting_indicators = [
            "teams.microsoft.com/l/meetup-join",  # More specific Teams meeting link
            "zoom.us/j/",  # Zoom meeting link
            "meet.google.com/",  # Google Meet link
            "webex.com/meet",  # WebEx meeting link
            "Join the meeting",
            "Meeting ID:",
            "Dial in by phone",
        ]

        text_to_check = f"{self.description or ''} {self.location or ''}".lower()
        for indicator in meeting_indicators:
            if indicator.lower() in text_to_check:
                return True

        return False

    @property
    def attendee_count(self) -> int:
        """Number of attendees."""
        return len(self.attendees)

    @property
    def attendee_emails(self) -> List[str]:
        """List of attendee email addresses."""
        return [a.email for a in self.attendees]

    @property
    def duration_minutes(self) -> int:
        """Event duration in minutes."""
        delta = self.end - self.start
        return int(delta.total_seconds() / 60)


@dataclass(slots=True)
class CalendarSettings:
    """User's calendar display settings for DATA."""

    # Which calendars to show (by calendar ID)
    enabled_calendars: List[str] = field(default_factory=list)

    # Work calendar designation (calendar ID that represents "work")
    work_calendar_id: Optional[str] = None

    # Display preferences
    show_declined_events: bool = False
    show_all_day_events: bool = True

    # Default view range (days)
    default_days_ahead: int = 14

    # Last sync time
    last_synced_at: Optional[datetime] = None


@dataclass(slots=True)
class CalendarListResponse:
    """Response from listing calendars."""

    calendars: List[CalendarInfo]
    next_page_token: Optional[str] = None


@dataclass(slots=True)
class EventListResponse:
    """Response from listing events."""

    events: List[CalendarEvent]
    next_page_token: Optional[str] = None
    next_sync_token: Optional[str] = None
