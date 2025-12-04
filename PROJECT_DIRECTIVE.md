# Project Directive — Daily Task Assistant (DATA)

Version: 2025-12-04  
Owner: David Royes  
AI Partner: Claude Opus 4.5 (switched from GPT-5.1 Codex on 2025-11-29)

---

## 1. Vision & Guardrails

- **Mission**: AI-backed command center that ingests Smartsheet tasks, prioritizes them, recommends next actions, and executes assists (email drafting/sending, context logging) through a secure web experience.
- **Security**: Secrets never committed. All live sends require explicit confirmation. Google OAuth protects the web UI with email allowlist. Personal + church Gmail accounts run as separate OAuth clients.
- **Deliverables**: Maintain a CLI + FastAPI backend + React web UI. Preserve traceability through Smartsheet comments and Firestore activity log.
- **Primary Use Case**: DATA partners with David (across Personal / Church / Work domains) to surface the most important active tasks, collaborate on refining next steps, and execute assists while conversations accumulate intelligence.

---

## 2. Architecture Snapshot

| Layer | Status | Notes |
| --- | --- | --- |
| **Ingestion** | ✅ | `SmartsheetClient` pulls live data (with graceful row-skip warnings). |
| **Analysis** | ✅ | `analysis/prioritizer.py` scores tasks + detects automation hints. |
| **Assist Engine** | ✅ | Anthropic-backed planner with web search, Research, Summarize, Contact features. |
| **Automation** | ✅ | Gmail sender for church + personal accounts, Smartsheet comments, Firestore activity log. |
| **Interfaces** | ✅ | CLI + FastAPI backend + React web dashboard (all operational). |
| **Storage/Logs** | ✅ | Firestore for activity log + conversation history (with local file fallback). |
| **CI/CD** | ✅ | GitHub Actions: automated testing, staging deploy, production deploy with approval. |
| **Hosting** | ✅ | Cloud Run (backend) + Firebase Hosting (frontend) for staging and production. |

---

## 3. Live Environments

| Environment | Frontend | Backend | Status |
| --- | --- | --- | --- |
| **Production** | https://daily-task-assistant-prod.web.app | https://daily-task-assistant-prod-368257400464.us-central1.run.app | ✅ Live |
| **Staging** | https://daily-task-assistant-church.web.app | https://daily-task-assistant-staging-368257400464.us-central1.run.app | ✅ Live |
| **Dev** | http://localhost:5173 | http://localhost:8000 | Local |

---

## 4. Timeline & Milestones

| Date | Milestone |
| --- | --- |
| 2025-11-27 | Initial CLI scaffold (config, stub tasks, Smartsheet schema). |
| 2025-11-28 AM | Prioritizer + Anthropic assist integration. |
| 2025-11-28 PM | Gmail church account wired; `--send-email` CLI flag. |
| 2025-11-28 late | Smartsheet comments auto-post + activity log introduced. |
| 2025-11-29 AM | FastAPI scaffolding (REST API, stub auth) + API tests. |
| 2025-11-29 Midday | React web dashboard scaffold + Google Sign-In wired. |
| 2025-11-29 PM | Activity log migrated to Firestore. **Model switch to Claude Opus 4.5**. |
| 2025-11-29 Evening | Local end-to-end validation + start/stop scripts. |
| 2025-11-30 | Assistant chat + Firestore history shipped (per-task conversations). |
| 2025-12-01 | Task list + assistant UX refresh (filters, collapsible rail, action buttons). |
| 2025-12-02 | **CI/CD Pipeline**: GitHub Actions for test/staging/prod workflows. Branch protection configured. |
| 2025-12-02 | **First Staging Deployment** (PR #8, 2m 32s). Auth persistence, email allowlist, Research improvements. |
| 2025-12-03 | **First Production Deployment** (PR #10, 8m 7s). Firebase multi-site hosting, IAM configuration. |
| 2025-12-04 | **Multi-Sheet Smartsheet Integration** + **Expanded Field Editing** (9 editable fields). |
| 2025-12-04 | **Context-Aware Planning & Email** (PR #12). Workspace selection for AI context. |

---

## 5. Features Delivered

### Core Features
1. **Task ingestion & scoring**: Live Smartsheet fetch with per-row warnings, rich `TaskDetail` model, deterministic stubs.
2. **Assist generation**: Anthropic-backed `plan_assist()` with model overrides, prompts, and fallback templates.
3. **CLI workflows**: `list`, `recommend`, `assist`, `schema`, `check-token`, plus `--send-email`, `--anthropic-model`, `--source`.
4. **Gmail automation**: Env-driven account loader (church/personal). Sends email + returns message ID.
5. **Smartsheet feedback**: Auto comment when email sends succeed.
6. **Activity logging**: Firestore log capturing each assist (task, account, model, message id, source).
7. **Persistent conversations**: Firestore-backed chat threads per task with REST/React UI.

### Web Dashboard Features
8. **React web UI**: Task list with filters, Assistant panel, Conversation view, Activity feed.
9. **Google OAuth**: Sign-in with ID token verification, email allowlist security.
10. **Auth persistence**: Login survives page refresh (localStorage with token expiry validation).
11. **Action buttons**: Plan, Research, Summarize, Contact, Draft Email.

### AI Features
12. **Research**: Web search with AI-generated insights (pros/cons, best practices, alternatives).
13. **Summarize**: Task + plan + conversation summary generation.
14. **Contact search**: AI-powered Named Entity Recognition for finding contacts in task notes.
15. **Email drafting**: Context-aware email generation with recipient detection.
16. **Context-Aware Planning**: Selected workspace items inform plan generation for task-specific advice.
17. **Context-Aware Email**: Selected workspace content becomes source material for email drafts.

### Smartsheet Integration
18. **Multi-sheet support**: Personal + Work Smartsheets with separate filtering (Work excluded from "All" view).
19. **Expanded field editing**: DATA can update 9 fields via chat (#, Priority, Contact, Recurring, Project, Task, Assigned To, Notes, Estimated Hours).
20. **Recurring task handling**: "Mark complete" on recurring tasks only checks Done box, preserving recurrence.
21. **Work badge**: Urgent/overdue work task count displayed on Work filter button.

### Infrastructure
22. **CI/CD Pipeline**: GitHub Actions with test.yml, deploy-staging.yml, deploy-prod.yml.
23. **Multi-environment**: Dev, Staging, Production with branch-based deployment flow.
24. **Health checks**: Post-deployment verification of Anthropic, Smartsheet, Gmail configuration.
25. **Secret Manager**: 10 secrets for API keys and OAuth credentials.

---

## 6. Implementation Notes & Decisions

- **Schema warnings**: We skip Smartsheet rows with missing required fields and report them via CLI/REST.
- **Anthropic fallback**: If the API key or model fails, we log a note in the AssistPlan and fall back to local templates.
- **Gmail sending**: Each account needs `*_GMAIL_CLIENT_ID/SECRET/REFRESH_TOKEN/ADDRESS` env vars.
- **Activity log**: Stored in Firestore (`activity_log` collection). CLI/API share the same writer. Local fallback via `DTA_ACTIVITY_FORCE_FILE`.
- **Conversation store**: Per-task chat history saved to Firestore (`conversations` collection) with file fallback via `DTA_CONVERSATION_FORCE_FILE`.
- **API auth**: FastAPI enforces Google ID tokens. Local dev can set `DTA_DEV_AUTH_BYPASS=1` and pass `X-User-Email`.
- **Email allowlist**: Only `davidroyes@southpointsda.org` and `david.a.royes@gmail.com` can access (configurable via `DTA_ALLOWED_EMAILS`).
- **Branch strategy**: `develop` → `staging` → `main` with PR requirements and status checks.

---

## 7. Outstanding Goals (Future Enhancements)

1. **Enhancements**
   - Notion/Slack notifications
   - Calendar scheduling integration
   - Document summarization from attachments
   - Multi-user support / role separation

2. **Observability**
   - Error tracking/alerting (Sentry or similar)
   - Usage analytics dashboard
   - Cost monitoring for AI API calls

3. **UX Improvements**
   - Mobile-optimized responsive design
   - Keyboard shortcuts
   - Bulk task operations
   - Custom filters/saved views

---

## 8. Working Agreements

- Update this directive whenever we finish a feature, face a major issue, or change course.
- Always document:
  1. **Goal** (what/why).
  2. **Actions taken** (key files/touches).
  3. **Result** (tests, deploys, issues).
  4. **Follow-ups** (open questions, next steps).
- Keep sections sorted by recency. Archive older details if the doc exceeds ~400 lines.
- Use CHANGELOG.md for detailed release notes; this doc is for high-level project status.

---

## 9. Key Documentation

| Document | Purpose |
| --- | --- |
| `PROJECT_DIRECTIVE.md` | This file - high-level project status and direction |
| `CHANGELOG.md` | Detailed release notes and version history |
| `BACKLOG.md` | Feature backlog, known issues, and planned enhancements |
| `docs/CI_CD_Setup.md` | CI/CD pipeline setup and deployment instructions |
| `DATA_PREFERENCES.md` | DATA's behavioral guidelines and persona tuning (chatbot behavior only) |
| `README.md` | Developer setup and API documentation |

---

## 10. Recent Session Log

### 2025-12-04: Context-Aware Planning & Multi-Sheet Integration
- ✅ **Multi-Sheet Smartsheet**: Added Work Smartsheet alongside Personal
  - Work tasks excluded from "All" filter, shown in dedicated "Work" view
  - Work badge shows urgent/overdue count
  - Source-aware writes (updates go to correct sheet)
- ✅ **Expanded Field Editing**: DATA can now update 9 Smartsheet fields via chat
  - #, Priority, Contact, Recurring, Project, Task, Assigned To, Notes, Estimated Hours
  - Picklist validation, MULTI_PICKLIST and MULTI_CONTACT column type support
- ✅ **Recurring Task Handling**: "Mark complete" preserves recurrence (only checks Done box)
- ✅ **Context-Aware Planning**: Workspace selection informs plan generation
  - Checkbox UI on workspace items for multi-select
  - "+" button to add new workspace content directly
  - Selected content passed to Anthropic as additional context
- ✅ **Context-Aware Email Draft**: Selected workspace items become email source content
- ✅ **Pydantic v2 Fix**: Added `populate_by_name=True` for proper alias handling
- ✅ **Staging deployment** (PR #12, 2m 45s) - Context-Aware Planning feature

### 2025-12-03: Production Deployment
- ✅ Created Firebase production hosting site (`daily-task-assistant-prod`)
- ✅ Configured `.firebaserc` with staging and production targets
- ✅ Resolved merge conflict in CI_CD_Setup.md
- ✅ Created PR #10 (staging → main) for production release
- ✅ Fixed IAM permissions (Secret Manager access for compute service account)
- ✅ Added production origin to Google OAuth client
- ✅ **Production deployed and verified operational**

### 2025-12-02: CI/CD Pipeline & Staging
- ✅ Implemented GitHub Actions workflows (test, deploy-staging, deploy-prod)
- ✅ Configured branch protection rules
- ✅ First staging deployment via CI/CD (PR #8)
- ✅ Added auth persistence (localStorage)
- ✅ Added email allowlist security
- ✅ Improved Research prompts for deeper insights
- ✅ Fixed Contact feature with AI entity extraction
- ✅ Fixed Email Draft JSON parsing (markdown code fences)

