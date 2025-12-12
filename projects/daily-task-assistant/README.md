# Daily Task Assistant

A companion service that regularly pulls prioritized tasks from the Task Management Smartsheet and proactively assists with execution/delivery. The assistant combines data ingestion, context enrichment, and automation workflows so that high-priority items are unblocked as quickly as possible.

## Objectives
- Mirror the user's Smartsheet task list locally with rich metadata (owners, due dates, blockers, assets).
- Classify tasks by effort, risk, dependency, and automation potential to recommend next actions.
- Offer hands-on assistance (drafting emails, preparing documents, scheduling follow-ups) where automation is feasible.
- Surface concise summaries and action plans through chat or dashboard interfaces.

## Data Source & Sync Plan
1. **Connector**: Poll the Smartsheet REST API using a dedicated access token scoped to the Task Management sheet. Support incremental sync via `modifiedSince` timestamps.
2. **Normalization**: Map Smartsheet columns (Task, Status, Owner, Due Date, Notes, Attachments) to an internal schema stored in a local SQLite/Parquet cache for quick querying.
3. **Change Detection**: Emit events when new tasks arrive, deadlines change, or blockers are added. These events kick off downstream automation.
4. **Security**: Store Smartsheet credentials in `.env` / secret manager; never commit.

### Secrets & Environment
- Cursor web secret `Smartsheet` should be injected as the runtime token (e.g., export `SMARTSHEET_API_TOKEN=$(cursor secrets get Smartsheet)` before running jobs).
- Local `.env` entries should reference `SMARTSHEET_API_TOKEN` only; never persist raw tokens in repo files.
- When running in CI or other environments, configure the same `Smartsheet` secret or equivalent secure store entry with least-privilege scope.

## Core Capability Roadmap
- **Intake Pipeline**: Background worker that syncs every 5 minutes and tags tasks needing attention.
- **Prioritization Engine**: Heuristics (deadline proximity, status stalled > 48h, blocker notes) combined with optional LLM scoring for ambiguity.
- **Assistance Library**: Reusable actions (draft communication, create Jira tickets, prep meeting agendas, summarize attachments) orchestrated via prompt templates and external APIs.
- **Progress Tracking**: Update Smartsheet rows (comments or status) when automations complete to keep humans in the loop.
- **Interface**: CLI/chat endpoint plus optional lightweight web UI for reviewing queued assists.

## Proposed Architecture
- `sync/collector` — handles Smartsheet API calls, pagination, and caching.
- `analysis/prioritizer` — ranks tasks, identifies blocking dependencies, and chooses assist strategies.
- `actions/` — modular executors for outbound emails, document drafting, scheduling, etc.
- `interfaces/` — adapters for CLI, chat, or future Notion/Slack integrations.
- `storage/` — persistence layer (SQLite now; can upgrade to Postgres + Redis for scale).

## Next Steps
1. Define the Smartsheet schema + column IDs in `config/smartsheet.yml`.
2. Scaffold the sync worker (likely Python FastAPI + Celery/APS) with local cache.
3. Draft a minimal CLI that lists tasks needing assistance and suggests one automated action each.
4. Add integration tests that mock Smartsheet responses to validate the sync + prioritization pipeline.

This README will evolve as components land; the first milestone is establishing reliable Smartsheet ingestion plus a CLI prototype that proves out automated assistance on real tasks.

## Prerequisites & Environment

1. Python 3.10+.
2. Install dependencies:
   ```bash
   pip install -r projects/daily-task-assistant/requirements.txt
   ```
3. Provide the Smartsheet API token (Cursor can inject the `Smartsheet` secret):
   ```bash
   export SMARTSHEET_API_TOKEN=$(cursor secrets get Smartsheet)
   ```
4. (Optional) Provide an Anthropic key + preferred model:
   ```bash
   export ANTHROPIC_API_KEY=sk-ant-***
   export ANTHROPIC_MODEL=claude-3-opus-20240229  # defaults to Opus if unset
   ```

## CLI Toolkit

All commands live in `projects/daily-task-assistant/cli.py`. Use `--source stub|auto|live` to control the data source (default `auto` prefers live but falls back to stubbed tasks with a warning).

| Command | Purpose |
| --- | --- |
| `list` | Shows prioritized tasks, score/label highlights, and automation ideas. |
| `recommend` | Summarizes the top *n* tasks (default 3) with suggested AI actions and email previews. |
| `assist <task_id>` | Generates a full assist bundle (next steps, efficiency tips, email draft) for a specific task. Pass `--send-email <account>` to email the draft via Gmail. |
| `check-token` | Confirms the Smartsheet token is configured. |
| `schema` | Validates the YAML schema and flags placeholder column IDs. |
| `--anthropic-model MODEL` (assist / recommend / chat CLI) | Overrides the Anthropics model for that run. Defaults to `ANTHROPIC_MODEL` env var or Opus. |

Examples:

```bash
python projects/daily-task-assistant/cli.py list --limit 5
python projects/daily-task-assistant/cli.py recommend --limit 3 --source stub
python projects/daily-task-assistant/cli.py assist 1002 --source stub --anthropic-model claude-3-sonnet-20240229 --send-email church
python projects/daily-task-assistant/cli.py schema
```

## Interactive Chat Prototype

An experimental split-view CLI lives at `daily_task_assistant/interfaces/chat_cli.py`. It lists ranked tasks on the left and opens a conversational assistant pane on the right after you select a task.

```bash
cd projects/daily-task-assistant
PYTHONPATH=. python -m daily_task_assistant.interfaces.chat_cli --limit 10 --anthropic-model claude-3-haiku-20240307
```

(When running from the repo root, prefix the command with `PYTHONPATH=projects/daily-task-assistant`.)

## Prompts & AI Actions

Reusable prompt templates live in `projects/daily-task-assistant/prompts/`. The assistant module (`daily_task_assistant/actions/assistant.py`) currently renders deterministic drafts from these templates so flows can be validated without a live LLM. Swap the renderer with a real LLM call when secrets are ready.

## Gmail Sending (optional)

To enable automated sends (e.g., for the church account) create an OAuth client, generate a refresh token, and add these environment variables:

```
CHURCH_GMAIL_CLIENT_ID=...
CHURCH_GMAIL_CLIENT_SECRET=...
CHURCH_GMAIL_REFRESH_TOKEN=...
CHURCH_GMAIL_ADDRESS=you@church.org
# Optional fallback recipient the assistant can use if a task lacks an email:
CHURCH_GMAIL_DEFAULT_TO=assistant@church.org
```

Then run:

```
python projects/daily-task-assistant/cli.py assist 1002 --source live --send-email church
```

Future accounts (e.g., personal Gmail) can use the same pattern with a different prefix, such as `PERSONAL_GMAIL_CLIENT_ID`.

## Email Management (Chief of Staff Model)

DATA includes email management capabilities that work with Google Apps Script to automate email labeling. This follows a "Chief of Staff" model where:

1. **Apps Script** handles clear-cut, rule-based email labeling (runs every 15 minutes)
2. **DATA** analyzes patterns, suggests new rules, and handles nuanced categorization
3. **Google Sheets** serves as the shared rules database

### Email Filter Rules

Rules are stored in a Google Sheet (`Gmail_Filter_Index`) with columns:
- `Email` - Which account the rule applies to
- `Filter Category` - Target label (Personal, Promotional, Transactional, etc.)
- `Filter Field` - What to match (Sender Email Address, Email Subject, Sender Name)
- `Operator` - Match type (Contains, Equals)
- `Value` - Pattern to match
- `Action` - What to do (Apply label, Remove, Trash)

### API Endpoints for Email Management

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/email/inbox` | GET | Get inbox summary for an account |
| `/email/rules` | GET | List filter rules from Google Sheets |
| `/email/rules` | POST | Add a new filter rule |
| `/email/rules/{id}` | DELETE | Remove a filter rule |
| `/email/analyze` | POST | Analyze inbox for patterns and suggestions |
| `/email/sync` | POST | Sync rules to Google Sheets |

### Supported Email Accounts

Configure in `.env`:
```
# Personal Gmail
PERSONAL_GMAIL_CLIENT_ID=...
PERSONAL_GMAIL_CLIENT_SECRET=...
PERSONAL_GMAIL_REFRESH_TOKEN=...
PERSONAL_GMAIL_ADDRESS=your@gmail.com

# Church Gmail
CHURCH_GMAIL_CLIENT_ID=...
CHURCH_GMAIL_CLIENT_SECRET=...
CHURCH_GMAIL_REFRESH_TOKEN=...
CHURCH_GMAIL_ADDRESS=you@church.org
```

## FastAPI Service

The `api/main.py` module exposes the same capabilities over HTTP (used by the upcoming React dashboard). Run locally with:

```bash
cd projects/daily-task-assistant
PYTHONPATH=. uvicorn api.main:app --reload
```

Scripts for convenience:

- `scripts/start-dev.ps1` – launches uvicorn (with `DTA_DEV_AUTH_BYPASS=1`) and the React dev server in separate windows.
- `scripts/stop-dev.ps1` – stops anything bound to ports 8000/5173 to avoid port conflicts.

### Auth

- Production: send a Google ID token in the `Authorization: Bearer <token>` header. Configure the backend with `GOOGLE_OAUTH_CLIENT_ID` (or `GOOGLE_OAUTH_AUDIENCE` for multiple audiences).  
- Local dev/testing: set `DTA_DEV_AUTH_BYPASS=1` and supply `X-User-Email` to simulate an authenticated user.

### Endpoints:

| Endpoint | Method | Description |
| --- | --- | --- |
| `/health` | GET | Basic status check. |
| `/tasks?source=auto&limit=5` | GET | Returns prioritized tasks plus metadata. |
| `/assist/{rowId}` | POST | Runs the assist workflow; request body supports `source`, `anthropicModel`, `sendEmailAccount`, and conversational `instructions`. Returns the refreshed plan plus chat history. |
| `/assist/{rowId}/history` | GET | Retrieves the stored conversation thread for that task (most recent 100 turns). |
| `/activity?limit=50` | GET | Returns recent entries from the activity log. |

The API reuses the same workflows as the CLI, including Gmail sending, Smartsheet comments, and activity logging.

## Activity Log & Conversation Store

Every accepted assist is appended to the Firestore collection `activity_log`. Make sure Application Default Credentials are available (e.g., set `GOOGLE_APPLICATION_CREDENTIALS` locally, or rely on the Cloud Run service account in production). During local development you can bypass Firestore by setting `DTA_ACTIVITY_FORCE_FILE=1`, which writes to `activity_log.jsonl` (or `DTA_ACTIVITY_LOG` if provided). Each entry captures timestamp, task details, selected Gmail account, message ID, Anthropics model, and whether live or stub data was used. Smartsheet comments are also posted automatically whenever an email is sent successfully.

Conversational history is stored per task under the Firestore collection `conversations`. Use `DTA_CONVERSATION_FORCE_FILE=1` (and optionally `DTA_CONVERSATION_DIR`) to keep history in local JSONL files during development.

## Deployment

### Live Environments

| Environment | Frontend | Backend |
|-------------|----------|---------|
| **Production** | https://daily-task-assistant-prod.web.app | https://daily-task-assistant-prod-368257400464.us-central1.run.app |
| **Staging** | https://daily-task-assistant-church.web.app | https://daily-task-assistant-staging-368257400464.us-central1.run.app |

### CI/CD Pipeline (Recommended)

Deployments are automated via GitHub Actions:

1. **Develop** → Push to `develop` branch, tests run automatically
2. **Staging** → Create PR from `develop` to `staging`, merge to deploy
3. **Production** → Create PR from `staging` to `main`, approve and merge to deploy

See [`docs/CI_CD_Setup.md`](docs/CI_CD_Setup.md) for complete setup instructions.

### Manual Deployment (Legacy)

#### Backend (Cloud Run)

1. **Build and push container**
   ```bash
   cd projects/daily-task-assistant
   gcloud builds submit --tag gcr.io/PROJECT_ID/daily-task-assistant-api
   ```
2. **Deploy to Cloud Run**
   ```bash
   gcloud run deploy daily-task-assistant-api \
     --image gcr.io/PROJECT_ID/daily-task-assistant-api \
     --region us-central1 \
     --service-account daily-task-assistant-backend@PROJECT_ID.iam.gserviceaccount.com \
     --allow-unauthenticated \
     --set-env-vars GOOGLE_OAUTH_CLIENT_ID=XXX,GOOGLE_OAUTH_AUDIENCE=XXX \
     --set-secrets SMARTSHEET_API_TOKEN=SMARTSHEET_API_TOKEN:latest,ANTHROPIC_API_TOKEN=ANTHROPIC_API_TOKEN:latest
   ```
   Supply any other env vars (e.g., `DTA_ENV`, Gmail config) via `--set-env-vars` or Secret Manager. The attached service account must have Firestore + Secret access.

#### Frontend (Firebase Hosting)

1. Build the React dashboard:
   ```bash
   cd projects/web-dashboard
   npm install
   npm run build
   ```
2. Deploy to Firebase Hosting (after `firebase init hosting` once):
   ```bash
   firebase deploy
   ```
   Configure `VITE_API_BASE_URL` to the Cloud Run URL via `.env.production` or Firebase config so the SPA calls the backend.

## Web Dashboard (React)

The React prototype lives in `projects/web-dashboard` (scaffolded with Vite + TypeScript). It consumes the FastAPI endpoints and provides:

- Google Sign-In (with optional developer bypass).
- Task list with status indicators.
- Assist panel (run assist, pick Gmail account, review drafts).
- Conversational chat thread (coach the assistant, iterate on drafts, view prior context).
- Activity feed viewer.

Local dev workflow:

```bash
cd projects/web-dashboard
npm install
npm run dev  # defaults to http://localhost:5173
```

Environment hints (optional):

```
# .env.local
VITE_API_BASE_URL=http://localhost:8000
VITE_API_DEFAULT_SOURCE=auto
VITE_DEV_USER_EMAIL=you@example.com
VITE_GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
VITE_DEV_AUTH_ENABLED=1
```

When using the dev auth bypass, set `DTA_DEV_AUTH_BYPASS=1` on the API server. With a real Google client ID configured, sign in normally and the UI will forward the resulting ID token automatically.

## Testing

### Unit Tests (Python)

Unit tests cover the prioritizer heuristics, assistant planning logic, email analyzer, and filter rules. Run them from the repo root:

```bash
cd projects/daily-task-assistant
PYTHONPATH=. pytest
```

The suite does not call external APIs and can run with stub data only.

### E2E Regression Tests (Playwright)

End-to-end tests validate the full application stack (frontend + backend) using real browser automation. The test suite lives in `projects/e2e-tests/`.

#### Quick Start

```bash
cd projects/e2e-tests
npm install                  # First time only
npm test                     # Run all tests headless
npm run test:ui              # Interactive UI mode (recommended)
npm run test:headed          # Watch browser as tests run
```

#### Test Coverage

| Area | Tests | Description |
|------|-------|-------------|
| API Health | 4 | Backend connectivity, endpoint responses |
| Task List | 9 | Task loading, filters, search, refresh |
| Portfolio View | 5 | Category tabs, Quick Question, chat input |
| Email Dashboard | 5 | Mode switching, navigation tabs |
| Email Rules | 7 | Rules table, filtering, search, add/delete |
| Account Switching | 2 | Personal/Church account toggle |

#### When to Run E2E Tests

- **Before merging to staging/main**: Run the full suite to catch regressions
- **After UI changes**: Run targeted tests (`npm run test:tasks` or `npm run test:email`)
- **After API changes**: Run API health checks (`npm run test:api`)
- **Building new features**: Use codegen to record tests (`npm run codegen`)

#### Generating New Tests

Playwright can record your browser interactions:

```bash
npm run codegen   # Opens browser, generates code as you click
```

#### Viewing Test Reports

After running tests, view the HTML report:

```bash
npm run report
```

Screenshots and videos are captured automatically on test failures.
