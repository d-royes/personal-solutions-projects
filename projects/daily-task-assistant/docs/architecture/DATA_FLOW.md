# DATA Flow Diagrams

> Last updated: 2026-01-21 by Architecture Agent  
> Analyzed commit: `2da6f89`

---

## Task Management Flow

### Overview

```mermaid
graph LR
    SS[Smartsheet<br/>Source of Truth] <-->|Sync| SYNC[SyncService]
    SYNC <-->|CRUD| FS[Firestore<br/>Cloud DB]
    FS <-->|Read/Write| API[FastAPI]
    API <-->|REST| UI[React UI]
    API -->|Context| LLM[Claude]
    LLM -->|Tools| API
```

### Task Lifecycle

```mermaid
stateDiagram-v2
    [*] --> Scheduled: Created
    Scheduled --> InProgress: Started
    Scheduled --> OnHold: Blocked
    InProgress --> FollowUp: Waiting
    InProgress --> AwaitingReply: Sent message
    FollowUp --> InProgress: Response received
    AwaitingReply --> InProgress: Reply received
    InProgress --> Validation: Testing
    Validation --> Completed: Approved
    InProgress --> Completed: Done
    OnHold --> Scheduled: Unblocked
    Scheduled --> Cancelled: Abandoned
    
    Completed --> [*]
    Cancelled --> [*]
```

### Task Scoring Flow

Tasks are scored and ranked for display priority:

```mermaid
graph TD
    TASKS[Tasks List] --> SCORE[score_task]
    
    subgraph "Scoring Factors"
        PRI[Priority Weight<br/>Critical=5, Low=1]
        STAT[Status Weight<br/>On Hold=3, Scheduled=1]
        DUE[Due Date Urgency<br/>Overdue=4, Today=3.5]
        QW[Quick Win Bonus<br/>≤2 hours = +1.0]
    end
    
    SCORE --> PRI
    SCORE --> STAT
    SCORE --> DUE
    SCORE --> QW
    
    PRI --> SUM[Sum Scores]
    STAT --> SUM
    DUE --> SUM
    QW --> SUM
    
    SUM --> LABELS[Assign Labels]
    LABELS --> RANKED[RankedTask]
    
    RANKED --> SORT[Sort by Score DESC]
    SORT --> DISPLAY[Display to User]
```

**Automation Detection:**

The `detect_automation_triggers()` function scans task text for keywords:

| Keyword | Automation Suggestion |
|---------|----------------------|
| "email", "follow up" | Draft follow-up email |
| "schedule", "calendar" | Propose meeting times |
| "summarize", "report" | Generate report draft |

### Sync Process

```mermaid
sequenceDiagram
    participant SS as Smartsheet
    participant SVC as SyncService
    participant FS as Firestore
    
    Note over SVC: POST /sync/now
    
    rect rgb(200, 220, 240)
        Note over SVC: Pull from Smartsheet
        SVC->>SS: GET rows (personal sheet)
        SS-->>SVC: Task rows
        SVC->>SS: GET rows (work sheet)
        SS-->>SVC: Task rows
        SVC->>FS: Upsert by FSID
        Note over FS: Creates FSID if missing
    end
    
    rect rgb(220, 240, 200)
        Note over SVC: Push to Smartsheet
        SVC->>FS: GET modified tasks
        FS-->>SVC: Changed tasks
        SVC->>SS: UPDATE rows
        Note over SS: Updates synced
    end
```

### Sync Conflict Resolution

**Strategy:** Last-updated-wins

When both Smartsheet and Firestore have changes to the same task, the system compares timestamps:

```mermaid
graph TD
    SYNC[Sync Triggered] --> COMPARE{Compare Timestamps}
    
    COMPARE -->|FS.updated_at > SS.modifiedAt| FS_WINS[Firestore Wins]
    COMPARE -->|SS.modifiedAt > FS.updated_at| SS_WINS[Smartsheet Wins]
    COMPARE -->|Equal or Unknown| SS_WINS2[Smartsheet Wins<br/>Legacy Priority]
    
    FS_WINS --> PUSH[Push FS → SS]
    SS_WINS --> PULL[Pull SS → FS]
    SS_WINS2 --> PULL
```

**Cross-Reference Fields:**

| System | Field | Purpose |
|--------|-------|---------|
| Smartsheet | `fsid` column | Stores Firestore task ID |
| Firestore | `smartsheet_row_id` | Stores Smartsheet row ID |
| Firestore | `smartsheet_sheet` | "personal" or "work" |
| Firestore | `smartsheet_modified_at` | Last known SS timestamp |
| Firestore | `sync_status` | "synced", "pending", "conflict" |
| Firestore | `last_synced_at` | When last sync occurred |

**Sync Status Values:**
- `local_only`: Task only exists in Firestore (DATA Task)
- `synced`: Task is in sync with Smartsheet
- `pending`: Local changes waiting to sync
- `conflict`: Conflicting changes detected (rare)
- `orphaned`: Smartsheet row deleted, needs review

### Status Translation Maps

Bidirectional mapping between Smartsheet and Firestore status values:

**Smartsheet → Firestore (`STATUS_MAP`):**

| Smartsheet Status | Firestore TaskStatus |
|-------------------|---------------------|
| Scheduled | SCHEDULED |
| Recurring | RECURRING |
| On Hold | ON_HOLD |
| In Progress | IN_PROGRESS |
| Follow-up | FOLLOW_UP |
| Awaiting Reply | AWAITING_REPLY |
| Delivered | DELIVERED |
| Validation | VALIDATION |
| Needs Approval | NEEDS_APPROVAL |
| Completed | COMPLETED |
| Cancelled | CANCELLED |
| Delegated | DELEGATED |

**Firestore → Smartsheet (`REVERSE_STATUS_MAP`):**

| Firestore TaskStatus | Smartsheet Status | Notes |
|---------------------|-------------------|-------|
| SCHEDULED | Scheduled | |
| RECURRING | Recurring | |
| ON_HOLD | On Hold | |
| IN_PROGRESS | In Progress | |
| FOLLOW_UP | Follow-up | |
| AWAITING_REPLY | Awaiting Reply | |
| BLOCKED | On Hold | Maps to same as ON_HOLD |
| DELIVERED | Delivered | |
| VALIDATION | Validation | |
| NEEDS_APPROVAL | Needs Approval | |
| COMPLETED | Completed | |
| CANCELLED | Cancelled | |
| DELEGATED | Delegated | |
| PENDING | Scheduled | Legacy status maps to Scheduled |

### Recurring Pattern Detection

The sync service detects recurring patterns from Smartsheet:

| Smartsheet Pattern | RecurringType | Days |
|-------------------|---------------|------|
| "M", "T", "W", "H", "F", "Sa" | WEEKLY | [day] |
| "Monthly" | MONTHLY | [] |

### Field Translation

Estimated hours must match Smartsheet picklist exactly:
- Valid values: `.05`, `.15`, `.25`, `.50`, `.75`, `1`, `2`, `3`, `4`, `5`, `6`, `7`, `8`

---

## Email Processing Flow

### Inbox Analysis

```mermaid
graph TD
    GM[Gmail API] -->|Fetch| INBOX[inbox.py]
    INBOX -->|Raw emails| AZ[analyzer.py]
    
    subgraph "Analysis Pipeline"
        AZ -->|Check| PROF[DavidProfile<br/>Role Matching]
        PROF -->|VIP/Patterns| SCORE1[High Confidence]
        AZ -->|Batch| HA[haiku_analyzer.py<br/>Claude Haiku]
        HA -->|AI Analysis| SCORE2[Variable Confidence]
    end
    
    SCORE1 --> ATT[attention_store.py]
    SCORE2 --> ATT
    ATT -->|High priority| UI[Email UI]
    
    subgraph "Rule Engine"
        RS[rule_store.py<br/>Google Sheets]
        SUG[suggestion_store.py]
    end
    
    AZ --> RS
    RS -->|Matches| SUG
    SUG --> UI
```

### Attention Analysis Methods

| Method | Trigger | Confidence |
|--------|---------|------------|
| `vip` | Sender in DavidProfile.vip_senders | High (0.9+) |
| `profile_match` | Keywords match role attention patterns | Medium-High |
| `haiku` | Claude Haiku semantic analysis | Variable |
| `regex` | Legacy rule matching | Medium |

### Attention TTL Management

```mermaid
graph LR
    NEW[New Attention] -->|Active| ACTIVE[30-day TTL]
    ACTIVE -->|User dismisses| DISMISSED[7-day TTL]
    ACTIVE -->|Task created| TASK[Linked to task]
    ACTIVE -->|Expires| EXPIRED[Auto-removed]
    DISMISSED -->|Expires| EXPIRED
```

**Environment Variables:**
- `DTA_ATTENTION_TTL_ACTIVE`: Days to keep active items (default: 30)
- `DTA_ATTENTION_TTL_DISMISSED`: Days to keep dismissed items (default: 7)

### Quality Tracking (Phase 1A)

The attention system tracks user actions for quality measurement:

| Field | Purpose |
|-------|---------|
| `first_viewed_at` | When user first saw the item |
| `action_taken_at` | When user acted on it |
| `action_type` | viewed, dismissed, task_created, email_replied, ignored |
| `suppressed_by_threshold` | Hidden due to low confidence |
| `user_modified_reason` | User changed suggested reason |

### Email Action Flow

```mermaid
sequenceDiagram
    participant U as User
    participant UI as Email UI
    participant API as FastAPI
    participant GM as Gmail API
    participant FS as Firestore
    
    U->>UI: View attention email
    UI->>API: POST /email/{account}/read/{id}
    API->>GM: Mark as read
    
    alt Create Task
        U->>UI: "Create task from email"
        UI->>API: POST /email/{account}/task-create
        API->>FS: Create FirestoreTask
        API->>UI: Task created
    else Reply
        U->>UI: "Reply"
        UI->>API: POST /email/{account}/reply-draft
        API->>UI: Draft content
        U->>UI: Send
        UI->>API: POST /email/{account}/reply-send
        API->>GM: Send email
    else Dismiss
        U->>UI: "Dismiss"
        UI->>API: POST /email/attention/{account}/{id}/dismiss
        API->>FS: Mark dismissed
    end
```

### Stale Email Detection

When emails are deleted, archived, or moved to TRASH/SPAM, referenced attention and suggestion items become "stale" and should be auto-dismissed.

```mermaid
graph TD
    REFRESH[Analysis Refresh] --> BATCH[batch_check_emails]
    BATCH --> CHECK{email_exists?}
    
    CHECK -->|Yes| KEEP[Keep Item]
    CHECK -->|No / TRASH / SPAM| STALE[Mark Stale]
    
    STALE --> ATT_DISMISS[dismiss_stale_attention]
    STALE --> SUG_EXPIRE[expire_stale_suggestions]
    
    USER[User Interaction] --> VERIFY[verify_email_for_interaction]
    VERIFY -->|Not Found| TOAST[Show Toast + Auto-dismiss]
```

**Key Functions (`email/sync.py`):**

- `email_exists(config, email_id)` - Check Gmail existence (TRASH/SPAM = deleted)
- `batch_check_emails(config, email_ids)` - Validate multiple emails
- `sync_stale_items(account, attention, suggestions, config)` - Full sync operation
- `verify_email_for_interaction(config, email_id)` - Quick check before user action

---

## Conversation Flow

### Chat Request Lifecycle

```mermaid
sequenceDiagram
    participant U as User
    participant UI as React UI
    participant API as FastAPI
    participant CTX as ContextAssembler
    participant LLM as Claude
    participant TOOLS as Tool Executor
    participant HIST as ConversationStore
    
    U->>UI: Send message
    UI->>API: POST /assist/{task_id}/chat
    
    API->>HIST: Load history
    HIST-->>API: Previous messages
    
    API->>CTX: Build context
    Note over CTX: Task details + history + system prompt
    CTX-->>API: Full context
    
    API->>LLM: Send to Claude
    
    alt Tool Call
        LLM-->>API: Tool request
        API->>TOOLS: Execute tool
        TOOLS-->>API: Tool result
        API->>LLM: Continue with result
    end
    
    LLM-->>API: Final response
    API->>HIST: Save exchange
    API-->>UI: Response
    UI-->>U: Display
```

### Context Assembly Process

```mermaid
graph TD
    INTENT[ClassifiedIntent] --> CTX[assemble_context]
    
    subgraph "Context Assembly"
        CTX --> SYS[Build System Prompt]
        CTX --> TOOLS[Select Tools for Intent]
        CTX --> TASK[Build Task Context]
        CTX --> WS[Include Workspace Content]
        CTX --> HIST[Prepare History]
        CTX --> IMG[Encode Selected Images]
    end
    
    HIST --> SUMM{History > 6 turns?}
    SUMM -->|Yes| SUMMARIZE[Summarize Older Turns]
    SUMM -->|No| KEEP_FULL[Keep Full History]
    
    SYS --> BUNDLE[ContextBundle]
    TOOLS --> BUNDLE
    TASK --> BUNDLE
    WS --> BUNDLE
    SUMMARIZE --> BUNDLE
    KEEP_FULL --> BUNDLE
    IMG --> BUNDLE
    
    BUNDLE --> LLM[Send to Claude]
```

**History Summarization:**

- Action intents: Last 2 turns only
- Other intents: Last 6 turns full, older summarized to "[Previous context: ...]"

### Tool Execution

```mermaid
graph TD
    LLM[Claude Response] -->|tool_use| EXEC[chat_executor.py]
    
    EXEC --> SS_UPDATE[update_smartsheet<br/>Update task fields]
    EXEC --> WEB[web_search<br/>Research]
    EXEC --> CONTACT[lookup_contact<br/>Find person]
    EXEC --> EMAIL[create_email_draft<br/>Draft email]
    EXEC --> PLAN[generate_plan<br/>Task planning]
    
    SS_UPDATE --> RESULT[Tool Result]
    WEB --> RESULT
    CONTACT --> RESULT
    EMAIL --> RESULT
    PLAN --> RESULT
    
    RESULT --> LLM2[Continue Conversation]
```

---

## Calendar Flow

### Event Management

```mermaid
graph LR
    GC[Google Calendar API] <-->|OAuth| CAL[calendar/]
    CAL <-->|CRUD| API[FastAPI]
    CAL -->|Analysis| ATT[Attention Store]
    API <-->|REST| UI[Calendar UI]
    API -->|Context| LLM[Claude]
```

### Calendar Attention

```mermaid
sequenceDiagram
    participant GC as Google Calendar
    participant API as FastAPI
    participant ATT as Attention System
    participant U as User
    
    Note over API: POST /calendar/{account}/attention/analyze
    API->>GC: Fetch upcoming events
    GC-->>API: Events
    API->>ATT: Analyze events
    Note over ATT: Score by urgency,<br/>prep needed, conflicts
    ATT-->>API: Attention items
    API-->>U: "Meeting in 30min needs prep"
```

---

## State Management

### Frontend State

```mermaid
graph TD
    subgraph "React State"
        TASKS[tasks: Task[]]
        SELECTED[selectedTask: Task]
        HISTORY[chatHistory: Message[]]
        EMAIL[emails: Email[]]
    end
    
    subgraph "API Calls"
        GET_TASKS[GET /tasks]
        GET_FS[GET /tasks/firestore]
        CHAT[POST /assist/{id}/chat]
        GET_INBOX[GET /inbox/{account}]
    end
    
    GET_TASKS --> TASKS
    GET_FS --> TASKS
    SELECTED --> CHAT
    CHAT --> HISTORY
    GET_INBOX --> EMAIL
```

### Backend State

- **Firestore**: Persistent state (tasks, conversations, feedback)
- **Smartsheet**: External source of truth for tasks
- **In-memory**: Request-scoped state only
- **No session state**: Stateless API design

---

## Related Documentation

- [OVERVIEW.md](./OVERVIEW.md) - System overview
- [COMPONENTS.md](./COMPONENTS.md) - Module breakdown
- [INTEGRATIONS.md](./INTEGRATIONS.md) - External services
- [API_REFERENCE.md](./API_REFERENCE.md) - All endpoints
