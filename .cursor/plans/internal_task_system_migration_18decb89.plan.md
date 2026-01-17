---
name: Internal Task System Migration
overview: Establish a unified internal task management system in Firestore that runs parallel to Smartsheet with bidirectional sync, full CRUD UI, and preserved calendar/portfolio integration - with DATA quality protection through collaborative testing.
todos:
  - id: phase0-setup
    content: "Phase 0: Create feature/unified-tasks branch and establish DATA quality baseline"
    status: pending
  - id: phase1-foundation
    content: "Phase 1: Foundation - Enhanced model, sync engine, direct CRUD UI (LOW RISK)"
    status: pending
  - id: phase2-data-awareness
    content: "Phase 2: DATA Awareness - Portfolio/rebalancing with Firestore tasks (MEDIUM RISK, quality gates)"
    status: pending
  - id: phase3-data-creation
    content: "Phase 3: DATA Task Creation - Add create_task tool to DATA (HIGH RISK, collaborative testing)"
    status: pending
  - id: phase4-migration
    content: "Phase 4: Migration - Sync dashboard, Firestore primary toggle, validation period"
    status: pending
---

# Internal Task Management System - Migration Plan

## Executive Summary

Migrate from Smartsheet-only task management to a unified Firestore-based system with:

- Bidirectional sync during parallel operation (30 min auto + manual trigger)
- Full CRUD UI independent of DATA (modals, quick actions)
- Preserved Portfolio view, rebalancing, and calendar integration
- DATA quality protection through collaborative testing
- Flexible timeline to Firestore-primary (1-2 months of validation)

---

## Design Decisions (Collaborative Walkthrough Results)

### Decision 1: Three-Date Model

| Field | Purpose | Behavior |

|-------|---------|----------|

| `planned_date` | When you plan to work on it | Auto-rolls forward (like current due_date) |

| `target_date` | Original goal | Set once on creation, never auto-changes |

| `hard_deadline` | External commitment | Optional, triggers escalating alerts |

| `times_rescheduled` | Slippage tracking | Increments on each reschedule |

**Benefit:** DATA can say "This task was originally due Jan 10, now planned for Jan 15 (slipped 5 days, rescheduled 1 time)"

### Decision 2: Hybrid Daily Ordering

- Keep `number` field for manual task ordering
- Add DATA assistance: "DATA, suggest my task order for today"
- DATA considers meetings, deadlines, energy patterns
- You review and adjust; DATA learns from adjustments

### Decision 3: Status Model (12 values)

**Core (8):** scheduled, in_progress, on_hold, awaiting_reply, follow_up, completed, cancelled

**Optional (4):** delivered, validation, needs_approval, delegated

**Removed:** create_zd_ticket, ticket_created (Zendesk-specific, use project field instead)

### Decision 4: Recurring as Attribute

- `is_recurring` / `recurring_pattern` is an ATTRIBUTE, not a status
- A recurring task can have status "in_progress" or "awaiting_reply"
- Status always reflects current workflow state
- Recurring badge shown in UI based on attribute

**Enhanced recurring patterns:**

- Weekly: S, M, T, W, H, F, Sa (same as Smartsheet)
- Monthly: 1st, 15th, last, first_monday, etc. (NEW)
- Custom: Every N days/weeks (NEW)

### Decision 5: Domain as Primary Category

- `domain`: "personal" | "church" | "work" (the meaningful categorization)
- Derived from project on Smartsheet import
- User can set directly for new tasks
- No separate "source sheet" tracking needed

### Decision 6: Work Domain Strategy

- Full bidirectional sync (same as personal/church)
- Company deprecating Smartsheet within ~1 year anyway
- Work tasks naturally migrate to Firestore as company exits SS
- During transition: work data appears in both systems (compliant)

### Decision 7: UI Patterns

- **Task Creation:** Modal dialog (consistent with Calendar events)
- **Task Detail/Edit:** Modal dialog
- **Quick Actions:** Appear on task selection (mobile-friendly, cleaner list)
- **All direct CRUD:** Calls API directly, NO LLM involvement

### Decision 8: Task Creation Modes

1. **UI Quick Creation** (Phase 1 - Low Risk)

   - [+ New Task] button → Modal form → Direct API
   - No LLM involved, fast, reliable

2. **DATA Chat Creation** (Phase 3 - High Risk, Careful)

   - "DATA, create a task to follow up on X"
   - Requires prompt/tool changes
   - Deploy with quality gates

### Decision 9: Sync Behavior

- **New task sync:** ALWAYS - every Firestore task syncs to Smartsheet
- **Timing:** Every 30 minutes + manual "Sync Now" button
- **Conflicts:** Flag in UI, user chooses resolution

---

## Critical Principle: DATA Quality Protection

### The Lesson Learned

Previous attempt to add task creation in Task mode caused DATA to **hallucinate** in Portfolio view. This was the ONLY time DATA has hallucinated. All work was scrapped.

### Protection Protocol

**All Medium & High risk changes (LLM-touching) will be done:**

1. **COLLABORATIVELY** - User involved in testing, not just informed
2. **INCREMENTALLY** - One feature at a time, each with own rollback
3. **WITH QUALITY GATES** - Baseline → Change → Test → Approve/Rollback

**Per-Feature Workflow:**

```
1. Plan: Discuss change, agree on approach
2. Baseline: User runs test prompts, document results
3. Implement: Make change, create git tag (restore point)
4. Test: User runs same prompts, compare quality
5. Decide: User approves or we rollback
6. Stabilize: Run 2-5 days before next LLM change
```

### Risk Classification

| Risk Level | Components | Approach |

|------------|-----------|----------|

| **LOW** | Firestore model, Sync engine, CRUD modals, TaskList UI | Move quickly, no quality gates needed |

| **MEDIUM** | Portfolio context with Firestore tasks, Rebalancing with three-date model | Quality gates, 2-3 day stabilization |

| **HIGH** | DATA create_task tool (Calendar), DATA create_task (Portfolio) | Extra careful, 5-7 day stabilization |

---

## Git Workflow & Environments

### Branch Strategy

```
feature/unified-tasks              (local dev only)
       │
       │ merge when phase complete
       ▼
Daily-Task-Assistant ─────────────► STAGING
       │
       │ merge when validated
       ▼
main ─────────────────────────────► PRODUCTION
```

### Hotfix Capability

If critical bug found during migration work:

1. `git stash` (save feature work)
2. `git checkout Daily-Task-Assistant`
3. Fix bug, commit, push to STAGING
4. Test fix, merge to main → PRODUCTION
5. `git checkout feature/unified-tasks`
6. `git rebase Daily-Task-Assistant` (get fix)
7. `git stash pop` (resume feature work)

---

## Enhanced FirestoreTask Model

```python
@dataclass(slots=True)
class FirestoreTask:
    # Identity
    id: str                          # UUID
    domain: str                      # "personal" | "church" | "work"
    
    # Core fields
    title: str
    status: str                      # 12 values (see Decision #3)
    priority: str                    # Critical/Urgent/Important/Standard/Low
    project: Optional[str]
    number: Optional[float]          # Daily ordering
    
    # Three-date model (Decision #1)
    planned_date: Optional[date]     # When to work on it (auto-rolls)
    target_date: Optional[date]      # Original goal (never changes)
    hard_deadline: Optional[date]    # External commitment
    times_rescheduled: int = 0       # Slippage counter
    
    # Recurring (Decision #4)
    recurring_type: Optional[str]    # "weekly" | "monthly" | "custom"
    recurring_days: List[str]        # ["M", "W", "F"] for weekly
    recurring_monthly: Optional[str] # "1st" | "15th" | "last" | etc.
    recurring_interval: Optional[int] # Every N days/weeks for custom
    
    # Task details
    notes: Optional[str]
    next_step: Optional[str]
    estimated_hours: Optional[float]
    assigned_to: Optional[str]
    contact_required: bool = False   # Task requires external contact
    
    # Completion
    done: bool = False
    completed_on: Optional[date]
    
    # Source tracking
    source: str                      # "email" | "manual" | "smartsheet_sync" | "chat"
    source_email_id: Optional[str]
    source_email_account: Optional[str]
    source_email_subject: Optional[str]
    
    # Sync tracking
    smartsheet_row_id: Optional[str]
    smartsheet_sheet: Optional[str]  # "personal" | "work"
    sync_status: str = "local_only"  # "synced" | "pending" | "conflict" | "local_only"
    last_synced_at: Optional[datetime]
    
    # Timestamps
    created_at: datetime
    updated_at: datetime
```

---

## Phased Implementation

### Phase 0: Setup (Day 1)

- [ ] Create `feature/unified-tasks` branch from `Daily-Task-Assistant`
- [ ] Document current DATA test prompts for baseline
- [ ] Run baseline prompts, save responses

### Phase 1: Foundation (LOW RISK - ~1 week)

**No LLM changes - move quickly**

- [ ] 1a. Enhance FirestoreTask model with all new fields
- [ ] 1b. Build SyncService (Smartsheet ↔ Firestore bidirectional)
- [ ] 1c. Add sync API endpoints (`/sync/now`, `/sync/status`)
- [ ] 1d. Create TaskCreateModal.tsx (direct API, no LLM)
- [ ] 1e. Create TaskDetailModal.tsx (direct API, no LLM)
- [ ] 1f. Enhance TaskList.tsx (integrate Firestore, sync indicators, quick actions)
- [ ] 1g. Test sync, modals, UI thoroughly

**Deliverable:** Full task CRUD UI working with Firestore + Smartsheet sync

### Phase 2: DATA Awareness (MEDIUM RISK - ~1.5-2 weeks)

**Quality gates required - user validates each step**

- [ ] 2a. **QUALITY GATE** - Capture baseline before starting
- [ ] 2b. Portfolio context includes Firestore tasks
  - Baseline → Implement → Test → Approve/Rollback
  - Stabilize 2-3 days
- [ ] 2c. Rebalancing with three-date model
  - Updates `planned_date`, preserves `target_date`
  - Increments `times_rescheduled`
  - Baseline → Implement → Test → Approve/Rollback
  - Stabilize 2-3 days
- [ ] 2d. Task engagement works with Firestore-sourced tasks
  - Baseline → Implement → Test → Approve/Rollback
  - Stabilize 2-3 days

**Deliverable:** DATA fully aware of Firestore tasks, rebalancing works with new model

### Phase 3: DATA Task Creation (HIGH RISK - ~2 weeks)

**Extra careful - this is where previous issues occurred**

- [ ] 3a. **QUALITY GATE** - Fresh baseline before starting
- [ ] 3b. Add `create_task` tool to DATA (Calendar mode first)
  - Safest context to test
  - Baseline → Implement → Test → Approve/Rollback
  - Stabilize 3-5 days
- [ ] 3c. Extend `create_task` to Portfolio/Task mode
  - HIGH RISK zone - most sensitive
  - Baseline → Implement → Test → Approve/Rollback
  - Stabilize 5-7 days

**Deliverable:** DATA can create tasks via chat in all modes

### Phase 4: Migration (Flexible timing)

- [ ] 4a. Add sync dashboard to Settings (status, conflicts, manual trigger)
- [ ] 4b. Add "Firestore Primary" toggle
- [ ] 4c. Validate for 1-2 months
- [ ] 4d. Switch to Firestore primary
- [ ] 4e. Optional: Disable Smartsheet sync entirely

**Deliverable:** Firestore is primary task store, Smartsheet optional

---

## Key Files to Modify

| File | Changes |

|------|---------|

| `task_store/store.py` | Extend model with all new fields |

| `api/main.py` | Sync endpoints, unified task API |

| `TaskList.tsx` | Firestore integration, sync indicators, quick actions |

| `types.ts` | Enhanced FirestoreTask type |

| `api.ts` | Sync API, CRUD API functions |

| `portfolio_context.py` | Include Firestore tasks |

| `anthropic_client.py` | create_task tool (Phase 3) |

## New Files to Create

| File | Purpose |

|------|---------|

| `services/sync_service.py` | Bidirectional sync logic |

| `TaskCreateModal.tsx` | Quick task creation UI |

| `TaskDetailModal.tsx` | Task view/edit modal |

---

## Timeline Estimate

| Phase | Duration | Risk | Quality Gates |

|-------|----------|------|---------------|

| Phase 0 | 1 day | None | Setup only |

| Phase 1 | ~1 week | LOW | None needed |

| Phase 2 | ~1.5-2 weeks | MEDIUM | 3 gates, stabilization periods |

| Phase 3 | ~2 weeks | HIGH | 2 gates, longer stabilization |

| Phase 4 | Flexible | LOW | User validation |

**Total: 4-6 weeks (flexible based on availability and testing)**

---

## Task Capture Channels (Preserved)

All existing capture methods continue working:

| Channel | Current Flow | With Unified System |

|---------|-------------|---------------------|

| Mobile Quick Capture | Voice → Smartsheet Form | Same (sync brings to Firestore) |

| Email Forwarding | it@southpointsda.org → SS | Same (sync brings to Firestore) |

| DATA Chat | Creates in Smartsheet | Creates in Firestore (syncs to SS) |

| Email Attention | Creates in Firestore | Same |

| Direct Smartsheet | Manual entry | Same (sync brings to Firestore) |

| [+ New Task] UI | N/A (new) | Creates in Firestore (syncs to SS) |

---

## Success Criteria

- [ ] All tasks visible from unified view (Smartsheet + Firestore)
- [ ] Sync works reliably (30 min auto + manual)
- [ ] Quick task creation from UI without DATA
- [ ] DATA can still create tasks via chat (Phase 3)
- [ ] Portfolio view and rebalancing work with three-date model
- [ ] DATA response quality unchanged (no hallucinations)
- [ ] Slippage tracking provides useful insights
- [ ] Path to Firestore-primary is clear and tested

---

## Existing Code to Leverage

- `daily_task_assistant/task_store/store.py` - FirestoreTask model exists (needs enhancement)
- `daily_task_assistant/task_store/__init__.py` - CRUD functions: create_task, get_task, list_tasks, update_task, delete_task, create_task_from_email
- `/tasks/firestore` endpoints in `api/main.py` - Already exist for listing/getting/updating Firestore tasks
- `TaskList.tsx` - Has "Email Tasks" filter showing Firestore tasks (needs integration into main list)
- `smartsheet_client.py` - Full Smartsheet CRUD (list, update, create, mark_complete, attachments, comments)