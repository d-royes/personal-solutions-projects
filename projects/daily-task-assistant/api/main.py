"""FastAPI service for Daily Task Assistant."""
from __future__ import annotations

import os
from dataclasses import asdict
from functools import lru_cache
from typing import Any, Dict, List, Literal, Optional
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from daily_task_assistant.api.auth import get_current_user
from daily_task_assistant.config import load_settings
from daily_task_assistant.conversations import (
    build_plan_summary,
    clear_conversation,
    fetch_conversation,
    log_assistant_message,
    log_user_message,
)
from daily_task_assistant.dataset import fetch_tasks as fetch_task_dataset
from daily_task_assistant.logs import fetch_activity_entries
from daily_task_assistant.services import execute_assist
from daily_task_assistant.tasks import TaskDetail


app = FastAPI(
    title="Daily Task Assistant API",
    version="0.1.0",
    description="REST interface powering the upcoming web dashboard.",
)

ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    os.getenv("DTA_ALLOWED_FRONTEND", "").strip(),
]
origins = [origin for origin in ALLOWED_ORIGINS if origin]

if origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


@lru_cache
def _get_settings():
    return load_settings()


def serialize_task(task: TaskDetail) -> dict:
    return {
        "rowId": task.row_id,
        "title": task.title,
        "status": task.status,
        "due": task.due.isoformat(),
        "priority": task.priority,
        "project": task.project,
        "assignedTo": task.assigned_to,
        "estimatedHours": task.estimated_hours,
        "notes": task.notes,
        "nextStep": task.next_step,
        "automationHint": task.automation_hint,
    }


def serialize_plan(result: AssistExecutionResult) -> dict:
    plan = result.plan
    return {
        "summary": plan.summary,
        "score": plan.score,
        "labels": plan.labels,
        "automationTriggers": plan.automation_triggers,
        "nextSteps": plan.next_steps,
        "efficiencyTips": plan.efficiency_tips,
        "emailDraft": plan.email_draft,
        "task": serialize_task(plan.task),
        "generator": plan.generator,
        "generatorNotes": plan.generator_notes,
        "messageId": result.message_id,
        "commentPosted": result.comment_posted,
        "warnings": result.warnings,
    }


class AssistRequest(BaseModel):
    source: Literal["auto", "live", "stub"] = "auto"
    limit: int = 50
    anthropic_model: Optional[str] = Field(
        None, alias="anthropicModel", description="Override Anthropic model name."
    )
    send_email_account: Optional[str] = Field(
        None,
        alias="sendEmailAccount",
        description="Gmail account prefix to send email (e.g., 'church').",
    )
    instructions: Optional[str] = None
    reset_conversation: bool = Field(
        False,
        alias="resetConversation",
        description="If true, clears stored conversation history before running assist.",
    )


class ConversationMessageModel(BaseModel):
    role: Literal["user", "assistant"]
    content: str
    ts: datetime
    metadata: Dict[str, Any] = Field(default_factory=dict)
    plan: Optional[Dict[str, Any]] = None
    send_email_account: Optional[str] = Field(
        None,
        alias="sendEmailAccount",
        description="Gmail account prefix to send email (e.g., 'church').",
    )


@app.get("/health")
def health_check() -> dict:
    settings = _get_settings()
    return {
        "status": "ok",
        "time": datetime.now(timezone.utc).isoformat(),
        "environment": settings.environment,
    }


@app.get("/tasks")
def list_tasks(
    source: Literal["auto", "live", "stub"] = Query("auto"),
    limit: int = Query(5, ge=1, le=50),
    user: str = Depends(get_current_user),
) -> dict:
    tasks, live_tasks, settings, warning = fetch_task_dataset(
    limit=limit, source=source
    )
    return {
        "tasks": [serialize_task(task) for task in tasks],
        "liveTasks": live_tasks,
        "environment": settings.environment,
        "warning": warning,
    }


@app.post("/assist/{task_id}")
def assist_task(
    task_id: str,
    request: AssistRequest,
    user: str = Depends(get_current_user),
) -> dict:
    tasks, live_tasks, settings, warning = fetch_task_dataset(
        limit=request.limit, source=request.source
    )
    target = next((task for task in tasks if task.row_id == task_id), None)
    if not target:
        raise HTTPException(status_code=404, detail="Task not found.")

    if request.reset_conversation:
        clear_conversation(task_id)

    history = fetch_conversation(task_id, limit=100)

    llm_history: List[Dict[str, str]] = [
        {"role": msg.role, "content": msg.content} for msg in history
    ]

    instructions = (request.instructions or "").strip()
    if instructions:
        user_turn = log_user_message(
            task_id,
            content=instructions,
            user_email=user,
            metadata={"source": request.source},
        )
        history = history + [user_turn]
        llm_history.append({"role": "user", "content": instructions})

    result = execute_assist(
        task=target,
        settings=settings,
        source=request.source,
        anthropic_model=request.anthropic_model,
        send_email_account=request.send_email_account,
        live_tasks=live_tasks,
        conversation_history=llm_history if llm_history else None,
    )

    assistant_turn = log_assistant_message(
        task_id,
        content=build_plan_summary(result.plan),
        plan=result.plan,
        metadata={
            "warnings": result.warnings,
            "anthropic_model": request.anthropic_model,
        },
    )
    history = history + [assistant_turn]

    response = {
        "plan": serialize_plan(result),
        "environment": settings.environment,
        "liveTasks": live_tasks,
        "warning": warning,
        "history": [
            ConversationMessageModel(**asdict(msg)).model_dump()
            for msg in history
        ],
    }
    return response


@app.get("/assist/{task_id}/history")
def get_conversation_history(
    task_id: str,
    limit: int = Query(100, ge=1, le=200),
    user: str = Depends(get_current_user),
) -> List[ConversationMessageModel]:
    history = fetch_conversation(task_id, limit=limit)
    return [ConversationMessageModel(**asdict(msg)) for msg in history]


@app.get("/activity")
def activity_feed(
    limit: int = Query(50, ge=1, le=200),
    user: str = Depends(get_current_user),
) -> dict:
    entries = fetch_activity_entries(limit)
    return {"entries": entries, "count": len(entries)}

