# Timezone Fix Documentation

> **Created**: 2026-01-02
> **Status**: Partially Complete
> **Priority**: High

## Overview

The application has inconsistent timezone handling that causes date-related calculations to be off by one day for users in timezones behind UTC (like Eastern Time). The root cause is parsing date strings as UTC instead of local time, then comparing them with local datetime values.

## Completed Fixes

### Frontend - Due Date Labels (Fixed 2026-01-02)

**Files Modified:**
- `projects/web-dashboard/src/components/TaskList.tsx`
- `projects/web-dashboard/src/components/CalendarDashboard.tsx`

**Problem:**
```typescript
// OLD CODE - Problematic
function dueLabel(due: string) {
  const dueDate = new Date(due)  // Parses "2026-01-03" as UTC midnight
  const today = new Date()        // Local time (e.g., 9:15 PM EST)
  // At 9:15 PM EST on 1/2, UTC midnight of 1/3 is actually 7:00 PM EST on 1/2
  // This causes "Due tomorrow" to show as "Due today"
}
```

**Solution:**
```typescript
// NEW CODE - Fixed
function toLocalMidnight(dateStr: string): Date {
  // Parse as local date by splitting the date string (avoids UTC interpretation)
  const [year, month, day] = dateStr.split('T')[0].split('-').map(Number)
  return new Date(year, month - 1, day, 0, 0, 0, 0)
}

function getTodayMidnight(): Date {
  const now = new Date()
  return new Date(now.getFullYear(), now.getMonth(), now.getDate(), 0, 0, 0, 0)
}

function dueLabel(due: string) {
  const dueDate = toLocalMidnight(due)
  const today = getTodayMidnight()
  // Now both dates are at local midnight, comparison is accurate
}
```

**Commit:** `72571f4` on `feature/calendar-integration`

---

## Remaining Issues

### 1. Smartsheet Date Parsing (Backend - Critical)

**File:** `projects/daily-task-assistant/daily_task_assistant/smartsheet_client.py`

**Line 633:**
```python
return datetime.utcfromtimestamp(value / 1000)
```

**Problem:** Uses deprecated `utcfromtimestamp()` which creates a naive datetime in UTC. When Smartsheet provides timestamps, they're interpreted as UTC without preserving timezone info.

**Lines 635-640:**
```python
for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y-%m-%dT%H:%M:%S%z"):
    try:
        return datetime.strptime(value, fmt)
    except ValueError:
        continue
```

**Problem:** Most date formats (`%Y-%m-%d`, `%m/%d/%Y`) produce naive datetimes with no timezone. Only the third format includes timezone info.

**Fix:**
```python
from zoneinfo import ZoneInfo

USER_TIMEZONE = ZoneInfo("America/New_York")

def parse_date(value):
    if isinstance(value, (int, float)):
        # Convert timestamp to timezone-aware datetime
        return datetime.fromtimestamp(value / 1000, tz=USER_TIMEZONE)

    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            dt = datetime.strptime(value, fmt)
            # If naive, assume it's in user's timezone
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=USER_TIMEZONE)
            return dt
        except ValueError:
            continue
    return None
```

---

### 2. Rebalancing Logic (Backend - Critical)

**File:** `projects/daily-task-assistant/api/main.py`

**Line 842:**
```python
today = datetime.now().date()
```

**Problem:** Uses naive `datetime.now()` without timezone. When comparing with task due dates that may be timezone-aware or interpreted differently, the comparison can be off by a day.

**Fix:**
```python
from daily_task_assistant.portfolio_context import USER_TIMEZONE

today = datetime.now(USER_TIMEZONE).date()
```

---

### 3. Default Due Date Calculation (Backend - High)

**File:** `projects/daily-task-assistant/api/main.py`

**Line 3501:**
```python
final_due = due_date or (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
```

**Problem:** Uses naive `datetime.now()` for calculating default due dates.

**Fix:**
```python
from daily_task_assistant.portfolio_context import USER_TIMEZONE

final_due = due_date or (datetime.now(USER_TIMEZONE) + timedelta(days=7)).strftime("%Y-%m-%d")
```

---

### 4. Email Date Extraction (Backend - Medium)

**File:** `projects/daily-task-assistant/daily_task_assistant/email/analyzer.py`

**Lines 638-642:**
```python
year = datetime.now().year  # Naive datetime
return datetime(year, month, day, tzinfo=timezone.utc)  # Hardcoded UTC
```

**Problem:** Uses naive `datetime.now()` to get the current year, then creates a UTC datetime. If an email mentions "January 3rd" in the body, it gets interpreted as January 3rd UTC, not Eastern.

**Fix:**
```python
from zoneinfo import ZoneInfo

USER_TIMEZONE = ZoneInfo("America/New_York")

year = datetime.now(USER_TIMEZONE).year
return datetime(year, month, day, tzinfo=USER_TIMEZONE)
```

---

### 5. Test Files (Low Priority)

Multiple test files use deprecated `datetime.utcnow()`:

| File | Line(s) |
|------|---------|
| `tests/test_actions.py` | 8 |
| `tests/test_prioritizer.py` | 18, 41 |
| `tests/test_activity_log.py` | 15 |
| `scripts/test_update_actions.py` | 88 |

**Fix:** Replace `datetime.utcnow()` with `datetime.now(timezone.utc)` or `datetime.now(USER_TIMEZONE)` as appropriate.

---

## Existing Good Pattern

**File:** `projects/daily-task-assistant/daily_task_assistant/portfolio_context.py`

This file already has the correct timezone handling:

```python
from zoneinfo import ZoneInfo

USER_TIMEZONE = ZoneInfo("America/New_York")

# Line 165
now = datetime.now(USER_TIMEZONE)

# Lines 180-185 - Handle both naive and aware datetimes
if due.tzinfo is None:
    due = due.replace(tzinfo=USER_TIMEZONE)
else:
    due = due.astimezone(USER_TIMEZONE)
```

**Recommendation:** Import `USER_TIMEZONE` from `portfolio_context.py` in other modules rather than defining it multiple times.

---

## Implementation Plan

### Phase 1: Backend Critical Fixes
1. Update `smartsheet_client.py` date parsing to use `USER_TIMEZONE`
2. Update `api/main.py` rebalancing logic (line 842)
3. Update `api/main.py` default due date calculation (line 3501)

### Phase 2: Backend Secondary Fixes
4. Update `email/analyzer.py` date extraction
5. Create shared timezone utility if needed

### Phase 3: Test Cleanup
6. Update test files to use timezone-aware datetimes

---

## Testing Checklist

After implementing fixes, verify:

- [ ] Tasks due tomorrow show "Due tomorrow" (not "Due today") at any time of day
- [ ] Tasks due today show "Due today"
- [ ] Overdue tasks show correct number of days overdue
- [ ] Portfolio rebalancing calculates due dates correctly
- [ ] Default due dates (7 days out) are calculated correctly
- [ ] Email-extracted dates are interpreted as Eastern Time
- [ ] All existing E2E tests pass

---

## References

- Python `zoneinfo` documentation: https://docs.python.org/3/library/zoneinfo.html
- JavaScript Date parsing gotchas: https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Date/parse
- Commit with frontend fix: `72571f4`
