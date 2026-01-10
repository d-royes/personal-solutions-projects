# Daily Task Assistant (DATA) - Project Instructions

## CRITICAL: Backend Restart Protocol (Windows)

**ALWAYS use `reset-backend.ps1` after ANY backend code changes.**

### Why This Matters

On Windows, uvicorn's `--reload` flag does NOT reliably kill child processes. When the parent uvicorn process is killed:
- Child worker processes can become **orphaned**
- These orphans continue serving **OLD CODE**
- The port shows as "in use" but `taskkill` can't find the process
- You end up debugging issues that were "already fixed"

This has caused significant time waste in this project - fixing the same bug multiple times because orphaned processes served stale code.

### References
- [FastAPI server stuck on Windows](https://rolisz.ro/2024/fastapi-server-stuck-on-windows/)
- [Uvicorn Issue #2289](https://github.com/Kludex/uvicorn/issues/2289)

### The Solution

```powershell
# From daily-task-assistant directory:
powershell -ExecutionPolicy Bypass -File scripts/reset-backend.ps1
```

The script:
1. Uses `taskkill /T /F` to kill entire process trees (not just parent)
2. Hunts for orphaned Python processes whose parents died
3. Verifies the port is clear before starting new server
4. Starts uvicorn in a new PowerShell window

### When to Use

**ALWAYS after:**
- Editing ANY Python file in `daily_task_assistant/` or `api/`
- When behavior doesn't match your code changes
- When debugging seems to lead in circles
- Before testing any fix

**Signs of orphaned process issues:**
- Debug print statements not appearing
- Old behavior persists after code changes
- `netstat` shows multiple PIDs on port 8000
- Some PIDs in netstat don't exist in `tasklist`

---

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
│   │   ├── calendar/         # Calendar chat functionality
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
│       └── components/       # React components
│
└── e2e-tests/                # Playwright regression tests
```

## Development Commands

### Starting Dev Servers
```powershell
cd projects/daily-task-assistant
powershell -ExecutionPolicy Bypass -File .\scripts\start-dev.ps1
```
- Backend: http://localhost:8000
- Frontend: http://localhost:5173

### Resetting Backend (CRITICAL - USE THIS!)
```powershell
cd projects/daily-task-assistant
powershell -ExecutionPolicy Bypass -File scripts/reset-backend.ps1
```

### Running Tests
```powershell
# Unit tests
python -m pytest tests/ -v

# E2E tests
cd projects/e2e-tests
npm test
```

## Key Files

| File | Purpose |
|------|---------|
| `api/main.py` | All FastAPI endpoints |
| `llm/anthropic_client.py` | Anthropic API integration, system prompts |
| `calendar/context.py` | Calendar context builder for DATA |
| `calendar/chat.py` | Calendar chat handler |
| `DATA_PREFERENCES.md` | DATA's behavioral guidelines |

## Recent Work: Calendar Chat

Calendar chat was activated for DATA with:
- Task filtering respecting "Days to Show" setting
- Proper date handling (local dates, not UTC conversion)
- Domain-based conversation persistence
- Event and task context in DATA prompts

**Important:** Task due dates are LOCAL dates. A due date of `2026-01-06T00:00:00` means "January 6th" in David's timezone, NOT midnight UTC (which would show as Jan 5th EST).
