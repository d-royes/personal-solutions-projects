# Feature Backlog & Known Issues

> **Last Updated**: 2025-12-31
> **Purpose**: Track planned features, enhancements, and known bugs for the Daily Task Assistant.

---

## DATA Cloud Vision

> **NEW**: A strategic vision document has been created for evolving DATA into a marketable product.
> See [DATA_CLOUD_VISION.md](docs/DATA_CLOUD_VISION.md) for the full roadmap.

**Key Decisions (2025-12-11):**
- Decouple from Smartsheet, build native task storage
- Abstract integrations (Gmail/Outlook, GCal/Outlook Calendar)
- User-scope all data for multi-tenancy
- Target: Tech-savvy early adopters
- Timeline: Phase A starts January 2025

---

## DATA 2.0 Roadmap

### The North Star
> "The world's most effective personal AI."

DATA's evolution follows three phases, each building on the last:

### Phase 1: Better Tool (Current)
Task management, email drafting, research, planning. All human-initiated, human-reviewed.

### Phase 2: Daily Companion (Next)
DATA learns David specifically through persistent memory and weekly reflection cycles.

### Phase 3: Strategic Partner (Future)
Earned autonomy through demonstrated understanding and tracked success.

**Trust Gradient**: Autonomy is earned, not granted.

---

## Known Issues / Bugs

| Issue | Description | Status | Date Logged |
|-------|-------------|--------|-------------|
| Smartsheet Comment on Email Send | Comments may not be posting reliably. | Open | 2025-12-01 |
| E2E Flaky Tests (3) | Three Playwright tests fail intermittently. 31/34 tests pass. | Open | 2025-12-11 |
| ~~Duplicate Suggestions Endpoint~~ | Two `/email/suggestions/{account}/pending` endpoints caused all suggestions to have `number: 1`, making approve clear all. | **Fixed** | 2025-12-19 |
| ~~Stale Cache on Account Switch~~ | Cache only updated when response had items, causing stale data when switching to account with empty results. | **Fixed** | 2025-12-19 |
| ~~Zombie Uvicorn Processes~~ | Orphaned uvicorn child processes held old code after restart. Documented fix in CLAUDE.md. | **Fixed** | 2025-12-19 |

---

## Feature Backlog

### Urgent Priority

| Feature | Description | Documentation |
|---------|-------------|---------------|
| **Email Task Assistant Integration** | Complete integration of Email Tasks (Firestore) into the Assistant workflow. | - |
| **F1: Attention Tab Testing** | Finish HITL testing of Attention tabs in Church and Personal accounts. Verify Haiku analysis consistency. | F1 Haiku Integration |
| **F1: Analysis Engine Badges** | Get AI/Regex badges working and consistent across all attention items. Role badges should also be styled consistently. | F1 Haiku Integration |

### High Priority

| Feature | Description | Documentation |
|---------|-------------|---------------|
| **Timezone Consistency (Backend)** | Fix remaining UTC/timezone issues in backend: Smartsheet date parsing, rebalancing logic, default due dates, email date extraction. Frontend labels fixed 2026-01-02. | [TIMEZONE_FIX.md](docs/TIMEZONE_FIX.md) |
| **Attachment Security Hardening** | Add defense-in-depth for attachment handling: (1) PDF download domain validation + size limits, (2) Image download domain validation, (3) Frontend URL sanitization for XSS prevention, (4) Error handling for read toggle cache consistency. | Code Review 2025-12-31 |
| **Phase A: Smartsheet Decoupling** | Create native Firestore task storage, abstract integrations into provider interfaces, user-scope all data. | [DATA_CLOUD_VISION.md](docs/DATA_CLOUD_VISION.md) |
| **Move Email Allowlist to Backend-Only** | Remove hardcoded ALLOWED_EMAILS from AuthContext.tsx:9-12. Frontend check is redundant since backend validates. Exposing authorized users in client code is unnecessary info disclosure. | Code Review 2025-12-14 |
| **Externalize Google Sheet ID** | Move hardcoded FILTER_SHEET_ID in filter_rules.py:29 to environment variable (GMAIL_FILTER_SHEET_ID). Improves configurability and follows 12-factor app principles. | Code Review 2025-12-14 |

### Medium Priority

| Feature | Description | Documentation |
|---------|-------------|---------------|
| **F2: Calendar Management Integration** | Complete the Assistant Trifecta (Email + Tasks + Calendar) with smart scheduling and meeting prep. | [Email Management Plan - F2](../.claude/plans/rippling-discovering-whale.md#f2-calendar-management-integration) |
| **F3: Full Memory Architecture** | Complete DATA Memory Architecture: weekly reflections, knowledge base, session notes. | [Email Management Plan - F3](../.claude/plans/rippling-discovering-whale.md#f3-full-memory-architecture-phase-2-foundation) |
| **F5: Smart Rule Suggestions** | AI-powered rule suggestions that understand context, not just patterns. Filter bad suggestions. | [Email Management Plan - F5](../.claude/plans/rippling-discovering-whale.md#f5-smart-rule-suggestions) |
| **F7: Parallel Haiku Prompts** | Split unified prompt into 3 focused parallel prompts (attention, action, rules). Trade efficiency for quality. See details below. | Backlog 2025-12-20 |
| Bulk Task Prioritization | Analyze all open tasks and propose realistic due date distribution. | [Gap_Analysis_Conversation_Review.md](docs/Gap_Analysis_Conversation_Review.md) |

### Low Priority

| Feature | Description | Documentation |
|---------|-------------|---------------|
| **F1a: User-Configurable Domain Blocklist** | Let users add/remove sensitive domains via Settings UI for Haiku privacy controls. | F1 Future Enhancement |
| **F1b: Metadata-Only Mode** | For semi-sensitive senders, send only subject/sender to Haiku (not body). | F1 Future Enhancement |
| **F1c: Privacy Audit Log** | Track what content was masked for transparency and debugging in Haiku analysis. | F1 Future Enhancement |
| **F4: Microsoft Integration** | Support Outlook ecosystem (MS Graph API) for DATA Cloud multi-tenancy. | [Email Management Plan - F4](../.claude/plans/rippling-discovering-whale.md#f4-microsoft-integration) |
| **F6: Bulk Email Actions** | Batch archive, label, dismiss operations with pattern recognition. | [Email Management Plan - F6](../.claude/plans/rippling-discovering-whale.md#f6-bulk-email-actions) |
| **Email Management Settings Page** | Admin settings for attention scanning time window, labels, notifications. | - |
| Feedback Summary View | Admin menu view for aggregated feedback statistics. | - |
| Save Contact Feature | Save frequently used contacts for quick email drafting access. | - |

### Superseded / Completed by Other Work

| Feature | Status | Notes |
|---------|--------|-------|
| ~~Dismissed Attention Cache~~ | Superseded | Now part of Sprint 2: Full Attention Persistence in [Email Management Plan](../.claude/plans/rippling-discovering-whale.md#sprint-2-persistence) |

---

## Completed Features

| Feature | Completed | Notes |
|---------|-----------|-------|
| **Task Attachments Gallery** | 2025-12-31 | Attachment viewer with thumbnails, selection, Claude Vision for images, pdfplumber for PDFs |
| **Mark as Read Toggle** | 2025-12-31 | Email read/unread toggle in Email Viewer and Suggestions tab |
| **F1: Full Persistence Layer** | 2025-12-19 | Suggestions, rules, and analysis results persist across refresh/machines via Firestore |
| **F1: Last Analysis Audit** | 2025-12-19 | Settings page shows analysis breakdown per account for auditing |
| **F1: Dashboard UI Improvements** | 2025-12-19 | Clickable tiles, Suggestions tile (yellow), count badges on tabs |
| **F1: Email Cache Persistence** | 2025-12-19 | Cache survives Task/Email mode switches (state lifted to App.tsx) |
| **F1: Storage Key Architecture** | 2025-12-19 | ACCOUNT-based keying prevents data fragmentation across logins |
| **F1: Haiku Intelligence Layer** | 2025-12-15 | AI-powered email analysis using Claude Haiku with privacy safeguards, usage limits, Settings UI |
| **Workspace Context Selection** | 2025-12-14 | Multi-select workspace items for Plan generation and Email drafts |
| **Email Rich Text Rendering** | 2025-12-14 | Email drafts render as HTML with proper formatting (bold, lists, paragraphs) |
| **Sanitize Test Conversations** | 2025-12-14 | Removed PII files from tracking, added to .gitignore |
| **Email Reply Feature** | 2025-12-12 | Full email body loading, thread context, AI reply drafts, Tiptap editor |
| **Email-Task Integration** | 2025-12-12 | Task creation from emails, Email Tasks filter |
| Email Management (Chief of Staff) | 2025-12-11 | Gmail inbox reader, Google Sheets rules integration |
| E2E Regression Testing | 2025-12-11 | Playwright framework with 34 tests |
| Dev to Staging to Prod Environments | 2025-12-03 | Full CI/CD pipeline |
| Auth Persistence | 2025-12-02 | Login survives page refresh |
| Email Allowlist Security | 2025-12-02 | Only authorized emails can access |

---

## Feature Details

### F7: Parallel Haiku Prompts

**Added**: 2025-12-20
**Status**: Under Consideration
**Rationale**: Current unified prompt asks Haiku to analyze attention, action, AND rule suggestions in one call. This may sacrifice quality for efficiency.

**Current Approach (Unified)**:
```
Email → Haiku → { attention, action, rule }
- 1 API call per email
- Single prompt juggling 3 objectives
- Shallow guidance per task
```

**Proposed Approach (Parallel)**:
```
Email → Haiku (attention prompt)  ─┐
Email → Haiku (action prompt)     ─┼→ Combine results
Email → Haiku (rule prompt)       ─┘
- 3 API calls per email (run via asyncio)
- Each prompt laser-focused with deep context
- ~3x cost, but similar latency (parallel)
```

**Trade-offs**:

| Factor | Unified | Parallel |
|--------|---------|----------|
| API calls/email | 1 | 3 |
| Cost | Lower | ~3x |
| Latency | Lower | Similar (parallel) |
| Prompt depth | Shallow | Deep |
| Quality | Compromised | Focused |

**Hybrid Option**: Keep attention+action unified (simpler tasks), separate rules into focused prompt (2 calls).

**Decision Criteria**: Monitor cost and quality over 2-3 weeks with improved unified prompt, then evaluate if parallel approach is warranted.

**Rule Prompt Benefits** (if separated):
- Full label definitions with examples
- Relationship detection guidance
- Pattern recognition criteria
- Account-specific context
- **Existing rules as examples**: Send current Google Sheets rules to show DATA what good rules look like and learn user preferences (field patterns, category choices, naming conventions)

---

## How to Use This Document

1. **Adding new items**: Add to appropriate priority section
2. **Completing items**: Move to "Completed Features" section with date
3. **Bugs**: Add to Known Issues table with status tracking
4. **Review**: Check during planning sessions to prioritize work
