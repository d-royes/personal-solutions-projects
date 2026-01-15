# DATA Quality Baseline - Phase 0

**Purpose:** Establish baseline responses for DATA quality before the Internal Task System Migration.  
**Created:** 2026-01-14  
**Branch:** `feature/unified-tasks`

---

## Overview

This document captures test prompts and expected behaviors for DATA across all current capabilities. Before making any LLM-touching changes (Phase 2+), we'll run these prompts and compare responses to detect quality regressions.

---

## Test Categories

### 1. Task Completion (Tool Use)

**Triggers:** "done", "finished", "close it", "complete", "mark it done"

| Prompt | Expected Behavior | Quality Check |
|--------|-------------------|---------------|
| "Done" | Calls `update_task(action="mark_complete")` + brief confirmation | No verbose summary |
| "Mark this complete" | Same as above | No "would you like me to..." |
| "Finished with this" | Same as above | Uses tool immediately |

### 2. Status Changes (Tool Use)

**Triggers:** "blocked", "waiting on", "stuck", "in progress"

| Prompt | Expected Behavior | Quality Check |
|--------|-------------------|---------------|
| "I'm blocked on this" | Calls `update_task(action="update_status", status="Blocked")` | Brief confirmation |
| "Mark as waiting" | Calls `update_task(status="Waiting")` | No lengthy explanation |
| "This is in progress now" | Calls `update_task(status="In Progress")` | Immediate tool use |

### 3. Due Date Changes (Tool Use)

**Triggers:** "push to", "move to", "reschedule"

| Prompt | Expected Behavior | Quality Check |
|--------|-------------------|---------------|
| "Push this to Friday" | Parses date, calls `update_task(action="update_due_date")` | Confirms the date |
| "Move due date to next Monday" | Same with correct date calculation | No asking "which date?" |
| "Reschedule to January 20th" | Calls with `due_date="2026-01-20"` | Immediate action |

### 4. Plan Generation (Action Button)

**Trigger:** Plan button click

| Task Type | Expected Content | Quality Check |
|-----------|------------------|---------------|
| Shopping task | Specific store/location guidance | Not generic "confirm blockers" |
| Technical task | Relevant technical steps | Task-specific, not boilerplate |
| Communication task | Draft/send suggestions | Clear recipient awareness |

**Anti-patterns to check:**
- ❌ "Confirm blockers/status" (too generic)
- ❌ "Complete 'Review notes' as the immediate deliverable" (meaningless)
- ❌ "Batch related work in the [X] stream" (productivity fluff)

### 5. Research (Action Button)

**Trigger:** Research button click

| Task Context | Expected Output | Quality Check |
|--------------|-----------------|---------------|
| Contact lookup | Phone numbers, addresses, hours | Specific data, not filler |
| Information gathering | Bullet points with facts | Structured, scannable |
| Process inquiry | Step-by-step guidance | Actionable, not vague |

### 6. Email Drafting (Action Button)

**Trigger:** Draft Email button click

| Scenario | Expected Behavior | Quality Check |
|----------|-------------------|---------------|
| No recipient specified | Asks "Who should receive this?" | Doesn't draft to task owner |
| Recipient in task notes | Generates draft to that person | Never emails task owner |
| Church task | Suggests church account | Account-aware |

### 7. Chat Interactions

**General conversation with DATA**

| Prompt | Expected Behavior | Quality Check |
|--------|-------------------|---------------|
| "What should I do first?" | Gives task-specific guidance | Concise, actionable |
| "Can you help me with this?" | Offers concrete actions | No verbose preamble |
| "I need a shorter version" | Provides condensed content | Respects instructions |

### 8. Summarize (Action Button)

**Trigger:** Summarize button click

| Context | Expected Output | Quality Check |
|---------|-----------------|---------------|
| Task with conversation | Synthesizes progress | Key points only |
| Task with plan | Reviews plan + task | No excessive recap |

---

## Baseline Capture Instructions

### Before Phase 2 (or any LLM change):

1. **Start dev servers:**
   ```powershell
   cd projects/daily-task-assistant
   powershell -ExecutionPolicy Bypass -File .\scripts\start-dev.ps1
   ```

2. **Open browser:** http://localhost:5173

3. **Select a test task** (suggest using stub data to ensure consistency)

4. **Run each prompt category** and capture:
   - Full DATA response text
   - Tool calls made (if any)
   - Response time
   - Any unexpected behavior

5. **Save responses** in a timestamped file:
   `docs/baselines/baseline_YYYY-MM-DD.md`

---

## Quality Criteria

### ✅ PASS Criteria

- Tool use when intent is clear
- Brief confirmatory responses (under 3 sentences for actions)
- Task-specific plan content (not generic)
- Research returns specific data (contacts, steps, facts)
- Never emails task owner about their own task
- No verbose summaries before taking action

### ⚠️ WARNING Indicators

- Response > 5 sentences for a simple action
- "Would you like me to..." when user already said "do it"
- Generic efficiency tips that apply to any task
- Asking for confirmation when intent is obvious

### ❌ FAIL Criteria

- Hallucination (inventing data not in task/context)
- Wrong tool use (e.g., email to task owner)
- Refusal to take action when clearly requested
- Significantly degraded response quality vs baseline

---

## Baseline Results

### Date: [PENDING - To be captured]

**Test Environment:**
- Branch: `feature/unified-tasks`
- Data Source: [live/stub]
- Model: [anthropic model version]

**Results will be captured here after running baseline prompts.**

---

## Change Log

| Date | Change | Author |
|------|--------|--------|
| 2026-01-14 | Created Phase 0 baseline document | Claude |

