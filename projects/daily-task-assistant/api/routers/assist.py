"""Assist Router - AI assistance, planning, and chat with tools.

Handles:
- Global portfolio chat and context
- Task-specific assist, plan, and chat
- Research, summarize, contact actions
- Email draft management
- Task workspace management
- Task updates with confirmation
- Feedback collection

Migrated from api/main.py as part of the API refactoring initiative.
"""
from __future__ import annotations

import logging
from dataclasses import asdict
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from api.dependencies import (
    get_current_user,
    get_settings,
    get_task_by_id,
    serialize_task,
    serialize_plan,
)
from daily_task_assistant.config import load_settings
from daily_task_assistant.conversations import (
    build_plan_summary,
    clear_conversation,
    fetch_conversation,
    fetch_conversation_for_llm,
    log_assistant_message,
    log_user_message,
    strike_message,
    unstrike_message,
)
from daily_task_assistant.dataset import fetch_tasks as fetch_task_dataset
from daily_task_assistant.services import execute_assist
from daily_task_assistant.tasks import AttachmentDetail

logger = logging.getLogger(__name__)

router = APIRouter()


# =============================================================================
# Pydantic Models
# =============================================================================

class ConversationMessageModel(BaseModel):
    """Model for conversation history messages."""
    role: Literal["user", "assistant", "tool"]
    content: str
    timestamp: Optional[str] = None
    message_id: Optional[str] = Field(None, alias="messageId")
    struck: bool = False
    ts: Optional[str] = None
    struck_at: Optional[str] = Field(None, alias="struckAt")

    model_config = ConfigDict(populate_by_name=True)


class GlobalChatRequest(BaseModel):
    """Request body for global portfolio chat."""
    model_config = ConfigDict(populate_by_name=True)
    
    message: str = Field(..., description="The user's message")
    perspective: Literal["personal", "church", "work", "holistic"] = Field(
        "personal", description="Portfolio perspective to analyze"
    )
    feedback: Optional[Literal["helpful", "not_helpful"]] = Field(
        None, description="Feedback on previous response"
    )
    anthropic_model: Optional[str] = Field(
        None, alias="anthropicModel", description="Override Anthropic model"
    )


class AssistRequest(BaseModel):
    """Request body for assist endpoints."""
    source: Literal["auto", "live", "stub"] = "auto"
    anthropic_model: Optional[str] = Field(
        None, alias="anthropicModel", description="Override Anthropic model name."
    )
    send_email_account: Optional[str] = Field(
        None, alias="sendEmailAccount", description="Gmail account prefix."
    )
    instructions: Optional[str] = None
    reset_conversation: bool = Field(
        False, alias="resetConversation", description="Clear history before running."
    )

    model_config = ConfigDict(populate_by_name=True)


class PlanRequest(BaseModel):
    """Request body for plan generation."""
    source: Literal["auto", "live", "stub"] = "auto"
    anthropic_model: Optional[str] = Field(
        None, alias="anthropicModel", description="Override Anthropic model name."
    )
    context_items: Optional[List[str]] = Field(
        None, alias="contextItems", description="User-provided context items."
    )
    selected_attachments: Optional[List[str]] = Field(
        None, alias="selectedAttachments", description="Attachment IDs to include."
    )

    model_config = ConfigDict(populate_by_name=True)


class ChatRequest(BaseModel):
    """Request body for chat endpoint."""
    model_config = ConfigDict(populate_by_name=True)

    message: str = Field(..., description="The user's message")
    source: Literal["auto", "live", "stub"] = "auto"
    workspace_context: Optional[str] = Field(
        None, alias="workspaceContext", description="Selected workspace content."
    )
    selected_attachments: Optional[List[str]] = Field(
        None, alias="selectedAttachments", description="Attachment IDs to include."
    )


class StrikeRequest(BaseModel):
    """Request body for striking a message."""
    message_ts: str = Field(..., alias="messageTs", description="Timestamp of message to strike")

    model_config = ConfigDict(populate_by_name=True)


class ResearchRequest(BaseModel):
    """Request body for research endpoint."""
    source: Literal["auto", "live", "stub"] = "auto"
    next_steps: Optional[List[str]] = Field(None, description="Next steps to inform research")


class ContactRequest(BaseModel):
    """Request body for contact action."""
    source: Literal["auto", "live", "stub"] = "auto"
    email_account: Optional[str] = Field(None, alias="emailAccount", description="Gmail account prefix")

    model_config = ConfigDict(populate_by_name=True)


class SummarizeRequest(BaseModel):
    """Request body for summarize action."""
    source: Literal["auto", "live", "stub"] = "auto"


class EmailDraftRequest(BaseModel):
    """Request body for creating email drafts."""
    source: Literal["auto", "live", "stub"] = "auto"
    email_account: str = Field(..., alias="emailAccount", description="Gmail account prefix")
    recipient: Optional[str] = Field(None, description="Optional recipient email")

    model_config = ConfigDict(populate_by_name=True)


class SendEmailRequest(BaseModel):
    """Request body for sending emails."""
    source: Literal["auto", "live", "stub"] = "auto"
    email_account: str = Field(..., alias="emailAccount")
    recipient: str
    subject: str
    body: str
    cc: Optional[List[str]] = None
    bcc: Optional[List[str]] = None

    model_config = ConfigDict(populate_by_name=True)


class SaveDraftRequest(BaseModel):
    """Request body for saving drafts."""
    content: str


class BulkTaskUpdate(BaseModel):
    """Single task update in a bulk operation."""
    row_id: str = Field(..., alias="rowId")
    source: str = "personal"
    action: str
    status: Optional[str] = None
    priority: Optional[str] = None
    due_date: Optional[str] = Field(None, alias="dueDate")
    comment: Optional[str] = None
    number: Optional[int] = None
    contact_flag: Optional[bool] = Field(None, alias="contactFlag")
    recurring: Optional[str] = None
    project: Optional[str] = None
    task_title: Optional[str] = Field(None, alias="taskTitle")
    assigned_to: Optional[str] = Field(None, alias="assignedTo")
    notes: Optional[str] = None
    estimated_hours: Optional[str] = Field(None, alias="estimatedHours")
    reason: Optional[str] = None

    model_config = ConfigDict(populate_by_name=True)


class BulkUpdateRequest(BaseModel):
    """Request body for bulk task updates."""
    updates: List[BulkTaskUpdate]


class RebalanceRequest(BaseModel):
    """Request body for workload rebalancing."""
    perspective: Literal["personal", "church", "work", "holistic"] = "personal"
    target_date: Optional[str] = Field(None, alias="targetDate")

    model_config = ConfigDict(populate_by_name=True)


class GlobalStrikeRequest(BaseModel):
    """Request body for striking a global message."""
    perspective: Literal["personal", "church", "work", "holistic"]
    message_ts: str = Field(..., alias="messageTs")

    model_config = ConfigDict(populate_by_name=True)


class GlobalDeleteRequest(BaseModel):
    """Request body for deleting a global message."""
    perspective: Literal["personal", "church", "work", "holistic"]
    message_id: str = Field(..., alias="messageId")

    model_config = ConfigDict(populate_by_name=True)


class FirestoreChatRequest(BaseModel):
    """Request body for Firestore task chat."""
    message: str
    workspace_context: Optional[str] = Field(None, alias="workspaceContext")

    model_config = ConfigDict(populate_by_name=True)


class WorkspaceSaveRequest(BaseModel):
    """Request body for saving workspace."""
    content: str


class TaskUpdateRequest(BaseModel):
    """Request body for task update endpoint."""
    source: Literal["personal", "work"] = "personal"
    action: Literal[
        "mark_complete", "update_status", "update_priority", "update_due_date", "add_comment",
        "update_number", "update_contact_flag", "update_recurring", "update_project",
        "update_task", "update_assigned_to", "update_notes", "update_estimated_hours"
    ]
    status: Optional[str] = None
    priority: Optional[str] = None
    due_date: Optional[str] = Field(None, alias="dueDate")
    comment: Optional[str] = None
    number: Optional[int] = None
    contact_flag: Optional[bool] = Field(None, alias="contactFlag")
    recurring: Optional[str] = None
    project: Optional[str] = None
    task_title: Optional[str] = Field(None, alias="taskTitle")
    assigned_to: Optional[str] = Field(None, alias="assignedTo")
    notes: Optional[str] = None
    estimated_hours: Optional[str] = Field(None, alias="estimatedHours")
    confirmed: bool = False

    model_config = ConfigDict(populate_by_name=True)


class FeedbackRequest(BaseModel):
    """Request body for feedback."""
    plan_generator: str = Field(..., alias="planGenerator")
    rating: Literal["helpful", "not_helpful"]
    comment: Optional[str] = None

    model_config = ConfigDict(populate_by_name=True)


# =============================================================================
# Helper Functions
# =============================================================================

def _summarize_research(full_research: str, max_length: int = 200) -> str:
    """Extract a brief summary from research results."""
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
                clean_line = line.strip().lstrip('-•').strip()
                if clean_line:
                    summary_lines.append(clean_line)
                    if len(summary_lines) >= 3:
                        break
    
    if summary_lines:
        summary = "; ".join(summary_lines)
        if len(summary) > max_length:
            summary = summary[:max_length-3] + "..."
        return f"🔍 **Research completed**: {summary}"
    
    truncated = full_research[:max_length-3].rsplit(' ', 1)[0] + "..."
    return f"🔍 **Research completed**: {truncated}"


def _summarize_summary(full_summary: str, max_length: int = 250) -> str:
    """Extract key points from a summary."""
    lines = full_summary.split('\n')
    key_points = []
    
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith('#'):
            continue
        if stripped.startswith('-') or stripped.startswith('•'):
            clean_line = stripped.lstrip('-•').strip()
            if clean_line and len(clean_line) > 10:
                key_points.append(clean_line)
                if len(key_points) >= 4:
                    break
        elif len(key_points) == 0 and len(stripped) > 30:
            key_points.append(stripped)
    
    if key_points:
        summary = "; ".join(key_points)
        if len(summary) > max_length:
            summary = summary[:max_length-3] + "..."
        return f"📋 **Summary generated**: {summary}"
    
    truncated = full_summary[:max_length-3].rsplit(' ', 1)[0] + "..."
    return f"📋 **Summary generated**: {truncated}"


def _is_pdf_mime(mime_type: str | None) -> bool:
    """Check if MIME type indicates a PDF."""
    if not mime_type:
        return False
    return "pdf" in mime_type.lower()


# =============================================================================
# Global Portfolio Endpoints
# =============================================================================

@router.post("/global/chat")
def global_chat(
    request: GlobalChatRequest,
    user: str = Depends(get_current_user),
) -> dict:
    """Chat with DATA about portfolio/workload with task update capability."""
    from daily_task_assistant.smartsheet_client import SmartsheetClient
    from daily_task_assistant.portfolio_context import build_portfolio_context
    from daily_task_assistant.llm.prompts import _format_portfolio_summary
    from daily_task_assistant.llm.anthropic_client import portfolio_chat_with_tools, AnthropicError
    from daily_task_assistant.trust import log_trust_event
    
    settings = get_settings()
    
    try:
        client = SmartsheetClient(settings)
        portfolio = build_portfolio_context(client, request.perspective)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to load portfolio: {exc}")
    
    conversation_id = f"global:{request.perspective}"
    history = fetch_conversation_for_llm(conversation_id, limit=20)
    llm_history = [{"role": msg.role, "content": msg.content} for msg in history]
    
    log_user_message(
        conversation_id,
        content=request.message,
        user_email=user,
        metadata={"perspective": request.perspective, "total_tasks": portfolio.total_open},
    )
    
    portfolio_context_text = _format_portfolio_summary(portfolio)
    
    try:
        chat_response = portfolio_chat_with_tools(
            portfolio_context=portfolio_context_text,
            task_summaries=portfolio.task_summaries,
            user_message=request.message,
            history=llm_history,
            perspective=request.perspective,
        )
        response_text = chat_response.message
        pending_actions = chat_response.pending_actions
    except AnthropicError as exc:
        raise HTTPException(status_code=502, detail=f"AI service error: {exc}")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"AI service error: {exc}")
    
    log_assistant_message(
        conversation_id,
        content=response_text,
        plan=None,
        metadata={"source": "global_chat", "perspective": request.perspective, "has_pending_actions": len(pending_actions) > 0},
    )
    
    if request.feedback:
        log_trust_event(
            scope="portfolio",
            perspective=request.perspective,
            suggestion_type="insight",
            suggestion=response_text[:200],
            response="accepted" if request.feedback == "helpful" else "rejected",
            user=user,
        )
    
    updated_history = fetch_conversation(conversation_id, limit=50)
    
    task_lookup = {t["row_id"]: t for t in portfolio.task_summaries}
    formatted_actions = []
    
    for action in pending_actions:
        task_info = task_lookup.get(action.row_id, {})
        formatted_actions.append({
            "rowId": action.row_id,
            "source": task_info.get("source", "personal"),
            "action": action.action,
            "status": action.status,
            "priority": action.priority,
            "dueDate": action.due_date,
            "comment": action.comment,
            "number": action.number,
            "contactFlag": action.contact_flag,
            "recurring": action.recurring,
            "project": action.project,
            "taskTitle": task_info.get("title") or action.task_title,
            "assignedTo": action.assigned_to,
            "notes": action.notes,
            "estimatedHours": action.estimated_hours,
            "reason": action.reason,
            "domain": task_info.get("domain", "Unknown"),
            "currentDue": task_info.get("due", "")[:10] if task_info.get("due") else None,
            "currentNumber": task_info.get("number"),
            "currentPriority": task_info.get("priority"),
            "currentStatus": task_info.get("status"),
        })
    
    return {
        "response": response_text,
        "perspective": request.perspective,
        "pendingActions": formatted_actions,
        "portfolio": {
            "totalOpen": portfolio.total_open,
            "overdue": portfolio.overdue,
            "dueToday": portfolio.due_today,
            "dueThisWeek": portfolio.due_this_week,
            "byPriority": portfolio.by_priority,
            "byProject": portfolio.by_project,
            "byDueDate": portfolio.by_due_date,
            "conflicts": portfolio.conflicts,
            "domainBreakdown": portfolio.domain_breakdown,
        },
        "history": [
            ConversationMessageModel(**asdict(msg)).model_dump()
            for msg in updated_history
        ],
    }


@router.get("/global/context")
def get_global_context(
    perspective: Literal["personal", "church", "work", "holistic"] = Query("personal"),
    user: str = Depends(get_current_user),
) -> dict:
    """Get portfolio context and conversation history."""
    from daily_task_assistant.smartsheet_client import SmartsheetClient
    from daily_task_assistant.portfolio_context import build_portfolio_context, get_perspective_description
    
    settings = get_settings()
    
    try:
        client = SmartsheetClient(settings)
        portfolio = build_portfolio_context(client, perspective)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to load portfolio: {exc}")
    
    conversation_id = f"global:{perspective}"
    history = fetch_conversation(conversation_id)
    
    return {
        "perspective": perspective,
        "description": get_perspective_description(perspective),
        "portfolio": {
            "totalOpen": portfolio.total_open,
            "overdue": portfolio.overdue,
            "dueToday": portfolio.due_today,
            "dueThisWeek": portfolio.due_this_week,
            "byPriority": portfolio.by_priority,
            "byProject": portfolio.by_project,
            "byDueDate": portfolio.by_due_date,
            "conflicts": portfolio.conflicts,
            "domainBreakdown": portfolio.domain_breakdown,
        },
        "history": [
            {"role": msg.role, "content": msg.content, "ts": msg.ts, "struck": msg.struck, "struckAt": msg.struck_at}
            for msg in history if not msg.struck
        ],
    }


@router.delete("/global/history")
def clear_global_history(
    perspective: Literal["personal", "church", "work", "holistic"] = Query("personal"),
    user: str = Depends(get_current_user),
) -> dict:
    """Clear conversation history for a global perspective."""
    conversation_id = f"global:{perspective}"
    clear_conversation(conversation_id)
    return {"cleared": True, "perspective": perspective}


@router.post("/global/bulk-update")
def execute_bulk_update(
    request: BulkUpdateRequest,
    user: str = Depends(get_current_user),
) -> dict:
    """Execute bulk task updates from portfolio chat."""
    from daily_task_assistant.smartsheet_client import SmartsheetClient, SmartsheetAPIError
    
    settings = get_settings()
    client = SmartsheetClient(settings)
    
    results = []
    for update in request.updates:
        try:
            updates_dict = {}
            if update.status:
                updates_dict["status"] = update.status
            if update.priority:
                updates_dict["priority"] = update.priority
            if update.due_date:
                updates_dict["due_date"] = update.due_date
            if update.comment:
                updates_dict["comment"] = update.comment
            if update.number is not None:
                updates_dict["number"] = update.number
            if update.contact_flag is not None:
                updates_dict["contact_flag"] = update.contact_flag
            if update.recurring:
                updates_dict["recurring"] = update.recurring
            if update.project:
                updates_dict["project"] = update.project
            if update.task_title:
                updates_dict["task"] = update.task_title
            if update.assigned_to:
                updates_dict["assigned_to"] = update.assigned_to
            if update.notes:
                updates_dict["notes"] = update.notes
            if update.estimated_hours:
                updates_dict["estimated_hours"] = update.estimated_hours
            
            if update.action == "mark_complete":
                updates_dict["done"] = True
            
            client.update_row(update.row_id, updates_dict, source=update.source)
            results.append({"rowId": update.row_id, "success": True})
        except SmartsheetAPIError as e:
            results.append({"rowId": update.row_id, "success": False, "error": str(e)})
        except Exception as e:
            results.append({"rowId": update.row_id, "success": False, "error": str(e)})
    
    return {
        "results": results,
        "totalUpdated": sum(1 for r in results if r["success"]),
        "totalFailed": sum(1 for r in results if not r["success"]),
    }


@router.post("/global/history/strike")
def strike_global_message(
    request: GlobalStrikeRequest,
    user: str = Depends(get_current_user),
) -> dict:
    """Strike a message from global conversation."""
    conversation_id = f"global:{request.perspective}"
    success = strike_message(conversation_id, request.message_ts)
    if not success:
        raise HTTPException(status_code=404, detail="Message not found.")
    
    history = fetch_conversation(conversation_id, limit=100)
    return {
        "status": "struck",
        "messageTs": request.message_ts,
        "history": [ConversationMessageModel(**asdict(msg)).model_dump() for msg in history],
    }


@router.post("/global/history/unstrike")
def unstrike_global_message(
    request: GlobalStrikeRequest,
    user: str = Depends(get_current_user),
) -> dict:
    """Unstrike a message from global conversation."""
    conversation_id = f"global:{request.perspective}"
    success = unstrike_message(conversation_id, request.message_ts)
    if not success:
        raise HTTPException(status_code=404, detail="Message not found.")
    
    history = fetch_conversation(conversation_id, limit=100)
    return {
        "status": "unstruck",
        "messageTs": request.message_ts,
        "history": [ConversationMessageModel(**asdict(msg)).model_dump() for msg in history],
    }


@router.delete("/global/message")
def delete_global_message(
    request: GlobalDeleteRequest,
    user: str = Depends(get_current_user),
) -> dict:
    """Delete a message from global conversation history."""
    from daily_task_assistant.conversations import delete_message
    
    conversation_id = f"global:{request.perspective}"
    success = delete_message(conversation_id, request.message_id)
    if not success:
        raise HTTPException(status_code=404, detail="Message not found.")
    
    return {"deleted": True, "messageId": request.message_id}


# =============================================================================
# Task-Scoped Endpoints
# =============================================================================

@router.post("/{task_id}")
def assist_task(
    task_id: str,
    request: AssistRequest,
    user: str = Depends(get_current_user),
) -> dict:
    """Load task context and conversation history."""
    from daily_task_assistant.conversations.history import get_latest_plan
    
    tasks, live_tasks, settings, warning = fetch_task_dataset(
        limit=None, source=request.source, include_work_in_all=True
    )
    target = next((task for task in tasks if task.row_id == task_id), None)
    if not target:
        raise HTTPException(status_code=404, detail="Task not found.")

    if request.reset_conversation:
        clear_conversation(task_id)

    history = fetch_conversation(task_id, limit=100)
    latest_plan = get_latest_plan(task_id)

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
            "complexity": latest_plan.get("complexity", "simple"),
            "crux": latest_plan.get("crux"),
            "approachOptions": latest_plan.get("approach_options"),
            "recommendedPath": latest_plan.get("recommended_path"),
            "openQuestions": latest_plan.get("open_questions"),
            "doneWhen": latest_plan.get("done_when"),
        }

    return {
        "plan": plan_response,
        "environment": settings.environment,
        "liveTasks": live_tasks,
        "warning": warning,
        "history": [ConversationMessageModel(**asdict(msg)).model_dump() for msg in history],
    }


@router.post("/{task_id}/plan")
def generate_plan(
    task_id: str,
    request: PlanRequest,
    user: str = Depends(get_current_user),
) -> dict:
    """Generate or update the plan for a task."""
    target, is_firestore, settings, live_tasks, warning = get_task_by_id(task_id, user, request.source)

    history = fetch_conversation_for_llm(task_id, limit=100)
    llm_history: List[Dict[str, str]] = [{"role": msg.role, "content": msg.content} for msg in history]

    workspace_context = None
    if request.context_items:
        workspace_context = "\n\n---\n\n".join(request.context_items)

    result = execute_assist(
        task=target,
        settings=settings,
        source=request.source,
        anthropic_model=request.anthropic_model,
        send_email_account=None,
        live_tasks=live_tasks,
        conversation_history=llm_history if llm_history else None,
        workspace_context=workspace_context,
    )

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


@router.get("/{task_id}/history")
def get_conversation_history(
    task_id: str,
    limit: int = Query(100, ge=1, le=200),
    user: str = Depends(get_current_user),
) -> List[dict]:
    """Get conversation history for a task."""
    history = fetch_conversation(task_id, limit=limit)
    return [ConversationMessageModel(**asdict(msg)).model_dump() for msg in history]


@router.post("/{task_id}/history/strike")
def strike_conversation_message(
    task_id: str,
    request: StrikeRequest,
    user: str = Depends(get_current_user),
) -> dict:
    """Strike (hide) a message from the conversation."""
    success = strike_message(task_id, request.message_ts)
    if not success:
        raise HTTPException(status_code=404, detail="Message not found.")
    
    history = fetch_conversation(task_id, limit=100)
    return {
        "status": "struck",
        "messageTs": request.message_ts,
        "history": [ConversationMessageModel(**asdict(msg)).model_dump() for msg in history],
    }


@router.post("/{task_id}/history/unstrike")
def unstrike_conversation_message(
    task_id: str,
    request: StrikeRequest,
    user: str = Depends(get_current_user),
) -> dict:
    """Unstrike (restore) a previously struck message."""
    success = unstrike_message(task_id, request.message_ts)
    if not success:
        raise HTTPException(status_code=404, detail="Message not found.")
    
    history = fetch_conversation(task_id, limit=100)
    return {
        "status": "unstruck",
        "messageTs": request.message_ts,
        "history": [ConversationMessageModel(**asdict(msg)).model_dump() for msg in history],
    }


@router.post("/{task_id}/chat")
def chat_with_task(
    task_id: str,
    request: ChatRequest,
    user: str = Depends(get_current_user),
) -> dict:
    """Send a conversational message about a task."""
    from daily_task_assistant.llm.anthropic_client import chat_with_tools, AnthropicError

    tasks, live_tasks, settings, warning = fetch_task_dataset(
        limit=None, source=request.source, include_work_in_all=True
    )
    target = next((task for task in tasks if task.row_id == task_id), None)
    if not target:
        raise HTTPException(status_code=404, detail="Task not found.")

    history = fetch_conversation(task_id, limit=50)
    llm_history_messages = fetch_conversation_for_llm(task_id, limit=50)

    log_user_message(
        task_id,
        content=request.message,
        user_email=user,
        metadata={"source": request.source},
    )

    llm_history: List[Dict[str, str]] = [{"role": msg.role, "content": msg.content} for msg in llm_history_messages]

    attachments: List[AttachmentDetail] = []
    if request.selected_attachments:
        from daily_task_assistant.smartsheet_client import SmartsheetClient
        ss_client = SmartsheetClient(load_settings())
        source_key = "personal" if target.source != "work" else "work"
        for att_id in request.selected_attachments:
            detail = ss_client.get_attachment_detail(att_id, source=source_key)
            if detail:
                attachments.append(detail)

    try:
        chat_response = chat_with_tools(
            task=target,
            user_message=request.message,
            history=llm_history,
            workspace_context=request.workspace_context,
            attachments=attachments if attachments else None,
        )
    except AnthropicError as exc:
        raise HTTPException(status_code=502, detail=f"AI service error: {exc}")

    log_assistant_message(
        task_id,
        content=chat_response.message,
        plan=None,
        metadata={"source": "chat", "has_pending_action": chat_response.pending_action is not None},
    )

    updated_history = fetch_conversation(task_id, limit=100)

    response_data = {
        "response": chat_response.message,
        "history": [ConversationMessageModel(**asdict(msg)).model_dump() for msg in updated_history],
    }
    
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
    
    if chat_response.email_draft_update:
        update = chat_response.email_draft_update
        response_data["emailDraftUpdate"] = {
            "subject": update.subject,
            "body": update.body,
            "reason": update.reason,
        }
    
    if chat_response.pending_email_draft:
        draft = chat_response.pending_email_draft
        response_data["pendingEmailDraft"] = {
            "recipient": draft.recipient,
            "subject": draft.subject,
            "body": draft.body,
            "reason": draft.reason,
        }

    return response_data


@router.post("/{task_id}/research")
def research_task_endpoint(
    task_id: str,
    request: ResearchRequest,
    user: str = Depends(get_current_user),
) -> dict:
    """Research information related to a task."""
    from daily_task_assistant.llm.anthropic_client import research_task, AnthropicError

    target, is_firestore, settings, live_tasks, warning = get_task_by_id(task_id, user, request.source)

    try:
        research_results = research_task(task=target, next_steps=request.next_steps)
    except AnthropicError as exc:
        raise HTTPException(status_code=502, detail=f"Research failed: {exc}")

    research_summary = _summarize_research(research_results)
    log_assistant_message(
        task_id,
        content=research_summary,
        plan=None,
        metadata={"source": "research", "full_results_available": True},
    )

    updated_history = fetch_conversation(task_id, limit=100)

    return {
        "research": research_results,
        "history": [ConversationMessageModel(**asdict(msg)).model_dump() for msg in updated_history],
    }


@router.post("/{task_id}/summarize")
def summarize_task(
    task_id: str,
    request: SummarizeRequest,
    user: str = Depends(get_current_user),
) -> dict:
    """Generate a summary of the task including attachments."""
    from daily_task_assistant.llm.anthropic_client import summarize_task as llm_summarize, AnthropicError

    target, is_firestore, settings, live_tasks, warning = get_task_by_id(task_id, user, request.source)

    try:
        summary_result = llm_summarize(task=target, settings=settings)
    except AnthropicError as exc:
        raise HTTPException(status_code=502, detail=f"Summary failed: {exc}")

    summary_text = _summarize_summary(summary_result)
    log_assistant_message(
        task_id,
        content=summary_text,
        plan=None,
        metadata={"source": "summarize", "full_results_available": True},
    )

    updated_history = fetch_conversation(task_id, limit=100)

    return {
        "summary": summary_result,
        "history": [ConversationMessageModel(**asdict(msg)).model_dump() for msg in updated_history],
    }


@router.get("/{task_id}/attachments")
def list_task_attachments(
    task_id: str,
    user: str = Depends(get_current_user),
) -> dict:
    """List attachments for a task."""
    from daily_task_assistant.smartsheet_client import SmartsheetClient
    
    settings = get_settings()
    client = SmartsheetClient(settings)
    
    attachments = client.list_attachments(task_id)
    
    return {
        "attachments": [
            {
                "attachmentId": att.attachment_id,
                "name": att.name,
                "mimeType": att.mime_type,
                "sizeInKB": att.size_in_kb,
                "createdAt": att.created_at.isoformat() if att.created_at else None,
            }
            for att in attachments
        ],
        "totalSizeKB": sum(att.size_in_kb or 0 for att in attachments),
    }


@router.get("/{task_id}/workspace")
def get_workspace(
    task_id: str,
    user: str = Depends(get_current_user),
) -> dict:
    """Get workspace content for a task."""
    from daily_task_assistant.workspace import get_workspace as fetch_workspace

    workspace = fetch_workspace(task_id)
    return {
        "taskId": task_id,
        "content": workspace.content if workspace else "",
        "updatedAt": workspace.updated_at.isoformat() if workspace and workspace.updated_at else None,
    }


@router.post("/{task_id}/workspace")
def save_workspace(
    task_id: str,
    request: WorkspaceSaveRequest,
    user: str = Depends(get_current_user),
) -> dict:
    """Save workspace content for a task."""
    from daily_task_assistant.workspace import save_workspace as store_workspace

    workspace = store_workspace(task_id, request.content)
    return {
        "taskId": task_id,
        "saved": True,
        "updatedAt": workspace.updated_at.isoformat() if workspace.updated_at else None,
    }


@router.delete("/{task_id}/workspace")
def clear_workspace(
    task_id: str,
    user: str = Depends(get_current_user),
) -> dict:
    """Clear workspace content for a task."""
    from daily_task_assistant.workspace import clear_workspace as delete_workspace

    delete_workspace(task_id)
    return {"taskId": task_id, "cleared": True}


@router.post("/{task_id}/feedback")
def submit_feedback(
    task_id: str,
    request: FeedbackRequest,
    user: str = Depends(get_current_user),
) -> dict:
    """Submit feedback on a plan."""
    from daily_task_assistant.feedback import save_feedback

    save_feedback(
        task_id=task_id,
        plan_generator=request.plan_generator,
        rating=request.rating,
        comment=request.comment,
        user_email=user,
    )
    
    return {"taskId": task_id, "feedbackSaved": True}
