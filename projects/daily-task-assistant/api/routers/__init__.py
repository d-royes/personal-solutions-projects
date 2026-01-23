"""API Routers Package.

This package contains modular API routers extracted from main.py.
Each router handles a specific domain:

- tasks.py: Task CRUD, list, Firestore operations, sync, work badge
- calendar.py: Calendar events, attention, chat (TODO)
- assist.py: AI assist, planning, chat with tools (TODO)
- email.py: Email inbox, attention, drafts, chat (TODO)

Routers are imported and included in main.py via:
    app.include_router(tasks_router, prefix="/tasks", tags=["tasks"])
"""

from .tasks import router as tasks_router
from .tasks import sync_router
from .tasks import work_router

# Future routers (uncomment as they are created)
# from .calendar import router as calendar_router
# from .assist import router as assist_router
# from .email import router as email_router

__all__ = [
    "tasks_router",
    "sync_router",
    "work_router",
    # "calendar_router", 
    # "assist_router",
    # "email_router",
]
