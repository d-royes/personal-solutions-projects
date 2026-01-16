"""Recurring task logic for Firestore-primary recurring management.

This module handles all recurring task calculations:
- Determining next occurrence date based on pattern
- Checking if a task should reset today
- Resetting tasks (uncheck done, advance planned_date)

Supported patterns:
- Weekly: M, T, W, H, F, Sa, Su (single or multiple days)
- Monthly: 1, 15, 28, last, first_monday, second_tuesday, etc.
- Bi-weekly: Every 2 weeks on specified day(s)
- Custom: Every N days

Note: This is separate from Smartsheet's recurring automation.
FS-managed recurring tasks use "X" in SS recurring_pattern column.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import List, Optional, Tuple
from calendar import monthrange
from zoneinfo import ZoneInfo

from .store import FirestoreTask, RecurringType, update_task


# Day code mapping (matches Smartsheet pattern)
DAY_CODES = {
    "M": 0,   # Monday
    "T": 1,   # Tuesday
    "W": 2,   # Wednesday
    "H": 3,   # Thursday (H for tHursday, avoiding T conflict)
    "F": 4,   # Friday
    "Sa": 5,  # Saturday
    "Su": 6,  # Sunday
}

# Reverse mapping for display
DAY_NAMES = {v: k for k, v in DAY_CODES.items()}

# Timezone for date calculations
TZ = ZoneInfo("America/New_York")


def get_next_occurrence(task: FirestoreTask, after_date: Optional[date] = None) -> Optional[date]:
    """Calculate the next occurrence date for a recurring task.
    
    Args:
        task: The FirestoreTask with recurring attributes
        after_date: Calculate next occurrence after this date (defaults to today)
        
    Returns:
        Next occurrence date, or None if task is not recurring
    """
    if not task.recurring_type:
        return None
    
    base_date = after_date or date.today()
    recurring_type = task.recurring_type
    
    if recurring_type == "daily":
        # Daily = next day
        return base_date + timedelta(days=1)
    
    elif recurring_type == RecurringType.WEEKLY.value:
        return _next_weekly(base_date, task.recurring_days or [])
    
    elif recurring_type == RecurringType.MONTHLY.value:
        return _next_monthly(base_date, task.recurring_monthly)
    
    elif recurring_type == "biweekly":
        return _next_biweekly(base_date, task.recurring_days or [], task.planned_date)
    
    elif recurring_type == RecurringType.CUSTOM.value:
        return _next_custom(base_date, task.recurring_interval or 1)
    
    return None


def _next_weekly(base_date: date, days: List[str]) -> Optional[date]:
    """Find next occurrence for weekly recurring on specified days.
    
    Args:
        base_date: Start searching from this date
        days: List of day codes like ["M", "W", "F"]
        
    Returns:
        Next date that falls on one of the specified days
    """
    if not days:
        return None
    
    # Convert day codes to weekday numbers
    target_weekdays = set()
    for day in days:
        if day in DAY_CODES:
            target_weekdays.add(DAY_CODES[day])
    
    if not target_weekdays:
        return None
    
    # Search up to 7 days forward
    for offset in range(1, 8):
        check_date = base_date + timedelta(days=offset)
        if check_date.weekday() in target_weekdays:
            return check_date
    
    return None


def _next_monthly(base_date: date, monthly_pattern: Optional[str]) -> Optional[date]:
    """Find next occurrence for monthly recurring.
    
    Args:
        base_date: Start searching from this date
        monthly_pattern: Pattern like "1", "15", "last", "first_monday", etc.
        
    Returns:
        Next monthly occurrence date
    """
    if not monthly_pattern:
        # Default to same day of month
        monthly_pattern = str(base_date.day)
    
    pattern = monthly_pattern.lower().strip()
    
    # Handle numeric day (1, 15, 28, etc.)
    if pattern.isdigit():
        target_day = int(pattern)
        return _next_monthly_day(base_date, target_day)
    
    # Handle "last" (last day of month)
    if pattern == "last":
        return _next_last_day_of_month(base_date)
    
    # Handle ordinal weekday patterns (first_monday, second_tuesday, last_friday, etc.)
    if "_" in pattern:
        return _next_ordinal_weekday(base_date, pattern)
    
    # Default: same day next month
    return _next_monthly_day(base_date, base_date.day)


def _next_monthly_day(base_date: date, target_day: int) -> date:
    """Find next occurrence on a specific day of month.
    
    Args:
        base_date: Start searching from this date
        target_day: Target day of month (1-31)
        
    Returns:
        Next date with that day of month
    """
    # Try current month first
    year, month = base_date.year, base_date.month
    days_in_month = monthrange(year, month)[1]
    actual_day = min(target_day, days_in_month)
    
    candidate = date(year, month, actual_day)
    if candidate > base_date:
        return candidate
    
    # Move to next month
    if month == 12:
        year += 1
        month = 1
    else:
        month += 1
    
    days_in_month = monthrange(year, month)[1]
    actual_day = min(target_day, days_in_month)
    
    return date(year, month, actual_day)


def _next_last_day_of_month(base_date: date) -> date:
    """Find the last day of the next applicable month.
    
    Args:
        base_date: Start searching from this date
        
    Returns:
        Last day of current month (if not passed) or next month
    """
    year, month = base_date.year, base_date.month
    days_in_month = monthrange(year, month)[1]
    
    last_day = date(year, month, days_in_month)
    if last_day > base_date:
        return last_day
    
    # Move to next month
    if month == 12:
        year += 1
        month = 1
    else:
        month += 1
    
    days_in_month = monthrange(year, month)[1]
    return date(year, month, days_in_month)


def _next_ordinal_weekday(base_date: date, pattern: str) -> Optional[date]:
    """Find next occurrence for ordinal weekday patterns.
    
    Args:
        base_date: Start searching from this date
        pattern: Like "first_monday", "second_tuesday", "last_friday"
        
    Returns:
        Next matching date
    """
    parts = pattern.split("_")
    if len(parts) != 2:
        return None
    
    ordinal_str, weekday_str = parts
    
    # Map ordinal words to numbers
    ordinals = {
        "first": 1, "1st": 1,
        "second": 2, "2nd": 2,
        "third": 3, "3rd": 3,
        "fourth": 4, "4th": 4,
        "last": -1,
    }
    
    # Map weekday names
    weekdays = {
        "monday": 0, "mon": 0,
        "tuesday": 1, "tue": 1,
        "wednesday": 2, "wed": 2,
        "thursday": 3, "thu": 3,
        "friday": 4, "fri": 4,
        "saturday": 5, "sat": 5,
        "sunday": 6, "sun": 6,
    }
    
    ordinal = ordinals.get(ordinal_str)
    weekday = weekdays.get(weekday_str)
    
    if ordinal is None or weekday is None:
        return None
    
    # Try current month first
    candidate = _get_ordinal_weekday_in_month(base_date.year, base_date.month, ordinal, weekday)
    if candidate and candidate > base_date:
        return candidate
    
    # Move to next month
    year, month = base_date.year, base_date.month
    if month == 12:
        year += 1
        month = 1
    else:
        month += 1
    
    return _get_ordinal_weekday_in_month(year, month, ordinal, weekday)


def _get_ordinal_weekday_in_month(year: int, month: int, ordinal: int, weekday: int) -> Optional[date]:
    """Get the nth weekday in a given month.
    
    Args:
        year: Year
        month: Month (1-12)
        ordinal: Which occurrence (1=first, 2=second, -1=last)
        weekday: Day of week (0=Monday, 6=Sunday)
        
    Returns:
        The date, or None if not valid
    """
    days_in_month = monthrange(year, month)[1]
    
    if ordinal == -1:
        # Last occurrence - start from end of month
        for day in range(days_in_month, 0, -1):
            candidate = date(year, month, day)
            if candidate.weekday() == weekday:
                return candidate
        return None
    
    # Find nth occurrence
    count = 0
    for day in range(1, days_in_month + 1):
        candidate = date(year, month, day)
        if candidate.weekday() == weekday:
            count += 1
            if count == ordinal:
                return candidate
    
    return None


def _next_biweekly(base_date: date, days: List[str], anchor_date: Optional[date]) -> Optional[date]:
    """Find next occurrence for bi-weekly recurring.
    
    Args:
        base_date: Start searching from this date
        days: List of day codes like ["M", "W", "F"]
        anchor_date: Reference date to calculate 2-week intervals from
        
    Returns:
        Next bi-weekly occurrence
    """
    if not days:
        return None
    
    # Convert day codes to weekday numbers
    target_weekdays = set()
    for day in days:
        if day in DAY_CODES:
            target_weekdays.add(DAY_CODES[day])
    
    if not target_weekdays:
        return None
    
    # Use anchor date to determine which weeks are "on"
    anchor = anchor_date or base_date
    
    # Calculate week number relative to anchor
    days_since_anchor = (base_date - anchor).days
    
    # Search up to 14 days forward
    for offset in range(1, 15):
        check_date = base_date + timedelta(days=offset)
        
        # Check if this is an "on" week (every 2 weeks from anchor)
        days_from_anchor = (check_date - anchor).days
        week_num = days_from_anchor // 7
        
        if week_num % 2 == 0 and check_date.weekday() in target_weekdays:
            return check_date
    
    return None


def _next_custom(base_date: date, interval_days: int) -> date:
    """Find next occurrence for custom interval recurring.
    
    Args:
        base_date: Start searching from this date
        interval_days: Number of days between occurrences
        
    Returns:
        Next occurrence date
    """
    return base_date + timedelta(days=max(1, interval_days))


def should_reset_today(task: FirestoreTask, today: Optional[date] = None) -> bool:
    """Check if a recurring task should reset today.
    
    A task should reset if:
    1. It is a recurring task (has recurring_type)
    2. It is marked done (done=True)
    3. Today matches the recurring pattern
    
    Args:
        task: The FirestoreTask to check
        today: Override today's date (for testing)
        
    Returns:
        True if task should reset today
    """
    if not task.recurring_type:
        return False
    
    if not task.done:
        return False
    
    check_date = today or date.today()
    recurring_type = task.recurring_type
    
    if recurring_type == "daily":
        # Daily tasks always reset (every day)
        return True
    
    elif recurring_type == RecurringType.WEEKLY.value:
        return _is_weekly_day(check_date, task.recurring_days or [])
    
    elif recurring_type == RecurringType.MONTHLY.value:
        return _is_monthly_day(check_date, task.recurring_monthly)
    
    elif recurring_type == "biweekly":
        return _is_biweekly_day(check_date, task.recurring_days or [], task.planned_date)
    
    elif recurring_type == RecurringType.CUSTOM.value:
        # For custom, check if enough days have passed since last planned_date
        if task.planned_date:
            days_since = (check_date - task.planned_date).days
            interval = task.recurring_interval or 1
            return days_since >= interval
        return True
    
    return False


def _is_weekly_day(check_date: date, days: List[str]) -> bool:
    """Check if date falls on one of the specified weekly days."""
    if not days:
        return False
    
    current_weekday = check_date.weekday()
    for day in days:
        if day in DAY_CODES and DAY_CODES[day] == current_weekday:
            return True
    return False


def _is_monthly_day(check_date: date, monthly_pattern: Optional[str]) -> bool:
    """Check if date matches the monthly pattern."""
    if not monthly_pattern:
        return False
    
    pattern = monthly_pattern.lower().strip()
    
    # Handle numeric day
    if pattern.isdigit():
        target_day = int(pattern)
        days_in_month = monthrange(check_date.year, check_date.month)[1]
        # Handle months with fewer days
        if target_day > days_in_month:
            return check_date.day == days_in_month
        return check_date.day == target_day
    
    # Handle "last"
    if pattern == "last":
        days_in_month = monthrange(check_date.year, check_date.month)[1]
        return check_date.day == days_in_month
    
    # Handle ordinal weekday patterns
    if "_" in pattern:
        expected = _get_ordinal_weekday_in_month(
            check_date.year, 
            check_date.month,
            _parse_ordinal(pattern.split("_")[0]),
            _parse_weekday(pattern.split("_")[1])
        )
        return expected == check_date
    
    return False


def _is_biweekly_day(check_date: date, days: List[str], anchor_date: Optional[date]) -> bool:
    """Check if date falls on a bi-weekly occurrence."""
    if not days or not anchor_date:
        return False
    
    # Check if it's the right day of week
    if not _is_weekly_day(check_date, days):
        return False
    
    # Check if it's an "on" week
    days_from_anchor = (check_date - anchor_date).days
    week_num = days_from_anchor // 7
    return week_num % 2 == 0


def _parse_ordinal(ordinal_str: str) -> int:
    """Parse ordinal string to number."""
    ordinals = {
        "first": 1, "1st": 1,
        "second": 2, "2nd": 2,
        "third": 3, "3rd": 3,
        "fourth": 4, "4th": 4,
        "last": -1,
    }
    return ordinals.get(ordinal_str.lower(), 1)


def _parse_weekday(weekday_str: str) -> int:
    """Parse weekday string to number."""
    weekdays = {
        "monday": 0, "mon": 0,
        "tuesday": 1, "tue": 1,
        "wednesday": 2, "wed": 2,
        "thursday": 3, "thu": 3,
        "friday": 4, "fri": 4,
        "saturday": 5, "sat": 5,
        "sunday": 6, "sun": 6,
    }
    return weekdays.get(weekday_str.lower(), 0)


def reset_recurring_task(user_id: str, task: FirestoreTask) -> Optional[FirestoreTask]:
    """Reset a recurring task for its next occurrence.
    
    This function:
    1. Sets done = False
    2. Advances planned_date to next occurrence
    3. Advances target_date to match (so slippage tracking resets each cycle)
    4. Clears completed_on
    5. Resets status to 'scheduled' (so it appears in active task list)
    
    Args:
        user_id: The user who owns the task
        task: The recurring task to reset
        
    Returns:
        Updated FirestoreTask, or None if not recurring
    """
    if not task.recurring_type:
        return None
    
    next_date = get_next_occurrence(task, task.planned_date or date.today())
    
    updates = {
        "done": False,
        "completed_on": None,
        "planned_date": next_date,
        "target_date": next_date,  # Reset target to match so slippage starts fresh
        "status": "scheduled",  # Reset status so task appears in active list
    }
    
    return update_task(user_id, task.id, updates)


def get_recurring_display(task: FirestoreTask) -> str:
    """Get a human-readable description of the recurring pattern.
    
    Args:
        task: The FirestoreTask with recurring attributes
        
    Returns:
        Display string like "Weekly on M, W, F" or "Monthly on 15th"
    """
    if not task.recurring_type:
        return ""
    
    recurring_type = task.recurring_type
    
    if recurring_type == "daily":
        return "Daily"
    
    elif recurring_type == RecurringType.WEEKLY.value:
        days = task.recurring_days or []
        if days:
            return f"Weekly on {', '.join(days)}"
        return "Weekly"
    
    elif recurring_type == RecurringType.MONTHLY.value:
        pattern = task.recurring_monthly or str(task.planned_date.day if task.planned_date else 1)
        if pattern.lower() == "last":
            return "Monthly on last day"
        elif "_" in pattern:
            parts = pattern.split("_")
            return f"Monthly on {parts[0]} {parts[1]}"
        else:
            return f"Monthly on {pattern}"
    
    elif recurring_type == "biweekly":
        days = task.recurring_days or []
        if days:
            return f"Every 2 weeks on {', '.join(days)}"
        return "Bi-weekly"
    
    elif recurring_type == RecurringType.CUSTOM.value:
        interval = task.recurring_interval or 1
        if interval == 1:
            return "Daily"
        return f"Every {interval} days"
    
    return ""
