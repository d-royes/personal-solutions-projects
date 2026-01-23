"""API Routers Package.

This package contains modular API routers extracted from main.py.
Each router handles a specific domain:

- tasks.py: Task CRUD, list, Firestore operations
- calendar.py: Calendar events, attention, chat
- assist.py: AI assist, planning, chat with tools
- email.py: Email inbox, attention, drafts, chat

Routers are imported and included in main.py via:
    app.include_router(tasks.router, prefix="/tasks", tags=["tasks"])
"""

# Routers will be exported here as they are created
# from .tasks import router as tasks_router
# from .calendar import router as calendar_router
# from .assist import router as assist_router
# from .email import router as email_router

__all__ = [
    # "tasks_router",
    # "calendar_router", 
    # "assist_router",
    # "email_router",
]
