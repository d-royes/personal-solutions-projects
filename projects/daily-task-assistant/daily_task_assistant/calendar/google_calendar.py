"""Google Calendar API client."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, List, Literal
from urllib import error as urlerror
from urllib import parse as urlparse
from urllib import request as urlrequest

from .types import (
    CalendarInfo,
    CalendarEvent,
    EventAttendee,
    CalendarListResponse,
    EventListResponse,
)


TOKEN_URL = "https://oauth2.googleapis.com/token"
CALENDAR_API_BASE = "https://www.googleapis.com/calendar/v3"


class CalendarError(RuntimeError):
    """Raised when Calendar API operations fail."""


@dataclass(slots=True)
class CalendarAccountConfig:
    """Google Calendar OAuth configuration."""

    name: str  # "personal" or "church"
    client_id: str
    client_secret: str
    refresh_token: str
    user_email: str  # Used for identifying "self" in attendees

    # Optional: specific calendar IDs to use for this account
    # If None, will discover calendars from API
    calendar_ids: Optional[List[str]] = None


def load_account_from_env(name: str) -> CalendarAccountConfig:
    """Load Calendar account credentials from environment variables.

    First tries CALENDAR-specific env vars, then falls back to GMAIL env vars
    (since they may share the same OAuth client with Calendar scopes).

    Args:
        name: Account name ("personal" or "church")

    Returns:
        CalendarAccountConfig with credentials
    """
    prefix = name.upper()

    # Try CALENDAR-specific first, fall back to GMAIL
    client_id = os.getenv(f"{prefix}_CALENDAR_CLIENT_ID") or os.getenv(
        f"{prefix}_GMAIL_CLIENT_ID"
    )
    client_secret = os.getenv(f"{prefix}_CALENDAR_CLIENT_SECRET") or os.getenv(
        f"{prefix}_GMAIL_CLIENT_SECRET"
    )
    # For refresh token, prefer CALENDAR-specific (may have different scopes)
    # but fall back to GMAIL if CALENDAR not set
    refresh_token = os.getenv(f"{prefix}_CALENDAR_REFRESH_TOKEN") or os.getenv(
        f"{prefix}_GMAIL_REFRESH_TOKEN"
    )
    user_email = os.getenv(f"{prefix}_CALENDAR_ADDRESS") or os.getenv(
        f"{prefix}_GMAIL_ADDRESS"
    )

    missing = [
        label
        for label, value in [
            ("CLIENT_ID", client_id),
            ("CLIENT_SECRET", client_secret),
            ("REFRESH_TOKEN", refresh_token),
            ("ADDRESS/EMAIL", user_email),
        ]
        if not value
    ]
    if missing:
        raise CalendarError(
            f"Missing Calendar env vars for account '{name}': {', '.join(missing)}. "
            f"Set {prefix}_CALENDAR_* or {prefix}_GMAIL_* env vars."
        )

    return CalendarAccountConfig(
        name=name,
        client_id=client_id,
        client_secret=client_secret,
        refresh_token=refresh_token,
        user_email=user_email,
    )


def _fetch_access_token(account: CalendarAccountConfig) -> str:
    """Get a fresh access token using the refresh token."""
    payload = urlparse.urlencode(
        {
            "client_id": account.client_id,
            "client_secret": account.client_secret,
            "refresh_token": account.refresh_token,
            "grant_type": "refresh_token",
        }
    ).encode("utf-8")

    req = urlrequest.Request(
        TOKEN_URL,
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )

    try:
        with urlrequest.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urlerror.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise CalendarError(
            f"Calendar token request failed ({exc.code}): {detail}"
        ) from exc
    except urlerror.URLError as exc:
        raise CalendarError(f"Calendar token network error: {exc}") from exc

    token = data.get("access_token")
    if not token:
        raise CalendarError("Calendar token response missing access_token.")
    return str(token)


def _make_request(
    account: CalendarAccountConfig,
    endpoint: str,
    method: str = "GET",
    params: Optional[dict] = None,
    body: Optional[dict] = None,
) -> dict:
    """Make an authenticated request to the Calendar API."""
    access_token = _fetch_access_token(account)

    url = f"{CALENDAR_API_BASE}{endpoint}"
    if params:
        url = f"{url}?{urlparse.urlencode(params)}"

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    data = json.dumps(body).encode("utf-8") if body else None
    req = urlrequest.Request(url, data=data, headers=headers, method=method)

    try:
        with urlrequest.urlopen(req, timeout=30) as resp:
            if resp.status == 204:  # No content
                return {}
            return json.loads(resp.read().decode("utf-8"))
    except urlerror.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise CalendarError(
            f"Calendar API request failed ({exc.code}): {detail}"
        ) from exc
    except urlerror.URLError as exc:
        raise CalendarError(f"Calendar API network error: {exc}") from exc


# ============================================================================
# Calendar List Operations
# ============================================================================


def list_calendars(
    account: CalendarAccountConfig,
    show_hidden: bool = False,
) -> CalendarListResponse:
    """List all calendars accessible by this account.

    Args:
        account: Calendar account configuration
        show_hidden: Include hidden calendars

    Returns:
        CalendarListResponse with list of calendars
    """
    params = {
        "showHidden": str(show_hidden).lower(),
    }

    response = _make_request(account, "/users/me/calendarList", params=params)

    calendars = []
    for item in response.get("items", []):
        calendars.append(
            CalendarInfo(
                id=item["id"],
                summary=item.get("summary", item["id"]),
                description=item.get("description"),
                color_id=item.get("colorId"),
                background_color=item.get("backgroundColor"),
                foreground_color=item.get("foregroundColor"),
                is_primary=item.get("primary", False),
                access_role=item.get("accessRole", "reader"),
            )
        )

    return CalendarListResponse(
        calendars=calendars,
        next_page_token=response.get("nextPageToken"),
    )


def get_calendar(account: CalendarAccountConfig, calendar_id: str) -> CalendarInfo:
    """Get details for a specific calendar.

    Args:
        account: Calendar account configuration
        calendar_id: Calendar ID (or "primary" for the user's primary calendar)

    Returns:
        CalendarInfo for the specified calendar
    """
    encoded_id = urlparse.quote(calendar_id, safe="")
    response = _make_request(account, f"/users/me/calendarList/{encoded_id}")

    return CalendarInfo(
        id=response["id"],
        summary=response.get("summary", response["id"]),
        description=response.get("description"),
        color_id=response.get("colorId"),
        background_color=response.get("backgroundColor"),
        foreground_color=response.get("foregroundColor"),
        is_primary=response.get("primary", False),
        access_role=response.get("accessRole", "reader"),
    )


# ============================================================================
# Event Operations
# ============================================================================


def _parse_event(
    item: dict,
    calendar_id: str,
    user_email: str,
    source_domain: str = "personal",
) -> CalendarEvent:
    """Parse a Google Calendar API event response into CalendarEvent."""

    # Parse start/end times
    start_data = item.get("start", {})
    end_data = item.get("end", {})

    is_all_day = "date" in start_data

    if is_all_day:
        # All-day events have date only (no time)
        start = datetime.fromisoformat(start_data["date"])
        end = datetime.fromisoformat(end_data["date"])
        start_tz = None
        end_tz = None
    else:
        # Timed events have dateTime
        start_str = start_data.get("dateTime", "")
        end_str = end_data.get("dateTime", "")
        start = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
        end = datetime.fromisoformat(end_str.replace("Z", "+00:00"))
        start_tz = start_data.get("timeZone")
        end_tz = end_data.get("timeZone")

    # Parse attendees
    attendees = []
    for att in item.get("attendees", []):
        attendees.append(
            EventAttendee(
                email=att.get("email", ""),
                display_name=att.get("displayName"),
                response_status=att.get("responseStatus", "needsAction"),
                is_organizer=att.get("organizer", False),
                is_self=att.get("self", False)
                or att.get("email", "").lower() == user_email.lower(),
            )
        )

    # Parse created/updated times
    created = None
    if item.get("created"):
        created = datetime.fromisoformat(
            item["created"].replace("Z", "+00:00")
        )

    updated = None
    if item.get("updated"):
        updated = datetime.fromisoformat(
            item["updated"].replace("Z", "+00:00")
        )

    return CalendarEvent(
        id=item["id"],
        calendar_id=calendar_id,
        summary=item.get("summary", "(No title)"),
        start=start,
        end=end,
        description=item.get("description"),
        location=item.get("location"),
        color_id=item.get("colorId"),
        start_timezone=start_tz,
        end_timezone=end_tz,
        is_all_day=is_all_day,
        status=item.get("status", "confirmed"),
        attendees=attendees,
        organizer_email=item.get("organizer", {}).get("email"),
        creator_email=item.get("creator", {}).get("email"),
        recurring_event_id=item.get("recurringEventId"),
        recurrence=item.get("recurrence"),
        html_link=item.get("htmlLink"),
        hangout_link=item.get("hangoutLink"),
        created=created,
        updated=updated,
        source_domain=source_domain,
    )


def list_events(
    account: CalendarAccountConfig,
    calendar_id: str = "primary",
    *,
    time_min: Optional[datetime] = None,
    time_max: Optional[datetime] = None,
    max_results: int = 100,
    single_events: bool = True,
    order_by: Literal["startTime", "updated"] = "startTime",
    page_token: Optional[str] = None,
    source_domain: str = "personal",
) -> EventListResponse:
    """List events from a calendar.

    Args:
        account: Calendar account configuration
        calendar_id: Calendar ID (or "primary")
        time_min: Lower bound for event start time (defaults to now)
        time_max: Upper bound for event start time
        max_results: Maximum events to return (1-2500)
        single_events: If True, expand recurring events into instances
        order_by: Sort order ("startTime" requires single_events=True)
        page_token: Token for pagination
        source_domain: Domain label for events ("personal", "work", "church")

    Returns:
        EventListResponse with events and pagination token
    """
    if time_min is None:
        time_min = datetime.now(timezone.utc)

    params = {
        "maxResults": str(min(max_results, 2500)),
        "singleEvents": str(single_events).lower(),
        "timeMin": time_min.isoformat(),
    }

    if time_max:
        params["timeMax"] = time_max.isoformat()

    if single_events:
        params["orderBy"] = order_by

    if page_token:
        params["pageToken"] = page_token

    encoded_id = urlparse.quote(calendar_id, safe="")
    response = _make_request(account, f"/calendars/{encoded_id}/events", params=params)

    events = []
    for item in response.get("items", []):
        # Skip cancelled events
        if item.get("status") == "cancelled":
            continue
        events.append(
            _parse_event(item, calendar_id, account.user_email, source_domain)
        )

    return EventListResponse(
        events=events,
        next_page_token=response.get("nextPageToken"),
        next_sync_token=response.get("nextSyncToken"),
    )


def get_event(
    account: CalendarAccountConfig,
    calendar_id: str,
    event_id: str,
    source_domain: str = "personal",
) -> CalendarEvent:
    """Get a specific event by ID.

    Args:
        account: Calendar account configuration
        calendar_id: Calendar ID
        event_id: Event ID
        source_domain: Domain label for the event

    Returns:
        CalendarEvent for the specified event
    """
    encoded_cal_id = urlparse.quote(calendar_id, safe="")
    encoded_event_id = urlparse.quote(event_id, safe="")

    response = _make_request(
        account, f"/calendars/{encoded_cal_id}/events/{encoded_event_id}"
    )

    return _parse_event(response, calendar_id, account.user_email, source_domain)


# ============================================================================
# Event Write Operations
# ============================================================================


def create_event(
    account: CalendarAccountConfig,
    calendar_id: str,
    *,
    summary: str,
    start: datetime,
    end: datetime,
    description: Optional[str] = None,
    location: Optional[str] = None,
    attendees: Optional[List[str]] = None,
    is_all_day: bool = False,
    send_notifications: bool = True,
    source_domain: str = "personal",
) -> CalendarEvent:
    """Create a new calendar event.

    Args:
        account: Calendar account configuration
        calendar_id: Calendar ID to create event in
        summary: Event title
        start: Start time
        end: End time
        description: Event description
        location: Event location
        attendees: List of attendee email addresses
        is_all_day: Whether this is an all-day event
        send_notifications: Whether to send notifications to attendees
        source_domain: Domain label for the event

    Returns:
        Created CalendarEvent
    """
    body: dict = {
        "summary": summary,
    }

    if is_all_day:
        body["start"] = {"date": start.strftime("%Y-%m-%d")}
        body["end"] = {"date": end.strftime("%Y-%m-%d")}
    else:
        body["start"] = {"dateTime": start.isoformat()}
        body["end"] = {"dateTime": end.isoformat()}

    if description:
        body["description"] = description

    if location:
        body["location"] = location

    if attendees:
        body["attendees"] = [{"email": email} for email in attendees]

    params = {"sendNotifications": str(send_notifications).lower()}

    encoded_id = urlparse.quote(calendar_id, safe="")
    response = _make_request(
        account,
        f"/calendars/{encoded_id}/events",
        method="POST",
        params=params,
        body=body,
    )

    return _parse_event(response, calendar_id, account.user_email, source_domain)


def update_event(
    account: CalendarAccountConfig,
    calendar_id: str,
    event_id: str,
    *,
    summary: Optional[str] = None,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    description: Optional[str] = None,
    location: Optional[str] = None,
    send_notifications: bool = True,
    source_domain: str = "personal",
) -> CalendarEvent:
    """Update an existing calendar event.

    Args:
        account: Calendar account configuration
        calendar_id: Calendar ID
        event_id: Event ID to update
        summary: New event title (if changing)
        start: New start time (if changing)
        end: New end time (if changing)
        description: New description (if changing)
        location: New location (if changing)
        send_notifications: Whether to send notifications to attendees
        source_domain: Domain label for the event

    Returns:
        Updated CalendarEvent
    """
    # First get the existing event
    existing = get_event(account, calendar_id, event_id, source_domain)

    # Build update body (patch)
    body: dict = {}

    if summary is not None:
        body["summary"] = summary

    if start is not None:
        if existing.is_all_day:
            body["start"] = {"date": start.strftime("%Y-%m-%d")}
        else:
            body["start"] = {"dateTime": start.isoformat()}

    if end is not None:
        if existing.is_all_day:
            body["end"] = {"date": end.strftime("%Y-%m-%d")}
        else:
            body["end"] = {"dateTime": end.isoformat()}

    if description is not None:
        body["description"] = description

    if location is not None:
        body["location"] = location

    if not body:
        # Nothing to update
        return existing

    params = {"sendNotifications": str(send_notifications).lower()}

    encoded_cal_id = urlparse.quote(calendar_id, safe="")
    encoded_event_id = urlparse.quote(event_id, safe="")

    response = _make_request(
        account,
        f"/calendars/{encoded_cal_id}/events/{encoded_event_id}",
        method="PATCH",
        params=params,
        body=body,
    )

    return _parse_event(response, calendar_id, account.user_email, source_domain)


def delete_event(
    account: CalendarAccountConfig,
    calendar_id: str,
    event_id: str,
    send_notifications: bool = True,
) -> bool:
    """Delete a calendar event.

    Args:
        account: Calendar account configuration
        calendar_id: Calendar ID
        event_id: Event ID to delete
        send_notifications: Whether to send notifications to attendees

    Returns:
        True if deleted successfully
    """
    params = {"sendNotifications": str(send_notifications).lower()}

    encoded_cal_id = urlparse.quote(calendar_id, safe="")
    encoded_event_id = urlparse.quote(event_id, safe="")

    _make_request(
        account,
        f"/calendars/{encoded_cal_id}/events/{encoded_event_id}",
        method="DELETE",
        params=params,
    )

    return True


# ============================================================================
# Quick Add (Natural Language)
# ============================================================================


def quick_add_event(
    account: CalendarAccountConfig,
    calendar_id: str,
    text: str,
    send_notifications: bool = True,
    source_domain: str = "personal",
) -> CalendarEvent:
    """Create an event using natural language.

    Google Calendar will parse the text to create an event.
    Example: "Meeting with Doug tomorrow at 2pm"

    Args:
        account: Calendar account configuration
        calendar_id: Calendar ID to create event in
        text: Natural language description of the event
        send_notifications: Whether to send notifications
        source_domain: Domain label for the event

    Returns:
        Created CalendarEvent
    """
    params = {
        "text": text,
        "sendNotifications": str(send_notifications).lower(),
    }

    encoded_id = urlparse.quote(calendar_id, safe="")
    response = _make_request(
        account,
        f"/calendars/{encoded_id}/events/quickAdd",
        method="POST",
        params=params,
    )

    return _parse_event(response, calendar_id, account.user_email, source_domain)
