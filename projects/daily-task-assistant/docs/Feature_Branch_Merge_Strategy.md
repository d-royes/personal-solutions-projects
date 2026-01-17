# Feature Branch Merge Strategy Analysis

> **Branch:** `feature/unified-tasks`  
> **Analysis Date:** January 17, 2026  
> **Target:** `develop` → `staging` → `main`  
> **Status:** Pending merge after local testing

---

## Feature Branch Summary

### Scope
- **30 commits** ahead of `develop`
- **147 files changed**
- **14,274 insertions / 20,965 deletions**

### Commits by Type

| Type | Count | Description |
|------|-------|-------------|
| feat | 16 | New features |
| fix | 9 | Bug fixes |
| docs | 4 | Documentation |
| chore | 3 | Maintenance |

---

## Commit History (Chronological)

```
79c9e69 fix: Attention tab conversation persistence
00fdc12 feat: Email-to-task creation with auto-sync and thread linking
da9570e feat: Add configurable Needs Attention filter with DATA Tasks integration
160475b chore: Update baseline tests and normalize line endings
ab49488 feat: Enable full DATA engagement with Firestore tasks
4c714d6 feat: Add Firestore task detail panel in AssistPanel with CRUD actions
76cd81d docs: Add staging deployment guide with Cloud Scheduler setup
90fb431 feat: Add global settings with Firestore persistence and automated sync config
5cfa0ae feat: Implement Firestore-primary recurring task management
f6c55c1 fix: Cascade delete and search for DATA Tasks
d17a21a feat: Bidirectional sync with conflict resolution and UI enhancements
e9e1fa9 chore: Move .cursorrules.md to workspace root for auto-loading
6ee798f docs: Add .cursorrules.md for consistent AI collaboration
8131543 docs: Update plan - focus on Phase 1 validation before LLM integration
ccaee10 docs: Add Phase 2 pickup plan for tomorrow
cb14399 feat: Add FSID bidirectional linking for duplicate prevention
56a764a fix(sync): Simplify duplicate detection to row_id only
25dfe50 fix(sync): Pass smartsheet_sheet in create_task to prevent duplicate detection failures
c0dbb45 feat(sync): Add translator layer for SS<->FS domain derivation
20cfa18 fix(sync): Prevent duplicates by using full task list for matching
e7b03d1 fix(sync): Fix duplicate detection for church tasks
881a22f feat(sync): Core sync fixes for bidirectional sync (Priority 1)
cf9b561 feat(sync): Add full field mapping for SS<->FS sync (Priority 0)
a6653cc fix(sync): Add comprehensive field translation for Smartsheet writes
120ec8d fix(ui): Correct authConfig variable name in App.tsx
d06135a feat(ui): Add task CRUD modals and TaskList integration (Phase 1d-1f)
6bd683b feat(sync): Add SyncService and API endpoints (Phase 1b & 1c)
9b8dcf7 feat(task-store): Enhance FirestoreTask with three-date model (Phase 1a)
9937230 feat: Add automated DATA baseline testing system (Phase 0)
0ac4f6e chore: Sync full codebase from develop for unified-tasks migration
```

---

## Major Feature Groups

### 1. Bidirectional Sync System (10 commits)
Core infrastructure for Smartsheet ↔ Firestore synchronization.

**Key Changes:**
- `SyncService` class with conflict resolution
- FSID column linking for duplicate prevention
- Field mapping/translation layer (SS ↔ FS)
- Domain derivation (personal/church/work)
- API endpoints for sync operations

**Files:** `sync/service.py`, `api/main.py`, `smartsheet_client.py`

### 2. Firestore Task System (5 commits)
Firestore as primary task store with full CRUD support.

**Key Changes:**
- Three-date model (plannedDate, targetDate, hardDeadline)
- Task detail panel in AssistPanel
- CRUD modals (create, edit, delete)
- Cascade delete handling
- Search functionality for DATA Tasks

**Files:** `task_store/store.py`, `TaskDetailModal.tsx`, `TaskCreateModal.tsx`, `TaskList.tsx`

### 3. Email-to-Task Integration (3 commits)
Create tasks directly from emails with automatic sync.

**Key Changes:**
- Task creation form in email views
- Auto-sync to Smartsheet on creation
- Thread ID linking for traceability
- Attention tab conversation persistence fix
- "SCHEDULED" badge on emails with linked tasks

**Files:** `EmailDashboard.tsx`, `api/main.py`, `attention_store.py`

### 4. Global Settings & Config (2 commits)
User preferences with Firestore persistence.

**Key Changes:**
- Global settings store
- Automated sync configuration
- Inactivity timeout settings
- Haiku analyzer preferences

**Files:** `settings/global_settings.py`, `SettingsContext.tsx`, `SettingsPanel.tsx`

### 5. Infrastructure & Testing (3 commits)
Development and deployment improvements.

**Key Changes:**
- Baseline testing system for DATA quality
- Staging deployment guide
- Cloud Scheduler setup documentation

**Files:** `baseline_tests/`, `docs/`

---

## Merge Strategy Options

### Option A: Single Squash Merge (Recommended)

```bash
# Merge feature to develop
git checkout develop
git merge --squash feature/unified-tasks
git commit -m "feat: Unified Tasks with Bidirectional Sync"

# Later, merge develop to staging
git checkout staging
git merge --squash develop
git commit -m "release: Unified Tasks feature"
```

#### Pros
- **Clean history**: One commit represents entire feature
- **Easy rollback**: `git revert <commit>` undoes everything
- **Simple to understand**: Clear what shipped in each release
- **Smaller diff in main branches**: No intermediate fix commits visible
- **Good for releases**: Each squash = one logical release

#### Cons
- **Lose granular history**: Can't see individual bug fixes in main branches
- **Can't cherry-pick**: If you need just one fix from the feature, you can't extract it
- **Harder to bisect**: If a bug is introduced, you can't bisect within the squashed commit
- **Large commit**: Single commit has 14K+ line changes (harder to review)

#### Best For
- Features that ship as a complete unit
- When you don't anticipate needing to rollback partial changes
- Teams that value clean release history

---

### Option B: Group Squashes by Feature

Create separate PRs/branches for each logical group, merge sequentially:

```bash
# Example: Create sub-branches from feature branch
git checkout -b feature/sync-system feature/unified-tasks~20
git checkout -b feature/firestore-tasks feature/unified-tasks~15
git checkout -b feature/email-integration feature/unified-tasks~5
# ... etc

# Merge each as separate squashed commits
git checkout develop
git merge --squash feature/sync-system
git commit -m "feat: Bidirectional Sync System"

git merge --squash feature/firestore-tasks  
git commit -m "feat: Firestore Task System"

# ... etc
```

#### Pros
- **Granular rollback**: Can revert just "Email Integration" without losing "Sync System"
- **Better debugging**: If sync breaks, you know which feature to investigate
- **Incremental releases**: Could ship sync first, email integration later
- **Easier code review**: Smaller, focused PRs

#### Cons
- **More work**: Need to create and manage multiple branches/PRs
- **Dependency management**: Features may have interdependencies (sync must merge before email-to-task)
- **Complex history**: More commits to track, even if each is smaller
- **Risk of merge conflicts**: Splitting an integrated feature branch can cause conflicts

#### Best For
- Large features with clearly separable components
- When you anticipate needing to rollback specific parts
- Teams with strict code review requirements

---

### Option C: Rebase and Merge (Preserve All Commits)

```bash
git checkout develop
git rebase feature/unified-tasks
# or
git merge feature/unified-tasks  # fast-forward if possible
```

#### Pros
- **Full history preserved**: All 30 commits visible in develop
- **Granular bisect**: Can find exactly which commit introduced a bug
- **Cherry-pick friendly**: Can extract any individual fix

#### Cons
- **Messy history**: 30 commits including "fix typo" and "WIP" commits
- **Harder to understand releases**: What shipped? All 30 commits.
- **Rollback complexity**: Which commits to revert for a feature rollback?

#### Best For
- Internal/development branches where history matters
- When you need maximum flexibility for debugging
- Open source projects where attribution matters

---

## Recommendation

### For `feature/unified-tasks` → `develop`

**Use Option A (Single Squash Merge)** because:

1. **Cohesive Feature**: The unified tasks system is interdependent
   - Sync system requires Firestore tasks
   - Email-to-task requires sync
   - Settings support both
   
2. **Testing Phase**: You're about to test locally for a few days
   - If issues found, you'll fix in feature branch and re-squash
   - No point preserving intermediate "fix" commits
   
3. **Release Unit**: This will ship as one release to staging/production
   - Users don't care about the 30-commit journey
   - They care that "Unified Tasks" works

### Suggested Commit Message for Squash

```
feat: Unified Tasks with Bidirectional Smartsheet Sync

Major feature release introducing Firestore-primary task management 
with bidirectional Smartsheet synchronization.

Key capabilities:
- Bidirectional sync between Firestore and Smartsheet (personal/church/work)
- FSID linking for duplicate prevention and conflict resolution  
- Three-date task model (planned, target, hard deadline)
- Full CRUD operations on Firestore tasks via UI
- Email-to-task creation with auto-sync
- Attention tab conversation persistence
- Global settings with Firestore persistence
- Automated DATA baseline testing system

Technical changes:
- New SyncService with field translation layer
- FirestoreTask dataclass with expanded schema
- TaskDetailModal and TaskCreateModal components
- Enhanced AssistPanel for task engagement
- AttentionItem threadId support for chat persistence

Breaking changes: None (additive feature)
Migration: None required (new Firestore collections)
```

---

## Post-Merge Rollback Procedures

### If Single Squash (Option A)

```bash
# Find the squash commit
git log --oneline develop

# Revert entire feature
git checkout develop
git revert <squash-commit-hash>
git push
```

### If Group Squashes (Option B)

```bash
# Revert just one feature group
git log --oneline develop  # Find the specific squash commit
git revert <email-integration-commit>  # Keeps sync, removes email feature
git push
```

---

## Decision Checklist

Before merging to develop, verify:

- [ ] Local testing complete (2-3 days)
- [ ] No critical bugs discovered
- [ ] Sync works for all domains (personal, church, work)
- [ ] Email-to-task creates and syncs correctly
- [ ] Conversation persistence works in Attention tab
- [ ] Settings persist across sessions
- [ ] No regressions in existing functionality

---

## References

- [Attention Conversation Persistence Design](./attention-conversation-persistence.md)
- [Phase 2 Pickup Plan](./Phase2_Pickup_Plan.md)
- [DATA Quality Baseline](./Phase0_DATA_Quality_Baseline.md)
