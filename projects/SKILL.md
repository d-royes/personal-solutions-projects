---
name: "daily-command-center"
description: "Generates comprehensive daily briefings by gathering calendar events, emails, and tasks from multiple sources (Google Calendar, Gmail, Smartsheet). Use this skill when the user wants to start their day, get a daily overview, or needs an executive briefing of their schedule, communications, and priorities."
---

# Daily Command Center Skill v1.0
**Status**: Ready for Testing
**Last Updated**: October 27, 2025

## Quick Start
```
User: "Good morning Claude, let's start our day"
Claude: [Executes Daily Command Center workflow]
```

## Core Configuration
```yaml
sheet_id: 4543936291884932
calendars:
  personal: "primary"  # Shared with Esther
  work: "rd9o8scps8kgpkkh4bdoh17p55pi148a@import.calendar.google.com"
emails:
  personal: "david.a.royes@gmail.com"
  church: "davidroyes@southpointsda.org"
timezone: "America/New_York"
```

## PROVEN WORKFLOW (Use These Exact Methods)

### Step 1: Parallel Data Gathering
```bash
# ALL THREE IN PARALLEL - 5 second target
1. Calendar Events (both calendars, today's range)
2. Unread Emails (both accounts, after yesterday)
3. Active Tasks (direct API call, not Zapier find)
```

### Step 2: Read Smartsheet (OPTIMAL METHOD)
```bash
curl -s -H "Authorization: Bearer ${SMARTSHEET_ACCESS_TOKEN}" \
  "https://api.smartsheet.com/2.0/sheets/4543936291884932" | jq -r '
  .columns as $cols |
  .rows[] |
  select(.cells | length > 0) |
  {
    rowId: .id,
    task: (.cells[] | select(.columnId == 7891210558744452) | .value),
    project: (.cells[] | select(.columnId == 7034410278539140) | .value),
    dueDate: (.cells[] | select(.columnId == 5637085716741956) | .value),
    priority: (.cells[] | select(.columnId == 279010837483396) | .value),
    status: (.cells[] | select(.columnId == 8863997627158404) | .value),
    done: (.cells[] | select(.columnId == 6762985623520132) | .value // false),
    number: (.cells[] | select(.columnId == 4360397999787908) | .value)
  } |
  select(.done == false and .status != "Complete")'
```

### Step 3: Process & Classify

#### Calendar Intelligence
```python
def process_calendar(events):
    relevant = []
    for event in events:
        # Work calendar - always relevant
        if event.calendar == 'work':
            relevant.append(tag_domain(event, 'WORK'))
        
        # Personal calendar - filter for David
        elif is_david_event(event):
            relevant.append(tag_domain(event, 'PERSONAL/CHURCH'))
    
    return {
        'events': relevant,
        'meeting_hours': calculate_meeting_time(relevant),
        'conflicts': detect_conflicts(relevant),
        'prep_needed': flag_prep_requirements(relevant)
    }
```

#### Email Triage
```python
CLASSIFICATION = {
    'ACTION': ['reply', 'respond', 'urgent', 'asap', 'waiting'],
    'FYI': ['newsletter', 'update', 'announcement'],
    'DELEGABLE': ['can you', 'someone', 'whoever']
}
```

#### Task Prioritization
```python
def daily_task_sequence(tasks):
    # Group by due date
    overdue = [t for t in tasks if t.dueDate < today]
    today = [t for t in tasks if t.dueDate == today]
    upcoming = [t for t in tasks if t.dueDate > today]
    
    # Reorder using # field
    return assign_daily_numbers(overdue + today)
```

### Step 4: Generate Briefing (NO DUPLICATION)

```markdown
# 📅 Monday, October 27, 2025 - Daily Command Center

## 🎯 KEY DECISIONS NEEDED TODAY
1. [Most critical decision with context]
2. [Second priority decision]
3. [Third if applicable]

## 📊 TODAY'S LANDSCAPE
**Meetings**: X hours | **Focus Time**: Y hours | **Tasks Due**: Z items

### Schedule Overview
🏢 **WORK** (X hours)
• 9:00 AM - Meeting with [who] about [what] [PREP: 15 min]
• 2:00 PM - Review session for [project]

⛪ **CHURCH** (Y hours)
• [Any church meetings/commitments]

🏠 **PERSONAL** (Z hours)
• [Family appointments, personal time]

### ⚠️ Conflicts/Warnings
• [Any double-bookings or tight transitions]

## ✉️ COMMUNICATIONS REQUIRING ACTION
**🏢 Work** (X emails)
• From [sender]: [subject] - [one-line summary of action needed]

**⛪ Church** (Y emails)
• From [sender]: [subject] - [action required]

## ✅ TODAY'S TASK PRIORITIES
Recommended execution order based on dependencies and energy:

1. [#1 Task] - [Project] - [Time Est] ⏰
2. [#2 Task] - [Project] - [Time Est]
3. [#3 Task] - [Project] - [Time Est]
[Up to 6-8 realistic tasks for the day]

**📋 Backlog Alert**: [X tasks need rescheduling]

## ⚡ ENERGY OPTIMIZATION
• **Peak Focus Window**: [Time range with no meetings]
• **Suggested Break**: [After back-to-back meetings]
• **Context Switches**: [Count] transitions between domains
• **Recommendation**: [Batch similar work, protect focus time]

## 👀 WATCH ITEMS
• [Deadline approaching without progress]
• [Person awaiting response > 3 days]
• [Recurring task not scheduled]
```

## CRITICAL VALIDATION RULES

### Required Fields for New Tasks
```javascript
REQUIRED_FIELDS = {
  'Task': string,           // Clear description
  'Project': picklist,      // MUST be from list below
  'Due Date': date,         // ISO format
  'Priority': validated,    // MUST be from list below
  'Status': 'Scheduled',    // Default
  'Assigned To': 'david.a.royes@gmail.com',
  'Estimated Hours': picklist // "0.5", "1", "2", "4", "8"
}
```

### Valid Picklist Values (EXACT MATCHES ONLY)
```javascript
PROJECT_VALUES = [
  "Around The House",      // 🏠
  "Church Tasks",          // ⛪
  "Family Time",           // 🏠 (NOT "Personal")
  "Shopping",              // 🏠
  "Sm. Projects & Tasks",  // Default
  "Zendesk Ticket"         // 🏢
]

PRIORITY_VALUES = [
  "Critical",
  "Urgent", 
  "Important",
  "Standard",  // Default
  "Low"
]

HOURS_VALUES = ["0.5", "1", "2", "4", "8"]  // Strings!
```

## Column ID Cache (For API Operations)
```javascript
const COLUMN_IDS = {
  'Task': 7891210558744452,
  '#': 4360397999787908,
  'Status': 8863997627158404,
  'Priority': 279010837483396,
  'Project': 7034410278539140,
  'Due Date': 5637085716741956,
  'Done': 6762985623520132,
  'Assigned To': 5908510371696516,
  'Estimated Hours': 8160310185381764
}
```

## Decision Tree for Task Addition
```
New Task Identified
    ↓
Is it routine & clear? → YES → Add automatically
    ↓ NO
Is it ambiguous? → YES → Present for review
    ↓ NO  
Is it sensitive? → YES → Present for review
    ↓ NO
Is it strategic? → YES → Present for review
    ↓ NO
Add with defaults
```

## Error Recovery
1. If Zapier update fails → Use direct API
2. If API fails → Log error, present manual instructions
3. If calendar conflict → Flag, don't auto-resolve
4. If email classification uncertain → Mark as "Action Required"

## Success Metrics
- ✅ Complete briefing < 30 seconds
- ✅ Zero duplicate items
- ✅ All domains clearly tagged
- ✅ Actionable next steps identified
- ✅ Realistic task count (max 8/day)

## WHAT NOT TO DO
❌ Use Zapier find_sheet_row for reading
❌ Make up picklist values
❌ Use "Personal" instead of "Family Time"
❌ Add > 8 tasks to a single day
❌ Duplicate items across sections
❌ Try multiple methods if first fails

---
## Resume Instructions for Next Session

### To Continue Development:
1. Test with live data: "Good morning Claude, let's start our day"
2. Refine output format based on readability
3. Add to MCP as user skill when satisfied

### Known Issues to Address:
- Personal calendar filtering (Esther's events)
- Email action classification accuracy
- Task dependency detection

### Session Context:
- Created: October 27, 2025
- Token Usage: Optimized to prevent Opus exhaustion
- Ready for: Live testing in next session
