"""API Routers Package.

This package contains modular API routers extracted from main.py as part of
the backend API refactoring initiative. Each router handles a specific domain.

Routers (all completed):
- tasks.py: Task CRUD, list, Firestore tasks, recurring tasks (~500 lines, 13 endpoints)
- calendar.py: Calendar events, settings, attention, chat (~800 lines, 19 endpoints)
- assist.py: AI assist, planning, chat, workspace, feedback (~1000 lines, 20 endpoints)
- email.py: Inbox, attention, drafts, chat, haiku, memory (~1200 lines, 56 endpoints)

Additionally, separate routers for sync and work badge are exported from tasks.py:
- sync_router: /sync/* endpoints for task synchronization
- work_router: /work/* endpoints for badge counts

Usage in main.py:
    from api.routers import tasks_router, sync_router, work_router, calendar_router, assist_router, email_router
    
    app.include_router(tasks_router, prefix="/tasks", tags=["tasks"])
    app.include_router(sync_router, prefix="/sync", tags=["sync"])
    app.include_router(work_router, prefix="/work", tags=["work"])
    app.include_router(calendar_router, prefix="/calendar", tags=["calendar"])
    app.include_router(assist_router, prefix="/assist", tags=["assist"])
    app.include_router(email_router, tags=["email"])  # No prefix - paths include /inbox and /email

Note: Original endpoints in main.py still exist (causing duplicate warnings).
These will be removed incrementally as each router is validated in production.
"""

from .tasks import router as tasks_router
from .tasks import sync_router
from .tasks import work_router
from .calendar import router as calendar_router
from .assist import router as assist_router
from .email import router as email_router

__all__ = [
    "tasks_router",
    "sync_router",
    "work_router",
    "calendar_router", 
    "assist_router",
    "email_router",
]
