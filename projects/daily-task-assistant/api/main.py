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
        "suggestedActions": plan.suggested_actions,
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
    limit: Optional[int] = Query(None, ge=1, le=500),
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
    """Load task context and conversation history. Does NOT generate a plan automatically.
    
    Use /assist/{task_id}/plan to generate or update the plan.
    Use /assist/{task_id}/chat for conversational messages.
    """
    from daily_task_assistant.conversations.history import get_latest_plan
    
    tasks, live_tasks, settings, warning = fetch_task_dataset(
        limit=request.limit, source=request.source
    )
    target = next((task for task in tasks if task.row_id == task_id), None)
    if not target:
        raise HTTPException(status_code=404, detail="Task not found.")

    if request.reset_conversation:
        clear_conversation(task_id)

    history = fetch_conversation(task_id, limit=100)
    
    # Retrieve the latest plan from conversation history (if any)
    latest_plan = get_latest_plan(task_id)

    # Build plan response object if we have a saved plan
    plan_response = None
    if latest_plan:
        plan_response = {
            "summary": latest_plan.get("summary", ""),
            "score": 0,
            "labels": latest_plan.get("labels", []),
            "automationTriggers": [],
            "nextSteps": latest_plan.get("next_steps", []),
            "efficiencyTips": latest_plan.get("efficiency_tips", []),
            "suggestedActions": latest_plan.get("suggested_actions", ["plan", "research", "draft_email", "follow_up"]),
            "task": serialize_task(target),
            "generator": "history",
            "generatorNotes": [],
            "generatedAt": latest_plan.get("generatedAt"),
        }

    response = {
        "plan": plan_response,  # Return saved plan if available
        "environment": settings.environment,
        "liveTasks": live_tasks,
        "warning": warning,
        "history": [
            ConversationMessageModel(**asdict(msg)).model_dump()
            for msg in history
        ],
    }
    return response


class PlanRequest(BaseModel):
    """Request body for plan generation."""
    source: Literal["auto", "live", "stub"] = "auto"
    anthropic_model: Optional[str] = Field(
        None, alias="anthropicModel", description="Override Anthropic model name."
    )


@app.post("/assist/{task_id}/plan")
def generate_plan(
    task_id: str,
    request: PlanRequest,
    user: str = Depends(get_current_user),
) -> dict:
    """Generate or update the plan for a task, considering conversation history.
    
    This is triggered explicitly by the user clicking the 'Plan' action button.
    The plan is stored in conversation history for persistence across sessions.
    """
    tasks, live_tasks, settings, warning = fetch_task_dataset(
        limit=None, source=request.source
    )
    target = next((task for task in tasks if task.row_id == task_id), None)
    if not target:
        raise HTTPException(status_code=404, detail="Task not found.")

    # Fetch conversation history to include in plan consideration
    history = fetch_conversation(task_id, limit=100)
    llm_history: List[Dict[str, str]] = [
        {"role": msg.role, "content": msg.content} for msg in history
    ]

    result = execute_assist(
        task=target,
        settings=settings,
        source=request.source,
        anthropic_model=request.anthropic_model,
        send_email_account=None,
        live_tasks=live_tasks,
        conversation_history=llm_history if llm_history else None,
    )

    # Log the plan to conversation history for persistence
    # This allows the plan to be retrieved when reopening the task
    log_assistant_message(
        task_id,
        content=build_plan_summary(result.plan),
        plan=result.plan,
        metadata={"source": "plan", "generator": result.plan.generator},
    )

    return {
        "plan": serialize_plan(result),
        "environment": settings.environment,
        "liveTasks": live_tasks,
        "warning": warning,
    }


@app.get("/assist/{task_id}/history")
def get_conversation_history(
    task_id: str,
    limit: int = Query(100, ge=1, le=200),
    user: str = Depends(get_current_user),
) -> List[ConversationMessageModel]:
    history = fetch_conversation(task_id, limit=limit)
    return [ConversationMessageModel(**asdict(msg)) for msg in history]


class ChatRequest(BaseModel):
    """Request body for chat endpoint."""
    message: str = Field(..., description="The user's message")
    source: Literal["auto", "live", "stub"] = "auto"


@app.post("/assist/{task_id}/chat")
def chat_with_task(
    task_id: str,
    request: ChatRequest,
    user: str = Depends(get_current_user),
) -> dict:
    """Send a conversational message about a task and get a response from DATA.
    
    If DATA detects a task update intent, returns a pending_action that the
    frontend can use to show a confirmation dialog.
    """
    from daily_task_assistant.llm.anthropic_client import chat_with_tools, AnthropicError

    tasks, live_tasks, settings, warning = fetch_task_dataset(
        limit=None, source=request.source
    )
    target = next((task for task in tasks if task.row_id == task_id), None)
    if not target:
        raise HTTPException(status_code=404, detail="Task not found.")

    # Fetch existing conversation history
    history = fetch_conversation(task_id, limit=50)
    
    # Log the user message
    user_turn = log_user_message(
        task_id,
        content=request.message,
        user_email=user,
        metadata={"source": request.source},
    )

    # Build history for LLM (excluding the message we just logged)
    llm_history: List[Dict[str, str]] = [
        {"role": msg.role, "content": msg.content} for msg in history
    ]

    # Call Anthropic with tool support for task updates
    try:
        chat_response = chat_with_tools(
            task=target,
            user_message=request.message,
            history=llm_history,
        )
    except AnthropicError as exc:
        raise HTTPException(status_code=502, detail=f"AI service error: {exc}")

    # Log the assistant response
    assistant_turn = log_assistant_message(
        task_id,
        content=chat_response.message,
        plan=None,  # No structured plan for chat responses
        metadata={
            "source": "chat",
            "has_pending_action": chat_response.pending_action is not None,
        },
    )

    # Fetch updated history
    updated_history = fetch_conversation(task_id, limit=100)

    # Build response
    response_data = {
        "response": chat_response.message,
        "history": [
            ConversationMessageModel(**asdict(msg)).model_dump()
            for msg in updated_history
        ],
    }
    
    # Include pending action if DATA detected an update intent
    if chat_response.pending_action:
        action = chat_response.pending_action
        response_data["pendingAction"] = {
            "action": action.action,
            "status": action.status,
            "priority": action.priority,
            "dueDate": action.due_date,
            "comment": action.comment,
            "reason": action.reason,
        }

    return response_data


class ResearchRequest(BaseModel):
    """Request body for research endpoint."""
    source: Literal["auto", "live", "stub"] = "auto"
    next_steps: Optional[List[str]] = Field(
        None, description="Optional next steps to inform the research"
    )


def _summarize_research(full_research: str, max_length: int = 200) -> str:
    """Extract a brief summary from research results for conversation history."""
    # Try to extract just the key findings section
    lines = full_research.split('\n')
    summary_lines = []
    in_key_findings = False
    
    for line in lines:
        if '## Key Findings' in line or '**Key Findings**' in line:
            in_key_findings = True
            continue
        if in_key_findings:
            if line.startswith('##') or line.startswith('**Action') or line.startswith('**Sources'):
                break
            if line.strip().startswith('-') or line.strip().startswith('•'):
                # Clean up the bullet point
                clean_line = line.strip().lstrip('-•').strip()
                if clean_line:
                    summary_lines.append(clean_line)
                    if len(summary_lines) >= 3:  # Max 3 key points
                        break
    
    if summary_lines:
        summary = "; ".join(summary_lines)
        if len(summary) > max_length:
            summary = summary[:max_length-3] + "..."
        return f"🔍 **Research completed**: {summary}"
    
    # Fallback: just truncate the beginning
    truncated = full_research[:max_length-3].rsplit(' ', 1)[0] + "..."
    return f"🔍 **Research completed**: {truncated}"


@app.post("/assist/{task_id}/research")
def research_task_endpoint(
    task_id: str,
    request: ResearchRequest,
    user: str = Depends(get_current_user),
) -> dict:
    """Research information related to a task using web search.
    
    Returns formatted research results for display in the action output area.
    Also logs a summary to the conversation history.
    """
    from daily_task_assistant.llm.anthropic_client import research_task, AnthropicError

    tasks, live_tasks, settings, warning = fetch_task_dataset(
        limit=None, source=request.source
    )
    target = next((task for task in tasks if task.row_id == task_id), None)
    if not target:
        raise HTTPException(status_code=404, detail="Task not found.")

    try:
        research_results = research_task(
            task=target,
            next_steps=request.next_steps,
        )
    except AnthropicError as exc:
        raise HTTPException(status_code=502, detail=f"Research failed: {exc}")

    # Log a summary to the conversation history
    research_summary = _summarize_research(research_results)
    log_assistant_message(
        task_id,
        content=research_summary,
        plan=None,
        metadata={"source": "research", "full_results_available": True},
    )

    # Fetch updated history to return
    updated_history = fetch_conversation(task_id, limit=100)

    return {
        "research": research_results,
        "taskId": task_id,
        "taskTitle": target.title,
        "history": [
            ConversationMessageModel(**asdict(msg)).model_dump()
            for msg in updated_history
        ],
    }


class SummarizeRequest(BaseModel):
    """Request body for summarize endpoint."""
    source: Literal["auto", "live", "stub"] = "auto"
    plan_summary: Optional[str] = Field(None, alias="planSummary")
    next_steps: Optional[List[str]] = Field(None, alias="nextSteps")
    efficiency_tips: Optional[List[str]] = Field(None, alias="efficiencyTips")


@app.post("/assist/{task_id}/summarize")
def summarize_task_endpoint(
    task_id: str,
    request: SummarizeRequest,
    user: str = Depends(get_current_user),
) -> dict:
    """Generate a summary of the task, plan, and conversation progress.
    
    Reviews the task details, current plan, and conversation history to provide
    a comprehensive summary of where things stand and recommendations for next steps.
    """
    from daily_task_assistant.llm.anthropic_client import summarize_task, AnthropicError

    tasks, live_tasks, settings, warning = fetch_task_dataset(
        limit=None, source=request.source
    )
    target = next((task for task in tasks if task.row_id == task_id), None)
    if not target:
        raise HTTPException(status_code=404, detail="Task not found.")

    # Fetch conversation history
    history = fetch_conversation(task_id, limit=100)
    llm_history: List[Dict[str, str]] = [
        {"role": msg.role, "content": msg.content} for msg in history
    ]

    try:
        summary_results = summarize_task(
            task=target,
            plan_summary=request.plan_summary,
            next_steps=request.next_steps,
            efficiency_tips=request.efficiency_tips,
            conversation_history=llm_history if llm_history else None,
        )
    except AnthropicError as exc:
        raise HTTPException(status_code=502, detail=f"Summarize failed: {exc}")

    # Log a brief note to the conversation history
    log_assistant_message(
        task_id,
        content=f"📋 **Summary generated** - Review the summary in the workspace for current task status and recommendations.",
        plan=None,
        metadata={"source": "summarize"},
    )

    # Fetch updated history to return
    updated_history = fetch_conversation(task_id, limit=100)

    return {
        "summary": summary_results,
        "taskId": task_id,
        "taskTitle": target.title,
        "history": [
            ConversationMessageModel(**asdict(msg)).model_dump()
            for msg in updated_history
        ],
    }


# --- Workspace endpoints ---

class WorkspaceSaveRequest(BaseModel):
    """Request body for saving workspace content."""
    items: List[str] = Field(..., description="List of markdown text blocks")


@app.get("/assist/{task_id}/workspace")
def get_workspace(
    task_id: str,
    user: str = Depends(get_current_user),
) -> dict:
    """Load workspace content for a task.
    
    Returns the saved workspace items (markdown text blocks) for editing.
    """
    from daily_task_assistant.workspace import load_workspace
    
    data = load_workspace(task_id)
    return {
        "taskId": task_id,
        "items": data.items,
        "updatedAt": data.updated_at,
    }


@app.post("/assist/{task_id}/workspace")
def save_workspace_endpoint(
    task_id: str,
    request: WorkspaceSaveRequest,
    user: str = Depends(get_current_user),
) -> dict:
    """Save workspace content for a task.
    
    Persists the workspace items so they survive across sessions.
    """
    from daily_task_assistant.workspace import save_workspace
    
    data = save_workspace(task_id, request.items)
    return {
        "taskId": task_id,
        "items": data.items,
        "updatedAt": data.updated_at,
    }


@app.delete("/assist/{task_id}/workspace")
def clear_workspace_endpoint(
    task_id: str,
    user: str = Depends(get_current_user),
) -> dict:
    """Clear workspace content for a task.
    
    Typically called when a task is marked complete.
    """
    from daily_task_assistant.workspace import clear_workspace
    
    clear_workspace(task_id)
    return {
        "taskId": task_id,
        "cleared": True,
    }


class TaskUpdateRequest(BaseModel):
    """Request body for task update endpoint."""
    action: Literal["mark_complete", "update_status", "update_priority", "update_due_date", "add_comment"]
    status: Optional[str] = Field(None, description="New status value (for update_status)")
    priority: Optional[str] = Field(None, description="New priority value (for update_priority)")
    due_date: Optional[str] = Field(None, description="New due date in YYYY-MM-DD format (for update_due_date)")
    comment: Optional[str] = Field(None, description="Comment text (for add_comment)")
    confirmed: bool = Field(False, description="User has confirmed this action")


# Valid values from smartsheet.yml
VALID_STATUSES = [
    "Scheduled", "In Progress", "Blocked", "Waiting", "Complete", "Recurring",
    "On Hold", "Follow-up", "Awaiting Reply", "Delivered", "Create ZD Ticket",
    "Ticket Created", "Validation", "Needs Approval", "Cancelled", "Delegated", "Completed"
]
VALID_PRIORITIES = ["Critical", "Urgent", "Important", "Standard", "Low"]


@app.post("/assist/{task_id}/update")
def update_task(
    task_id: str,
    request: TaskUpdateRequest,
    user: str = Depends(get_current_user),
) -> dict:
    """Update a task in Smartsheet.
    
    Requires confirmation=True to execute. If not confirmed, returns a preview
    of the proposed changes for user confirmation.
    """
    from daily_task_assistant.smartsheet_client import SmartsheetClient, SmartsheetAPIError
    from datetime import datetime as dt
    
    settings = _get_settings()
    
    # Validate the action and required fields
    if request.action == "update_status":
        if not request.status:
            raise HTTPException(status_code=400, detail="status field required for update_status action")
        if request.status not in VALID_STATUSES:
            raise HTTPException(
                status_code=400, 
                detail=f"Invalid status '{request.status}'. Valid: {VALID_STATUSES}"
            )
    elif request.action == "update_priority":
        if not request.priority:
            raise HTTPException(status_code=400, detail="priority field required for update_priority action")
        if request.priority not in VALID_PRIORITIES:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid priority '{request.priority}'. Valid: {VALID_PRIORITIES}"
            )
    elif request.action == "update_due_date":
        if not request.due_date:
            raise HTTPException(status_code=400, detail="due_date field required for update_due_date action")
        try:
            dt.strptime(request.due_date, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(status_code=400, detail="due_date must be in YYYY-MM-DD format")
    elif request.action == "add_comment":
        if not request.comment:
            raise HTTPException(status_code=400, detail="comment field required for add_comment action")
    
    # Build preview of proposed changes
    preview = {
        "taskId": task_id,
        "action": request.action,
        "changes": {},
    }
    
    if request.action == "mark_complete":
        preview["changes"] = {"status": "Complete", "done": True}
        preview["description"] = "Mark task as complete (Status → Complete, Done → checked)"
    elif request.action == "update_status":
        preview["changes"] = {"status": request.status}
        preview["description"] = f"Update status to '{request.status}'"
    elif request.action == "update_priority":
        preview["changes"] = {"priority": request.priority}
        preview["description"] = f"Update priority to '{request.priority}'"
    elif request.action == "update_due_date":
        preview["changes"] = {"due_date": request.due_date}
        preview["description"] = f"Update due date to '{request.due_date}'"
    elif request.action == "add_comment":
        preview["changes"] = {"comment": request.comment}
        preview["description"] = f"Add comment: '{request.comment[:50]}...'" if len(request.comment or "") > 50 else f"Add comment: '{request.comment}'"
    
    # If not confirmed, return preview for user confirmation
    if not request.confirmed:
        return {
            "status": "pending_confirmation",
            "preview": preview,
            "message": "Please confirm this action before it is executed.",
        }
    
    # Execute the update
    try:
        client = SmartsheetClient(settings)
        
        if request.action == "mark_complete":
            client.mark_complete(task_id)
        elif request.action == "update_status":
            client.update_row(task_id, {"status": request.status})
        elif request.action == "update_priority":
            client.update_row(task_id, {"priority": request.priority})
        elif request.action == "update_due_date":
            client.update_row(task_id, {"due_date": request.due_date})
        elif request.action == "add_comment":
            client.post_comment(task_id, request.comment)
        
        # Log the action to conversation history
        action_description = preview["description"]
        log_assistant_message(
            task_id,
            content=f"✅ **Smartsheet updated**: {action_description}",
            plan=None,
            metadata={"source": "task_update", "action": request.action, "changes": preview["changes"]},
        )
        
        return {
            "status": "success",
            "action": request.action,
            "changes": preview["changes"],
            "message": f"Task updated successfully: {action_description}",
        }
        
    except SmartsheetAPIError as exc:
        raise HTTPException(status_code=502, detail=f"Smartsheet API error: {exc}")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


class FeedbackRequest(BaseModel):
    """Request body for feedback endpoint."""
    feedback: Literal["helpful", "needs_work"]
    context: Literal["research", "plan", "chat", "email", "task_update"]
    message_content: str = Field(..., description="The content being rated")
    message_id: Optional[str] = Field(None, description="Optional conversation message ID")


@app.post("/assist/{task_id}/feedback")
def submit_feedback(
    task_id: str,
    request: FeedbackRequest,
    user: str = Depends(get_current_user),
) -> dict:
    """Submit feedback on a DATA response.
    
    This feedback is used to improve DATA's responses over time.
    """
    from daily_task_assistant.feedback import log_feedback
    
    entry = log_feedback(
        task_id=task_id,
        feedback=request.feedback,
        context=request.context,
        message_content=request.message_content,
        user_email=user,
        message_id=request.message_id,
        metadata={"source": "user_feedback"},
    )
    
    return {
        "status": "success",
        "feedbackId": entry.id,
        "message": f"Thank you for your feedback!",
    }


@app.get("/feedback/summary")
def feedback_summary(
    days: int = Query(30, ge=1, le=365),
    user: str = Depends(get_current_user),
) -> dict:
    """Get aggregated feedback statistics for tuning sessions."""
    from daily_task_assistant.feedback import fetch_feedback_summary
    
    summary = fetch_feedback_summary(days=days)
    
    return {
        "totalHelpful": summary.total_helpful,
        "totalNeedsWork": summary.total_needs_work,
        "helpfulRate": round(summary.helpful_rate * 100, 1),
        "byContext": summary.by_context,
        "recentIssues": summary.recent_issues,
        "periodDays": days,
    }


@app.get("/activity")
def activity_feed(
    limit: int = Query(50, ge=1, le=200),
    user: str = Depends(get_current_user),
) -> dict:
    entries = fetch_activity_entries(limit)
    return {"entries": entries, "count": len(entries)}

