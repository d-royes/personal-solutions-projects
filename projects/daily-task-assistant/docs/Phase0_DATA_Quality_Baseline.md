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

### 9. Portfolio View (CRITICAL - Hallucination Risk Zone)

**Context:** Portfolio/holistic view of tasks across domains

| Prompt | Expected Behavior | Quality Check |
|--------|-------------------|---------------|
| "What should I focus on today?" | Prioritizes based on due dates, urgency | Uses REAL task data only |
| "How's my workload looking?" | Summarizes task counts, blockers | No invented statistics |
| "Any tasks slipping?" | Reports overdue/at-risk items | Accurate dates from data |
| Quick Question chat | Responds with task-aware context | No hallucinated tasks |

**CRITICAL Anti-patterns (from hallucination incident):**
- ❌ Inventing tasks that don't exist
- ❌ Making up due dates or statistics
- ❌ Referencing projects not in the data
- ❌ Confident assertions not grounded in actual task list

### 10. Calendar Mode Integration

**Context:** Calendar view with tasks tab

| Prompt | Expected Behavior | Quality Check |
|--------|-------------------|---------------|
| "What do I have today?" | Lists events AND relevant tasks | Accurate calendar data |
| "Any conflicts?" | Identifies scheduling issues | Real event/task overlap |
| "When can I work on [task]?" | Suggests time slots | Based on actual calendar |

### 11. Email Mode

**Context:** Email dashboard with triage and task creation

| Action | Expected Behavior | Quality Check |
|--------|-------------------|---------------|
| "Create task from this email" | Extracts subject, sender, key details | Preserves email context |
| "What should I do with this?" | Analyzes email, suggests action | Account-aware (personal/church) |
| Email analysis | Categorizes correctly | No misclassification |

### 12. Cross-Mode Consistency

**Context:** Switching between Task, Email, Calendar modes

| Scenario | Expected Behavior | Quality Check |
|----------|-------------------|---------------|
| Same task discussed in different modes | Consistent information | No contradictions |
| Task created from email, viewed in Task mode | All metadata preserved | Source tracking intact |
| Calendar event with associated task | Both reference each other | Linked correctly |

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
- Commit: `0ac4f6e` (Level 0 baseline)
- Data Source: Live Smartsheet data
- Model: Claude 3.5 Sonnet (via Anthropic API)
- Frontend: http://localhost:5173
- Backend: http://localhost:8000

---

## Recommended Test Tasks

Use these specific tasks for consistent baseline testing:

### Task Mode Tests
1. **Church task with clear action** - e.g., "File Claim" or similar
2. **Personal task with DATA bug** - e.g., "DATA - Email Management" 
3. **Task requiring contact** - Any task with contact_flag set

### Portfolio View Tests
1. **Personal perspective** - View personal domain tasks
2. **Church perspective** - View church domain tasks  
3. **Holistic perspective** - Cross-domain view

### Calendar Mode Tests
1. **Personal calendar** - Check events and task integration
2. **Church calendar** - Check events and task integration

### Email Mode Tests
1. **Personal inbox** - Test email triage
2. **Church inbox** - Test email triage and task creation

---

## Baseline Capture Template

For each test, capture:

```markdown
### Test: [Category] - [Specific Test]
**Timestamp:** YYYY-MM-DD HH:MM
**Task/Context:** [Task title or context description]

**Prompt:** "[Exact user input]"

**DATA Response:**
> [Full response text]

**Tool Calls:** [List any tools invoked]

**Quality Assessment:** ✅ PASS / ⚠️ WARNING / ❌ FAIL

**Notes:** [Any observations]
```

---

## Captured Baselines

### Baseline Run #1: [DATE PENDING]

_Results will be captured during baseline testing session._

---

## Change Log

| Date | Change | Author |
|------|--------|--------|
| 2026-01-14 | Created Phase 0 baseline document | Claude |
| 2026-01-15 | Added Portfolio, Calendar, Email mode tests; Added test task recommendations; Added capture template | Claude (Opus 4.5) |

