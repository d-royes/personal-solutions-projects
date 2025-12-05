# Feature Backlog & Known Issues

> **Last Updated**: 2025-12-05  
> **Purpose**: Track planned features, enhancements, and known bugs for the Daily Task Assistant.

---

## DATA 2.0 Roadmap

### The North Star
> "The world's most effective personal AI."

DATA's evolution follows three phases, each building on the last:

### Phase 1: Better Tool (Current)
Task management, email drafting, research, planning. All human-initiated, human-reviewed.

- ✅ Task ingestion & scoring
- ✅ AI-powered planning & research
- ✅ Email drafting & sending
- ✅ Conversation history
- ✅ Feedback collection

### Phase 2: Daily Companion (Next)
DATA learns David specifically through persistent memory and weekly reflection cycles.

| Feature | Description | Status |
|---------|-------------|--------|
| **David Profile (Firestore)** | Work patterns, communication preferences, priorities, quirks | Planned |
| **Session Observation Logging** | Automatic capture of learnings from each interaction | Planned |
| **Weekly Digest Generation** | Summarize patterns, confirm/challenge preferences | Planned |
| **Quarterly Interview Process** | Structured Q&A about David's world AND DATA's performance | Planned |
| **Knowledge Graph (Entities/Relations)** | People, orgs, tools, projects - built organically over time | Planned |

**Key Design Decision**: DATA builds its own memory from scratch in Firestore. No external file dependencies. Entities/relations emerge naturally from task conversations.

### Phase 3: Strategic Partner (Future)
Earned autonomy through demonstrated understanding and tracked success.

| Feature | Description | Status |
|---------|-------------|--------|
| **Suggestion/Voting System** | DATA surfaces proactive suggestions, David votes approve/reject | Planned |
| **Success Threshold Tracking** | Measure suggestion accuracy over time | Planned |
| **Graduated Trust Levels** | Level 0 (suggest) → Level 1 (vote) → Level 2 (act + report) → Level 3 (periodic review) | Planned |
| **Proactive Task Reprioritization** | "You haven't touched X in 2 weeks" | Planned |
| **Autonomous Small Actions** | Mark tasks complete, reorder due dates (after earning trust) | Planned |

**Trust Gradient**: Autonomy is earned, not granted. Size/scope of autonomous tasks increases as success thresholds are met.

---

## Known Issues / Bugs

| Issue | Description | Status | Date Logged |
|-------|-------------|--------|-------------|
| Smartsheet Comment on Email Send | When an email is sent, the system should post a comment to the Smartsheet task (e.g., "Email sent: [subject] to [recipient] via [account]"). Currently, comments may not be posting reliably. Requires investigation of `live_tasks` flag and `SmartsheetClient.post_comment()` execution path. | Open | 2025-12-01 |
| Google OAuth blocks personal Gmail | `david.a.royes@gmail.com` gets "user not in org" error. OAuth consent screen in GCP is likely set to "Internal" (Workspace only) instead of "External", or email isn't added as test user. | **Resolved** - Changed to External | 2025-12-05 |

---

## Feature Backlog

### High Priority

*None currently*

### Medium Priority

| Feature | Description | Documentation |
|---------|-------------|---------------|
| Smartsheet Attachments | Enable DATA to access and understand task attachments (images, documents). Lazy load on task engage, full Claude vision integration for AI-assisted analysis. | [Feature_Smartsheet_Attachments.md](docs/Feature_Smartsheet_Attachments.md) |
| Bulk Task Prioritization | Allow DATA to analyze all open tasks and propose realistic due date distribution over 1-2 weeks based on priority and estimated hours. Batch update capability. | [Gap_Analysis_Conversation_Review.md](docs/Gap_Analysis_Conversation_Review.md) |

### Low Priority

| Feature | Description | Documentation |
|---------|-------------|---------------|
| Feedback Summary View | Admin menu view to see aggregated feedback statistics and patterns. | - |
| Save Contact Feature | Save frequently used contacts for quick access in email drafting. Contact management in admin menu. | - |
| Custom AI-Generated Actions | After Plan generation, DATA suggests context-specific action buttons (e.g., "Draft Template"). Hover tooltips, visual distinction from standard actions. | [Gap_Analysis_Conversation_Review.md](docs/Gap_Analysis_Conversation_Review.md) |
| Activity Feed Enhancement | Richer detail when clicking activity items - show conversation snippets, action results, full context. | [Gap_Analysis_Conversation_Review.md](docs/Gap_Analysis_Conversation_Review.md) |
| Header Cleanup / Environment Menu | Move API Base URL and Data Source to admin menu "Environment" view. Clean up header to just logo + menu button. | [Gap_Analysis_Conversation_Review.md](docs/Gap_Analysis_Conversation_Review.md) |

---

## Completed Features

Features that have been implemented and can be removed from backlog:

| Feature | Completed | Notes |
|---------|-----------|-------|
| Conversation Strike/Reject | 2025-12-05 | Users can strike poor DATA responses, collapsing to single line with audit trail |
| Dev → Staging → Prod Environments | 2025-12-03 | Full CI/CD pipeline with GitHub Actions, Cloud Run, Firebase Hosting |
| Auth Persistence | 2025-12-02 | Login survives page refresh via localStorage |
| Email Allowlist Security | 2025-12-02 | Only authorized emails can access the app |
| AI-Powered Contact Search | 2025-12-02 | Named Entity Recognition for finding contacts |
| Research Improvements | 2025-12-02 | Deeper insights, pros/cons, best practices |

---

## How to Use This Document

1. **Adding new items**: Add to appropriate priority section with description and any relevant documentation links
2. **Completing items**: Move to "Completed Features" section with date and notes
3. **Bugs**: Add to Known Issues table with status tracking
4. **Review**: Check this document during planning sessions to prioritize work


