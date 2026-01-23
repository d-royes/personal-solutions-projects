# DATA API Reference

> Last updated: 2026-01-21 by Architecture Agent  
> Analyzed commit: `66e5be7` (refactor/api-routers branch)  
> Total endpoints: **136+** (~108 in routers, remainder in main.py)

---

## Router Organization

As of January 2026, endpoints are organized into **modular routers** for maintainability:

| Router File | URL Prefix | Domain | Endpoints |
|-------------|------------|--------|-----------|
| `api/routers/tasks.py` | `/tasks` | Task CRUD, Firestore, recurring | ~10 |
| `api/routers/tasks.py` | `/sync` | Smartsheet ↔ Firestore sync | ~3 |
| `api/routers/tasks.py` | `/work` | Work task badge | ~1 |
| `api/routers/calendar.py` | `/calendar` | Events, settings, attention, chat | ~19 |
| `api/routers/assist.py` | `/assist` | AI assist, planning, chat, workspace | ~20 |
| `api/routers/email.py` | `/inbox`, `/email` | Inbox, attention, drafts, haiku | ~56 |
| `api/main.py` | various | Settings, profile, contacts, health | ~28 |

**Note:** Original endpoint definitions in `main.py` still exist during migration. Routers take precedence due to registration order.

See [COMPONENTS.md](./COMPONENTS.md#api-layer-modular-routers) for architecture details.

---

## Base URL

| Environment | URL |
|-------------|-----|
| Development | `http://localhost:8000` |
| Staging | `https://data-staging-xxx.run.app` |
| Production | `https://data-xxx.run.app` |

## Authentication

**Production:** Google OAuth ID token in `Authorization: Bearer <token>` header

**Development:** 
```bash
$env:DTA_DEV_AUTH_BYPASS = "1"
curl -H "X-User-Email: david.a.royes@gmail.com" localhost:8000/tasks
```

---

## Health & Core

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check |
| GET | `/tasks` | Fetch Smartsheet tasks |
| GET | `/work/badge` | Work task badge count |

---

## Global Assist

Chat and operations across all tasks (not task-specific).

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/assist/global/chat` | Global chat message |
| GET | `/assist/global/context` | Get global context |
| DELETE | `/assist/global/history` | Clear global history |
| POST | `/assist/global/bulk-update` | Bulk update tasks |
| POST | `/assist/global/rebalance` | Rebalance task schedule |
| POST | `/assist/global/history/strike` | Strike history item |
| POST | `/assist/global/history/unstrike` | Unstrike history |
| DELETE | `/assist/global/message` | Delete specific message |

---

## Firestore Tasks

Tasks stored in Firestore (DATA Tasks, not Smartsheet-synced).

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/tasks/firestore` | List Firestore tasks |
| POST | `/tasks/firestore` | Create Firestore task |
| GET | `/tasks/firestore/{task_id}` | Get specific task |
| PATCH | `/tasks/firestore/{task_id}` | Update task |
| DELETE | `/tasks/firestore/{task_id}` | Delete task |
| POST | `/assist/firestore/{task_id}` | Engage Firestore task |
| POST | `/assist/firestore/{task_id}/chat` | Chat with Firestore task |

---

## Task Assist

Task-specific chat and operations (Smartsheet tasks).

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/assist/{task_id}` | Engage with task |
| POST | `/assist/{task_id}/plan` | Generate plan |
| POST | `/assist/{task_id}/chat` | Send chat message |
| POST | `/assist/{task_id}/research` | Web research |
| POST | `/assist/{task_id}/contact` | Contact lookup |
| POST | `/assist/{task_id}/summarize` | Summarize content |
| POST | `/assist/{task_id}/update` | Update Smartsheet |
| POST | `/assist/{task_id}/feedback` | Submit feedback |
| GET | `/assist/{task_id}/history` | Get conversation history |
| POST | `/assist/{task_id}/history/strike` | Strike history item |
| POST | `/assist/{task_id}/history/unstrike` | Unstrike history |
| GET | `/assist/{task_id}/attachments` | Get task attachments |
| GET | `/assist/{task_id}/attachment/{id}` | Get specific attachment |
| POST | `/assist/{task_id}/draft-email` | Draft email |
| POST | `/assist/{task_id}/send-email` | Send email |
| GET | `/assist/{task_id}/draft` | Get saved draft |
| POST | `/assist/{task_id}/draft` | Save draft |
| DELETE | `/assist/{task_id}/draft` | Delete draft |
| GET | `/assist/{task_id}/workspace` | Get workspace |
| POST | `/assist/{task_id}/workspace` | Save workspace |
| DELETE | `/assist/{task_id}/workspace` | Delete workspace |

---

## Email - Inbox

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/inbox/{account}` | Fetch inbox |
| GET | `/inbox/{account}/unread` | Get unread count |
| GET | `/inbox/{account}/search` | Search emails |
| GET | `/email/{account}/message/{id}` | Get message |
| GET | `/email/{account}/thread/{id}` | Get thread |

---

## Email - Actions

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/email/{account}/archive/{id}` | Archive message |
| POST | `/email/{account}/delete/{id}` | Delete message |
| POST | `/email/{account}/star/{id}` | Star message |
| POST | `/email/{account}/important/{id}` | Mark important |
| POST | `/email/{account}/read/{id}` | Mark as read |
| POST | `/email/{account}/reply-draft` | Draft reply |
| POST | `/email/{account}/reply-send` | Send reply |
| GET | `/email/{account}/labels` | Get labels |
| POST | `/email/{account}/label/{id}` | Apply label |

---

## Email - Attention

AI-analyzed emails requiring action.

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/email/analyze/{account}` | Analyze inbox |
| GET | `/email/attention/{account}` | Get attention items |
| POST | `/email/attention/{account}/{id}/dismiss` | Dismiss |
| POST | `/email/attention/{account}/{id}/snooze` | Snooze |
| POST | `/email/attention/{account}/{id}/viewed` | Mark viewed |
| GET | `/email/attention/{account}/quality-metrics` | Quality metrics |

---

## Email - Rules & Suggestions

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/email/rules/{account}` | Get filter rules |
| POST | `/email/rules/{account}` | Create rule |
| DELETE | `/email/rules/{account}/{row}` | Delete rule |
| GET | `/email/rules/{account}/pending` | Pending rule suggestions |
| POST | `/email/rules/{account}/{id}/decide` | Accept/reject rule |
| GET | `/email/rules/{account}/stats` | Rule stats |
| GET | `/email/rules/{account}/allowed-labels` | Allowed labels |
| GET | `/email/suggestions/{account}/pending` | Pending suggestions |
| POST | `/email/suggestions/{account}/{id}/decide` | Decide suggestion |
| GET | `/email/suggestions/{account}/stats` | Suggestion stats |
| GET | `/email/suggestions/rejection-patterns` | Rejection patterns |
| GET | `/email/{account}/suggestions` | Get suggestions |

---

## Email - Pinned & Tasks

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/email/{account}/pin/{id}` | Pin email |
| DELETE | `/email/{account}/pin/{id}` | Unpin email |
| GET | `/email/{account}/pinned` | Get pinned |
| POST | `/email/task-from-email/{account}` | Create task from email |
| POST | `/email/{account}/task-preview` | Preview task creation |
| POST | `/email/{account}/task-create` | Create task |
| POST | `/email/{account}/check-tasks` | Check related tasks |

---

## Email - Chat & Conversation

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/email/{account}/chat` | Email chat |
| GET | `/email/{account}/conversation/{id}` | Get conversation |
| DELETE | `/email/{account}/conversation/{id}` | Delete conversation |

---

## Email - Memory & Privacy

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/email/{account}/memory/sender-profiles` | Sender profiles |
| GET | `/email/{account}/memory/sender/{email}` | Specific sender |
| POST | `/email/{account}/memory/seed` | Seed memory |
| GET | `/email/{account}/memory/category-patterns` | Category patterns |
| POST | `/email/{account}/memory/category-approval` | Approve category |
| POST | `/email/{account}/memory/category-dismissal` | Dismiss category |
| GET | `/email/{account}/memory/timing` | Timing memory |
| GET | `/email/{account}/memory/response-warning` | Response warnings |
| GET | `/email/{account}/privacy/{id}` | Privacy info |
| POST | `/email/sync/{account}` | Sync inbox |

---

## Email - Haiku

Lightweight Gemini analysis settings.

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/email/haiku/settings` | Haiku settings |
| PUT | `/email/haiku/settings` | Update settings |
| GET | `/email/haiku/usage` | Haiku usage stats |
| GET | `/email/trust-metrics` | Trust metrics |

---

## Calendar

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/calendar/{account}/calendars` | List calendars |
| GET | `/calendar/{account}/events` | List events |
| GET | `/calendar/{account}/events/{id}` | Get event |
| POST | `/calendar/{account}/events` | Create event |
| PUT | `/calendar/{account}/events/{id}` | Update event |
| DELETE | `/calendar/{account}/events/{id}` | Delete event |
| POST | `/calendar/{account}/quick-add` | Quick add (NL) |
| GET | `/calendar/{account}/settings` | Get settings |
| PUT | `/calendar/{account}/settings` | Update settings |

---

## Calendar - Attention

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/calendar/{account}/attention` | Attention items |
| POST | `/calendar/{account}/attention/{id}/viewed` | Mark viewed |
| POST | `/calendar/{account}/attention/{id}/dismiss` | Dismiss |
| POST | `/calendar/{account}/attention/{id}/act` | Act on event |
| GET | `/calendar/{account}/attention/quality-metrics` | Quality metrics |
| POST | `/calendar/{account}/attention/analyze` | Analyze calendar |

---

## Calendar - Chat

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/calendar/{domain}/chat` | Calendar chat |
| GET | `/calendar/{domain}/conversation` | Get conversation |
| DELETE | `/calendar/{domain}/conversation` | Delete conversation |
| PUT | `/calendar/{domain}/conversation` | Update conversation |

---

## Sync & Recurring

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/sync/now` | Trigger sync |
| GET | `/sync/status` | Sync status |
| POST | `/sync/scheduled` | Scheduled sync |
| POST | `/tasks/recurring/reset` | Reset recurring |
| GET | `/tasks/recurring/preview` | Preview recurring |

---

## Profile & Contacts

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/profile` | Get profile |
| PUT | `/profile` | Update profile |
| POST | `/profile/not-actionable/add` | Add not-actionable |
| POST | `/profile/not-actionable/remove` | Remove not-actionable |
| GET | `/profile/blocklist` | Get blocklist |
| POST | `/profile/blocklist/add` | Add to blocklist |
| POST | `/profile/blocklist/remove` | Remove from blocklist |
| POST | `/contacts` | Create contact |
| GET | `/contacts` | List contacts |
| GET | `/contacts/{id}` | Get contact |
| DELETE | `/contacts/{id}` | Delete contact |

---

## Settings & Feedback

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/settings` | Get settings |
| PUT | `/settings` | Update settings |
| GET | `/feedback/summary` | Feedback summary |
| GET | `/activity` | Activity log |
| POST | `/tasks/create` | Create task |

---

## Related Documentation

- [OVERVIEW.md](./OVERVIEW.md) - System overview
- [COMPONENTS.md](./COMPONENTS.md) - Module breakdown
- [DATA_FLOW.md](./DATA_FLOW.md) - Data flow diagrams
- [INTEGRATIONS.md](./INTEGRATIONS.md) - External services
