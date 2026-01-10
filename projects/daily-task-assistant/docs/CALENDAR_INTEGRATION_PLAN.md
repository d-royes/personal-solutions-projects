# Calendar Integration for DATA - Implementation Plan

**Status:** Ready for implementation
**Date:** 2026-01-02

---

## Quick Reference - Key Files

| Layer | File | Purpose |
|-------|------|---------|
| **Frontend** | `src/App.tsx` | Add Calendar mode, state lifting |
| **Frontend** | `src/types.ts` | Add CalendarEvent, CalendarAccount types |
| **Frontend** | `src/api.ts` | Add calendar API functions |
| **Frontend** | `src/components/CalendarDashboard.tsx` | New component (mirror EmailDashboard) |
| **Backend** | `api/main.py` | Add `/calendar/{account}/*` endpoints |
| **Backend** | `daily_task_assistant/calendar/` | New module for calendar logic |
| **Backend** | `daily_task_assistant/calendar/google_calendar.py` | Google Calendar API client |
| **Backend** | `daily_task_assistant/calendar/calendar_store.py` | Firestore persistence |

---

## David's Calendar Landscape

### Calendars Used
- [x] Google Calendar (Personal) - `david.a.royes@gmail.com` - **PRIMARY VIEW**
- [x] Google Calendar (Church) - `davidroyes@southpointsda.org`
- [x] Work calendar (O365/Outlook) - **Shared TO personal Google Calendar**

**Key Insight:** Personal Google Calendar is the unified view - work calendar is shared there, so DATA sees all three domains through one integration point.

### Current Pain Points
1. **Keeping everything in sync** across domains
2. **Dropping the ball** on upcoming events
3. **Awareness gap** - things David should know about or has responsibility for slip through

### Vision & Goals

**Long-term:** All four directions:
1. Proactive surfacing (attention items for calendar events)
2. Task-calendar linkage (bidirectional context)
3. Preparation prompts ("help me prepare for this meeting")
4. Conflict/gap detection (commitments vs. availability)

**Initial Focus:** Work domain - connecting work tasks to work calendar
- Greatest immediate value
- Most structured data (Smartsheet tasks + work meetings)
- Clear relationships to discover

---

---

## Implementation Phases

### Phase 1: MVP
- [ ] Calendar mode with account switcher (Personal, Work, Church, Combined)
- [ ] Events tab - list view of upcoming events, grouped by day
- [ ] Basic DATA panel - select event, see details, chat about it
- [ ] Google Calendar API integration
  - Read/Write for Personal & Church
  - Read-only for Work (shared from O365)
- [ ] Create/modify events capability
- [ ] Create reminders for urgent tasks
- [ ] Settings tab with basic color/calendar filtering (for shared personal calendar)

### Phase 2: Task Integration
- [ ] Meetings tab (filter events with attendees)
- [ ] Tasks tab (unified view: calendar events + Smartsheet tasks)
- [ ] Task-event matching suggestions (AI-powered, approval flow)

### Phase 3: Enhanced Views
- [ ] Timeline/Agenda view ("What do I work on today?")
- [ ] Linked task indicators
- [ ] DATA proactive conflict detection

### Future Considerations
- Week view for workload distribution
- Time blocking suggestions
- Google Tasks/Reminders integration (if value > noise)

---

## Technical Implementation

### Backend: Google Calendar API Integration

**OAuth Pattern (mirror Gmail):**
```python
# Only TWO OAuth connections needed (same as Gmail):
PERSONAL_CALENDAR_CLIENT_ID      # Access to Personal, Family, AND David's Work Calendar
PERSONAL_CALENDAR_CLIENT_SECRET
PERSONAL_CALENDAR_REFRESH_TOKEN

CHURCH_CALENDAR_CLIENT_ID        # Access to Church calendars
CHURCH_CALENDAR_CLIENT_SECRET
CHURCH_CALENDAR_REFRESH_TOKEN

# NOTE: "Work" view is NOT a separate OAuth - it's a filtered view of
# "David's Work Calendar" which lives in the Personal account (O365 share)
```

**View-to-Account Mapping:**
| DATA View | OAuth Account | Calendar Filter |
|-----------|---------------|-----------------|
| Personal | Personal | Personal + Family calendars |
| Work | Personal | David's Work Calendar ONLY |
| Church | Church | David Royes + Elders + Southpoint |
| Combined | Both | All enabled calendars |

**New module: `daily_task_assistant/calendar/`**
```
calendar/
├── __init__.py
├── google_calendar.py    # API client (list, get, create, update events)
├── calendar_store.py     # Firestore persistence for settings, matches
├── types.py              # CalendarEvent, CalendarSettings dataclasses
└── sync.py               # Fetch and cache calendar data
```

**Key dataclasses:**
```python
@dataclass(slots=True)
class CalendarEvent:
    id: str
    calendar_id: str           # Which calendar within account
    summary: str               # Event title
    description: Optional[str]
    start: datetime
    end: datetime
    location: Optional[str]
    attendees: List[str]       # Email addresses
    is_all_day: bool
    color_id: Optional[str]    # Google Calendar color
    recurrence: Optional[str]  # RRULE
    source_domain: str         # "personal", "work", "church"

    @property
    def is_meeting(self) -> bool:
        return len(self.attendees) > 1
```

**Firestore structure (ACCOUNT-based):**
```
email_accounts/{account}/calendar_settings/{setting_id}  # Filters, preferences
email_accounts/{account}/calendar_matches/{match_id}     # Task-event links
```

### Backend: API Endpoints

```python
# Read operations
GET  /calendar/{account}/events?start=&end=&calendar_ids=
GET  /calendar/{account}/events/{event_id}
GET  /calendar/{account}/calendars          # List calendars within account

# Write operations (Personal/Church only)
POST /calendar/{account}/events             # Create event
PUT  /calendar/{account}/events/{event_id}  # Update event
POST /calendar/{account}/reminders          # Create reminder

# Settings
GET  /calendar/{account}/settings
PUT  /calendar/{account}/settings

# Task-event matching (Phase 2)
GET  /calendar/{account}/match-suggestions
POST /calendar/{account}/matches/{match_id}/decide
```

### Frontend: Component Structure

**Update types.ts:**
```typescript
export type AppMode = 'tasks' | 'email' | 'calendar'
export type CalendarAccount = 'personal' | 'work' | 'church' | 'combined'

export interface CalendarEvent {
  id: string
  calendarId: string
  summary: string
  description?: string
  start: string  // ISO datetime
  end: string
  location?: string
  attendees: string[]
  isAllDay: boolean
  colorId?: string
  sourceDomain: 'personal' | 'work' | 'church'
  isMeeting: boolean
}

export interface CalendarCacheState {
  events: CalendarEvent[]
  calendars: Calendar[]
  settings: CalendarSettings
  loaded: boolean
}
```

**CalendarDashboard.tsx structure (mirror EmailDashboard):**
```typescript
interface CalendarDashboardProps {
  authConfig: AuthConfig
  apiBase: string
  onBack: () => void
  // Lifted state
  cache?: Record<CalendarAccount, CalendarCacheState>
  setCache?: React.Dispatch<...>
  selectedAccount?: CalendarAccount
  setSelectedAccount?: React.Dispatch<...>
}

type CalendarTabView = 'events' | 'meetings' | 'tasks' | 'suggestions' | 'settings'
```

### Frontend: App.tsx Changes

1. Add `'calendar'` to `AppMode` type
2. Add calendar cache state (lifted)
3. Add mode selector button with `/Selector_Calendar_v1.png`
4. Add conditional render for `<CalendarDashboard />`

### Google Calendar API Scopes Needed

```
https://www.googleapis.com/auth/calendar.readonly     # Read events
https://www.googleapis.com/auth/calendar.events       # Create/modify events
https://www.googleapis.com/auth/calendar.settings.readonly  # Read settings
```

### Work Calendar Special Handling

Work calendar is shared from O365 → Personal Google Calendar:
- Appears as a separate calendar within Personal account
- Read-only (no write access)
- Identify by calendar ID or name pattern
- In Settings: let David specify which calendar ID = "work"

---

## MVP Implementation Steps (Phase 1)

### Step 1: Google Calendar OAuth Setup
- [ ] Create OAuth credentials in Google Cloud Console (reuse existing project)
- [ ] Add Calendar API scopes to existing OAuth consent screen
- [ ] Generate refresh tokens for Personal and Church accounts
- [ ] Add env vars: `PERSONAL_CALENDAR_*`, `CHURCH_CALENDAR_*`

### Step 2: Backend Calendar Module
- [ ] Create `daily_task_assistant/calendar/` directory
- [ ] `types.py` - CalendarEvent, CalendarSettings dataclasses
- [ ] `google_calendar.py` - API client with token refresh (mirror mailer.py pattern)
- [ ] `calendar_store.py` - Firestore persistence for settings
- [ ] Unit tests for calendar module

### Step 3: Backend API Endpoints
- [ ] `GET /calendar/{account}/calendars` - List calendars in account
- [ ] `GET /calendar/{account}/events` - List events with date range filter
- [ ] `GET /calendar/{account}/events/{id}` - Get single event
- [ ] `POST /calendar/{account}/events` - Create event
- [ ] `PUT /calendar/{account}/events/{id}` - Update event
- [ ] `POST /calendar/{account}/reminders` - Create reminder
- [ ] `GET/PUT /calendar/{account}/settings` - Filter settings (colors, calendars)

### Step 4: Frontend Types & API
- [ ] Add `CalendarAccount`, `CalendarEvent`, `CalendarSettings` to types.ts
- [ ] Add `'calendar'` to `AppMode` type
- [ ] Add calendar API functions to api.ts (mirror email patterns)

### Step 5: Frontend CalendarDashboard Component
- [ ] Create `CalendarDashboard.tsx` (start from EmailDashboard scaffold)
- [ ] Account switcher: Personal | Work | Church | Combined
- [ ] Tabs: Events | Meetings | Settings
- [ ] Events list view grouped by day
- [ ] Event detail panel (right side)
- [ ] Basic DATA assistant integration (select event → chat)

### Step 6: App.tsx Integration
- [ ] Add calendar mode selector button
- [ ] Copy `images/Selector_Calendar_v1.png` to `web-dashboard/public/`
- [ ] Lift calendar cache state to App.tsx
- [ ] Conditional render CalendarDashboard

### Step 7: Settings Tab - Calendar Selection
- [ ] Fetch all available calendars from Google Calendar API (per account)
- [ ] Display list with toggle on/off for each calendar
- [ ] Show calendar color from Google
- [ ] Work calendar designation dropdown (select which shared calendar = "David's Work Calendar")
- [ ] Persist selections to Firestore (`calendar_settings`)
- [ ] Default selections based on discovered calendar structure

### Step 8: Testing & Validation
- [ ] Manual testing with real calendar data
- [ ] E2E tests for calendar mode (basic flow)
- [ ] Verify work calendar read-only behavior

---

## Open Questions (Resolved)

| Question | Resolution |
|----------|------------|
| Calendar service? | Google Calendar (all 3 domains) |
| Work calendar access? | Shared to Personal Google Calendar (read-only) |
| Initial scope? | MVP: list/view/create events, then task linking |
| UI placement? | Dedicated Calendar mode (3rd mode) |
| Display format? | List view first, then Timeline/Agenda, then Week |

---

## Conversation Notes

### Connection Discovery Model
- **AI matching** - DATA analyzes task titles/descriptions against calendar event titles/descriptions
- **Trust Gradient applies** - DATA doesn't auto-link; presents proposed matches for David to review
- **UI pattern** - Similar to Suggestions tab: confirm, edit, dismiss
- **Learning loop** - Confirmed/dismissed matches feed back into improving future suggestions
- **Earned autonomy** - Eventually high-confidence matches could auto-link (future phase)

### Parallels to Existing Features
- Email suggestions → Calendar match suggestions
- Attention items → Calendar attention items (eventually)
- Rule approval flow → Match approval flow

---

## Design Ideas

### UI Layout - Calendar Mode

**Structure mirrors Email mode:**
```
┌─────────────────────────────────────────────────────────────────┐
│  [Tasks] [Email] [Calendar]          [Personal|Work|Church|Combined] │
├─────────────────────────────────────┬───────────────────────────┤
│  [Events] [Tasks] [Suggestions] [Settings] ...                  │
├─────────────────────────────────────┤                           │
│                                     │                           │
│  Calendar Dashboard                 │   DATA Assistant Panel    │
│  - Event list / calendar view       │   - Context about         │
│  - Selectable items                 │     selected event        │
│                                     │   - Chat interface        │
│                                     │   - Action buttons        │
│                                     │                           │
└─────────────────────────────────────┴───────────────────────────┘
```

**Key Elements:**
- **Mode selector:** Tasks | Email | Calendar (top nav)
- **Account switcher:** Personal | Work | Church | Combined (upper right)
  - Work, Personal, Church = 3 distinct calendar entities
  - Combined = all 3 visible, color-coded by domain
- **Filter tabs:** Events, Meetings, Suggestions, Settings
- **Left panel:** Calendar dashboard with selectable items
- **Right panel:** DATA assistant for engagement

**Interaction Pattern:**
Select event → View details → Engage DATA (same as email/task pattern)

### Tab Definitions

| Tab | Content |
|-----|---------|
| **Events** | All calendar events (appointments, blocks, etc.) |
| **Meetings** | Subset: actual meetings with attendees |
| **Suggestions** | Task-event match proposals for approval |
| **Settings** | Calendar preferences, sync options |

### The Core Vision: Unified Time View

**Problem:** David is over-extended. Every day has only 24 hours, but commitments span:
- Smartsheet tasks (with due dates)
- Meetings (actual meetings on calendar)
- Events (other calendar items)

**Solution:** A view where all commitments come together in TIME context:
- See realistic daily/weekly capacity
- Recognize over-extension EARLY
- Make more realistic commitments
- Set expectations proactively

**DATA's Role:**
- Surface conflicts before David can see them himself
- Call out over-commitment earlier than manual review
- Enable proactive expectation-setting on critical dates

### Task-Calendar Relationship

- **Linked tasks:** Smartsheet tasks linked to calendar events (clear indicator)
- **Unlinked tasks with dates:** Tasks with due dates shown in time context
- **Google Tasks/Reminders:** Maybe future, avoid noise for now
- **Time blocking suggestions:** Future goal (DATA suggests blocking time for tasks)

### Account/Calendar Model (From Screenshots)

**Church Account (`davidroyes@southpointsda.org`):**
| Calendar | Color | Include |
|----------|-------|---------|
| David Royes | Blue | ✅ Yes |
| Elders Calendar | Green | ✅ Yes |
| Southpoint Event Calendar | Red | ✅ Yes |
| Birthdays | - | ❌ No |
| Health Ministries | Red/Orange | ❌ No |
| Tasks | - | ❌ No |

**Personal Account (`david.a.royes@gmail.com`):**
| Calendar | Color | Include | Notes |
|----------|-------|---------|-------|
| Personal | Orange | ✅ Yes | David's personal events |
| Family | Gray | ✅ Yes | Family coordination |
| David's Work Calendar | Yellow | ✅ Yes | O365 share - THIS IS WORK |
| Esther Royes | Purple | ❌ No | Wife's events (not David's commitments) |
| Birthdays | - | ❌ No | |
| 11 SouthpointAllStarsAdve... | - | ❌ No | |
| Spiritual | - | ❌ No | |
| Tasks | - | ❌ No | |
| Esther Mucho | - | ❌ No | |
| PGA TOUR Schedule | - | ❌ No | |

**DATA Views:**
| View | Source Account | Calendars Included |
|------|----------------|-------------------|
| **Work** | Personal | David's Work Calendar (yellow) ONLY |
| **Personal** | Personal | Personal (orange) + Family (gray) |
| **Church** | Church | David Royes + Elders Calendar + Southpoint Event Calendar |
| **Combined** | Both | All of the above, color-coded by domain |

**Settings Page - Calendar Selection:**
- List all available Google Calendars from each account
- Toggle on/off for each calendar
- Allows future flexibility (e.g., add Esther's calendar if needed)
- Persists to Firestore (per account)

### Display Format - Progressive Build

| Phase | View | Purpose |
|-------|------|---------|
| **MVP** | List view | Events grouped by day, scrollable, familiar pattern |
| **Soon after** | Timeline/Agenda | "What do I work on today?" focus |
| **Future** | Week view | Workload distribution at a glance |

### Task Display Strategy

| Tab | Task Display |
|-----|--------------|
| **Events** | Count of tasks due that day (badge/indicator) |
| **Meetings** | Count of tasks due that day (badge/indicator) |
| **Tasks** | Combined view: calendar events + tasks due (full detail) |

**Tasks tab = the unified capacity view**
- Shows both calendar events AND Smartsheet tasks with due dates
- Day or week grouping
- This is where time-based planning happens

### Calendar Permissions by Domain

| Domain | Access | Reason |
|--------|--------|--------|
| Personal | Read/Write | Create events, reminders, modify |
| Church | Read/Write | Create events, reminders, modify |
| Work | Read-only | Shared from O365, inherently read-only |

**Reminders:** Ability to create reminders for urgent tasks (shows on calendar)

### Shared Calendar Complexity

**Personal calendar is shared with Esther (wife)**
- Family coordination: both see each other's events
- Most events on personal calendar aren't David's events
- Color-coding system in Google Calendar:
  - School events
  - Family events
  - Around the house
  - etc.

**Challenge:** Filter out events that don't affect David's day-to-day commitments

**Solution (Settings tab):**
- Color-based filtering (show/hide by Google Calendar color)
- Calendar filtering (multiple calendars within account)
- "My events only" toggle (organizer or sole attendee)
- Custom filter rules (keywords, patterns)

---
