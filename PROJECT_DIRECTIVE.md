# Project Directive — Daily Task Assistant (DATA)

Version: 2025-12-11  
Owner: David Royes  
AI Partner: Claude Opus 4.5 (switched from GPT-5.1 Codex on 2025-11-29)

---

## 1. Vision & Guardrails

- **Mission**: AI-backed command center that ingests Smartsheet tasks, prioritizes them, recommends next actions, executes assists (email drafting/sending, context logging), and manages email workflow through a secure web experience.
- **Security**: Secrets never committed. All live sends require explicit confirmation. Google OAuth protects the web UI with email allowlist. Personal + church Gmail accounts run as separate OAuth clients.
- **Deliverables**: Maintain a CLI + FastAPI backend + React web UI + E2E test suite. Preserve traceability through Smartsheet comments and Firestore activity log.
- **Primary Use Case**: DATA partners with David (across Personal / Church / Work domains) to surface the most important active tasks, collaborate on refining next steps, execute assists, and manage email inbox using a "Chief of Staff" delegation model.

---

## 1.5. DATA's Evolution Philosophy

> **The North Star**: "The world's most effective personal AI."
>
> - **Personal** — Knows David specifically, not generic productivity advice
> - **Effective** — Actually moves things forward, not just chatty
> - **AI** — Gets smarter, not just configured once

### Three Phases of Growth

| Phase | Name | Description |
|-------|------|-------------|
| **1** | Better Tool | Task management, email drafting, research, planning. Human-initiated, human-reviewed. *(Current)* |
| **2** | Daily Companion | Persistent memory, weekly reflections, quarterly interviews. DATA learns David deeply. *(Next)* |
| **3** | Strategic Partner | Earned autonomy through demonstrated understanding. Proactive suggestions with voting, graduated trust levels. *(Future)* |

### Trust Gradient (Earned Autonomy)

Autonomy is earned, not granted. DATA progresses through trust levels:

```
Level 0: Suggest → Wait for command
Level 1: Suggest with rationale → Vote to approve/reject
Level 2: Act on small scope → Report after
Level 3: Act on larger scope → Periodic review
```

Success thresholds determine when DATA can "climb" the ladder. Size and scope of autonomous tasks increases as trust is proven through consistent, quality suggestions.

### Memory Architecture (Phase 2)

DATA builds its own Firestore-native memory from scratch:
- **David Profile**: Work patterns, communication preferences, priorities, quirks
- **Session Notes**: Raw observations from interactions (7-day TTL)
- **Weekly Digests**: Summarized learnings, pattern analysis
- **Quarterly Interviews**: Structured updates about David's world AND DATA's performance
- **Entities/Relations**: People, orgs, tools - emerging organically from conversations

**Key Decision**: No migration from external memory graphs. DATA's memory is self-contained and production-grade.

### Feedback Loop

Performance feedback about DATA *is* data about David — it reveals his values, expectations, and evolving needs. Quarterly interview includes:
- What do you think DATA is doing well?
- What area(s) could DATA stand to improve the most?

---

## 2. Architecture Snapshot

| Layer | Status | Notes |
| --- | --- | --- |
| **Ingestion** | ✅ | `SmartsheetClient` pulls live data (with graceful row-skip warnings). |
| **Analysis** | ✅ | `analysis/prioritizer.py` scores tasks + detects automation hints. |
| **Assist Engine** | ✅ | Anthropic-backed planner with web search, Research, Summarize, Contact features. |
| **Automation** | ✅ | Gmail sender for church + personal accounts, Smartsheet comments, Firestore activity log. |
| **Email Management** | ✅ | Chief of Staff model: DATA suggests rules, Apps Script executes. Google Sheets as rules DB. |
| **Interfaces** | ✅ | CLI + FastAPI backend + React web dashboard + Email Dashboard (all operational). |
| **Storage/Logs** | ✅ | Firestore for activity log + conversation history (with local file fallback). |
| **CI/CD** | ✅ | GitHub Actions: automated testing, staging deploy, production deploy with approval. |
| **E2E Testing** | ✅ | Playwright regression tests: 32 tests across API, Tasks, Email, multi-browser. |
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
| 2025-12-05 | Portfolio View: Category-based task organization (Personal/Church/Work/Holistic) with quick questions. |
| 2025-12-08 | Feedback System: Thumbs up/down on DATA responses, Firestore storage, tuning session support. |
| 2025-12-10 | **Email Management**: Chief of Staff model with Google Sheets integration, Gmail inbox reader, pattern analyzer. |
| 2025-12-11 | **Apps Script Automation**: Personal + Church email labeling rules deployed with 15-min triggers. |
| 2025-12-11 | **E2E Regression Tests**: Playwright framework with 32 tests across API, Tasks, Email features. |

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

### Infrastructure
16. **CI/CD Pipeline**: GitHub Actions with test.yml, deploy-staging.yml, deploy-prod.yml.
17. **Multi-environment**: Dev, Staging, Production with branch-based deployment flow.
18. **Health checks**: Post-deployment verification of Anthropic, Smartsheet, Gmail configuration.
19. **Secret Manager**: 10 secrets for API keys and OAuth credentials.

### Email Management (Chief of Staff Model)
20. **Email Dashboard**: Mode switcher (Tasks/Email), account selector (Personal/Church), tabbed interface.
21. **Filter Rules Manager**: Google Sheets integration for CRUD operations on email labeling rules.
22. **Gmail Inbox Reader**: Read inbox messages, extract sender patterns, identify attention items.
23. **Email Analyzer**: Pattern detection for promotional, transactional, junk emails; rule suggestions.
24. **Apps Script Delegation**: DATA suggests rules; Google Apps Script executes labeling every 15 minutes.
25. **Multi-Account Support**: Shared Google Sheet serves both Personal and Church Gmail accounts.

### Portfolio & Feedback
26. **Portfolio View**: Task organization by category (Personal/Church/Work) with holistic cross-domain view.
27. **Quick Questions**: Pre-defined prompts for rapid task consultation without full assist workflow.
28. **Feedback System**: Thumbs up/down ratings on DATA responses stored in Firestore.
29. **Tuning Sessions**: Feedback aggregation endpoint for periodic DATA behavior improvements.

### Testing & Quality
30. **Unit Tests**: 69 tests covering inbox, filter rules, email analyzer, API endpoints.
31. **E2E Regression Tests**: Playwright framework with 32 browser-automated tests.
32. **Multi-Browser Coverage**: Chrome, Firefox, Safari, Mobile Chrome test configurations.

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
- **Email filter rules**: Stored in shared Google Sheet (`Gmail_Filter_Index`). Each rule has Email, Filter Category, Filter Field, Operator, Value, Action columns.
- **Apps Script integration**: Separate scripts for Personal/Church accounts filter rules by `Email` column. Runs every 15 minutes via time-based trigger.
- **E2E test framework**: Playwright tests in `projects/e2e-tests/`. Auto-starts backend/frontend servers. Run with `npm test` or `npm run test:ui` for interactive mode.
- **Feedback storage**: Stored in Firestore (`feedback` collection) or local file via `DTA_FEEDBACK_FORCE_FILE=1`.

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
| `.cursorrules` | AI assistant project rules, code style, testing workflow |
| `e2e-tests/README.md` | Playwright E2E test documentation and commands |

---

## 10. Recent Session Log

### 2025-12-11: Email Management & E2E Testing

**Email Management (Chief of Staff Model)**
- ✅ Built Gmail inbox reader module (`mailer.py` enhancements)
- ✅ Created Google Sheets integration (`sheets/filter_rules.py`) for filter rules CRUD
- ✅ Built email pattern analyzer (`email/analyzer.py`) for suggestions
- ✅ Added Email Dashboard to React frontend with account switching
- ✅ Deployed Apps Script automation for Personal account (308 rules, 31 applied in test)
- ✅ Deployed Apps Script automation for Church account (34 rules, 135 applied in test)
- ✅ Optimized Apps Script for performance (batch processing, rule indexing, email extraction)
- ✅ Both accounts now auto-label emails every 15 minutes

**E2E Regression Testing**
- ✅ Set up Playwright framework in `projects/e2e-tests/`
- ✅ Created 32 tests: API health (4), Tasks (14), Email (14)
- ✅ Multi-browser support: Chrome, Firefox, Safari, Mobile
- ✅ Auto-server startup configuration
- ✅ npm scripts: `test`, `test:ui`, `test:headed`, `test:chrome`, `codegen`

**Documentation**
- ✅ Updated `.cursorrules` with E2E testing workflow and guidelines
- ✅ Updated `README.md` with email management and testing sections
- ✅ Created `e2e-tests/README.md` with comprehensive test documentation
- ✅ Updated `PROJECT_DIRECTIVE.md` with all new features

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

