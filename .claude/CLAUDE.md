# Daily Task Assistant (DATA) - Project Instructions

## Project Overview

This is the **Daily Task Assistant (DATA)** project - a FastAPI backend + React frontend application that helps David manage tasks from Smartsheet with AI assistance.

**Repository:** `d-royes/personal-solutions-projects`
**Primary Branch:** `develop`

## Architecture

```
projects/
├── daily-task-assistant/     # FastAPI backend
│   ├── api/main.py           # API endpoints
│   ├── daily_task_assistant/ # Core Python modules
│   │   ├── llm/              # Anthropic integration
│   │   ├── conversations/    # Chat history persistence
│   │   ├── actions/          # Task planning logic
│   │   ├── sheets/           # Google Sheets integration (email rules)
│   │   ├── email/            # Email analysis and suggestions
│   │   └── services/         # Assist workflow orchestration
│   ├── config/smartsheet.yml # Smartsheet schema
│   ├── DATA_PREFERENCES.md   # DATA's behavioral guidelines
│   └── tests/                # pytest unit tests
│
├── web-dashboard/            # React + Vite frontend
│   └── src/
│       ├── App.tsx           # Main application
│       ├── api.ts            # Backend API client
│       ├── components/       # React components
│       │   └── EmailDashboard.tsx  # Email management UI
│       └── auth/             # Google OAuth integration
│
└── e2e-tests/                # Playwright regression tests
    ├── playwright.config.ts  # Multi-browser test config
    └── tests/
        ├── api-health.spec.ts    # Backend API health checks
        ├── tasks/                # Task list & portfolio tests
        └── email/                # Email management tests
```

## Code Style

### Python (Backend)
- **Python 3.11+** with type hints everywhere
- **Dataclasses with `slots=True`** for models
- **Snake_case** for variables and functions
- **Docstrings** on all public functions
- **Pydantic v2** for API request/response models
- Use `from __future__ import annotations` at top of files

### TypeScript (Frontend)
- **Functional components with hooks**
- **CamelCase** for variables, **PascalCase** for components
- **Async/await** for API calls
- **Types in `types.ts`**, API functions in `api.ts`

## Key Files

| File | Purpose |
|------|---------|
| `api/main.py` | All FastAPI endpoints |
| `llm/anthropic_client.py` | Anthropic API integration, system prompts |
| `smartsheet_client.py` | Smartsheet API wrapper |
| `DATA_PREFERENCES.md` | DATA's behavioral guidelines - READ THIS |
| `config/smartsheet.yml` | Column IDs and validation rules |
| `App.tsx` | Main React component, state management |
| `AssistPanel.tsx` | Assistant UI, chat interface |
| `EmailDashboard.tsx` | Email management UI |
| `sheets/filter_rules.py` | Google Sheets email rules integration |
| `email/analyzer.py` | Email pattern detection and suggestions |

## Development Commands

### Starting Dev Servers
```powershell
cd projects/daily-task-assistant
powershell -ExecutionPolicy Bypass -File .\scripts\start-dev.ps1
```
- Backend: http://localhost:8000
- Frontend: http://localhost:5173

### Running Unit Tests
```powershell
cd projects/daily-task-assistant
python -m pytest tests/ -v
```

### Running E2E Tests
```powershell
cd projects/e2e-tests
npm test              # Run all tests headless
npm run test:ui       # Interactive UI mode
npm run test:headed   # Watch browser as tests run
npm run test:chrome   # Chrome only (faster)
```

### Test Categories
```powershell
npm run test:api      # API Health (4 tests)
npm run test:tasks    # Task Management (14 tests)
npm run test:email    # Email Management (14 tests)
```

## Environment Variables

The `.env` file in `projects/daily-task-assistant/` contains:
- `SMARTSHEET_API_TOKEN` - Smartsheet access
- `ANTHROPIC_API_KEY` - Claude API
- `GOOGLE_APPLICATION_CREDENTIALS` - Firestore access
- Gmail OAuth credentials for church/personal accounts

## API Endpoints

- `POST /assist/{task_id}` - Engage with a task (load context)
- `POST /assist/{task_id}/plan` - Generate a plan
- `POST /assist/{task_id}/chat` - Send chat message
- `POST /assist/{task_id}/research` - Web research
- `POST /assist/{task_id}/update` - Update Smartsheet
- `POST /assist/{task_id}/feedback` - Submit feedback
- `GET /feedback/summary` - Get aggregated feedback statistics

## Storage

### Conversation History
- Production: Firestore
- Dev: Local JSON files (set `DTA_CONVERSATION_FORCE_FILE=1`)
- Per-task, cleared when task is marked complete

### Feedback System
- Production: Firestore
- Dev: `feedback_log/feedback.jsonl` (set `DTA_FEEDBACK_FORCE_FILE=1`)

### Authentication
- Production: Google OAuth with ID token verification
- Dev: Set `DTA_DEV_AUTH_BYPASS=1` and use `X-User-Email` header

## Boundaries

### Do
- Write tests for new backend functionality
- Run `npx tsc --noEmit` before committing frontend changes
- Update `DATA_PREFERENCES.md` when changing DATA's behavior
- Commit at logical checkpoints with descriptive messages
- Run E2E tests after significant UI or API changes
- Add E2E tests when building new user-facing features

### Ask First
- Changes to Smartsheet schema (`config/smartsheet.yml`)
- New API endpoints that modify external data
- Changes to authentication flow
- UI/UX changes - present plans for approval before implementing

### Don't
- Hardcode API keys or secrets
- Skip tests for Smartsheet write operations
- Change DATA's personality without updating preferences file
- Deploy to production without user approval
- Skip regression tests before merging to staging/main

## Common Workflows

### Adding a New DATA Capability
1. Define the tool in `llm/anthropic_client.py`
2. Add endpoint in `api/main.py`
3. Add frontend API function in `api.ts`
4. Update UI in `AssistPanel.tsx`
5. Document in `DATA_PREFERENCES.md`
6. Write tests

### Fixing DATA's Response Behavior
1. Check `DATA_PREFERENCES.md` for expected behavior
2. Update system prompt in `anthropic_client.py`
3. Add example to preferences file
4. Test with real conversation

### Conducting a Tuning Session
1. Pull feedback summary: `GET /feedback/summary?days=30`
2. Review `needs_work` patterns
3. Update `DATA_PREFERENCES.md` with new examples or anti-patterns
4. Adjust system prompts in `anthropic_client.py` if needed
5. Track `helpfulRate` over time
6. Document changes in version history

### Adding Smartsheet Field Support
1. Get column ID from Smartsheet API
2. Add to `config/smartsheet.yml`
3. Update `SmartsheetClient` if needed
4. Add validation in API endpoint

## Git Workflow

- **Primary branch:** `develop`
- **Commit style:** `type(scope): description` (feat, fix, docs, test, security)
- Push after each logical milestone
- Create restore points before major changes
- PR to `main` for production releases

## Project Documentation

- `BACKLOG.md` - Feature backlog and known issues
- `CHANGELOG.md` - Version history (Keep a Changelog format)
- `DATA_PREFERENCES.md` - DATA's behavioral guidelines
- `docs/DATA_CLOUD_VISION.md` - Product roadmap
- `docs/Gap_Analysis_Conversation_Review.md` - UX improvement ideas

## Resources

- [Smartsheet API Docs](https://smartsheet.redoc.ly/)
- [Anthropic API Docs](https://docs.anthropic.com/)
- [FastAPI Docs](https://fastapi.tiangolo.com/)
- [Playwright Docs](https://playwright.dev/)
