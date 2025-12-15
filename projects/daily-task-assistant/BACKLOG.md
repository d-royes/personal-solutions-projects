# Feature Backlog & Known Issues

> **Last Updated**: 2025-12-14
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

---

## Feature Backlog

### Urgent Priority

| Feature | Description | Documentation |
|---------|-------------|---------------|
| **Email Task Assistant Integration** | Complete integration of Email Tasks (Firestore) into the Assistant workflow. | - |

### High Priority

| Feature | Description | Documentation |
|---------|-------------|---------------|
| **Phase A: Smartsheet Decoupling** | Create native Firestore task storage, abstract integrations into provider interfaces, user-scope all data. | [DATA_CLOUD_VISION.md](docs/DATA_CLOUD_VISION.md) |
| **Move Email Allowlist to Backend-Only** | Remove hardcoded ALLOWED_EMAILS from AuthContext.tsx:9-12. Frontend check is redundant since backend validates. Exposing authorized users in client code is unnecessary info disclosure. | Code Review 2025-12-14 |
| **Externalize Google Sheet ID** | Move hardcoded FILTER_SHEET_ID in filter_rules.py:29 to environment variable (GMAIL_FILTER_SHEET_ID). Improves configurability and follows 12-factor app principles. | Code Review 2025-12-14 |

### Medium Priority

| Feature | Description | Documentation |
|---------|-------------|---------------|
| **Dismissed Attention Cache** | Track dismissed attention items (email IDs) so they don't resurface. 7-day TTL. | - |
| Bulk Task Prioritization | Analyze all open tasks and propose realistic due date distribution. | [Gap_Analysis_Conversation_Review.md](docs/Gap_Analysis_Conversation_Review.md) |

### Low Priority

| Feature | Description | Documentation |
|---------|-------------|---------------|
| **Email Management Settings Page** | Admin settings for attention scanning time window, labels, notifications. | - |
| Feedback Summary View | Admin menu view for aggregated feedback statistics. | - |
| Save Contact Feature | Save frequently used contacts for quick email drafting access. | - |

---

## Completed Features

| Feature | Completed | Notes |
|---------|-----------|-------|
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

## How to Use This Document

1. **Adding new items**: Add to appropriate priority section
2. **Completing items**: Move to "Completed Features" section with date
3. **Bugs**: Add to Known Issues table with status tracking
4. **Review**: Check during planning sessions to prioritize work
