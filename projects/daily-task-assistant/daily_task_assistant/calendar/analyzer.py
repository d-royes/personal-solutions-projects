"""Calendar Analyzer - attention detection for calendar events.

This module analyzes calendar events to surface items needing David's attention.
It uses profile.vip_senders for VIP detection and configurable thresholds.

MVP (Phase CA-1) Detection Types:
- VIP Meeting Alert: Meetings with VIP attendees
- Meeting Preparation: Meetings in next 24-48h needing prep

Future Detection Types (Phase CA-2+):
- Task-Event Conflict: Task due dates overlapping dense meeting days
- Overcommitment Warning: Days exceeding max_meetings_per_day

Confidence Thresholds (from plan):
- VIP Meeting: 0.80
- Meeting Preparation: 0.60
- Task-Event Conflict: 0.55
- Overcommitment Warning: 0.65
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple


def _ensure_utc(dt: datetime) -> datetime:
    """Ensure datetime is UTC timezone-aware.

    If naive, assumes UTC. If aware, converts to UTC.
    """
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)

from .types import CalendarEvent, CalendarAttentionRecord, CalendarSettings, _now
from .attention_store import save_attention, is_already_analyzed
from ..memory.profile import get_or_create_profile, DavidProfile


# Confidence thresholds from the plan
CONFIDENCE_VIP_MEETING = 0.80
CONFIDENCE_PREP_NEEDED = 0.60
CONFIDENCE_TASK_CONFLICT = 0.55
CONFIDENCE_OVERCOMMITMENT = 0.65


def analyze_events(
    events: List[CalendarEvent],
    account: str,
    settings: Optional[CalendarSettings] = None,
) -> List[CalendarAttentionRecord]:
    """Analyze calendar events and create attention records.

    Args:
        events: List of CalendarEvent objects to analyze
        account: Calendar account ("personal", "church", "work")
        settings: Optional CalendarSettings for thresholds

    Returns:
        List of CalendarAttentionRecord objects created
    """
    profile = get_or_create_profile()
    records = []

    for event in events:
        # Skip if already analyzed
        if is_already_analyzed(account, event.id):
            continue

        # Skip cancelled events
        if event.status == "cancelled":
            continue

        # Run detection algorithms
        attention = _detect_attention(event, account, profile, settings)
        if attention:
            save_attention(account, attention)
            records.append(attention)

    return records


def _detect_attention(
    event: CalendarEvent,
    account: str,
    profile: DavidProfile,
    settings: Optional[CalendarSettings] = None,
) -> Optional[CalendarAttentionRecord]:
    """Detect if an event needs attention.

    Runs detection in priority order and returns first match.

    Args:
        event: CalendarEvent to analyze
        account: Calendar account
        profile: DavidProfile for VIP detection
        settings: Optional CalendarSettings

    Returns:
        CalendarAttentionRecord if attention needed, None otherwise
    """
    # 1. VIP Meeting Detection (highest priority)
    vip_match = _detect_vip_meeting(event, account, profile)
    if vip_match:
        return _create_attention_record(
            event=event,
            account=account,
            attention_type="vip_meeting",
            reason=f"Meeting includes VIP: {vip_match}",
            confidence=CONFIDENCE_VIP_MEETING,
            matched_vip=vip_match,
        )

    # 2. Meeting Preparation Detection
    needs_prep, prep_reason = _detect_prep_needed(event)
    if needs_prep:
        return _create_attention_record(
            event=event,
            account=account,
            attention_type="prep_needed",
            reason=prep_reason,
            confidence=CONFIDENCE_PREP_NEEDED,
        )

    # Future: Task conflict and overcommitment detection
    # These require additional context (task list, daily meeting counts)

    return None


def _detect_vip_meeting(
    event: CalendarEvent,
    account: str,
    profile: DavidProfile,
) -> Optional[str]:
    """Detect if meeting includes a VIP attendee.

    Uses fuzzy matching against profile.vip_senders.

    Args:
        event: CalendarEvent to check
        account: Calendar account for VIP lookup
        profile: DavidProfile with vip_senders

    Returns:
        Name of matched VIP, or None if no VIP found
    """
    if not event.attendees:
        return None

    # Get VIP patterns for this account
    # Also check "work" VIPs for work calendar events
    vip_patterns = []
    if account in profile.vip_senders:
        vip_patterns.extend(profile.vip_senders[account])

    # Work calendar might also check personal VIPs (family emergencies)
    if account == "work" and "personal" in profile.vip_senders:
        vip_patterns.extend(profile.vip_senders.get("personal", []))

    if not vip_patterns:
        return None

    # Check each attendee against VIP patterns (fuzzy match)
    for attendee in event.attendees:
        if attendee.is_self:
            continue

        # Check email and display name
        email_lower = attendee.email.lower()
        name_lower = (attendee.display_name or "").lower()

        for vip in vip_patterns:
            vip_lower = vip.lower()
            # Fuzzy match: VIP pattern appears in email or name
            if vip_lower in email_lower or vip_lower in name_lower:
                return attendee.display_name or attendee.email

    return None


def _detect_prep_needed(event: CalendarEvent) -> Tuple[bool, str]:
    """Detect if a meeting needs preparation.

    Criteria:
    - Meeting starts within next 48 hours
    - Has external attendees (not self)
    - Is an actual meeting (not all-day event, not solo block)

    Args:
        event: CalendarEvent to check

    Returns:
        Tuple of (needs_prep: bool, reason: str)
    """
    now = _now()
    event_start = _ensure_utc(event.start)
    hours_until = (event_start - now).total_seconds() / 3600

    # Only consider meetings in next 48 hours
    if hours_until < 0 or hours_until > 48:
        return False, ""

    # Skip all-day events (typically not meetings)
    if event.is_all_day:
        return False, ""

    # Skip if no other attendees
    if not event.is_meeting:
        return False, ""

    # Count external attendees (not self)
    external_count = sum(1 for a in event.attendees if not a.is_self)
    if external_count == 0:
        return False, ""

    # Determine urgency
    if hours_until <= 24:
        urgency = "tomorrow" if hours_until > 12 else "today"
        reason = f"Meeting with {external_count} attendee(s) {urgency} - prepare agenda or materials"
    else:
        reason = f"Meeting with {external_count} attendee(s) in {int(hours_until)} hours"

    return True, reason


def _create_attention_record(
    event: CalendarEvent,
    account: str,
    attention_type: str,
    reason: str,
    confidence: float,
    matched_vip: Optional[str] = None,
) -> CalendarAttentionRecord:
    """Create a CalendarAttentionRecord from an event.

    Args:
        event: Source CalendarEvent
        account: Calendar account
        attention_type: Type of attention needed
        reason: Human-readable reason
        confidence: Confidence score
        matched_vip: Optional matched VIP name

    Returns:
        CalendarAttentionRecord
    """
    return CalendarAttentionRecord(
        event_id=event.id,
        calendar_account=account,
        calendar_id=event.calendar_id,
        summary=event.summary,
        start=event.start,
        end=event.end,
        attendees=[a.email for a in event.attendees if not a.is_self],
        location=event.location,
        html_link=event.html_link,
        attention_type=attention_type,
        reason=reason,
        confidence=confidence,
        matched_vip=matched_vip,
    )


# =============================================================================
# Future: Phase CA-3 - Capacity & Conflicts
# =============================================================================

def detect_overcommitment(
    events: List[CalendarEvent],
    max_meetings_per_day: int = 5,
) -> List[Tuple[datetime, int]]:
    """Detect days with too many meetings.

    Args:
        events: List of calendar events
        max_meetings_per_day: Threshold for warnings

    Returns:
        List of (date, meeting_count) tuples for overcommitted days
    """
    from collections import Counter

    # Count meetings per day
    meeting_days: Counter = Counter()

    for event in events:
        if event.is_meeting and not event.is_all_day:
            # Use date part only
            day = event.start.date()
            meeting_days[day] += 1

    # Find overcommitted days
    overcommitted = [
        (datetime.combine(day, datetime.min.time()), count)
        for day, count in meeting_days.items()
        if count > max_meetings_per_day
    ]

    return sorted(overcommitted, key=lambda x: x[0])
