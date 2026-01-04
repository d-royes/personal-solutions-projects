"""Calendar data types."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Literal, Optional, List


# Type aliases for attention tracking (Phase CA-1)
CalendarAttentionType = Literal[
    "vip_meeting",
    "prep_needed",
    "task_conflict",
    "overcommitment",
]
CalendarAttentionStatus = Literal["active", "dismissed", "acted", "expired"]
CalendarActionType = Literal["viewed", "dismissed", "task_linked", "prep_started"]


def _now() -> datetime:
    """Return current UTC datetime."""
    return datetime.now(timezone.utc)


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

    # Capacity threshold for overcommitment warnings (Phase CA-1)
    max_meetings_per_day: int = 5

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


# =============================================================================
# Phase CA-1: Calendar Attention Record
# =============================================================================


@dataclass
class CalendarAttentionRecord:
    """Persistent calendar attention item.

    Represents a calendar event that has been flagged as requiring David's
    attention. Follows the same pattern as email AttentionRecord for consistency.

    Extended with Phase 1A action tracking fields to support:
    - User action tracking for acceptance rate measurement
    - Quality metrics for calibration
    """
    # Identity
    event_id: str
    calendar_account: str  # "personal", "church", "work"
    calendar_id: str

    # Event snapshot
    summary: str
    start: datetime
    end: datetime
    attendees: List[str] = field(default_factory=list)
    location: Optional[str] = None
    html_link: Optional[str] = None

    # Attention analysis
    attention_type: CalendarAttentionType = "prep_needed"
    reason: str = ""
    confidence: float = 0.5
    matched_vip: Optional[str] = None

    # Status
    status: CalendarAttentionStatus = "active"
    dismissed_at: Optional[datetime] = None

    # Phase 1A: Action tracking for quality metrics
    first_viewed_at: Optional[datetime] = None
    action_taken_at: Optional[datetime] = None
    action_type: Optional[CalendarActionType] = None

    # Metadata
    created_at: datetime = field(default_factory=_now)
    expires_at: Optional[datetime] = None

    def __post_init__(self):
        """Set default expires_at based on event end time."""
        if self.expires_at is None:
            self.expires_at = self.end + timedelta(hours=1)

    def is_expired(self) -> bool:
        """Check if this record has expired."""
        if self.expires_at is None:
            return False
        return _now() > self.expires_at

    def to_dict(self) -> Dict[str, Any]:
        """Convert record to dictionary for storage."""
        def dt_to_str(dt: Optional[datetime]) -> Optional[str]:
            return dt.isoformat() if dt else None

        return {
            "event_id": self.event_id,
            "calendar_account": self.calendar_account,
            "calendar_id": self.calendar_id,
            "summary": self.summary,
            "start": dt_to_str(self.start),
            "end": dt_to_str(self.end),
            "attendees": self.attendees,
            "location": self.location,
            "html_link": self.html_link,
            "attention_type": self.attention_type,
            "reason": self.reason,
            "confidence": self.confidence,
            "matched_vip": self.matched_vip,
            "status": self.status,
            "dismissed_at": dt_to_str(self.dismissed_at),
            "first_viewed_at": dt_to_str(self.first_viewed_at),
            "action_taken_at": dt_to_str(self.action_taken_at),
            "action_type": self.action_type,
            "created_at": dt_to_str(self.created_at),
            "expires_at": dt_to_str(self.expires_at),
        }

    def to_api_dict(self) -> Dict[str, Any]:
        """Convert to API-friendly dict (camelCase for JavaScript)."""
        def dt_to_str(dt: Optional[datetime]) -> Optional[str]:
            return dt.isoformat() if dt else None

        return {
            "eventId": self.event_id,
            "calendarAccount": self.calendar_account,
            "calendarId": self.calendar_id,
            "summary": self.summary,
            "start": dt_to_str(self.start),
            "end": dt_to_str(self.end),
            "attendees": self.attendees,
            "location": self.location,
            "htmlLink": self.html_link,
            "attentionType": self.attention_type,
            "reason": self.reason,
            "confidence": self.confidence,
            "matchedVip": self.matched_vip,
            "status": self.status,
            "dismissedAt": dt_to_str(self.dismissed_at),
            "firstViewedAt": dt_to_str(self.first_viewed_at),
            "actionTakenAt": dt_to_str(self.action_taken_at),
            "actionType": self.action_type,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CalendarAttentionRecord":
        """Create record from dictionary."""
        def str_to_dt(s: Optional[str]) -> Optional[datetime]:
            if s is None:
                return None
            return datetime.fromisoformat(s)

        return cls(
            event_id=data["event_id"],
            calendar_account=data["calendar_account"],
            calendar_id=data["calendar_id"],
            summary=data["summary"],
            start=str_to_dt(data["start"]) or _now(),
            end=str_to_dt(data["end"]) or _now(),
            attendees=data.get("attendees", []),
            location=data.get("location"),
            html_link=data.get("html_link"),
            attention_type=data.get("attention_type", "prep_needed"),
            reason=data.get("reason", ""),
            confidence=data.get("confidence", 0.5),
            matched_vip=data.get("matched_vip"),
            status=data.get("status", "active"),
            dismissed_at=str_to_dt(data.get("dismissed_at")),
            first_viewed_at=str_to_dt(data.get("first_viewed_at")),
            action_taken_at=str_to_dt(data.get("action_taken_at")),
            action_type=data.get("action_type"),
            created_at=str_to_dt(data.get("created_at")) or _now(),
            expires_at=str_to_dt(data.get("expires_at")),
        )
