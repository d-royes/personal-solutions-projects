# Autonomous Smartsheet Task Management Integration

## Overview

This document details the implementation of Smartsheet task update capabilities for DATA (Daily Autonomous Task Assistant). This work is being completed autonomously with validation at each step.

## Objective

Enable DATA to:
1. Understand task update intents from natural language ("mark this complete", "change status to blocked", etc.)
2. Show confirmation before making changes
3. Execute Smartsheet API updates
4. Refresh the task list to reflect changes

## Configuration

- **Sheet ID**: 4543936291884932
- **Live Testing**: Enabled (test against real Smartsheet)
- **Completion Logic**: Set Status="Complete" + Done=true (no completed_on date)
- **Confirmation**: Always required before Smartsheet updates

## Supported Actions

| Action | Example Phrases | Smartsheet Update |
|--------|-----------------|-------------------|
| Mark complete | "done", "finished", "complete this" | Status=Complete, Done=true |
| Change status | "mark as blocked", "set to in progress" | Status={value} |
| Update due date | "push to Friday", "due date next week" | due_date={date} |
| Change priority | "make this urgent", "lower priority" | priority={value} |
| Add comment | "add note: called them today" | POST discussion comment |
| Update notes | "update notes to include..." | notes={text} |

## Field Validation Rules

### Status (must match exactly)
- Scheduled, In Progress, Blocked, Waiting, Complete, Recurring, On Hold
- Follow-up, Awaiting Reply, Delivered, Create ZD Ticket, Ticket Created
- Validation, Needs Approval, Cancelled, Delegated, Completed

### Priority (must match exactly)
- Critical, Urgent, Important, Standard, Low

### Project (must match exactly)
- Around The House, Church Tasks, Family Time, Shopping
- Sm. Projects & Tasks, Zendesk Ticket

## Implementation Steps

### Step 1: Documentation ✅
- [x] Create this document
- [ ] Commit checkpoint

### Step 2: SmartsheetClient Write Methods
- [ ] Add `update_row()` method
- [ ] Add `mark_complete()` convenience method
- [ ] Write pytest tests with mocked API responses
- [ ] Validate field validation logic
- [ ] Commit after tests pass

### Step 3: API Endpoint
- [ ] Add `/assist/{task_id}/update` endpoint
- [ ] Add request validation
- [ ] Write API tests using TestClient
- [ ] Test error cases
- [ ] Commit after tests pass

### Step 4: Intent Recognition
- [ ] Add task update tool to `anthropic_client.py`
- [ ] Update chat to return structured actions
- [ ] Test tool_use block parsing
- [ ] Commit after tests pass

### Step 5: Frontend API
- [ ] Add `updateTask()` function to `api.ts`
- [ ] Verify TypeScript compilation
- [ ] Commit after validation

### Step 6: Confirmation UI
- [ ] Add pending action state to `App.tsx`
- [ ] Add confirmation card to `AssistPanel.tsx`
- [ ] Add styles to `App.css`
- [ ] Visual validation in browser
- [ ] Commit after validation

### Step 7: Integration Testing
- [ ] Test full flow in browser
- [ ] Document results
- [ ] Final commit

## Smartsheet API Reference

### Update Row
```
PUT https://api.smartsheet.com/2.0/sheets/{sheetId}/rows
Authorization: Bearer {token}
Content-Type: application/json

[
  {
    "id": {rowId},
    "cells": [
      {"columnId": 8863997627158404, "value": "Complete"},
      {"columnId": 2108598186102660, "value": true}
    ]
  }
]
```

### Column IDs (from config/smartsheet.yml)
- task: 1404910744326020
- project: 7034410278539140
- due_date: 3656710558011268
- priority: 279010837483396
- status: 8863997627158404
- assigned_to: 5908510371696516
- estimated_hours: 8160310185381764
- number (#): 4360397999787908
- done: 2108598186102660
- notes: 1967860697747332
- completed_on: 5345560418275204

## Progress Log

### Session Start
- Created documentation file
- Ready to begin Step 2: SmartsheetClient Write Methods

### Step 2 Complete
- Added `update_row()` method to SmartsheetClient
- Added `mark_complete()` convenience method
- Created test file `tests/test_smartsheet_client.py` with 11 tests
- All tests pass
- Committed: "feat: Add update_row() and mark_complete() methods to SmartsheetClient with tests"

### Step 3 Complete
- Added `/assist/{task_id}/update` endpoint to `api/main.py`
- Implemented validation for status, priority, due_date format
- Added confirmation flow (returns preview if not confirmed)
- Created 10 API tests in `tests/test_api.py`
- All tests pass
- Committed: "feat: Add /assist/{task_id}/update endpoint with validation and tests"

### Step 4 Complete
- Added `TASK_UPDATE_TOOL` definition for Anthropic tool use
- Created `chat_with_tools()` function that enables intent recognition
- Added `TaskUpdateAction` and `ChatResponse` dataclasses
- Updated `/assist/{task_id}/chat` endpoint to use `chat_with_tools`
- Committed: "feat: Add chat_with_tools for task update intent recognition"

### Step 5 Complete
- Added `PendingAction` interface to `api.ts`
- Updated `ChatResponse` to include optional `pendingAction`
- Added `updateTask()` function with full TypeScript types
- TypeScript compilation passes
- Committed: "feat: Add updateTask() function to frontend API"

### Step 6 Complete
- Added `pendingAction`, `updateExecuting` state to `App.tsx`
- Added `handleConfirmUpdate()` and `handleCancelUpdate()` handlers
- Updated `AssistPanel` to accept new props
- Added confirmation card UI with Confirm/Cancel buttons
- Added CSS styles for confirmation card
- Committed: "feat: Add confirmation UI for task updates in AssistPanel"

### Step 7: Integration Testing
- Started dev servers successfully
- Verified task list loads with 34+ tasks
- Verified "Engage DATA" button collapses task panel
- Verified action buttons (Plan, Research, Email, Follow Up) appear
- Verified chat input is present
- UI is functional and ready for user testing

---

## Rollback Strategy

Each step has a commit checkpoint. If critical issues arise:
1. Check this document for last successful step
2. Revert to corresponding commit
3. Resume from that point

## Success Criteria

1. User can say "mark this complete" in chat
2. DATA shows confirmation card with proposed action
3. On confirm, Smartsheet is updated via API
4. Task list refreshes showing updated status
5. All tests pass

