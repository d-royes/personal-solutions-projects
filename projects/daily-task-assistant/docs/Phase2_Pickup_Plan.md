# Phase 1 Continuation Plan - Sync Validation & Stability
**Date:** January 15, 2026  
**Status:** Infrastructure built, needs validation and refinement  
**Priority:** Stability before LLM integration

---

## Where We Left Off

### Phase 1 Infrastructure Built (NOT fully validated)

| Component | Built | Validated | Notes |
|-----------|-------|-----------|-------|
| FirestoreTask dataclass | ✅ | ⚠️ | Needs recurring field testing |
| SyncService (SS↔FS) | ✅ | ⚠️ | Only tested personal/church sheet |
| FSID duplicate prevention | ✅ | ❌ | Just implemented, not tested |
| Work sheet sync | ❌ | ❌ | Not yet integrated |
| Recurring items | ❌ | ❌ | Need to define behavior |
| UI task details | ✅ | ⚠️ | Modal works but feels wrong |
| Sync automation | ❌ | ❌ | Currently manual trigger only |
| Task creation from email | ❌ | ❌ | Future feature |

---

## Tomorrow's Priorities (In Order)

### 1. Validate FSID Duplicate Prevention
**Goal:** Prove the new FSID logic prevents duplicates

**Tests:**
- [ ] Create task in Firestore UI
- [ ] Trigger FS→SS sync
- [ ] Verify task appears in Smartsheet WITH fsid
- [ ] Trigger FS→SS sync again
- [ ] Verify NO duplicate created (fsid check worked)
- [ ] Modify task in Firestore
- [ ] Trigger sync, verify UPDATE not CREATE

### 2. Validate Bidirectional Sync Reliability
**Goal:** Prove changes flow correctly in both directions

**SS→FS Tests:**
- [ ] Create new task in Smartsheet
- [ ] Trigger SS→FS sync
- [ ] Verify task appears in Firestore with correct fields
- [ ] Modify task in Smartsheet (title, status, priority, due_date)
- [ ] Trigger sync, verify changes reflect in Firestore
- [ ] Delete task in Smartsheet
- [ ] Trigger sync, verify cascade delete in Firestore

**FS→SS Tests:**
- [ ] Create task in Firestore UI
- [ ] Trigger FS→SS sync
- [ ] Verify all fields map correctly to Smartsheet
- [ ] Modify task in Firestore (all field types)
- [ ] Trigger sync, verify Smartsheet updates
- [ ] Delete task in Firestore
- [ ] Verify cascade delete in Smartsheet

### 3. Add Work Sheet Integration
**Goal:** Sync works for work tasks too, not just personal/church

**Tasks:**
- [ ] Verify work sheet has fsid column (you added it)
- [ ] Test SS→FS sync with work tasks
- [ ] Test FS→SS sync with work tasks
- [ ] Verify domain detection works (work vs personal vs church)

### 4. Define Recurring Items Behavior
**Goal:** Clear rules for how recurring tasks sync

**Questions to Answer:**
- When recurring task marked "Done" in SS, what happens in FS?
- Does FS track recurrence pattern separately from status?
- When next occurrence triggers, how does FS update?
- Should FS create new task or update existing?

**Current State:**
- `TaskDetail` has `recurring_pattern` field (parsed from SS)
- `FirestoreTask` has `recurring_type`, `recurring_days`, `recurring_monthly`
- Sync maps `recurring_pattern` → Firestore fields

**Needs Decision:** Document the expected behavior before testing

### 5. UI Improvements - Task Details in Assistant Panel
**Goal:** View task details in Assistant window, not separate modal

**Issues with Current Modal:**
- Feels disconnected from workflow
- Have to close modal to engage DATA
- Can't see task details while chatting with DATA

**Proposed Solution:**
- Show task details in the Assistant panel when task is selected
- Keep modal for CREATE only (or remove entirely)
- Task list click → loads details in Assistant panel
- "Engage DATA" becomes seamless (already have context)

**This is a UI/UX decision - discuss before implementing**

### 6. Sync Automation
**Goal:** Sync happens automatically, not manual trigger

**Options:**
| Option | Trigger | Pros | Cons |
|--------|---------|------|------|
| Polling | Every N minutes | Simple, predictable | Delays, unnecessary API calls |
| On-demand | After each FS change | Immediate | Many API calls |
| Webhooks | SS notifies on change | Real-time, efficient | Complex setup |
| Hybrid | On-demand + periodic | Best of both | More code |

**Recommendation:** Start with polling (every 5 min) for simplicity. Add webhooks later if needed.

### 7. Task Creation from Email (Future)
**Goal:** Create tasks directly from email context

**This depends on:**
- Stable sync infrastructure
- Clear task field mapping
- UI for task creation in email context

**Park this for now** - focus on core sync stability first.

---

## LLM Integration (Phase 2) - LATER

**Do NOT start Phase 2 until:**
- [ ] All Phase 1 validation tests pass
- [ ] Work sheet sync validated
- [ ] Recurring items behavior defined and tested
- [ ] UI improvements complete (or at least planned)
- [ ] Sync automation in place
- [ ] User confirms sync is reliable

**Phase 2 includes:**
- Portfolio context from Firestore
- Task engagement from Firestore
- Rebalancing with three-date model
- DATA tool updates

---

## Server Commands

**Backend:**
```powershell
cd C:\Users\david\psp-cli\DATA_Task_Refactor_Cursor\projects\daily-task-assistant
$env:PYTHONPATH = "."
$env:DTA_DEV_AUTH_BYPASS = "1"
python -m uvicorn api.main:app --host 0.0.0.0 --port 8000
```

**Frontend:**
```powershell
cd C:\Users\david\psp-cli\DATA_Task_Refactor_Cursor\projects\web-dashboard
npm run dev
```

**Trigger Sync (manual):**
```powershell
# SS → FS
Invoke-RestMethod -Uri "http://localhost:8000/sync/now" -Method POST -Headers @{"X-User-Email"="david.a.royes@gmail.com"; "Content-Type"="application/json"} -Body '{"direction": "smartsheet_to_firestore"}'

# FS → SS
Invoke-RestMethod -Uri "http://localhost:8000/sync/now" -Method POST -Headers @{"X-User-Email"="david.a.royes@gmail.com"; "Content-Type"="application/json"} -Body '{"direction": "firestore_to_smartsheet"}'

# Both (bidirectional)
Invoke-RestMethod -Uri "http://localhost:8000/sync/now" -Method POST -Headers @{"X-User-Email"="david.a.royes@gmail.com"; "Content-Type"="application/json"} -Body '{"direction": "bidirectional"}'
```

---

## Git Status

- Branch: `feature/unified-tasks`
- Last commit: `ccaee10 docs: Add Phase 2 pickup plan for tomorrow`
- All changes pushed to GitHub ✅

---

## Summary

**Tomorrow's focus:** VALIDATION, not new features.

1. Test FSID duplicate prevention
2. Test bidirectional sync thoroughly
3. Add work sheet
4. Define recurring behavior
5. Discuss UI improvements
6. Plan sync automation

**LLM integration is Phase 2** - only after sync is proven stable.
