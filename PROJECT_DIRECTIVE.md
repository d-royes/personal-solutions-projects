# Project Directive — Daily Task Assistant

Version: 2025-11-28  
Owner: David Royes  
AI Partner: GPT-5.1 Codex

---

## 1. Vision & Guardrails

- **Mission**: AI-backed command center that ingests Smartsheet tasks, prioritizes them, recommends next actions, and executes assists (email drafting/sending, context logging) through a secure web experience.
- **Security**: Secrets never committed. All live sends require explicit confirmation. Google OAuth protects the eventual web UI. Personal + church Gmail accounts run as separate OAuth clients.
- **Deliverables**: Maintain a CLI + FastAPI backend + React web UI. Preserve traceability through Smartsheet comments and a local/cloud activity log.

---

## 2. Architecture Snapshot (current)

| Layer | Status | Notes |
| --- | --- | --- |
| **Ingestion** | ✅ | `SmartsheetClient` pulls live data (with graceful row-skip warnings). |
| **Analysis** | ✅ | `analysis/prioritizer.py` scores tasks + detects automation hints. |
| **Assist Engine** | ✅ | Anthropic-backed planner with template fallback. Model override via env/CLI. |
| **Automation** | ✅ | Gmail sender for church + personal accounts, Smartsheet comments, JSONL activity log. |
| **Interfaces** | 🟡 | CLI + chat prototype. FastAPI + React web UI pending. |
| **Storage/Logs** | ✅ | Activity log (`activity_log.jsonl` or `DTA_ACTIVITY_LOG` path), Smartsheet comments. |

Upcoming: FastAPI service (Cloud Run) + React web dashboard (Firebase hosting or Cloud Run) + Google OAuth protection.

---

## 3. Timeline & Milestones

| Date | Milestone |
| --- | --- |
| 2025-11-27 | Initial CLI scaffold (config, stub tasks, Smartsheet schema). |
| 2025-11-28 AM | Prioritizer + Anthropic assist integration. |
| 2025-11-28 PM | Gmail church account wired; `--send-email` CLI flag; README updates. |
| 2025-11-28 late PM | Smartsheet comments auto-post + activity log introduced. |
| 2025-11-29 early AM | FastAPI scaffolding (REST API, stub auth) + API tests. |
| 2025-11-29 Morning | React web dashboard scaffold (dev auth panel, task list, assist + activity feeds). |
| 2025-11-29 Midday | Google Sign-In wired into dashboard + backend token verification. |
| 2025-11-29 Afternoon | Activity log migrated to Firestore with file fallback and service account credentials configured. |
| 2025-11-29 Evening | Local end-to-end validation (backend + React dev server, CORS + dev bypass fixes) + start/stop scripts. |
| 2025-11-29 Night | Task warning banner summarized (counts + guidance) for clearer UI. |
| 2025-11-29 Late | Committed to Dev → Staging → Prod environment strategy despite higher cost. |
| 2025-11-30 Early | Web UI header rebuilt (auth status badge, admin menu, trimmed notes) to maximize working columns. |
| 2025-11-30 Afternoon | Assistant chat + Firestore history shipped (per-task conversations with persona tuning). |
| 2025-11-30 Evening | Manual chat validation (long notes, blocked task, multi-turn logging, persistence, reset). Findings logged in `Autonomous_Chat_and_History_Integration.md`. |
| Next | Wire true Google Sign-In + deployment automation. |

---

## 4. Features Delivered (summary)

1. **Task ingestion & scoring**: Live Smartsheet fetch with per-row warnings, rich `TaskDetail` model, deterministic stubs.
2. **Assist generation**: Anthropic-backed `plan_assist()` with model overrides, prompts, and fallback templates.
3. **CLI workflows**: `list`, `recommend`, `assist`, `schema`, `check-token`, plus `--send-email`, `--anthropic-model`, `--source`.
4. **Gmail automation**: Env-driven account loader (church/personal). Sends email + returns message ID.
5. **Smartsheet feedback**: Auto comment when email sends succeed.
6. **Activity logging**: JSONL/Firestore log capturing each assist (task, account, model, message id, source).
7. **Persistent conversations**: Firestore-backed chat threads per task with REST/React UI, motivational/project-manager persona baked in.
8. **Testing**: Pytest suite covering prioritizer, assistant, Gmail helpers, API (incl. conversation history), and activity logger.

---

## 5. Outstanding Goals

1. **FastAPI backend (Cloud Run)**  
   - Expose REST endpoints for tasks, assists, activity, health.  
   - Share logic with CLI modules.  
   - Pull secrets from env/Secret Manager.

2. **React Web UI (mobile-friendly)**  
   - Task list (grouped, filterable), conversation pane, action buttons.  
   - Show log + Smartsheet comment summaries.

3. **Google OAuth integration**  
   - Use Google Identity for sign-in; restrict to approved accounts.  
   - Verify tokens on backend; pass ID token from frontend.  
   - Handle multi-account Gmail selection (“send via church/personal”).

4. **Deployment automation**  
   - Dockerfile + Cloud Build/GitHub Actions for backend.  
   - Firebase/Cloud Run deploy for frontend.  

5. **Enhancements** (stretch)  
   - Notion/Slack notifications, calendar scheduling, document summarization.  
   - Switch activity log to Firestore for querying.  
   - Multi-user support / role separation.

---

## 6. Implementation Notes & Decisions

- **Schema warnings**: We skip Smartsheet rows with missing required fields and report them via CLI/REST. Fixing data upstream re-enables the row automatically.
- **Anthropic fallback**: If the API key or model fails, we log a note in the AssistPlan, fall back to local templates, and surface the warning in CLI output.
- **Gmail sending**: Each account needs `*_GMAIL_CLIENT_ID/SECRET/REFRESH_TOKEN/ADDRESS` env vars. `*_GMAIL_DEFAULT_TO` provides a fallback recipient when task owners are blank.
 - **Activity log**: Stored in Firestore (`activity_log` collection). CLI/API share the same writer.
- **Smartsheet comments**: Use discussion API rather than sheet “comment” column. Keeps history attached to the row without altering schema.
- **API auth**: FastAPI now enforces Google ID tokens by default. Local dev/testing can set `DTA_DEV_AUTH_BYPASS=1` and pass `X-User-Email`.
- **Conversation store**: Per-task chat history saved to Firestore (`conversations` collection) with file fallback via `DTA_CONVERSATION_FORCE_FILE`.

---

## 7. Working Agreements

- Update this directive whenever we finish a feature, face a major issue, or change course. Keep entries concise; older details can be archived if they bloat the doc.
- Always document:
  1. **Goal** (what/why).  
  2. **Actions taken** (key files/touches).  
  3. **Result** (tests, deploys, issues).  
  4. **Follow-ups** (open questions, next steps).
- Keep sections sorted by recency within each category. Consider rotating “Milestones” and “Outstanding Goals” as we progress.

---

## 8. Next Actions (short list)

1. [x] FastAPI scaffolding (tasks/assist/activity endpoints, auth stub).  
2. [x] React UI scaffold with Google Sign-In + task list/assist/activity panels.  
3. [ ] Decide hosting stack (Cloud Run + Firebase vs. single container) and create deployment scripts.  
4. [ ] Finalize Google OAuth strategy (test users, scopes, token verification refresh flow).  
5. [ ] Connect production Google Sign-In (publish OAuth consent, add testers, wire session refresh).  
6. [ ] Containerize FastAPI backend + deploy to Cloud Run (w/ secrets + service account).  
7. [ ] Configure Firebase Hosting build/deploy hooked to API base URL.  
8. [ ] Smooth task ingestion (auto schema repair, better fallback copy) based on local validation learnings.
9. [ ] Provision Dev/Staging/Prod stacks (Cloud Run + Firebase) with clear promotion flow and cost tracking.  
10. **Autonomous night session (complete)**  
   - ✅ Built FastAPI service with `/health`, `/tasks`, `/assist/{rowId}`, `/activity`.  
   - ✅ Stubbed auth via `X-User-Email`; centralized logging & warnings.  
   - ✅ Added pytest coverage for API/logging paths.  
   - ✅ Documented run instructions + API contract for upcoming React + deployed React scaffold.  
11. **Chat validation pass (2025-11-30)**  
   - ✅ Exercised long-note task, blocked task, multi-turn instructions, persistence, and reset workflows (see `Autonomous_Chat_and_History_Integration.md`).  
   - ⚠️ Template responses still ignore user coaching until Anthropic API access is wired up; track as follow-up.*** End Patch

Update this file after each major step. Keep it lean; archive older milestone details if the doc exceeds ~400 lines.*** End Patch

