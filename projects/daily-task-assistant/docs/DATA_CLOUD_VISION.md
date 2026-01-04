# DATA Cloud Vision

> **Document Created**: 2025-12-11  
> **Status**: Strategic Planning  
> **Target Start**: January 2025

---

## Executive Summary

DATA (Daily Autonomous Task Assistant) began as a personal AI assistant for David Royes. Through months of development, it has evolved into something with broader potential: **a personal AI that actually does things**.

This document outlines the vision for **DATA Cloud** - a productized version of DATA that could serve tech-savvy early adopters who want an AI assistant that integrates with their email, calendar, and task management.

---

## The Opportunity

### Market Gap

Most "AI assistants" fall into one of two categories:

| Category | Examples | Limitation |
|----------|----------|------------|
| **All Chat, No Action** | ChatGPT, Claude | They advise but can't *do* anything |
| **All Automation, No Intelligence** | Zapier, IFTTT | They execute rules but can't *think* |

DATA occupies a unique position: **AI intelligence + real integrations + earned trust**.

### What Makes DATA Different

1. **Chief of Staff Model**: DATA delegates to other systems (Apps Script, email providers) rather than trying to replace them
2. **Multi-Domain Context**: Personal, Church, Work - all understood in one assistant
3. **Trust Gradient**: Autonomy is earned through demonstrated success, not granted blindly
4. **Real Integrations**: Gmail, Calendar, Sheets - actual actions, not just suggestions

### Target Users (Phase 1)

Tech-savvy early adopters who:
- Manage multiple email accounts
- Have significant task/calendar overhead
- Are comfortable with OAuth consent flows
- Want AI to *do* things, not just chat
- Will tolerate some setup friction for real value

---

## Core Value Proposition

> "An AI assistant that knows your email, tasks, and calendar - and actually helps you manage them."

The three domains are interconnected in everyone's life:

```
┌──────────────────────────────────────────────────────────────┐
│                    The Assistant Trifecta                    │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│    ┌─────────┐                                               │
│    │  EMAIL  │ ─── "Can you help with X?" ───┐               │
│    └─────────┘                               │               │
│         │                                    ▼               │
│         │ action                        ┌─────────┐          │
│         │ needed                        │  TASKS  │          │
│         ▼                               └─────────┘          │
│    ┌─────────┐                               │               │
│    │ CALENDAR│ ◄── "Schedule time for" ──────┘               │
│    └─────────┘                                               │
│                                                              │
│    DATA sees all three, understands the connections,         │
│    and helps orchestrate your productivity.                  │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

---

## Strategic Roadmap

### Phase A: Foundation (January 2025)

**Goal**: Architect for multi-tenancy without breaking personal DATA.

#### A1: Decouple from Smartsheet
- Create `TaskStore` in Firestore (native task management)
- Build task CRUD UI in DATA dashboard
- Optional: One-way sync FROM Smartsheet during transition
- **Why**: Smartsheet licensing is degrading; own your data

#### A2: Abstract Integrations
Create provider interfaces that can have multiple implementations:

```python
class EmailProvider(Protocol):
    def list_messages(self, query: str) -> list[Message]: ...
    def send_message(self, to: str, subject: str, body: str) -> str: ...
    
class CalendarProvider(Protocol):
    def get_events(self, start: date, end: date) -> list[Event]: ...
    def create_event(self, event: Event) -> str: ...

class TaskProvider(Protocol):
    def list_tasks(self) -> list[Task]: ...
    def create_task(self, task: Task) -> str: ...
    def update_task(self, task_id: str, updates: dict) -> None: ...
```

Implementations:
- `GmailProvider`, `OutlookProvider`
- `GoogleCalendarProvider`, `OutlookCalendarProvider`
- `FirestoreTaskProvider`, `SmartsheetTaskProvider` (legacy)

#### A3: User-Scope Everything
- Replace hardcoded `david.a.royes@gmail.com` with `current_user.email`
- Move integration credentials from `.env` to Firestore `users/{uid}/integrations`
- Every query includes `user_id` context

**Deliverable**: DATA works exactly as before for David, but architecture supports multiple users.

---

### Phase B: Architecture (February 2025)

**Goal**: Design the multi-tenant system; build OAuth flows.

#### B1: Multi-Tenant Data Model

```
Firestore Structure:
├── users/
│   └── {uid}/
│       ├── profile (name, email, preferences)
│       ├── integrations/
│       │   ├── google (tokens, scopes, connected_at)
│       │   └── microsoft (tokens, scopes, connected_at)
│       ├── tasks/
│       │   └── {task_id} (title, status, due_date, ...)
│       ├── conversations/
│       │   └── {conversation_id} (messages, context)
│       ├── email_rules/
│       │   └── {rule_id} (pattern, action, category)
│       └── memory/
│           └── {memory_id} (Phase 2: personalization)
```

#### B2: OAuth Flow Design

"Connect with Google" flow:
1. User clicks "Connect Google Account"
2. OAuth consent screen requests: Gmail, Calendar, Tasks scopes
3. DATA receives tokens, stores in `users/{uid}/integrations/google`
4. Token refresh handled automatically
5. User can disconnect anytime

"Connect with Microsoft" flow: Same pattern for Outlook ecosystem.

#### B3: Graceful Degradation
- If email disconnected, calendar still works
- If calendar disconnected, tasks still work
- Clear UI indicators of what's connected

**Deliverable**: Technical design docs and OAuth implementation.

---

### Phase C: DATA Cloud MVP (March 2025+)

**Goal**: Launch to beta users.

#### C1: User Onboarding
- Landing page explaining value proposition
- Signup with Google or Microsoft
- Guided onboarding: "What do you want DATA to help with?"
- Connect integrations step-by-step

#### C2: Core Features (MVP)
- **Email Triage**: Categorize, prioritize, suggest actions
- **Task Management**: Create, organize, prioritize tasks
- **Calendar Awareness**: See schedule, suggest timing for tasks
- **AI Chat**: Conversational interface to all three domains

#### C3: Beta Program
- Invite 5-10 early adopters (David's friends/coworkers)
- Feedback collection built into the product
- Weekly iteration based on real usage
- Track what features get used vs. ignored

#### C4: Pricing Model (TBD)
Options to explore:
- Freemium (limited tasks/emails per month)
- Subscription ($10-20/month)
- Usage-based (per AI interaction)

**Deliverable**: Working product with real users providing feedback.

---

## Technical Architecture (Target State)

```
┌─────────────────────────────────────────────────────────────────┐
│                        DATA Cloud                               │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐      │
│  │   Frontend   │    │   Backend    │    │   AI Layer   │      │
│  │   (React)    │◄──►│  (FastAPI)   │◄──►│  (Claude)    │      │
│  └──────────────┘    └──────────────┘    └──────────────┘      │
│         │                   │                   │               │
│         │                   ▼                   │               │
│         │           ┌──────────────┐            │               │
│         │           │  Firestore   │            │               │
│         │           │  (Users,     │            │               │
│         │           │   Tasks,     │            │               │
│         │           │   Memory)    │            │               │
│         │           └──────────────┘            │               │
│         │                   │                   │               │
│         ▼                   ▼                   ▼               │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              Provider Abstraction Layer                 │   │
│  ├──────────────┬──────────────┬──────────────────────────┤   │
│  │EmailProvider │CalendarProv. │     TaskProvider         │   │
│  ├──────────────┼──────────────┼──────────────────────────┤   │
│  │ - Gmail      │ - GCal       │ - Firestore (native)     │   │
│  │ - Outlook    │ - Outlook    │ - Smartsheet (legacy)    │   │
│  │ - (future)   │ - (future)   │ - Todoist (future)       │   │
│  └──────────────┴──────────────┴──────────────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Success Metrics

### Phase A Success
- [ ] David using Firestore tasks instead of Smartsheet
- [ ] Integration code uses provider interfaces
- [ ] All features work with `user_id` parameter

### Phase B Success
- [ ] OAuth flow working for Google
- [ ] Second user can onboard (even if manual)
- [ ] Data properly isolated between users

### Phase C Success
- [ ] 5+ beta users actively using DATA
- [ ] Net Promoter Score > 8
- [ ] Users completing tasks they wouldn't have without DATA
- [ ] Clear signal on pricing tolerance

---

## Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| OAuth complexity scares users | Guided onboarding with clear explanations |
| AI costs at scale | Efficient prompting, caching, tier limits |
| Data privacy concerns | Clear privacy policy, user data export, delete account |
| Competition launches similar product | Move fast, leverage David's daily usage for rapid iteration |
| Feature creep delays launch | MVP mindset - launch with core 3 domains only |

---

## Open Questions

1. **Pricing**: What would users pay for this? Need validation.
2. **Microsoft Support**: How important is Outlook/M365 vs Google-only?
3. **Mobile**: Web-first, but mobile is where people live. PWA? Native app?
4. **Enterprise**: Stay personal-focused or add team features?

---

## Appendix: Lessons from Building Personal DATA

What we learned from David's daily usage:

1. **Email categorization works** - The Chief of Staff model (DATA suggests, Apps Script executes) is powerful
2. **Context is king** - Knowing task history makes AI suggestions dramatically better
3. **Trust takes time** - Users need to see DATA succeed before granting more autonomy
4. **Integration > Intelligence** - Being able to *do* things matters more than being clever
5. **Personal means personal** - Generic productivity advice is ignored; specific help is valued

---

## Document History

| Date | Author | Changes |
|------|--------|---------|
| 2025-12-11 | David + DATA | Initial vision document |


