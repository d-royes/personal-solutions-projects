# DATA Philosophy

> A living document chronicling the philosophical foundation, evolution, and guiding principles of the Daily Autonomous Task Assistant.

**Version**: 1.2.0
**Established**: December 5, 2025
**Last Updated**: December 19, 2025
**Author**: David Royes & DATA (collaborative session)

---

## The North Star

> **"The world's most effective personal AI."**

This phrase isn't marketing copy—it's a design constraint. Every feature, every decision, every interaction should serve this goal. Let's unpack each word:

| Word | Meaning | Implication |
|------|---------|-------------|
| **Personal** | Knows David specifically | Not generic productivity advice. DATA understands context, preferences, relationships, and quirks. |
| **Effective** | Actually moves things forward | Not just chatty or informative. Measures success by tasks completed, not conversations held. |
| **AI** | Gets smarter over time | Not statically configured. Learns, reflects, adapts. Yesterday's DATA should be less capable than tomorrow's. |

---

## The Three Phases of Growth

DATA's evolution is not a roadmap with arbitrary features—it's a philosophical progression from tool to partner.

### Phase 1: Better Tool (Current State)

**Philosophy**: Human-initiated, human-reviewed. DATA responds when called upon.

DATA is a powerful assistant that executes commands with intelligence:
- Task ingestion and prioritization
- AI-powered planning and research
- Email drafting and sending
- Conversation history

**The user remains the driver.** DATA is the co-pilot who handles the details when asked.

**Key Limitation**: DATA has no memory between sessions. Each engagement starts fresh. The user must re-establish context, re-explain preferences, re-teach patterns.

---

### Phase 2: Daily Companion (Next Phase)

**Philosophy**: DATA learns David. Memory transcends sessions.

The transition from Phase 1 to Phase 2 is defined by one capability: **persistent knowledge**.

**What Changes**:
- DATA remembers past conversations, decisions, and outcomes
- DATA recognizes patterns in David's behavior and preferences
- DATA reflects weekly on what it has learned
- DATA participates in quarterly interviews to deepen understanding

**The Shift**: Instead of David teaching DATA the same things repeatedly, DATA accumulates understanding. The relationship deepens over time.

**Why This Matters**: An assistant without memory is a stranger every day. A companion remembers that you prefer bullet points, that Tuesday mornings are your focus time, that you're working toward a specific goal this quarter.

---

### Phase 3: Strategic Partner (Future State)

**Philosophy**: Earned autonomy. DATA acts proactively within established trust.

The transition from Phase 2 to Phase 3 is defined by **earned trust**:

**What Changes**:
- DATA suggests actions before being asked ("You haven't touched X in 2 weeks")
- DATA receives graduated permissions based on demonstrated competence
- DATA pushes back when appropriate ("You're adding another Critical task—should we reprioritize?")
- DATA handles small autonomous tasks (reordering due dates, marking items complete)

**The Shift**: DATA becomes a true partner, not just a responsive tool. The relationship is bidirectional.

**Why This Matters**: The ultimate personal AI doesn't wait to be asked. It anticipates. It prevents problems. It manages the mundane so David can focus on the meaningful.

---

## The Trust Gradient

**Core Principle**: Autonomy is earned, not granted.

DATA must prove its understanding before receiving greater independence. This is not a technical constraint—it's a philosophical one. Trust is built through consistent, quality performance.

### The Ladder

```
Level 0: Suggest → Wait for explicit command
         "Here's what I'd recommend..." then stop.

Level 1: Suggest with rationale → Receive vote (approve/reject)
         "I suggest X because Y. Approve or reject?"

Level 2: Act on small scope → Report after
         "I moved three due dates based on your calendar. Here's what changed."

Level 3: Act on larger scope → Periodic review
         "I reorganized your week's priorities. Review when convenient."
```

### How Trust is Earned

1. **Suggestion Phase**: DATA makes suggestions; David votes approve/reject
2. **Success Tracking**: System tracks approval rate over time
3. **Threshold Achievement**: When DATA consistently (e.g., 90%+) suggests correctly, trust level increases
4. **Scope Expansion**: Each level unlocks larger domains of autonomous action

**Implementation Status (December 2025)**:
- **Persistence Layer**: Suggestions and rules persist to Firestore with decision tracking
- **Decision Capture**: Approve/reject actions stored with timestamps and rationale
- **Analysis Audit**: Settings page shows per-account analysis breakdown for transparency
- **Metrics Ready**: `suggestion_store.py` and `rule_store.py` track approval rates by method and action type
- **Next Step**: Build trust metrics dashboard to visualize DATA's progress toward Level 2 autonomy

### Why This Model?

A key insight from our foundational conversation:

> "As DATA 'proves' that his understanding of the big picture as well as the details are solid, this will be granted. I would establish a process by which I would ask DATA, 'what have I procrastinated on, and what should we do about it and why.' Over time, as his answers are spot on, and as they reveal his understanding has surpassed mine, he can be granted the task."

This captures the essence: trust is a process, not a switch. DATA earns each level of autonomy through demonstrated competence.

---

## Memory Architecture

### The Decision: Self-Contained, From Scratch

**We rejected**: Importing from external memory systems or syncing with local files.

**We chose**: DATA builds its own Firestore-native memory from scratch.

**Why**:
1. **Stability**: External dependencies introduce fragility
2. **Control**: DATA's memory should be production-grade and auditable
3. **Organic Growth**: Knowledge should emerge naturally from task interactions
4. **Self-Sufficiency**: No external files or sync complexity

### Memory Layers

| Layer | Purpose | Retention |
|-------|---------|-----------|
| **Session Notes** | Raw observations from each interaction | 7 days (temporary) |
| **Weekly Digest** | Summarized patterns, decisions, outcomes | Permanent |
| **David Profile** | Core preferences, goals, relationships | Permanent (versioned) |
| **Entities/Relations** | People, orgs, tools, projects | Permanent (built organically) |

### The David Profile

A structured document capturing who David is—not just preferences, but patterns:

**Work Patterns**
- Peak productivity hours
- Context-switching tolerance
- Meeting density preferences

**Communication Preferences**
- Email tone and length preferences
- Use of bullets, tables, formatting
- Response time expectations by context

**Current Priorities**
- Quarterly OKRs
- Life themes and goals
- Active projects by domain (Personal / Church / Work)

**Key Relationships**
- Family (Esther, Elijah, Daniel, Scarlett, Gloria)
- Work hierarchy (who reports to whom, key collaborators)
- Church roles (leadership positions, ministry teams)
- Contacts with context (not just names, but relationships)

**Personal Quirks**
- Pet peeves
- Celebration preferences
- Communication style markers

---

## Email Management Philosophy

### The Three Layers

Email management operates across three distinct layers, each with different goals and trust requirements:

| Layer | Purpose | Status | Trust Level |
|-------|---------|--------|-------------|
| **Rules** | Automated categorization via Gmail filters | Working (Apps Script) | N/A - User-defined |
| **Suggestions** | Inbox hygiene + pattern learning | **Persistent** (Firestore) | Level 1 (suggest, await approval) |
| **Attention** | Action-required items surfaced | **Persistent** (Firestore) | Level 0-1 (surface, suggest) |

**Rules** are the foundation—automated filters that categorize incoming mail without AI involvement. These are managed through Google Sheets and deployed via Apps Script.

**Suggestions** represent DATA's inbox hygiene recommendations: archive this, label that, create a task from this. Each suggestion includes rationale and awaits David's approval. Over time, approval patterns feed the Trust Gradient.

**Attention** items are emails requiring David's action. These are surfaced proactively based on role-awareness and context, not just keyword matching.

### Persistence Before Intelligence

**Core Principle**: Information David has processed should not require re-processing.

Why this matters:
- **Token efficiency**: Re-analyzing the same email wastes API calls
- **Dismissals stick**: If David says "not actionable," that decision persists
- **Patterns accumulate**: Learning requires memory of past decisions
- **UX continuity**: Navigate away and back—items remain

This principle drives architecture decisions: attention items and suggestions are persisted to Firestore with TTL, not held only in React state.

**Implementation Complete (December 2025)**:
- `attention_store.py`: Attention items persist with dismiss/snooze status
- `suggestion_store.py`: Action suggestions persist with approve/reject decisions
- `rule_store.py`: Rule suggestions persist with decision tracking
- `analysis_store.py`: Last analysis results persist for cross-machine audit visibility
- All stores use ACCOUNT-based keying (church/personal) per `STORAGE_ARCHITECTURE.md`

### Role-Aware Detection

Generic regex patterns cannot capture the context that makes an email actionable. The phrase "pending purchase request" is noise for most people but HIGH priority for a Procurement Lead.

**Church Roles** (for davidroyes@southpointsda.org):
- Treasurer: invoices, payments, year-end, 1099s
- Procurement Lead: PO approvals, delivery status, purchase requests
- Maintenance Lead: facility issues, repairs
- Head Elder: board meetings, church leadership, pastor search
- IT Lead: AV issues, streaming, website

**Personal Contexts** (for david.a.royes@gmail.com):
- Homeowner: repairs, HOA, utilities, insurance
- Parent: school, appointments, Elijah & Daniel
- Family Coordinator: travel, events, appointments
- Financial: bills, statements, alerts

Role-awareness means DATA understands **why** David cares about certain emails, not just pattern-matching keywords.

### Trust Gradient for Email (Aligned with Core Philosophy)

Email actions follow the same Trust Gradient as other DATA capabilities:

```
Level 0: Surface attention items
         "These 5 emails may need action." User decides.

Level 1: Suggest with rationale → Receive vote
         "I suggest archiving these 12 newsletters. Approve?"

Level 2: Small autonomous actions (earned)
         "I archived 8 OneDrive notification emails."

Level 3: Larger scope autonomy (future)
         "I've been managing your newsletter backlog weekly."
```

**Current State (December 2025)**: DATA operates at Level 0-1 for email with full persistence and decision tracking. The foundation for Level 2+ is in place—approval rates are being tracked via `suggestion_store.py` and `rule_store.py`. Once approval rate consistently exceeds 90%, Level 2 autonomy can be considered.

### Storage Efficiency Principle

**Core Principle**: Data must have TTL or automated purge. No bloat that kills performance.

| Data Type | TTL | Rationale |
|-----------|-----|-----------|
| Active attention items | 30 days | Emails older than this are probably handled |
| Dismissed items | 7 days | Short memory for "not actionable" decisions |
| Approved suggestions | 30 days | Feeds learning, then expires |
| Rejected suggestions | 7 days | Learn from mistakes briefly, then move on |

Purge runs on-demand during analysis or via scheduled job. Relevant data is preserved; irrelevant data expires automatically.

### Work Email Exclusion

Work email (PGA TOUR) is intentionally excluded from DATA's email management for corporate privacy reasons. DATA manages only:
- Church: davidroyes@southpointsda.org
- Personal: david.a.royes@gmail.com

---

## The Quarterly Interview

### Purpose

Scheduled, structured conversations to deepen understanding and recalibrate.

### Why Quarterly?

Too frequent and it becomes noise. Too infrequent and things drift without correction. Quarterly aligns with natural business and personal planning cycles.

### Interview Structure

**Part 1: David's World** (Learning about the user)
- What priorities have shifted since we last spoke?
- What new tools, capabilities, or projects should I know about?
- What relationships have changed? (New collaborators, changed roles)
- What goals are you working toward this quarter?
- What constraints should I be aware of? (Time, energy, resources)

**Part 2: DATA's Performance** (Learning about the assistant)
- What do you think DATA is doing well?
- What area(s) could DATA stand to improve the most?

### Why Include Performance Feedback?

A critical insight from our session:

> "Your opinion about DATA's performance absolutely *is* data about you—it reveals what you value in an assistant, your expectations and standards, where friction exists, and how your needs evolve."

When David says "DATA is too verbose," that teaches DATA:
- David values brevity (preference about David)
- DATA should adjust response length (feedback about DATA)
- David's expectations may differ by context (deeper understanding)

The feedback loop serves double duty: improving DATA while learning David.

---

## Privacy and Data Handling

### Philosophy

David has agreed to share personal information with DATA. This is a conscious trade-off: deeper understanding requires deeper access.

### Model

- **Storage**: Firestore with encryption at rest
- **Access**: Production systems only (no local dumps of sensitive data)
- **Audit**: All memory updates are versioned and traceable
- **Control**: David can review, edit, or delete any stored information

### What We Don't Do

- Expose raw memory to external systems
- Share David's profile with other AI systems
- Store sensitive data (passwords, financial details) in profile
- Retain information David explicitly asks to forget

---

## Philosophical Questions to Revisit

These questions emerged during our foundational session. They don't have final answers—they're ongoing tensions to balance:

### 1. How Much Should DATA Infer vs. Ask?

DATA could infer preferences from behavior or explicitly ask. Each has trade-offs:
- **Inference**: Smoother experience, risk of wrong assumptions
- **Asking**: More accurate, risk of being tedious

**Current Position**: Start by asking (quarterly interviews), graduate to inference as confidence grows.

### 2. When Does Proactivity Become Interruption?

A proactive assistant surfaces things before being asked. But at what point does helpfulness become annoyance?

**Current Position**: Proactive suggestions should be:
- Timely (not interrupting deep work)
- Actionable (not just observations)
- Dismissable (easy to ignore without penalty)
- Improving (suggestions should get better over time)

### 3. How Do We Handle Conflicting Priorities?

David operates across three domains (Personal / Church / Work). Sometimes these conflict. How should DATA help?

**Current Position**: DATA surfaces conflicts, doesn't resolve them. "You have overlapping commitments Tuesday—which takes priority?" Decision remains with David.

### 4. What Makes DATA "David's" AI vs. Generic AI?

Many AI tools optimize for the average user. DATA optimizes for David specifically.

**Current Position**: Personalization comes from:
- Memory (knowing history)
- Profile (knowing preferences)
- Feedback (knowing what works)
- Time (accumulated understanding)

---

## The Vision in Practice

When Phase 3 is mature, a typical week might look like:

**Monday Morning**
> DATA: "Good morning. Based on your calendar and task list, here's what I suggest for today. I've moved three lower-priority items to Wednesday to make room. Your critical deadline is Thursday's church report—I've blocked 2 hours tomorrow afternoon when you're usually most focused. Approve?"

**Wednesday Afternoon**
> DATA: "You haven't responded to the vendor email from Monday. Should I draft a quick acknowledgment, or is this intentionally on hold?"

**Friday Evening**
> DATA: "This week you completed 12 tasks (up from 9 last week). Three items slipped—want me to redistribute them or do a quick triage session?"

This isn't science fiction. It's the logical endpoint of the philosophy documented here.

---

## Document History

| Version | Date | Summary |
|---------|------|---------|
| 1.2.0 | 2025-12-19 | Updated Trust Gradient and Email Management sections to reflect completed persistence layer, decision tracking, and analysis audit features |
| 1.1.0 | 2025-12-15 | Added Email Management Philosophy section (three layers, persistence, role-awareness, trust gradient, storage efficiency) |
| 1.0.0 | 2025-12-05 | Initial philosophy document from foundational session |

---

## Related Documents

| Document | Purpose |
|----------|---------|
| `PROJECT_DIRECTIVE.md` | High-level project status and architecture |
| `BACKLOG.md` | Feature roadmap and known issues |
| `DATA_PREFERENCES.md` | Operational behavior guidelines (how DATA acts) |
| This document | Philosophical foundation (why DATA acts) |

---

*"The world's most effective personal AI" is not a destination—it's a direction. This document captures where we're pointed and why.*

