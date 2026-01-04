"""Calendar context builder for DATA chat.

This module builds the context string that DATA sees when chatting about calendar.
It formats events, attention items, and tasks into a structured prompt.

Note: Task due dates are LOCAL dates, not UTC. No timezone conversion needed.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional
from zoneinfo import ZoneInfo

from .types import CalendarEvent, CalendarAttentionRecord


DomainType = Literal["personal", "church", "work", "combined"]

# David's timezone - all times displayed to DATA should be in this timezone
_LOCAL_TZ = ZoneInfo("America/New_York")


def _to_local(dt: datetime) -> datetime:
    """Convert datetime to local timezone (Eastern Time).

    This ensures DATA sees times in David's timezone, not UTC.
    """
    if dt.tzinfo is None:
        # Assume naive datetimes are UTC
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(_LOCAL_TZ)


def _now() -> datetime:
    """Return current datetime in local timezone."""
    return datetime.now(_LOCAL_TZ)


def _format_datetime(dt: datetime) -> str:
    """Format datetime for display in local timezone."""
    local_dt = _to_local(dt)
    return local_dt.strftime("%a %b %d, %Y at %I:%M %p")


def _format_date(dt: datetime) -> str:
    """Format date only in local timezone."""
    local_dt = _to_local(dt)
    return local_dt.strftime("%a %b %d, %Y")


def _format_time(dt: datetime) -> str:
    """Format time only in local timezone."""
    local_dt = _to_local(dt)
    return local_dt.strftime("%I:%M %p")


def _format_duration(minutes: int) -> str:
    """Format duration in human-readable form."""
    if minutes < 60:
        return f"{minutes} min"
    hours = minutes // 60
    mins = minutes % 60
    if mins == 0:
        return f"{hours}h"
    return f"{hours}h {mins}m"


@dataclass
class CalendarChatContext:
    """Context for calendar chat with DATA.

    Attributes:
        domain: The calendar domain (personal, church, work, combined)
        events: List of events in the current view
        attention_items: Active attention items (VIP meetings, prep needed)
        tasks: Tasks from the Task tab (with calendar-relevant fields)
        selected_event: The currently selected event, if any
        selected_task: The currently selected task, if any
        date_range_start: Start of the view range
        date_range_end: End of the view range
    """
    domain: DomainType
    events: List[CalendarEvent]
    attention_items: List[CalendarAttentionRecord]
    tasks: List[Dict[str, Any]]
    selected_event: Optional[CalendarEvent] = None
    selected_task: Optional[Dict[str, Any]] = None
    date_range_start: Optional[datetime] = None
    date_range_end: Optional[datetime] = None

    def to_context_string(self) -> str:
        """Build the context string for DATA's system prompt."""
        parts = []

        # Header
        now = _now()
        parts.append(f"Current Time: {_format_datetime(now)}")
        parts.append(f"Domain: {self.domain.title()}")

        if self.date_range_start and self.date_range_end:
            parts.append(f"Viewing: {_format_date(self.date_range_start)} to {_format_date(self.date_range_end)}")

        parts.append("")

        # Selected event (if any)
        if self.selected_event:
            parts.append("=== SELECTED EVENT ===")
            parts.append(self._format_event_detail(self.selected_event))
            parts.append("")

        # Selected task (if any)
        if self.selected_task:
            parts.append("=== SELECTED TASK ===")
            parts.append(self._format_task_detail(self.selected_task))
            parts.append("")

        # Attention items
        if self.attention_items:
            parts.append("=== ATTENTION ITEMS ===")
            for item in self.attention_items:
                parts.append(self._format_attention_item(item))
            parts.append("")

        # Events summary
        if self.events:
            parts.append(f"=== CALENDAR EVENTS ({len(self.events)} events) ===")

            # Group by date
            events_by_date: Dict[str, List[CalendarEvent]] = {}
            for event in self.events:
                date_key = _format_date(event.start)
                if date_key not in events_by_date:
                    events_by_date[date_key] = []
                events_by_date[date_key].append(event)

            for date_key, day_events in events_by_date.items():
                parts.append(f"\n{date_key}:")
                for event in day_events:
                    parts.append(self._format_event_brief(event))
            parts.append("")
        else:
            parts.append("=== CALENDAR EVENTS ===")
            parts.append("No events in this view.")
            parts.append("")

        # Tasks
        if self.tasks:
            parts.append(f"=== TASKS ({len(self.tasks)} tasks) ===")
            for task in self.tasks:
                parts.append(self._format_task(task))
            parts.append("")

        return "\n".join(parts)

    def _format_event_brief(self, event: CalendarEvent) -> str:
        """Format event as a brief one-liner."""
        time_str = _format_time(event.start)
        duration = _format_duration(event.duration_minutes)

        meeting_indicator = "[Meeting]" if event.is_meeting else ""
        attendee_count = f"({event.attendee_count} attendees)" if event.attendee_count > 1 else ""

        parts = [f"  - {time_str} ({duration}): {event.summary}"]
        if meeting_indicator:
            parts.append(meeting_indicator)
        if attendee_count:
            parts.append(attendee_count)
        if event.location:
            parts.append(f"@ {event.location}")

        return " ".join(parts)

    def _format_event_detail(self, event: CalendarEvent) -> str:
        """Format event with full details."""
        lines = []
        lines.append(f"Title: {event.summary}")
        lines.append(f"Event ID: {event.id}")  # Required for update/delete actions
        lines.append(f"When: {_format_datetime(event.start)} - {_format_time(event.end)}")
        lines.append(f"Duration: {_format_duration(event.duration_minutes)}")

        if event.location:
            lines.append(f"Location: {event.location}")

        if event.is_meeting:
            lines.append(f"Type: Meeting")
            if event.attendees:
                attendee_list = []
                for a in event.attendees[:5]:  # Limit to 5
                    name = a.display_name or a.email
                    status = f"({a.response_status})" if a.response_status != "accepted" else ""
                    attendee_list.append(f"{name} {status}".strip())
                lines.append(f"Attendees: {', '.join(attendee_list)}")
                if len(event.attendees) > 5:
                    lines.append(f"  ... and {len(event.attendees) - 5} more")

        if event.description:
            # Truncate long descriptions
            desc = event.description[:500]
            if len(event.description) > 500:
                desc += "..."
            lines.append(f"Description: {desc}")

        if event.html_link:
            lines.append(f"Link: {event.html_link}")

        lines.append(f"Domain: {event.source_domain}")

        return "\n".join(lines)

    def _format_attention_item(self, item: CalendarAttentionRecord) -> str:
        """Format attention item."""
        lines = []
        type_label = {
            "vip_meeting": "VIP Meeting",
            "prep_needed": "Prep Needed",
            "task_conflict": "Task Conflict",
            "overcommitment": "Overcommitment",
        }.get(item.attention_type, item.attention_type)

        lines.append(f"  [{type_label}] {item.summary}")
        lines.append(f"    When: {_format_datetime(item.start)}")
        lines.append(f"    Reason: {item.reason}")
        if item.matched_vip:
            lines.append(f"    VIP: {item.matched_vip}")

        return "\n".join(lines)

    def _format_task(self, task: Dict[str, Any]) -> str:
        """Format task from Task tab."""
        title = task.get("task") or task.get("title") or "Untitled"
        status = task.get("status", "Unknown")
        # Handle multiple due date field names (due, due_date, dueDate)
        due_date = task.get("due") or task.get("due_date") or task.get("dueDate")
        priority = task.get("priority", "Standard")
        domain = task.get("domain", "personal")
        row_id = task.get("row_id") or task.get("rowId")

        # Format due date - parse and format for human readability
        # NOTE: Due dates are LOCAL dates (not UTC timestamps). A due date of
        # 2026-01-06T00:00:00 means "January 6th" in David's timezone, NOT
        # "midnight UTC on Jan 6th" (which would be 7pm EST on Jan 5th).
        due_str = ""
        if due_date:
            if isinstance(due_date, str):
                try:
                    # Parse ISO format - treat as LOCAL time, not UTC
                    if "T" in due_date:
                        # Remove any timezone suffix and treat as local date
                        date_part = due_date.split("T")[0]  # Get just YYYY-MM-DD
                        parsed = datetime.strptime(date_part, "%Y-%m-%d")
                        # Format directly without timezone conversion
                        due_str = parsed.strftime("%a %b %d, %Y")
                    else:
                        # Already date-only, parse and format
                        parsed = datetime.strptime(due_date, "%Y-%m-%d")
                        due_str = parsed.strftime("%a %b %d, %Y")
                except (ValueError, TypeError):
                    # Fall back to raw string if parsing fails
                    due_str = due_date
            elif isinstance(due_date, datetime):
                # For datetime objects, just format the date portion
                due_str = due_date.strftime("%a %b %d, %Y")

        parts = [f"  - [{status}] {title}"]
        if due_str:
            parts.append(f"(Due: {due_str})")
        if priority and priority != "Standard":
            parts.append(f"[{priority}]")
        if row_id:
            parts.append(f"[ID: {row_id}]")

        return " ".join(parts)

    def _format_task_detail(self, task: Dict[str, Any]) -> str:
        """Format task with full details for selected task context."""
        lines = []

        title = task.get("task") or task.get("title") or "Untitled"
        lines.append(f"Title: {title}")

        row_id = task.get("row_id") or task.get("rowId")
        if row_id:
            lines.append(f"Task ID: {row_id}")

        status = task.get("status", "Unknown")
        lines.append(f"Status: {status}")

        priority = task.get("priority", "Standard")
        lines.append(f"Priority: {priority}")

        # Handle multiple due date field names
        due_date = task.get("due") or task.get("due_date") or task.get("dueDate")
        if due_date:
            if isinstance(due_date, str):
                try:
                    if "T" in due_date:
                        date_part = due_date.split("T")[0]
                        parsed = datetime.strptime(date_part, "%Y-%m-%d")
                        due_str = parsed.strftime("%a %b %d, %Y")
                    else:
                        parsed = datetime.strptime(due_date, "%Y-%m-%d")
                        due_str = parsed.strftime("%a %b %d, %Y")
                except (ValueError, TypeError):
                    due_str = due_date
            elif isinstance(due_date, datetime):
                due_str = due_date.strftime("%a %b %d, %Y")
            else:
                due_str = str(due_date)
            lines.append(f"Due Date: {due_str}")

        domain = task.get("domain", "personal")
        lines.append(f"Domain: {domain}")

        project = task.get("project")
        if project:
            lines.append(f"Project: {project}")

        notes = task.get("notes")
        if notes:
            lines.append(f"Notes: {notes}")

        source = task.get("source", "personal")
        lines.append(f"Source: {source}")

        return "\n".join(lines)


def build_calendar_context(
    domain: DomainType,
    events: List[CalendarEvent],
    attention_items: Optional[List[CalendarAttentionRecord]] = None,
    tasks: Optional[List[Dict[str, Any]]] = None,
    selected_event: Optional[CalendarEvent] = None,
    selected_task: Optional[Dict[str, Any]] = None,
    date_range_start: Optional[datetime] = None,
    date_range_end: Optional[datetime] = None,
) -> str:
    """Build calendar context string for DATA.

    Args:
        domain: Calendar domain (personal, church, work, combined)
        events: Events in current view
        attention_items: Active attention items
        tasks: Tasks from Task tab
        selected_event: Currently selected event
        selected_task: Currently selected task
        date_range_start: Start of view range
        date_range_end: End of view range

    Returns:
        Formatted context string for DATA's system prompt
    """
    ctx = CalendarChatContext(
        domain=domain,
        events=events,
        attention_items=attention_items or [],
        tasks=tasks or [],
        selected_event=selected_event,
        selected_task=selected_task,
        date_range_start=date_range_start,
        date_range_end=date_range_end,
    )
    return ctx.to_context_string()
