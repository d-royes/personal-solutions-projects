# Phase 2 Pickup Plan - DATA Awareness
**Date:** January 15, 2026  
**Status:** Ready to begin after Phase 1 completion  
**Risk Level:** Medium (LLM-touching changes)

---

## Where We Left Off

### Phase 1 Complete ✅
All sync infrastructure is in place and tested:

| Component | Status | Notes |
|-----------|--------|-------|
| FirestoreTask dataclass | ✅ | Full field support including three-date model |
| SyncService (SS↔FS) | ✅ | Bidirectional sync working |
| Sync API endpoints | ✅ | `/sync/now` with direction control |
| Task list from Firestore | ✅ | UI displays Firestore tasks |
| Task create modal | ✅ | Creates directly in Firestore |
| Task detail/edit modal | ✅ | Updates Firestore with auto sync_status |
| Date string parsing | ✅ | Fixed `.isoformat()` error on updates |
| FSID bidirectional linking | ✅ | Prevents duplicates on both sides |

### Key Files Modified (for reference)
- `daily_task_assistant/task_store/store.py` - FirestoreTask + CRUD
- `daily_task_assistant/sync/service.py` - SyncService with FSID
- `daily_task_assistant/smartsheet_client.py` - Added `find_by_fsid()`
- `config/smartsheet.yml` - Added fsid column IDs
- `api/main.py` - Task CRUD endpoints + sync endpoints
- `web-dashboard/src/components/TaskCreateModal.tsx` - New
- `web-dashboard/src/components/TaskDetailModal.tsx` - New

---

## Phase 2: DATA Awareness

### Overview
This phase makes DATA (the LLM assistant) aware of Firestore tasks instead of only Smartsheet. This is **medium risk** because it touches LLM prompts and context assembly.

### Decisions Needed Before Implementation

#### Decision 1: Portfolio Data Source
**Question:** Where should DATA's portfolio view get task data?

| Option | Description | Pros | Cons |
|--------|-------------|------|------|
| **A) Firestore Only** | Replace Smartsheet calls with Firestore | Single source of truth, faster queries | Dependent on sync being reliable |
| **B) Smartsheet Only** | Keep current behavior | No changes needed, proven stable | Doesn't leverage new system |
| **C) Both Merged** | Query both, deduplicate | Fallback if one fails | Complex, potential duplicates |

**Recommendation:** Option A (Firestore Only) - Since sync is now reliable with FSID linking, Firestore should be the primary source. This simplifies the architecture.

#### Decision 2: Task Engagement Context
**Question:** When user clicks "Engage DATA" on a task, where should context come from?

| Option | Description |
|--------|-------------|
| **A) Firestore** | Load task details from Firestore (has all fields including three-date model) |
| **B) Smartsheet** | Keep current behavior (proven, but missing new fields) |

**Recommendation:** Option A (Firestore) - This enables DATA to see `target_date`, `hard_deadline`, `times_rescheduled`, etc.

#### Decision 3: Rebalancing Logic
**Question:** How should rebalancing work with the three-date model?

Current behavior: DATA suggests moving `due_date` when tasks slip.

New behavior options:
- Move `planned_date` only (preserves `target_date` for slippage tracking)
- Auto-increment `times_rescheduled` when `planned_date` changes (already implemented in `update_task`)
- Show slippage warnings when `planned_date` > `target_date`

**Recommendation:** Move `planned_date`, keep `target_date` fixed, auto-increment `times_rescheduled`.

---

## Implementation Plan (After Decisions)

### Phase 2a: Portfolio Context ✅ (Already done - baseline captured)

### Phase 2b: Portfolio Uses Firestore
**Files to modify:**
- `daily_task_assistant/portfolio_context.py`

**Changes:**
1. Import `list_tasks` from `task_store`
2. Replace Smartsheet query with Firestore query
3. Map FirestoreTask fields to portfolio format
4. Ensure all existing portfolio features work (grouping, filtering, etc.)

**Testing:**
- Run baseline test: Portfolio prompts
- Compare DATA's responses to baseline
- Verify task counts match

### Phase 2c: Rebalancing with Three-Date Model
**Files to modify:**
- `daily_task_assistant/llm/anthropic_client.py` (system prompts)
- `DATA_PREFERENCES.md` (behavioral guidelines)

**Changes:**
1. Update rebalancing prompts to use `planned_date` vs `target_date`
2. Add slippage awareness to DATA's context
3. Include `times_rescheduled` in task summaries

**Testing:**
- Run baseline test: Rebalancing prompts
- Verify DATA suggests `planned_date` changes (not `target_date`)
- Verify `times_rescheduled` increments

### Phase 2d: Task Engagement from Firestore
**Files to modify:**
- `daily_task_assistant/services/assist.py`
- `api/main.py` (assist endpoints)

**Changes:**
1. Load task context from Firestore instead of Smartsheet
2. Include three-date model fields in task context
3. Update tool definitions if needed

**Testing:**
- Run baseline test: Task engagement prompts
- Verify DATA sees all task fields
- Test task updates via DATA tools

---

## Quality Gates

Before each sub-phase:
1. Run baseline tests: `python baseline_tests/run_baseline.py`
2. Review any response differences
3. Get user approval before proceeding

After each sub-phase:
1. Re-run baseline tests
2. Compare to previous baseline
3. Document any intentional changes
4. Commit with descriptive message

---

## Server Status

The backend server should be restarted before continuing:
```powershell
cd C:\Users\david\psp-cli\DATA_Task_Refactor_Cursor\projects\daily-task-assistant
$env:PYTHONPATH = "."
$env:DTA_DEV_AUTH_BYPASS = "1"
python -m uvicorn api.main:app --host 0.0.0.0 --port 8000
```

Frontend dev server:
```powershell
cd C:\Users\david\psp-cli\DATA_Task_Refactor_Cursor\projects\web-dashboard
npm run dev
```

---

## Tomorrow's First Steps

1. **Review this plan** - Confirm decisions on data sources
2. **Start servers** - Backend on 8000, frontend on 5173
3. **Run baseline tests** - Ensure DATA is still functioning correctly
4. **Begin Phase 2b** - Portfolio context from Firestore (after approval)

---

## Git Status

- Branch: `feature/unified-tasks`
- Last commit: `cb14399 feat: Add FSID bidirectional linking for duplicate prevention`
- All changes pushed to GitHub ✅
