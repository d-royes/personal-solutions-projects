# Portfolio View Plan v2 - Global DATA Engagement

## Architecture Context (CRITICAL)

### Multi-Sheet Support (Already Implemented!)

The codebase already has full multi-sheet support in `feature/multi-sheet-support`:

**`config/smartsheet.yml`:**
```yaml
sheets:
  personal:
    id: 4543936291884932  # Personal/Church tasks
    include_in_all: true
  work:
    id: 5336144276678532  # Work tasks (Project Task Tracker)
    include_in_all: false
```

**`SmartsheetClient.list_tasks()`:**
- `sources: Optional[List[str]]` - e.g., `["personal"]`, `["work"]`, `["personal", "work"]`
- Each task has `source: str` field ("personal" or "work")

**Frontend `deriveDomain(task)`:**
- If `task.source === 'work'` → 'Work'
- Else: project contains 'church' → 'Church', otherwise → 'Personal'

### Perspective Mapping

| Perspective | Backend `sources` | Filter Logic |
|-------------|-------------------|--------------|
| **Personal** | `["personal"]` | Exclude tasks where `project.lower().includes('church')` |
| **Church** | `["personal"]` | Only tasks where `project.lower().includes('church')` |
| **Work** | `["work"]` | All tasks (work sheet only) |
| **Holistic** | `["personal", "work"]` | All tasks from both sheets |

---

## Implementation Plan

### Phase 1: Backend - Portfolio Context Endpoint

**File: `api/main.py`**

Add new endpoint that leverages existing multi-sheet support:

```python
@app.get("/assist/global/context")
def get_global_context(
    perspective: Literal["personal", "church", "work", "holistic"] = Query("personal"),
    user: str = Depends(get_current_user),
) -> dict:
    """Get portfolio context for global DATA engagement."""
    from daily_task_assistant.portfolio_context import build_portfolio_context
    
    settings = load_settings()
    client = SmartsheetClient(settings=settings)
    
    portfolio = build_portfolio_context(client, perspective)
    return {
        "perspective": perspective,
        "portfolio": asdict(portfolio),
    }
```

**File: `daily_task_assistant/portfolio_context.py` (NEW)**

```python
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional
from .smartsheet_client import SmartsheetClient
from .tasks import TaskDetail

@dataclass(slots=True)
class PortfolioContext:
    """Aggregated portfolio statistics for a perspective."""
    perspective: str
    total_open: int = 0
    overdue: int = 0
    due_today: int = 0
    due_this_week: int = 0
    by_priority: Dict[str, int] = field(default_factory=dict)
    by_project: Dict[str, int] = field(default_factory=dict)
    by_due_date: Dict[str, int] = field(default_factory=dict)  # "overdue", "today", "this_week", "later"
    by_domain: Dict[str, int] = field(default_factory=dict)  # For holistic view
    task_summaries: List[Dict] = field(default_factory=list)


def build_portfolio_context(client: SmartsheetClient, perspective: str) -> PortfolioContext:
    """Build portfolio context using existing multi-sheet support."""
    
    # Determine which sources to fetch based on perspective
    if perspective == "work":
        sources = ["work"]
    elif perspective == "holistic":
        sources = ["personal", "work"]
    else:  # personal or church
        sources = ["personal"]
    
    # Fetch tasks using existing multi-sheet support
    all_tasks = client.list_tasks(sources=sources, fallback_to_stub=False)
    
    # Filter to open tasks only
    open_tasks = [t for t in all_tasks if _is_task_open(t)]
    
    # Apply perspective-specific filtering for personal/church
    if perspective == "personal":
        open_tasks = [t for t in open_tasks if not _is_church_task(t)]
    elif perspective == "church":
        open_tasks = [t for t in open_tasks if _is_church_task(t)]
    
    # Build aggregations
    return _aggregate_portfolio(perspective, open_tasks)


def _is_task_open(task: TaskDetail) -> bool:
    """Check if task is open (not completed/cancelled)."""
    status_lower = (task.status or "").lower()
    return status_lower not in ("completed", "cancelled", "delegated")


def _is_church_task(task: TaskDetail) -> bool:
    """Check if task is a church task based on project name."""
    project = (task.project or "").lower()
    return "church" in project


def _aggregate_portfolio(perspective: str, tasks: List[TaskDetail]) -> PortfolioContext:
    """Aggregate task data into portfolio statistics."""
    now = datetime.now(timezone.utc)
    today_end = now.replace(hour=23, minute=59, second=59)
    week_end = now + timedelta(days=7)
    
    ctx = PortfolioContext(perspective=perspective)
    ctx.total_open = len(tasks)
    
    for task in tasks:
        due = task.due
        if due.tzinfo is None:
            due = due.replace(tzinfo=timezone.utc)
        
        # Due date buckets
        if due < now:
            ctx.overdue += 1
            ctx.by_due_date["overdue"] = ctx.by_due_date.get("overdue", 0) + 1
        elif due <= today_end:
            ctx.due_today += 1
            ctx.by_due_date["today"] = ctx.by_due_date.get("today", 0) + 1
        elif due <= week_end:
            ctx.due_this_week += 1
            ctx.by_due_date["this_week"] = ctx.by_due_date.get("this_week", 0) + 1
        else:
            ctx.by_due_date["later"] = ctx.by_due_date.get("later", 0) + 1
        
        # Priority distribution
        priority = task.priority or "Unknown"
        ctx.by_priority[priority] = ctx.by_priority.get(priority, 0) + 1
        
        # Project distribution
        project = task.project or "Uncategorized"
        ctx.by_project[project] = ctx.by_project.get(project, 0) + 1
        
        # Domain distribution (for holistic view)
        domain = "Work" if task.source == "work" else ("Church" if _is_church_task(task) else "Personal")
        ctx.by_domain[domain] = ctx.by_domain.get(domain, 0) + 1
        
        # Task summaries (limited for prompt size)
        if len(ctx.task_summaries) < 50:
            ctx.task_summaries.append({
                "title": task.title,
                "project": task.project,
                "priority": task.priority,
                "status": task.status,
                "due": due.isoformat(),
                "source": task.source,
            })
    
    return ctx
```

### Phase 2: Backend - Global Chat Endpoint

**File: `api/main.py`**

```python
class GlobalChatRequest(BaseModel):
    message: str
    perspective: Literal["personal", "church", "work", "holistic"] = "personal"

@app.post("/assist/global/chat")
def global_chat(
    request: GlobalChatRequest,
    user: str = Depends(get_current_user),
) -> dict:
    """Chat with DATA about portfolio without task context."""
    from daily_task_assistant.portfolio_context import build_portfolio_context
    from daily_task_assistant.llm.anthropic_client import global_portfolio_chat, AnthropicError
    
    settings = load_settings()
    client = SmartsheetClient(settings=settings)
    
    # Build portfolio context
    portfolio = build_portfolio_context(client, request.perspective)
    
    # Conversation ID for global mode
    conversation_id = f"global:{request.perspective}"
    
    # Fetch history and log user message
    history = fetch_conversation_for_llm(conversation_id, limit=20)
    log_user_message(conversation_id, content=request.message, user_email=user)
    
    try:
        response = global_portfolio_chat(
            portfolio=portfolio,
            message=request.message,
            history=[{"role": m.role, "content": m.content} for m in history],
        )
    except AnthropicError as exc:
        raise HTTPException(status_code=502, detail=f"AI service error: {exc}")
    
    # Log assistant response
    log_assistant_message(conversation_id, content=response)
    
    return {
        "response": response,
        "perspective": request.perspective,
        "portfolio": asdict(portfolio),
    }
```

### Phase 3: LLM - Portfolio Analysis Prompt

**File: `daily_task_assistant/llm/anthropic_client.py`**

Add new function:

```python
def global_portfolio_chat(
    portfolio: PortfolioContext,
    message: str,
    history: List[Dict[str, str]],
) -> str:
    """Chat with DATA about portfolio/workload."""
    from .prompts import PORTFOLIO_ANALYSIS_PROMPT
    
    system_prompt = PORTFOLIO_ANALYSIS_PROMPT.format(
        perspective=portfolio.perspective,
        total_open=portfolio.total_open,
        overdue=portfolio.overdue,
        due_today=portfolio.due_today,
        due_this_week=portfolio.due_this_week,
        by_priority=portfolio.by_priority,
        by_project=portfolio.by_project,
        by_due_date=portfolio.by_due_date,
        domain_breakdown=portfolio.by_domain if portfolio.perspective == "holistic" else "",
        task_list=_format_task_list(portfolio.task_summaries),
    )
    
    # Call Anthropic with portfolio context
    # ... implementation using existing patterns
```

**File: `daily_task_assistant/llm/prompts.py`**

```python
PORTFOLIO_ANALYSIS_PROMPT = """You are DATA, David's AI chief of staff, analyzing his task portfolio.

PERSPECTIVE: {perspective}
- Personal: Home, family, and personal projects
- Church: Ministry and church leadership responsibilities  
- Work: Professional responsibilities (from separate Smartsheet)
- Holistic: Complete view across all life domains

PORTFOLIO SNAPSHOT ({perspective}):
- Total Open Tasks: {total_open}
- Overdue: {overdue}
- Due Today: {due_today}
- Due This Week: {due_this_week}

DISTRIBUTION:
Priority: {by_priority}
Projects: {by_project}
Due Dates: {by_due_date}
{domain_breakdown}

TASK SUMMARY:
{task_list}

YOUR ROLE:
1. Surface actionable insights specific to this domain
2. Identify risks and bottlenecks
3. Suggest priorities based on urgency and importance
4. In holistic mode: flag cross-domain conflicts and competing demands

Remember: You're building toward earned autonomy. Provide value through insight, not just information.
"""
```

### Phase 4: Frontend - Portfolio View UI

**File: `web-dashboard/src/components/AssistPanel.tsx`**

Modify to handle global mode when no task is selected:

```tsx
// When no task is selected, show Portfolio View
if (!selectedTask && globalMode) {
  return (
    <section className="panel assist-panel global-mode">
      <header className="assist-header-compact">
        <h2>DATA - Portfolio View</h2>
        <button onClick={onExitGlobalMode}>Show Tasks</button>
      </header>
      
      {/* 4-Tab Perspective Selector */}
      <div className="perspective-tabs">
        {(['personal', 'church', 'work', 'holistic'] as const).map((p) => (
          <button
            key={p}
            className={perspective === p ? 'active' : ''}
            onClick={() => setPerspective(p)}
          >
            {p.charAt(0).toUpperCase() + p.slice(1)}
          </button>
        ))}
      </div>
      
      {/* Portfolio Stats */}
      <PortfolioStats stats={portfolioStats} />
      
      {/* Chat Interface */}
      <GlobalChatInterface
        perspective={perspective}
        conversation={globalConversation}
        onSend={handleGlobalChat}
      />
    </section>
  )
}
```

**File: `web-dashboard/src/components/TaskList.tsx`**

Add Portfolio button to header:

```tsx
<header>
  <div>
    <h2>Tasks</h2>
    <p className="subtle">...</p>
  </div>
  <div className="task-list-controls">
    <button className="secondary portfolio-btn" onClick={onShowPortfolio}>
      📊 Portfolio
    </button>
    {/* existing Refresh button */}
  </div>
</header>
```

### Phase 5: Frontend - API Client

**File: `web-dashboard/src/api.ts`**

```typescript
export type Perspective = 'personal' | 'church' | 'work' | 'holistic'

export interface PortfolioStats {
  perspective: Perspective
  totalOpen: number
  overdue: number
  dueToday: number
  dueThisWeek: number
  byPriority: Record<string, number>
  byProject: Record<string, number>
  byDueDate: Record<string, number>
  byDomain: Record<string, number>
  taskSummaries: TaskSummary[]
}

export async function fetchPortfolioContext(
  perspective: Perspective,
  auth: AuthConfig,
  baseUrl: string = defaultBase,
): Promise<{ portfolio: PortfolioStats }> {
  const url = new URL('/assist/global/context', baseUrl)
  url.searchParams.set('perspective', perspective)
  const resp = await fetch(url, { headers: buildHeaders(auth) })
  if (!resp.ok) throw new Error(`Portfolio request failed: ${resp.statusText}`)
  return resp.json()
}

export async function sendGlobalChat(
  message: string,
  perspective: Perspective,
  auth: AuthConfig,
  baseUrl: string = defaultBase,
): Promise<{ response: string; portfolio: PortfolioStats }> {
  const url = new URL('/assist/global/chat', baseUrl)
  const resp = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...buildHeaders(auth) },
    body: JSON.stringify({ message, perspective }),
  })
  if (!resp.ok) {
    const detail = await safeJson(resp)
    throw new Error(detail?.detail ?? `Chat failed: ${resp.statusText}`)
  }
  return resp.json()
}
```

---

## Files Changed Summary

| File | Changes |
|------|---------|
| `api/main.py` | Add `/assist/global/context` and `/assist/global/chat` endpoints |
| `portfolio_context.py` | NEW - Portfolio aggregation using existing multi-sheet support |
| `llm/anthropic_client.py` | Add `global_portfolio_chat()` function |
| `llm/prompts.py` | Add `PORTFOLIO_ANALYSIS_PROMPT` |
| `AssistPanel.tsx` | Portfolio View UI when no task selected |
| `TaskList.tsx` | Add Portfolio button to header |
| `api.ts` | Add `fetchPortfolioContext()` and `sendGlobalChat()` |
| `App.tsx` | State management for global mode |
| `App.css` | Styling for portfolio view and perspective tabs |

---

## Key Design Decisions

1. **Reuse existing multi-sheet support** - No new Smartsheet integration needed
2. **Perspective filtering happens in Python** - Uses `task.source` field from multi-sheet
3. **Church vs Personal derived from project name** - Same logic as frontend `deriveDomain()`
4. **Conversation ID scheme** - `global:{perspective}` for history isolation
5. **Portfolio stats include task summaries** - For LLM context (capped at 50)

---

## Testing Checklist

- [ ] Personal perspective shows only non-church tasks from personal sheet
- [ ] Church perspective shows only church tasks from personal sheet
- [ ] Work perspective shows all tasks from work sheet (46 expected)
- [ ] Holistic perspective shows tasks from both sheets
- [ ] Portfolio stats are accurate
- [ ] Global chat maintains conversation history per perspective
- [ ] Portfolio button switches to global mode
- [ ] "Show Tasks" button returns to task list

