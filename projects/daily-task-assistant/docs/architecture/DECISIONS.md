# Architecture Decision Records

> Last updated: 2026-01-21 by Architecture Agent  
> Analyzed commit: `2da6f89`

This document tracks significant architecture decisions for the DATA project.

---

## ADR Index

| ID | Decision | Status | Date |
|----|----------|--------|------|
| [ADR-001](#adr-001) | Use Firestore for cloud persistence | Accepted | 2025-12-01 |
| [ADR-002](#adr-002) | Bidirectional Smartsheet sync with FSID | Accepted | 2026-01-15 |
| [ADR-003](#adr-003) | Multi-LLM architecture (Claude + Gemini) | Accepted | 2025-12-01 |
| [ADR-004](#adr-004) | Claude Haiku for email analysis | Accepted | 2025-12-01 |
| [ADR-005](#adr-005) | Three-date model for task scheduling | Accepted | 2026-01-15 |
| [ADR-006](#adr-006) | Smartsheet-to-Firestore transition strategy | Accepted | 2026-01-15 |
| [ADR-007](#adr-007) | Protect FS-managed recurring tasks during sync | Accepted | 2026-01-21 |
| [ADR-008](#adr-008) | Modular API router architecture | Accepted | 2026-01-21 |

---

## ADR-001: Use Firestore for Cloud Persistence

**Date:** 2025-12-01  
**Status:** Accepted

### Context
DATA needed cloud persistence for tasks, conversations, and feedback to support:
- Multi-device access
- Cloud Run deployment
- Data durability beyond local storage

### Decision
Use Google Firestore as the primary cloud database.

### Consequences
**Pros:**
- Native Google Cloud integration
- Real-time capabilities (future)
- Flexible document model
- Free tier sufficient for personal use

**Cons:**
- Vendor lock-in to Google Cloud
- Query limitations vs SQL
- Cost at scale (not a concern for personal use)

### Alternatives Considered
- **PostgreSQL**: More powerful queries, but requires managing a server
- **SQLite + Cloud Storage**: Simpler, but no real-time or concurrent access
- **Supabase**: Good alternative, but adds another vendor

---

## ADR-002: Bidirectional Smartsheet Sync with FSID

**Date:** 2026-01-15  
**Status:** Accepted

### Context
David's established workflow uses Smartsheet. DATA needs to integrate with Smartsheet while also supporting:
- Firestore-only tasks (DATA Tasks)
- Offline/local changes
- Duplicate prevention

### Decision
Implement bidirectional sync between Smartsheet and Firestore using an FSID (Firestore ID) column in Smartsheet.

### Consequences
**Pros:**
- Preserves existing Smartsheet workflow
- Enables DATA Tasks without Smartsheet
- FSID prevents duplicates during sync

**Cons:**
- Sync complexity (conflict resolution)
- Requires FSID column in Smartsheet
- Two sources of truth to manage

### Alternatives Considered
- **Smartsheet only**: Simpler, but no offline support or DATA Tasks
- **Firestore only**: Cleaner, but breaks existing workflow
- **Webhook-based sync**: Real-time, but more complex infrastructure

---

## ADR-003: Multi-LLM Architecture (Claude + Gemini)

**Date:** 2025-12-01  
**Status:** Accepted

### Context
DATA needs LLMs to power:
- Intelligent chat assistance with tool use
- Fast intent classification
- Cost-effective conversational responses
- Email analysis at scale

A single model can't optimize for all use cases.

### Decision
Implement a multi-LLM architecture:
- **Claude Opus 4.5** (`claude-opus-4-5-20251101`): Tool-heavy operations (task updates, research, planning with actions)
- **Claude 3.5 Haiku** (`claude-3-5-haiku-20241022`): Email batch analysis (attention detection, rule suggestions)
- **Gemini 2.5 Flash** (`gemini-2.5-flash`): Intent classification (fast, cheap routing)
- **Gemini 2.5 Pro** (`gemini-2.5-pro`): Conversational chat without tools (quality responses)

### Consequences
**Pros:**
- Cost optimization (cheap models for simple tasks)
- Speed optimization (Gemini Flash for classification)
- Best model for each job (Claude for tools, Gemini for chat)
- Fallback capability (if one provider fails)

**Cons:**
- Multiple API keys to manage
- More complex routing logic
- Two vendor dependencies

### Alternatives Considered
- **Claude only**: Simpler, but expensive for classification/chat
- **Gemini only**: Cheaper, but tool use less mature
- **Local LLM (Llama)**: Free, but requires GPU and lower quality

---

## ADR-004: Claude Haiku for Email Analysis

**Date:** 2025-12-01  
**Status:** Accepted

### Context
Analyzing all inbox emails with Claude Opus 4.5 would be expensive. Need a cost-effective solution for:
- Email urgency scoring (attention detection)
- Batch classification
- Rule suggestions
- Action recommendations (archive, label, star)

### Decision
Use **Claude 3.5 Haiku** (model: `claude-3-5-haiku-20241022`) for email analysis in `haiku_analyzer.py`.

**Naming Note:** The file is named `haiku_analyzer.py` because it uses the actual Anthropic Haiku model, not as a metaphor for brevity. This naming is intentional and accurate.

**Deprecation Warning:** Anthropic is retiring Haiku API access in February 2026. Migration plan needed.

### Consequences
**Pros:**
- Significantly lower cost than Opus for batch operations
- Fast processing for email triage
- Privacy safeguards built in (blocklist, content masking)
- Good enough quality for classification tasks

**Cons:**
- Haiku model being deprecated (Feb 2026)
- Less capable than Opus for complex reasoning
- Still requires Anthropic API key

### Alternatives Considered
- **Claude Opus only**: Higher quality, but 10x cost for batch analysis
- **Gemini Flash**: Cheaper, but less proven for email analysis
- **Rule-based only**: Cheapest, but misses nuance and context
- **Post-deprecation options**: Gemini Flash, Claude 3 Haiku replacement (if any)

---

## ADR-005: Three-Date Model for Task Scheduling

**Date:** 2026-01-15  
**Status:** Accepted

### Context
Tasks need flexible scheduling that distinguishes between:
- When you plan to work on it
- When you originally wanted it done
- When it absolutely must be done

### Decision
Implement a three-date model:
- `planned_date`: When you'll work on it (mutable)
- `target_date`: Original goal (informational)
- `hard_deadline`: Must complete by (immutable)

### Consequences
**Pros:**
- Enables realistic rescheduling without losing context
- Hard deadlines remain visible even when replanning
- Supports both flexible and fixed commitments

**Cons:**
- More complex than single due date
- UI must clearly distinguish the three
- Sync mapping to Smartsheet columns

### Alternatives Considered
- **Single due date**: Simpler, but loses context when rescheduling
- **Due date + deadline only**: Misses the "when will I do it" aspect
- **Full calendar blocking**: Too heavyweight for task management

---

## ADR-006: Smartsheet-to-Firestore Transition Strategy

**Date:** 2026-01-15  
**Status:** Accepted (In Progress)

### Context
David has used Smartsheet for task management for 8+ years. It's deeply integrated into his workflow, especially for work tasks. However, Firestore offers advantages:
- No API rate limits
- Better querying capabilities
- Native integration with DATA features (email-to-task, three-date model)
- Offline support potential

Need a transition strategy that:
- Preserves existing Smartsheet workflow during transition
- Allows gradual adoption of Firestore
- Handles sync conflicts gracefully
- Doesn't require "big bang" migration

### Decision
Implement gradual transition with bidirectional sync:

1. **Current Phase (Testing):** Firestore integrated but Smartsheet remains primary
2. **Transition Phase:** Bidirectional sync keeps both systems current
3. **Future Phase:** Firestore becomes primary, Smartsheet becomes read-only archive

**Conflict Resolution:** Last-updated-wins strategy
- Both systems store cross-references (FSID in Smartsheet, smartsheet_row_id in Firestore)
- `smartsheet_modified_at` timestamp stored in Firestore for comparison
- `updated_at` in Firestore tracks local changes
- Sync compares timestamps to determine which version is newer

### Consequences
**Pros:**
- No disruption to existing workflow
- Can validate Firestore before committing
- Rollback is trivial (just use Smartsheet)
- Work tasks can stay in Smartsheet longer

**Cons:**
- Maintaining two systems during transition
- Sync bugs can cause confusion
- Need to eventually cut over fully

### Current Status (January 2026)
- Firestore task CRUD: ✅ Implemented
- Bidirectional sync: ✅ Implemented (testing)
- Three-date model: ✅ Implemented in FirestoreTask
- Minor bugs: 🔄 Being resolved
- Full cutover: ⏳ Pending validation

---

## ADR-007: Protect FS-Managed Recurring Tasks During Sync

**Date:** 2026-01-21  
**Status:** Accepted

### Context

Bidirectional sync between Smartsheet and Firestore creates a potential conflict for recurring tasks. Smartsheet has its own automation for recurring tasks (checking off "Done" triggers a new row creation). However, Firestore's recurring logic is more sophisticated and manages:
- `planned_date`: Next occurrence
- `done`: Completion status
- `completed_on`: Completion timestamp
- `recurring_type`: Pattern (daily, weekly, monthly)
- `recurring_days`: Specific days (M, T, W, etc.)

When syncing from Smartsheet to Firestore, if we blindly overwrite these fields, Smartsheet's automation can corrupt Firestore's recurring logic.

### Decision

Implement a **protection layer** in `sync/service.py` that detects FS-managed recurring tasks and skips updating recurring-sensitive fields.

**Implementation:**
```python
# Check if this is a FS-managed recurring task
is_fs_managed_recurring = bool(existing.recurring_type)

# For FS-managed recurring tasks, skip recurring-sensitive fields
if not is_fs_managed_recurring:
    updates["planned_date"] = translated["planned_date"]
    updates["done"] = translated["done"]
    updates["completed_on"] = translated["completed_on"]
    updates["recurring_type"] = translated["recurring_type"]
    updates["recurring_days"] = translated["recurring_days"]
```

**Code Reference:** `daily_task_assistant/sync/service.py` lines 920-956

### Consequences

**Pros:**
- Preserves Firestore's advanced recurring logic
- Allows Firestore to implement recurring patterns beyond Smartsheet's capabilities
- Prevents accidental data corruption during sync
- Sync continues to work normally for non-recurring fields (title, status, priority, etc.)

**Cons:**
- Recurring tasks have "split brain" - Smartsheet automation and Firestore logic operate independently
- Changes to recurring fields in Smartsheet are ignored for FS-managed tasks
- Requires understanding of which system "owns" recurring logic

### Alternatives Considered

- **Always sync all fields**: Simpler, but Smartsheet automation would corrupt Firestore recurring logic
- **Disable Smartsheet recurring automation**: Would work, but requires manual row management in Smartsheet
- **Flag-based override**: Add explicit field to choose sync behavior - more complex for marginal benefit

---

## ADR-008: Modular API Router Architecture

**Date:** 2026-01-21  
**Status:** Accepted

### Context

The `api/main.py` file had grown to ~8000 lines containing all 136+ API endpoints. This created several problems:

1. **Maintainability**: Difficult to navigate, understand, and modify
2. **Testing**: Hard to test endpoints in isolation
3. **Collaboration**: Merge conflicts when multiple developers touch the file
4. **Onboarding**: Overwhelming for new contributors
5. **Code organization**: No clear domain boundaries

### Decision

Refactor the API layer into **modular FastAPI routers** organized by domain:

```
api/
├── main.py              # App setup, middleware, router registration
├── dependencies.py      # Shared auth helpers (get_current_user, etc.)
├── models.py            # Shared Pydantic request/response models
└── routers/
    ├── __init__.py      # Router exports
    ├── tasks.py         # /tasks, /sync, /work endpoints
    ├── calendar.py      # /calendar endpoints
    ├── assist.py        # /assist endpoints
    └── email.py         # /inbox, /email endpoints
```

**Implementation approach:**
1. Create router infrastructure (`dependencies.py`, `models.py`, `routers/`)
2. Extract endpoints incrementally by domain (tasks → calendar → assist → email)
3. Keep original endpoints during transition (causes duplicate warnings)
4. Validate via regression tests (Schemathesis + snapshots)
5. Remove original endpoints after production validation

### Consequences

**Pros:**
- **Maintainability**: Each router is ~200-1200 lines, focused on one domain
- **Testability**: Can test routers in isolation
- **Discoverability**: Clear file names indicate endpoint locations
- **Scalability**: Easy to add new routers for new domains
- **Shared code**: Common dependencies extracted to reusable modules

**Cons:**
- **Migration period**: Duplicate endpoints cause OpenAPI warnings
- **Import complexity**: Routers must import from dependencies.py
- **Path management**: Email router needs no prefix (paths include /inbox and /email)

### Testing Strategy

To prevent regressions during refactoring:
- **Schemathesis**: Auto-generated tests validate all endpoints against OpenAPI schema
- **Snapshot tests**: Verify response structures remain unchanged
- **All 33 existing tests**: Must pass before and after

### Alternatives Considered

- **Keep monolithic main.py**: Simpler, but unsustainable at 8000+ lines
- **Split by HTTP method**: Would scatter related endpoints across files
- **Microservices**: Overkill for a single-user application
- **Class-based views**: FastAPI's router system is more idiomatic

### Related Files

- `api/routers/__init__.py`: Router package with exports
- `api/dependencies.py`: Shared `get_current_user()`, constants
- `api/models.py`: Shared Pydantic models
- `tests/test_api_regression.py`: Schemathesis contract tests
- `tests/test_api_snapshots.py`: Response structure snapshots

---

## Template for New ADRs

```markdown
## ADR-XXX: [Title]

**Date:** YYYY-MM-DD  
**Status:** Proposed | Accepted | Deprecated | Superseded

### Context
[Why was this decision needed? What problem are we solving?]

### Decision
[What was decided?]

### Consequences
**Pros:**
- [Benefit 1]
- [Benefit 2]

**Cons:**
- [Drawback 1]
- [Drawback 2]

### Alternatives Considered
- **Option A**: [Description and why rejected]
- **Option B**: [Description and why rejected]
```

---

## Related Documentation

- [OVERVIEW.md](./OVERVIEW.md) - System overview
- [COMPONENTS.md](./COMPONENTS.md) - Module breakdown
- [INTEGRATIONS.md](./INTEGRATIONS.md) - External services
