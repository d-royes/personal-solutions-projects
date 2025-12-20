"""FastAPI service for Daily Task Assistant."""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)
from dataclasses import asdict
from functools import lru_cache
from typing import Any, Dict, List, Literal, Optional
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field

from daily_task_assistant.api.auth import get_current_user
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
    "http://localhost:5174",
    "http://127.0.0.1:5174",
    os.getenv("DTA_ALLOWED_FRONTEND", "").strip(),
    # Custom domains
    "https://staging.dailytaskassistant.ai",
    "https://dailytaskassistant.ai",
    "https://www.dailytaskassistant.ai",
]

# Account-specific labels to include in attention scanning
# These labels may contain action items that automations have filed away
ATTENTION_SCAN_CONFIG = {
    "church": {
        "include": ["Admin", "Ministry Comms", "Personal", "Unknown"],
        "exclude": ["Junk", "Promotional", "Trash"],
    },
    "personal": {
        "include": ["1 Week Hold", "Admin", "Transactional", "Personal"],
        "exclude": ["Junk", "Promotional", "Trash"],
    },
}
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
        "source": task.source,  # "personal" or "work"
        "done": task.done,  # True if Done checkbox is checked
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
    ts: str  # Keep as string to preserve exact timestamp format for strike matching
    metadata: Dict[str, Any] = Field(default_factory=dict)
    plan: Optional[Dict[str, Any]] = None
    send_email_account: Optional[str] = Field(
        None,
        alias="sendEmailAccount",
        description="Gmail account prefix to send email (e.g., 'church').",
    )
    struck: bool = False
    struck_at: Optional[str] = Field(None, alias="struckAt")  # Keep as string


@app.get("/health")
def health_check() -> dict:
    """Health check endpoint with service configuration status."""
    import os
    settings = _get_settings()
    
    # Check service configurations
    services = {
        "anthropic": "configured" if os.getenv("ANTHROPIC_API_KEY") else "not_configured",
        "smartsheet": "configured" if os.getenv("SMARTSHEET_API_TOKEN") else "not_configured",
        "church_gmail": "configured" if all([
            os.getenv("CHURCH_GMAIL_CLIENT_ID"),
            os.getenv("CHURCH_GMAIL_CLIENT_SECRET"),
            os.getenv("CHURCH_GMAIL_REFRESH_TOKEN"),
        ]) else "not_configured",
        "personal_gmail": "configured" if all([
            os.getenv("PERSONAL_GMAIL_CLIENT_ID"),
            os.getenv("PERSONAL_GMAIL_CLIENT_SECRET"),
            os.getenv("PERSONAL_GMAIL_REFRESH_TOKEN"),
        ]) else "not_configured",
    }
    
    return {
        "status": "ok",
        "time": datetime.now(timezone.utc).isoformat(),
        "environment": settings.environment,
        "services": services,
    }


@app.get("/tasks")
def list_tasks(
    source: Literal["auto", "live", "stub"] = Query("auto"),
    limit: Optional[int] = Query(None, ge=1, le=500),
    include_work: bool = Query(False, alias="includeWork"),
    user: str = Depends(get_current_user),
) -> dict:
    tasks, live_tasks, settings, warning = fetch_task_dataset(
        limit=limit, source=source, include_work_in_all=include_work
    )
    return {
        "tasks": [serialize_task(task) for task in tasks],
        "liveTasks": live_tasks,
        "environment": settings.environment,
        "warning": warning,
    }


@app.get("/work/badge")
def get_work_badge(
    user: str = Depends(get_current_user),
) -> dict:
    """Get work task badge/notification counts.
    
    Returns counts of work tasks that need attention for the Work filter badge.
    """
    from daily_task_assistant.smartsheet_client import SmartsheetClient
    from datetime import datetime, date
    
    settings = _get_settings()
    
    try:
        client = SmartsheetClient(settings)
        # Fetch work tasks only
        tasks = client.list_tasks(sources=["work"])
    except Exception:
        # If work sheet not available, return zeros
        return {
            "needsAttention": 0,
            "overdue": 0,
            "dueToday": 0,
            "total": 0,
        }
    
    today = date.today()
    overdue = 0
    due_today = 0
    
    for task in tasks:
        if task.due:
            try:
                # Handle both date objects and date strings
                if isinstance(task.due, date):
                    due_date = task.due
                elif isinstance(task.due, str):
                    due_date = datetime.fromisoformat(task.due.replace("Z", "+00:00")).date()
                else:
                    continue
                    
                if due_date < today:
                    overdue += 1
                elif due_date == today:
                    due_today += 1
            except (ValueError, AttributeError, TypeError):
                pass
    
    return {
        "needsAttention": overdue + due_today,
        "overdue": overdue,
        "dueToday": due_today,
        "total": len(tasks),
    }


# --- Global Portfolio Mode Endpoints ---
# NOTE: These routes MUST be defined BEFORE /assist/{task_id} routes
# to prevent FastAPI from matching "global" as a task_id

class GlobalChatRequest(BaseModel):
    """Request body for global portfolio chat."""
    model_config = {"populate_by_name": True}
    
    message: str = Field(..., description="The user's message")
    perspective: Literal["personal", "church", "work", "holistic"] = Field(
        "personal", description="Portfolio perspective to analyze"
    )
    feedback: Optional[Literal["helpful", "not_helpful"]] = Field(
        None, description="Feedback on previous response for trust tracking"
    )
    anthropic_model: Optional[str] = Field(
        None, alias="anthropicModel", description="Override Anthropic model"
    )


@app.post("/assist/global/chat")
def global_chat(
    request: GlobalChatRequest,
    user: str = Depends(get_current_user),
) -> dict:
    """Chat with DATA about portfolio/workload with task update capability.
    
    This enables DATA to operate at a global level, analyzing workload
    across perspectives (Personal, Church, Work, Holistic) AND execute
    task updates when requested.
    
    The perspective parameter filters which tasks are included:
    - personal: Personal projects (Around The House, Family Time, etc.)
    - church: Church ministry tasks only
    - work: Professional tasks from work Smartsheet
    - holistic: All tasks across all domains
    
    Returns pending_actions when DATA wants to update tasks - frontend
    should display these for user confirmation before executing.
    """
    from daily_task_assistant.smartsheet_client import SmartsheetClient
    from daily_task_assistant.portfolio_context import build_portfolio_context
    from daily_task_assistant.llm.prompts import _format_portfolio_summary
    from daily_task_assistant.llm.anthropic_client import (
        portfolio_chat_with_tools,
        AnthropicError,
    )
    from daily_task_assistant.trust import log_trust_event
    
    settings = _get_settings()
    
    # Build portfolio context for the selected perspective
    try:
        client = SmartsheetClient(settings)
        portfolio = build_portfolio_context(client, request.perspective)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to load portfolio: {exc}")
    
    # Use global conversation ID scoped by perspective
    conversation_id = f"global:{request.perspective}"
    
    # Fetch conversation history
    history = fetch_conversation_for_llm(conversation_id, limit=20)
    llm_history = [{"role": msg.role, "content": msg.content} for msg in history]
    
    # Log user message
    log_user_message(
        conversation_id,
        content=request.message,
        user_email=user,
        metadata={
            "perspective": request.perspective,
            "total_tasks": portfolio.total_open,
        },
    )
    
    # Format portfolio context for LLM
    portfolio_context_text = _format_portfolio_summary(portfolio)
    
    # Execute LLM call with tools
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
    
    # Log assistant response
    log_assistant_message(
        conversation_id,
        content=response_text,
        plan=None,
        metadata={
            "source": "global_chat",
            "perspective": request.perspective,
            "has_pending_actions": len(pending_actions) > 0,
        },
    )
    
    # Log trust event if feedback provided
    if request.feedback:
        log_trust_event(
            scope="portfolio",
            perspective=request.perspective,
            suggestion_type="insight",
            suggestion=response_text[:200],
            response="accepted" if request.feedback == "helpful" else "rejected",
            user=user,
        )
    
    # Fetch updated history
    updated_history = fetch_conversation(conversation_id, limit=50)
    
    # Format pending actions for frontend - enrich with task details from portfolio
    task_lookup = {t["row_id"]: t for t in portfolio.task_summaries}
    formatted_actions = []
    
    # Debug: log available row_ids vs requested row_ids
    available_ids = list(task_lookup.keys())[:5]
    logger.info(f"[DEBUG] Available task row_ids (first 5): {available_ids}")
    requested_ids = [a.row_id for a in pending_actions[:5]]
    logger.info(f"[DEBUG] LLM requested row_ids (first 5): {requested_ids}")
    
    for action in pending_actions:
        # Look up task details to include title and domain
        task_info = task_lookup.get(action.row_id, {})
        if not task_info:
            logger.warning(f"[DEBUG] No task found for row_id: {action.row_id}")
        formatted_actions.append({
            "rowId": action.row_id,
            "source": task_info.get("source", "personal"),  # Which Smartsheet to update
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
            # Add enriched data from portfolio
            "domain": task_info.get("domain", "Unknown"),
            "currentDue": task_info.get("due", "")[:10] if task_info.get("due") else None,
            "currentNumber": task_info.get("number"),
            "currentPriority": task_info.get("priority"),
            "currentStatus": task_info.get("status"),
        })
    
    return {
        "response": response_text,
        "perspective": request.perspective,
        "pendingActions": formatted_actions,  # NEW: Task updates for confirmation
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


@app.get("/assist/global/context")
def get_global_context(
    perspective: Literal["personal", "church", "work", "holistic"] = Query(
        "personal", description="Portfolio perspective"
    ),
    user: str = Depends(get_current_user),
) -> dict:
    """Get portfolio context and conversation history without sending a chat message.
    
    Useful for displaying portfolio stats and existing conversation in the UI
    before the user starts/continues a conversation.
    """
    from daily_task_assistant.smartsheet_client import SmartsheetClient
    from daily_task_assistant.portfolio_context import (
        build_portfolio_context,
        get_perspective_description,
    )
    
    settings = _get_settings()
    
    try:
        client = SmartsheetClient(settings)
        portfolio = build_portfolio_context(client, perspective)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to load portfolio: {exc}")
    
    # Fetch existing conversation history for this perspective
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
            {
                "role": msg.role,
                "content": msg.content,
                "ts": msg.ts,
                "struck": msg.struck,
                "struckAt": msg.struck_at,
            }
            for msg in history
            if not msg.struck  # Don't include struck messages in UI
        ],
    }


@app.delete("/assist/global/history")
def clear_global_history(
    perspective: Literal["personal", "church", "work", "holistic"] = Query(
        "personal", description="Portfolio perspective to clear"
    ),
    user: str = Depends(get_current_user),
) -> dict:
    """Clear conversation history for a global perspective.
    
    WARNING: This permanently deletes messages. For soft-hiding, use
    the strike endpoint instead.
    """
    conversation_id = f"global:{perspective}"
    clear_conversation(conversation_id)
    
    return {
        "status": "cleared",
        "perspective": perspective,
    }


# ============================================================================
# BULK TASK UPDATES (Portfolio Actions)
# ============================================================================

class BulkTaskUpdate(BaseModel):
    """Single task update in a bulk operation."""
    model_config = {"populate_by_name": True}
    
    row_id: str = Field(..., alias="rowId", description="Smartsheet row ID")
    source: str = Field("personal", description="Source sheet: 'personal' or 'work'")
    action: Literal[
        "mark_complete", "update_status", "update_priority", "update_due_date",
        "add_comment", "update_number", "update_contact_flag", "update_recurring",
        "update_project", "update_task", "update_assigned_to", "update_notes",
        "update_estimated_hours"
    ]
    # Optional fields based on action
    status: Optional[str] = None
    priority: Optional[str] = None
    due_date: Optional[str] = Field(None, alias="dueDate")
    comment: Optional[str] = None
    number: Optional[float] = None  # Supports decimals: 0.1-0.9 for recurring, 1+ for regular
    contact_flag: Optional[bool] = Field(None, alias="contactFlag")
    recurring: Optional[str] = None
    project: Optional[str] = None
    task_title: Optional[str] = Field(None, alias="taskTitle")
    assigned_to: Optional[str] = Field(None, alias="assignedTo")
    notes: Optional[str] = None
    estimated_hours: Optional[str] = Field(None, alias="estimatedHours")
    reason: str = ""


class BulkUpdateRequest(BaseModel):
    """Request body for bulk task updates."""
    model_config = {"populate_by_name": True}
    
    updates: List[BulkTaskUpdate] = Field(..., description="List of task updates to perform")
    perspective: Literal["personal", "church", "work", "holistic"] = "holistic"


class BulkUpdateResult(BaseModel):
    """Result for a single task update."""
    model_config = {"populate_by_name": True}
    
    row_id: str = Field(..., alias="rowId")
    success: bool
    error: Optional[str] = None


@app.post("/assist/global/bulk-update")
def bulk_update_tasks(
    request: BulkUpdateRequest,
    user: str = Depends(get_current_user),
) -> dict:
    """Execute multiple task updates in a single request.
    
    This enables portfolio-level task management like:
    - Rescheduling multiple overdue tasks
    - Reordering tasks for the day (# field)
    - Bulk status changes
    
    Each update is executed independently - failures don't stop subsequent updates.
    Returns results for each update with success/failure status.
    """
    import logging
    logging.warning(f"[BULK-UPDATE] Received {len(request.updates)} updates")
    for i, upd in enumerate(request.updates):
        logging.warning(f"[BULK-UPDATE] Update {i}: row_id={upd.row_id}, action={upd.action}, number={upd.number}, due_date={upd.due_date}")
    
    from daily_task_assistant.smartsheet_client import SmartsheetClient
    
    settings = _get_settings()
    
    try:
        client = SmartsheetClient(settings)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to connect to Smartsheet: {exc}")
    
    results: List[BulkUpdateResult] = []
    success_count = 0
    
    for update in request.updates:
        try:
            # Handle mark_complete specially - uses dedicated method with recurring logic
            if update.action == "mark_complete":
                logging.warning(f"[BULK-UPDATE] Executing mark_complete: row_id={update.row_id}, source={update.source}")
                client.mark_complete(update.row_id, source=update.source)
                logging.warning(f"[BULK-UPDATE] Success: row_id={update.row_id}")
                results.append(BulkUpdateResult(row_id=update.row_id, success=True))
                success_count += 1
                continue
            
            # Build the update payload based on action
            update_data = {}
            
            if update.action == "update_status":
                update_data["status"] = update.status
                # Terminal statuses also mark done
                if update.status in ("Completed", "Cancelled", "Delegated", "Ticket Created"):
                    update_data["done"] = True
                    
            elif update.action == "update_priority":
                update_data["priority"] = update.priority
                
            elif update.action == "update_due_date":
                update_data["due_date"] = update.due_date
                
            elif update.action == "add_comment":
                update_data["notes"] = update.comment
                
            elif update.action == "update_number":
                update_data["number"] = update.number
                
            elif update.action == "update_contact_flag":
                update_data["contact_flag"] = update.contact_flag
                
            elif update.action == "update_recurring":
                update_data["recurring_pattern"] = update.recurring
                
            elif update.action == "update_project":
                update_data["project"] = update.project
                
            elif update.action == "update_task":
                update_data["task"] = update.task_title
                
            elif update.action == "update_assigned_to":
                update_data["assigned_to"] = update.assigned_to
                
            elif update.action == "update_notes":
                update_data["notes"] = update.notes
                
            elif update.action == "update_estimated_hours":
                update_data["estimated_hours"] = update.estimated_hours
            
            # Execute the update
            logging.warning(f"[BULK-UPDATE] Executing: row_id={update.row_id}, source={update.source}, update_data={update_data}")
            client.update_row(update.row_id, update_data, source=update.source)
            logging.warning(f"[BULK-UPDATE] Success: row_id={update.row_id}")
            
            results.append(BulkUpdateResult(row_id=update.row_id, success=True))
            success_count += 1
            
        except Exception as exc:
            results.append(BulkUpdateResult(
                row_id=update.row_id,
                success=False,
                error=str(exc)[:200]
            ))
    
    # Log summary to conversation history for audit trail and DATA context
    if success_count > 0:
        conversation_id = f"global:{request.perspective}"
        summary = _build_bulk_update_summary(request.updates, results, success_count)
        log_assistant_message(
            conversation_id,
            content=summary,
            plan=None,
            metadata={
                "source": "bulk_update",
                "perspective": request.perspective,
                "success_count": success_count,
                "total_count": len(request.updates),
            },
        )
    
    return {
        "success": success_count == len(request.updates),
        "totalUpdates": len(request.updates),
        "successCount": success_count,
        "failureCount": len(request.updates) - success_count,
        "results": [r.model_dump(by_alias=True) for r in results],
    }


def _build_bulk_update_summary(
    updates: List[BulkTaskUpdate],
    results: List[BulkUpdateResult],
    success_count: int
) -> str:
    """Build a human-readable summary of bulk update results for conversation history."""
    from collections import Counter
    from datetime import datetime
    from daily_task_assistant.portfolio_context import USER_TIMEZONE
    
    timestamp = datetime.now(USER_TIMEZONE).strftime("%I:%M %p")
    
    # Count actions by type
    action_counts: Counter = Counter()
    for update, result in zip(updates, results):
        if result.success:
            action_counts[update.action] += 1
    
    # Build action summary
    action_labels = {
        "update_due_date": "due date changes",
        "update_number": "sequence updates",
        "mark_complete": "tasks marked complete",
        "update_status": "status changes",
        "update_priority": "priority changes",
        "add_comment": "comments added",
        "update_contact_flag": "contact flags updated",
        "update_recurring": "recurrence changes",
        "update_project": "project assignments",
        "update_task": "task renames",
        "update_assigned_to": "assignee changes",
        "update_notes": "notes updated",
        "update_estimated_hours": "hour estimates updated",
    }
    
    action_parts = []
    for action, count in action_counts.items():
        label = action_labels.get(action, action.replace("_", " "))
        action_parts.append(f"{count} {label}")
    
    failure_count = len(updates) - success_count
    
    lines = [f"📋 **Rebalancing applied** at {timestamp}"]
    lines.append("")
    
    if action_parts:
        lines.append(f"**{success_count} updates executed:**")
        for part in action_parts:
            lines.append(f"  • {part}")
    
    if failure_count > 0:
        lines.append("")
        lines.append(f"⚠️ {failure_count} update(s) failed")
    
    return "\n".join(lines)


# ============================================================================
# WORKLOAD REBALANCING
# ============================================================================

class RebalanceRequest(BaseModel):
    """Request for workload rebalancing proposal."""
    model_config = {"populate_by_name": True}
    
    perspective: Literal["personal", "church", "work", "holistic"] = "holistic"
    focus: Literal["overdue", "today", "week", "all"] = "overdue"
    include_sequencing: bool = Field(True, alias="includeSequencing", description="Include # ordering suggestions")


class RebalanceProposedChange(BaseModel):
    """A single proposed change in the rebalancing plan."""
    model_config = {"populate_by_name": True}
    
    row_id: str = Field(..., alias="rowId")
    title: str
    domain: str  # Personal, Church, Work
    current_due: str = Field(..., alias="currentDue")
    proposed_due: str = Field(..., alias="proposedDue")
    current_number: Optional[float] = Field(None, alias="currentNumber")  # 0.1-0.9 = recurring, 1+ = regular
    proposed_number: Optional[float] = Field(None, alias="proposedNumber")
    priority: str
    reason: str


@app.post("/assist/global/rebalance")
def propose_rebalancing(
    request: RebalanceRequest,
    user: str = Depends(get_current_user),
) -> dict:
    """Generate a workload rebalancing proposal.
    
    This endpoint analyzes the portfolio and generates specific date/ordering
    changes to create a more realistic workload. The proposal is returned
    for user review and modification before execution.
    
    The proposal includes:
    - Suggested new due dates for overdue/overloaded tasks
    - Suggested # ordering for today's tasks (if includeSequencing=true)
    - Reasoning for each change
    
    User can modify the proposal in the UI before sending to /bulk-update.
    """
    from daily_task_assistant.smartsheet_client import SmartsheetClient
    from daily_task_assistant.portfolio_context import build_portfolio_context
    from daily_task_assistant.llm.anthropic_client import (
        build_anthropic_client,
        resolve_config,
        AnthropicError,
    )
    from datetime import datetime, timedelta
    
    settings = _get_settings()
    
    try:
        client = SmartsheetClient(settings)
        portfolio = build_portfolio_context(client, request.perspective)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to load portfolio: {exc}")
    
    # Get tasks that need rebalancing based on focus
    tasks_to_rebalance = []
    today = datetime.now().date()
    
    for task in portfolio.task_summaries:
        try:
            due_date = datetime.fromisoformat(task["due"].replace("Z", "+00:00")).date()
        except (ValueError, KeyError):
            continue
            
        if request.focus == "overdue" and due_date < today:
            tasks_to_rebalance.append(task)
        elif request.focus == "today" and due_date == today:
            tasks_to_rebalance.append(task)
        elif request.focus == "week" and due_date <= today + timedelta(days=7):
            tasks_to_rebalance.append(task)
        elif request.focus == "all":
            tasks_to_rebalance.append(task)
    
    if not tasks_to_rebalance:
        return {
            "status": "no_changes_needed",
            "message": f"No tasks found for {request.focus} rebalancing",
            "proposedChanges": [],
        }
    
    # Build prompt for LLM to generate rebalancing proposal
    task_list = "\n".join([
        f"- [{t['row_id']}] {t['title'][:50]} | {t['priority']} | Due: {t['due'][:10]} | #: {t.get('number', '-')} | Domain: {t.get('domain', 'Unknown')}"
        for t in tasks_to_rebalance[:30]
    ])
    
    rebalance_prompt = f"""You are David's AI chief of staff. Analyze these {len(tasks_to_rebalance)} tasks and propose a realistic rebalancing plan.

TODAY: {today.isoformat()}

TASKS NEEDING REBALANCING:
{task_list}

REBALANCING RULES:
1. Spread overdue tasks across the next 1-2 weeks
2. No more than 5-7 tasks per day
3. Consider priority - Critical/Urgent should be scheduled sooner
4. Consider domain balance - don't overload one domain on a single day
5. Use weekdays primarily (Mon-Fri)
6. If includeSequencing is true, suggest # ordering for today's tasks (1-10)

OUTPUT FORMAT (JSON array):
[
  {{"row_id": "...", "proposed_due": "YYYY-MM-DD", "proposed_number": N or null, "reason": "brief reason"}}
]

Generate {min(len(tasks_to_rebalance), 20)} changes maximum. Focus on the most impactful changes."""

    try:
        llm_client = build_anthropic_client()
        config = resolve_config()
        
        response = llm_client.messages.create(
            model=config.model,
            max_tokens=2000,
            temperature=0.3,
            system="You are a task scheduling assistant. Output ONLY valid JSON arrays, no markdown.",
            messages=[{"role": "user", "content": rebalance_prompt}],
        )
        
        # Extract response text
        response_text = ""
        for block in response.content:
            if hasattr(block, "text"):
                response_text += block.text
        
        # Parse JSON from response
        import json
        import re
        
        # Try to extract JSON array from response
        json_match = re.search(r'\[[\s\S]*\]', response_text)
        if json_match:
            proposed_changes_raw = json.loads(json_match.group())
        else:
            proposed_changes_raw = []
            
    except Exception as exc:
        # Fallback: generate simple rebalancing
        proposed_changes_raw = []
        for i, task in enumerate(tasks_to_rebalance[:15]):
            days_offset = (i // 5) + 1  # Spread 5 per day
            new_date = today + timedelta(days=days_offset)
            proposed_changes_raw.append({
                "row_id": task["row_id"],
                "proposed_due": new_date.isoformat(),
                "proposed_number": (i % 5) + 1 if request.include_sequencing else None,
                "reason": "Auto-distributed to reduce overload"
            })
    
    # Build formatted response with task details
    proposed_changes = []
    task_lookup = {t["row_id"]: t for t in tasks_to_rebalance}
    
    for change in proposed_changes_raw:
        row_id = change.get("row_id")
        if row_id not in task_lookup:
            continue
            
        task = task_lookup[row_id]
        proposed_changes.append(RebalanceProposedChange(
            row_id=row_id,
            title=task.get("title", "Unknown"),
            domain=task.get("domain", "Unknown"),
            current_due=task.get("due", "")[:10],
            proposed_due=change.get("proposed_due", ""),
            current_number=task.get("number"),
            proposed_number=change.get("proposed_number"),
            priority=task.get("priority", "Standard"),
            reason=change.get("reason", ""),
        ))
    
    return {
        "status": "proposal_ready",
        "message": f"Proposed {len(proposed_changes)} changes to rebalance your {request.focus} workload",
        "perspective": request.perspective,
        "focus": request.focus,
        "proposedChanges": [c.model_dump(by_alias=True) for c in proposed_changes],
    }


class GlobalStrikeRequest(BaseModel):
    """Request body for striking/unstriking global messages."""
    message_ts: str = Field(..., alias="messageTs", description="Timestamp of the message")
    perspective: Literal["personal", "church", "work", "holistic"] = "personal"


@app.post("/assist/global/history/strike")
def strike_global_message(
    request: GlobalStrikeRequest,
    user: str = Depends(get_current_user),
) -> dict:
    """Mark a global chat message as struck (hidden from UI but preserved in DB).
    
    Struck messages are:
    - Hidden from the user interface
    - Excluded from LLM context
    - Preserved in the database for tuning/analysis
    """
    conversation_id = f"global:{request.perspective}"
    success = strike_message(conversation_id, request.message_ts)
    
    if not success:
        raise HTTPException(status_code=404, detail="Message not found")
    
    # Return updated history
    history = fetch_conversation(conversation_id, limit=50)
    return {
        "status": "struck",
        "messageTs": request.message_ts,
        "perspective": request.perspective,
        "history": [ConversationMessageModel(**asdict(msg)).model_dump() for msg in history],
    }


@app.post("/assist/global/history/unstrike")
def unstrike_global_message(
    request: GlobalStrikeRequest,
    user: str = Depends(get_current_user),
) -> dict:
    """Restore a struck global chat message (make visible again)."""
    conversation_id = f"global:{request.perspective}"
    success = unstrike_message(conversation_id, request.message_ts)
    
    if not success:
        raise HTTPException(status_code=404, detail="Message not found")
    
    # Return updated history
    history = fetch_conversation(conversation_id, limit=50)
    return {
        "status": "unstruck",
        "messageTs": request.message_ts,
        "perspective": request.perspective,
        "history": [ConversationMessageModel(**asdict(msg)).model_dump() for msg in history],
    }


class GlobalDeleteRequest(BaseModel):
    """Request body for permanently deleting a global message."""
    message_ts: str = Field(..., alias="messageTs", description="Timestamp of the message")
    perspective: Literal["personal", "church", "work", "holistic"] = "personal"


@app.delete("/assist/global/message")
def delete_global_message(
    request: GlobalDeleteRequest,
    user: str = Depends(get_current_user),
) -> dict:
    """Permanently delete a global chat message.
    
    WARNING: This is irreversible. Use strike for soft-hiding.
    Only use for truly unwanted content.
    """
    from daily_task_assistant.conversations.history import delete_message
    
    conversation_id = f"global:{request.perspective}"
    success = delete_message(conversation_id, request.message_ts)
    
    if not success:
        raise HTTPException(status_code=404, detail="Message not found")
    
    # Return updated history
    history = fetch_conversation(conversation_id, limit=50)
    return {
        "status": "deleted",
        "messageTs": request.message_ts,
        "perspective": request.perspective,
        "history": [ConversationMessageModel(**asdict(msg)).model_dump() for msg in history],
    }


# --- Task-Scoped Endpoints ---

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
        limit=None, source=request.source, include_work_in_all=True
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
    context_items: Optional[List[str]] = Field(
        None, alias="contextItems", description="User-provided context items from workspace."
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
        limit=None, source=request.source, include_work_in_all=True
    )
    target = next((task for task in tasks if task.row_id == task_id), None)
    if not target:
        raise HTTPException(status_code=404, detail="Task not found.")

    # Fetch conversation history to include in plan consideration (excluding struck messages)
    history = fetch_conversation_for_llm(task_id, limit=100)
    llm_history: List[Dict[str, str]] = [
        {"role": msg.role, "content": msg.content} for msg in history
    ]

    # Build workspace context from context items if provided
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


class StrikeRequest(BaseModel):
    """Request body for striking a message."""
    message_ts: str = Field(..., alias="messageTs", description="Timestamp of the message to strike")


@app.post("/assist/{task_id}/history/strike")
def strike_conversation_message(
    task_id: str,
    request: StrikeRequest,
    user: str = Depends(get_current_user),
) -> dict:
    """Strike (hide) a message from the conversation.
    
    Struck messages are hidden from the UI and excluded from LLM context.
    """
    success = strike_message(task_id, request.message_ts)
    if not success:
        raise HTTPException(status_code=404, detail="Message not found.")
    
    # Return updated history
    history = fetch_conversation(task_id, limit=100)
    return {
        "status": "struck",
        "messageTs": request.message_ts,
        "history": [ConversationMessageModel(**asdict(msg)).model_dump() for msg in history],
    }


@app.post("/assist/{task_id}/history/unstrike")
def unstrike_conversation_message(
    task_id: str,
    request: StrikeRequest,
    user: str = Depends(get_current_user),
) -> dict:
    """Unstrike (restore) a previously struck message."""
    success = unstrike_message(task_id, request.message_ts)
    if not success:
        raise HTTPException(status_code=404, detail="Message not found.")
    
    # Return updated history
    history = fetch_conversation(task_id, limit=100)
    return {
        "status": "unstruck",
        "messageTs": request.message_ts,
        "history": [ConversationMessageModel(**asdict(msg)).model_dump() for msg in history],
    }


class ChatRequest(BaseModel):
    """Request body for chat endpoint."""
    model_config = {"populate_by_name": True}

    message: str = Field(..., description="The user's message")
    source: Literal["auto", "live", "stub"] = "auto"
    workspace_context: Optional[str] = Field(
        None,
        alias="workspaceContext",
        description="Selected workspace content to include in context"
    )


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
        limit=None, source=request.source, include_work_in_all=True
    )
    target = next((task for task in tasks if task.row_id == task_id), None)
    if not target:
        raise HTTPException(status_code=404, detail="Task not found.")

    # Fetch existing conversation history (full history for logging, filtered for LLM)
    history = fetch_conversation(task_id, limit=50)
    llm_history_messages = fetch_conversation_for_llm(task_id, limit=50)

    # Log the user message
    user_turn = log_user_message(
        task_id,
        content=request.message,
        user_email=user,
        metadata={"source": request.source},
    )

    # Build history for LLM (excluding struck messages and the message we just logged)
    llm_history: List[Dict[str, str]] = [
        {"role": msg.role, "content": msg.content} for msg in llm_history_messages
    ]

    # Call Anthropic with tool support for task updates
    try:
        chat_response = chat_with_tools(
            task=target,
            user_message=request.message,
            history=llm_history,
            workspace_context=request.workspace_context,
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
    
    # Include email draft update if DATA suggested changes
    if chat_response.email_draft_update:
        update = chat_response.email_draft_update
        response_data["emailDraftUpdate"] = {
            "subject": update.subject,
            "body": update.body,
            "reason": update.reason,
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


def _summarize_summary(full_summary: str, max_length: int = 250) -> str:
    """Extract key points from a summary for conversation history."""
    lines = full_summary.split('\n')
    key_points = []
    
    for line in lines:
        stripped = line.strip()
        # Skip headers and empty lines
        if not stripped or stripped.startswith('#'):
            continue
        # Capture bullet points
        if stripped.startswith('-') or stripped.startswith('•'):
            clean_line = stripped.lstrip('-•').strip()
            if clean_line and len(clean_line) > 10:  # Skip very short items
                key_points.append(clean_line)
                if len(key_points) >= 4:  # Max 4 key points
                    break
        # Or capture the first substantive paragraph
        elif len(key_points) == 0 and len(stripped) > 30:
            key_points.append(stripped)
    
    if key_points:
        summary = "; ".join(key_points)
        if len(summary) > max_length:
            summary = summary[:max_length-3] + "..."
        return f"📋 **Summary generated**: {summary}"
    
    # Fallback: just truncate the beginning
    truncated = full_summary[:max_length-3].rsplit(' ', 1)[0] + "..."
    return f"📋 **Summary generated**: {truncated}"


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
        limit=None, source=request.source, include_work_in_all=True
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


class ContactRequest(BaseModel):
    """Request body for contact search endpoint."""
    source: Literal["auto", "live", "stub"] = "auto"
    confirm_search: bool = Field(False, alias="confirmSearch")


class ContactCardModel(BaseModel):
    """A contact card returned from search."""
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    title: Optional[str] = None
    organization: Optional[str] = None
    location: Optional[str] = None
    source: str = "unknown"
    confidence: str = "low"
    sourceUrl: Optional[str] = Field(None, alias="source_url")


class ContactSearchResponse(BaseModel):
    """Response from contact search."""
    contacts: List[ContactCardModel]
    entitiesFound: List[Dict[str, Any]]
    needsConfirmation: bool
    confirmationMessage: Optional[str] = None
    searchPerformed: bool
    message: str
    taskId: str
    taskTitle: str


@app.post("/assist/{task_id}/contact")
def contact_search_endpoint(
    task_id: str,
    request: ContactRequest,
    user: str = Depends(get_current_user),
) -> dict:
    """Search for contact information related to a task.
    
    Extracts entities (people, organizations) from task details and searches
    for their contact information. Returns structured contact cards.
    """
    from daily_task_assistant.contacts import search_contacts, ContactCard

    tasks, live_tasks, settings, warning = fetch_task_dataset(
        limit=None, source=request.source, include_work_in_all=True
    )
    target = next((task for task in tasks if task.row_id == task_id), None)
    if not target:
        raise HTTPException(status_code=404, detail="Task not found.")

    # Perform contact search
    result = search_contacts(target)
    
    # If confirmation is needed and not confirmed, return early
    if result.needs_confirmation and not request.confirm_search:
        return {
            "contacts": [],
            "entitiesFound": [
                {"name": e.name, "entityType": e.entity_type, "context": e.context}
                for e in result.entities_found
            ],
            "needsConfirmation": True,
            "confirmationMessage": result.confirmation_message,
            "searchPerformed": False,
            "message": result.message,
            "taskId": task_id,
            "taskTitle": target.title,
        }
    
    # If confirmed and needs search, search again with confirmation
    if result.needs_confirmation and request.confirm_search:
        # Re-run search (the search function will proceed past confirmation)
        result = search_contacts(target)
    
    # Format contacts for response
    contacts_data = [
        {
            "name": c.name,
            "email": c.email,
            "phone": c.phone,
            "title": c.title,
            "organization": c.organization,
            "location": c.location,
            "source": c.source,
            "confidence": c.confidence,
            "sourceUrl": c.source_url,
        }
        for c in result.contacts
    ]
    
    # Log to conversation if contacts found
    if result.contacts:
        contact_summary = f"📇 **Found {len(result.contacts)} contact(s)**: "
        contact_names = [c.name for c in result.contacts[:3]]
        contact_summary += ", ".join(contact_names)
        if len(result.contacts) > 3:
            contact_summary += f" (+{len(result.contacts) - 3} more)"
        
        log_assistant_message(
            task_id,
            content=contact_summary,
            plan=None,
            metadata={"source": "contact", "contact_count": len(result.contacts)},
        )
    
    # Fetch updated history
    updated_history = fetch_conversation(task_id, limit=100)
    
    return {
        "contacts": contacts_data,
        "entitiesFound": [
            {"name": e.name, "entityType": e.entity_type, "context": e.context}
            for e in result.entities_found
        ],
        "needsConfirmation": False,
        "confirmationMessage": None,
        "searchPerformed": result.search_performed,
        "message": result.message,
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
        limit=None, source=request.source, include_work_in_all=True
    )
    target = next((task for task in tasks if task.row_id == task_id), None)
    if not target:
        raise HTTPException(status_code=404, detail="Task not found.")

    # Fetch conversation history (excluding struck messages for LLM)
    history = fetch_conversation_for_llm(task_id, limit=100)
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

    # Log a condensed version of the summary to the conversation history
    summary_excerpt = _summarize_summary(summary_results)
    log_assistant_message(
        task_id,
        content=summary_excerpt,
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


# --- Email Draft endpoints ---

class EmailDraftRequest(BaseModel):
    """Request body for draft email endpoint."""
    source: Literal["auto", "live", "stub"] = "auto"
    source_content: Optional[str] = Field(None, alias="sourceContent", description="Workspace content to transform into email")
    recipient: Optional[str] = Field(None, description="Recipient email address")
    regenerate_input: Optional[str] = Field(None, alias="regenerateInput", description="Instructions for regenerating the draft")


class EmailDraftResponse(BaseModel):
    """Response from draft email endpoint."""
    subject: str
    body: str
    body_html: str = Field(alias="bodyHtml")
    needs_recipient: bool = Field(alias="needsRecipient")
    task_id: str = Field(alias="taskId")
    task_title: str = Field(alias="taskTitle")


@app.post("/assist/{task_id}/draft-email")
def draft_email_endpoint(
    task_id: str,
    request: EmailDraftRequest,
    user: str = Depends(get_current_user),
) -> dict:
    """Generate an email draft based on task context and optional workspace content.
    
    If sourceContent is provided, it will be used as the primary content for the email.
    Otherwise, the task notes and context will be used.
    """
    from daily_task_assistant.llm.anthropic_client import generate_email_draft, AnthropicError

    tasks, live_tasks, settings, warning = fetch_task_dataset(
        limit=None, source=request.source, include_work_in_all=True
    )
    target = next((task for task in tasks if task.row_id == task_id), None)
    if not target:
        raise HTTPException(status_code=404, detail="Task not found.")

    # Build source content - include regenerate instructions if provided
    source_content = request.source_content
    if request.regenerate_input and source_content:
        source_content = f"{source_content}\n\n[User instructions: {request.regenerate_input}]"

    try:
        draft_result = generate_email_draft(
            task=target,
            recipient=request.recipient,
            source_content=source_content,
        )
    except AnthropicError as exc:
        raise HTTPException(status_code=502, detail=f"Email draft failed: {exc}")

    return {
        "subject": draft_result.subject,
        "body": draft_result.body,
        "bodyHtml": draft_result.body_html,
        "needsRecipient": draft_result.needs_recipient,
        "taskId": task_id,
        "taskTitle": target.title,
    }


class SendEmailRequest(BaseModel):
    """Request body for sending email."""
    source: Literal["auto", "live", "stub"] = "auto"
    account: str = Field(..., description="Gmail account prefix (e.g., 'church' or 'personal')")
    to: List[str] = Field(..., description="List of recipient email addresses")
    cc: Optional[List[str]] = Field(None, description="List of CC email addresses")
    subject: str
    body: str


@app.post("/assist/{task_id}/send-email")
def send_email_endpoint(
    task_id: str,
    request: SendEmailRequest,
    user: str = Depends(get_current_user),
) -> dict:
    """Send an email via Gmail API and log to conversation + Smartsheet.
    
    Sends the email using the specified Gmail account, then logs the action
    to the conversation history and posts a comment to Smartsheet.
    """
    from daily_task_assistant.mailer import GmailError, load_account_from_env, send_email

    tasks, live_tasks, settings, warning = fetch_task_dataset(
        limit=None, source=request.source, include_work_in_all=True
    )
    target = next((task for task in tasks if task.row_id == task_id), None)
    if not target:
        raise HTTPException(status_code=404, detail="Task not found.")

    # Load Gmail account configuration
    try:
        gmail_config = load_account_from_env(request.account)
    except GmailError as exc:
        raise HTTPException(status_code=400, detail=f"Gmail configuration error: {exc}")

    # Combine recipients for sending
    all_recipients = request.to.copy()
    if request.cc:
        all_recipients.extend(request.cc)

    # Send to primary recipient (Gmail API sends one at a time for simple case)
    # For multiple recipients, we include them all in the To field
    to_address = ", ".join(request.to)
    
    # Build body with CC note if applicable
    email_body = request.body
    if request.cc:
        cc_line = f"CC: {', '.join(request.cc)}\n\n"
        # Note: For proper CC handling, we'd need to modify the email builder
        # For now, we'll send to all recipients in To field

    try:
        message_id = send_email(
            account=gmail_config,
            to_address=to_address,
            subject=request.subject,
            body=email_body,
        )
    except GmailError as exc:
        raise HTTPException(status_code=502, detail=f"Email send failed: {exc}")

    # Log to conversation history
    recipient_display = to_address
    if request.cc:
        recipient_display += f" (CC: {', '.join(request.cc)})"
    
    log_assistant_message(
        task_id,
        content=f"✉️ **Email sent** via {request.account} account\n\n**To:** {recipient_display}\n**Subject:** {request.subject}",
        plan=None,
        metadata={
            "source": "email_sent",
            "account": request.account,
            "recipients": request.to,
            "cc": request.cc,
            "subject": request.subject,
            "message_id": message_id,
        },
    )

    # Post Smartsheet comment if using live data
    comment_posted = False
    comment_error = None
    if live_tasks:
        try:
            from daily_task_assistant.smartsheet_client import SmartsheetClient
            client = SmartsheetClient(settings=settings)
            client.post_comment(
                row_id=task_id,
                text=f"Email sent: \"{request.subject}\" to {recipient_display} via {request.account} account",
            )
            comment_posted = True
        except Exception as exc:
            # Log warning but don't fail the request
            comment_error = str(exc)
            print(f"WARNING: Failed to post Smartsheet comment for task {task_id}: {exc}")
    else:
        print(f"INFO: Skipping Smartsheet comment - live_tasks is False (source: {request.source})")

    # Fetch updated history to return
    updated_history = fetch_conversation(task_id, limit=100)

    # Delete the draft after successful send
    from daily_task_assistant.drafts import delete_draft
    delete_draft(task_id)

    return {
        "status": "sent",
        "messageId": message_id,
        "taskId": task_id,
        "commentPosted": comment_posted,
        "commentError": comment_error,
        "liveTasks": live_tasks,  # Debug: verify live_tasks flag
        "history": [
            ConversationMessageModel(**asdict(msg)).model_dump()
            for msg in updated_history
        ],
    }


# --- Email Draft Persistence endpoints ---

class SaveDraftRequest(BaseModel):
    """Request body for saving an email draft."""
    to: List[str] = Field(default_factory=list, description="List of recipient email addresses")
    cc: List[str] = Field(default_factory=list, description="List of CC email addresses")
    subject: str = ""
    body: str = ""
    fromAccount: str = Field("", alias="from_account", description="Gmail account prefix")
    sourceContent: str = Field("", alias="source_content", description="Original content used to generate draft")


@app.get("/assist/{task_id}/draft")
def get_draft(
    task_id: str,
    user: str = Depends(get_current_user),
) -> dict:
    """Load a saved email draft for a task.
    
    Returns the draft if one exists, or empty fields if not.
    """
    from daily_task_assistant.drafts import load_draft
    
    draft = load_draft(task_id)
    has_draft = bool(draft.subject or draft.body or draft.to)
    
    return {
        "taskId": task_id,
        "hasDraft": has_draft,
        "draft": draft.to_dict() if has_draft else None,
    }


@app.post("/assist/{task_id}/draft")
def save_draft_endpoint(
    task_id: str,
    request: SaveDraftRequest,
    user: str = Depends(get_current_user),
) -> dict:
    """Save an email draft for a task.
    
    Drafts persist until explicitly deleted or until the email is sent.
    """
    from daily_task_assistant.drafts import save_draft
    
    draft = save_draft(
        task_id=task_id,
        to=request.to,
        cc=request.cc,
        subject=request.subject,
        body=request.body,
        from_account=request.fromAccount,
        source_content=request.sourceContent,
    )
    
    return {
        "status": "saved",
        "taskId": task_id,
        "draft": draft.to_dict(),
    }


@app.delete("/assist/{task_id}/draft")
def delete_draft_endpoint(
    task_id: str,
    user: str = Depends(get_current_user),
) -> dict:
    """Delete an email draft for a task.
    
    Called when user explicitly discards a draft.
    """
    from daily_task_assistant.drafts import delete_draft
    
    delete_draft(task_id)
    
    return {
        "status": "deleted",
        "taskId": task_id,
    }


# --- Inbox Reading endpoints ---

class EmailMessageModel(BaseModel):
    """Response model for an email message."""
    model_config = {"populate_by_name": True}
    
    id: str
    thread_id: str = Field(alias="threadId")
    from_address: str = Field(alias="fromAddress")
    from_name: str = Field(alias="fromName")
    to_address: str = Field(alias="toAddress")
    subject: str
    snippet: str
    date: str
    is_unread: bool = Field(alias="isUnread")
    is_important: bool = Field(alias="isImportant")
    is_starred: bool = Field(alias="isStarred")
    age_hours: float = Field(alias="ageHours")


class InboxSummaryModel(BaseModel):
    """Response model for inbox summary."""
    model_config = {"populate_by_name": True}
    
    total_unread: int = Field(alias="totalUnread")
    unread_important: int = Field(alias="unreadImportant")
    unread_from_vips: int = Field(alias="unreadFromVips")
    recent_messages: List[EmailMessageModel] = Field(alias="recentMessages")
    vip_messages: List[EmailMessageModel] = Field(alias="vipMessages")


def _email_to_model(msg, include_body: bool = False) -> dict:
    """Convert EmailMessage to dict for API response.
    
    Args:
        msg: EmailMessage object.
        include_body: If True, include body content and attachments.
        
    Returns:
        Dict representation for JSON response.
    """
    result = {
        "id": msg.id,
        "threadId": msg.thread_id,
        "fromAddress": msg.from_address,
        "fromName": msg.from_name,
        "toAddress": msg.to_address,
        "subject": msg.subject,
        "snippet": msg.snippet,
        "date": msg.date.isoformat(),
        "isUnread": msg.is_unread,
        "isImportant": msg.is_important,
        "isStarred": msg.is_starred,
        "ageHours": round(msg.age_hours(), 2),
        "labels": msg.labels,
    }
    
    if include_body:
        result["body"] = msg.body
        result["bodyHtml"] = msg.body_html
        result["ccAddress"] = msg.cc_address
        result["messageIdHeader"] = msg.message_id_header
        result["references"] = msg.references
        result["attachmentCount"] = msg.attachment_count
        result["attachments"] = [
            {
                "filename": a.filename,
                "mimeType": a.mime_type,
                "size": a.size,
                "attachmentId": a.attachment_id,
            }
            for a in (msg.attachments or [])
        ]
    
    return result


@app.get("/inbox/{account}")
def get_inbox(
    account: Literal["church", "personal"],
    max_results: int = Query(20, ge=1, le=100),
    user: str = Depends(get_current_user),
) -> dict:
    """Get inbox summary for a Gmail account.
    
    Returns unread counts and recent messages.
    """
    from daily_task_assistant.mailer import (
        GmailError,
        load_account_from_env,
        get_inbox_summary,
    )
    
    try:
        gmail_config = load_account_from_env(account)
    except GmailError as exc:
        raise HTTPException(status_code=400, detail=f"Gmail config error: {exc}")
    
    try:
        summary = get_inbox_summary(gmail_config, max_recent=max_results)
    except GmailError as exc:
        raise HTTPException(status_code=502, detail=f"Gmail API error: {exc}")
    
    return {
        "account": account,
        "email": gmail_config.from_address,
        "totalUnread": summary.total_unread,
        "unreadImportant": summary.unread_important,
        "unreadFromVips": summary.unread_from_vips,
        "recentMessages": [_email_to_model(m) for m in summary.recent_messages],
        "vipMessages": [_email_to_model(m) for m in summary.vip_messages],
    }


@app.get("/inbox/{account}/unread")
def get_unread(
    account: Literal["church", "personal"],
    max_results: int = Query(20, ge=1, le=100),
    from_filter: Optional[str] = Query(None, description="Filter by sender"),
    user: str = Depends(get_current_user),
) -> dict:
    """Get unread messages from a Gmail account.
    
    Optionally filter by sender address pattern.
    """
    from daily_task_assistant.mailer import (
        GmailError,
        load_account_from_env,
        get_unread_messages,
    )
    
    try:
        gmail_config = load_account_from_env(account)
    except GmailError as exc:
        raise HTTPException(status_code=400, detail=f"Gmail config error: {exc}")
    
    try:
        messages = get_unread_messages(
            gmail_config,
            max_results=max_results,
            from_filter=from_filter,
        )
    except GmailError as exc:
        raise HTTPException(status_code=502, detail=f"Gmail API error: {exc}")
    
    return {
        "account": account,
        "email": gmail_config.from_address,
        "count": len(messages),
        "messages": [_email_to_model(m) for m in messages],
    }


@app.get("/inbox/{account}/search")
def search_inbox(
    account: Literal["church", "personal"],
    q: str = Query(..., description="Gmail search query"),
    max_results: int = Query(20, ge=1, le=100),
    user: str = Depends(get_current_user),
) -> dict:
    """Search messages in a Gmail account.
    
    Uses Gmail search syntax (e.g., "is:unread from:boss@company.com").
    
    Examples:
    - is:unread subject:urgent
    - from:@company.com after:2025/01/01
    - has:attachment filename:pdf
    """
    from daily_task_assistant.mailer import (
        GmailError,
        load_account_from_env,
        search_messages,
    )
    
    try:
        gmail_config = load_account_from_env(account)
    except GmailError as exc:
        raise HTTPException(status_code=400, detail=f"Gmail config error: {exc}")
    
    try:
        messages = search_messages(gmail_config, query=q, max_results=max_results)
    except GmailError as exc:
        raise HTTPException(status_code=502, detail=f"Gmail API error: {exc}")
    
    return {
        "account": account,
        "email": gmail_config.from_address,
        "query": q,
        "count": len(messages),
        "messages": [_email_to_model(m) for m in messages],
    }


@app.get("/email/{account}/message/{message_id}")
def get_email_full(
    account: Literal["church", "personal"],
    message_id: str,
    full: bool = Query(True, description="Include full body content"),
    user: str = Depends(get_current_user),
) -> dict:
    """Get a single email message with optional full body content.
    
    When full=True, includes:
    - Plain text and HTML body
    - CC recipients
    - Message-ID and References headers (for replying)
    - Attachment metadata
    """
    from daily_task_assistant.mailer import (
        GmailError,
        load_account_from_env,
        get_message,
    )
    
    try:
        gmail_config = load_account_from_env(account)
    except GmailError as exc:
        raise HTTPException(status_code=400, detail=f"Gmail config error: {exc}")
    
    try:
        # Use "full" format to get body content
        format_type = "full" if full else "metadata"
        msg = get_message(gmail_config, message_id, format=format_type)
    except GmailError as exc:
        raise HTTPException(status_code=502, detail=f"Gmail API error: {exc}")
    
    return {
        "account": account,
        "message": _email_to_model(msg, include_body=full),
    }


@app.get("/email/{account}/thread/{thread_id}")
def get_thread_context(
    account: Literal["church", "personal"],
    thread_id: str,
    user: str = Depends(get_current_user),
) -> dict:
    """Get thread context for composing a reply.
    
    Returns all messages in the thread with:
    - An AI-summarized thread context (for long threads)
    - The full content of the most recent message
    - A condensed view of earlier messages
    
    This helps DATA understand the conversation context without
    loading excessive data.
    """
    from daily_task_assistant.mailer import (
        GmailError,
        load_account_from_env,
        get_message,
    )
    
    try:
        gmail_config = load_account_from_env(account)
    except GmailError as exc:
        raise HTTPException(status_code=400, detail=f"Gmail config error: {exc}")
    
    # Get thread messages via Gmail API
    access_token = None
    try:
        from daily_task_assistant.mailer.gmail import _fetch_access_token
        import json
        from urllib import request as urlrequest
        from urllib import error as urlerror
        
        access_token = _fetch_access_token(gmail_config)
        
        # Fetch the thread
        thread_url = f"https://gmail.googleapis.com/gmail/v1/users/me/threads/{thread_id}?format=full"
        headers = {"Authorization": f"Bearer {access_token}"}
        
        req = urlrequest.Request(thread_url, headers=headers, method="GET")
        with urlrequest.urlopen(req, timeout=30) as resp:
            thread_data = json.loads(resp.read().decode("utf-8"))
    except urlerror.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise HTTPException(status_code=502, detail=f"Gmail API error ({exc.code}): {detail}")
    except urlerror.URLError as exc:
        raise HTTPException(status_code=502, detail=f"Gmail network error: {exc}")
    
    # Parse messages from thread
    from daily_task_assistant.mailer.inbox import _parse_message
    
    thread_messages = []
    for msg_data in thread_data.get("messages", []):
        msg = _parse_message(msg_data, include_body=True)
        thread_messages.append(msg)
    
    # Sort by date (oldest first for reading context)
    thread_messages.sort(key=lambda m: m.date)
    
    # Build condensed context for older messages, full body for most recent
    messages_for_response = []
    for i, msg in enumerate(thread_messages):
        is_latest = (i == len(thread_messages) - 1)
        messages_for_response.append(_email_to_model(msg, include_body=is_latest))
    
    # Generate AI summary for long threads (>3 messages)
    thread_summary = None
    if len(thread_messages) > 3:
        thread_summary = _summarize_thread(thread_messages)
    
    return {
        "account": account,
        "threadId": thread_id,
        "messageCount": len(thread_messages),
        "summary": thread_summary,
        "messages": messages_for_response,
    }


def _summarize_thread(messages: list) -> str:
    """Generate a brief summary of an email thread.
    
    Uses a lightweight summarization to provide context without
    overwhelming the reply generation prompt.
    """
    # Build a simple text representation of the thread
    thread_text_parts = []
    for msg in messages[:-1]:  # Exclude the last message (which will be shown in full)
        sender = msg.from_name or msg.from_address
        date_str = msg.date.strftime("%b %d")
        body_preview = (msg.body or msg.snippet or "")[:200]
        if len(msg.body or msg.snippet or "") > 200:
            body_preview += "..."
        thread_text_parts.append(f"[{date_str}] {sender}: {body_preview}")
    
    thread_text = "\n\n".join(thread_text_parts)
    
    # For now, return a structured summary without AI
    # This can be upgraded to use Gemini Flash for longer threads
    if len(thread_text_parts) <= 5:
        return f"Thread with {len(messages)} messages. Earlier exchanges:\n" + thread_text
    
    # For very long threads, try AI summarization
    try:
        from daily_task_assistant.llm.anthropic_client import get_client
        
        client = get_client()
        response = client.messages.create(
            model="claude-3-haiku-20240307",  # Fast, cheap model for summarization
            max_tokens=300,
            system="You are summarizing an email thread to help someone write a reply. Be concise and focus on: (1) Main topic, (2) Key points discussed, (3) Any action items or questions raised. Keep it under 100 words.",
            messages=[
                {"role": "user", "content": f"Summarize this email thread:\n\n{thread_text}"}
            ],
        )
        return response.content[0].text
    except Exception:
        # Fall back to simple summary if AI fails
        return f"Thread with {len(messages)} messages discussing: {messages[0].subject}"


# --- Email Management endpoints ---

class FilterRuleModel(BaseModel):
    """Response model for a filter rule."""
    model_config = {"populate_by_name": True}
    
    email_account: str = Field(alias="emailAccount")
    order: int
    category: str
    field: str
    operator: str
    value: str
    action: str = ""
    row_number: Optional[int] = Field(None, alias="rowNumber")


class RuleSuggestionModel(BaseModel):
    """Response model for a rule suggestion."""
    model_config = {"populate_by_name": True}
    
    type: str
    suggested_rule: FilterRuleModel = Field(alias="suggestedRule")
    confidence: str
    reason: str
    examples: List[str]
    email_count: int = Field(alias="emailCount")


class AttentionItemModel(BaseModel):
    """Response model for an attention item."""
    model_config = {"populate_by_name": True}
    
    email_id: str = Field(alias="emailId")
    subject: str
    from_address: str = Field(alias="fromAddress")
    from_name: str = Field(alias="fromName")
    date: str
    reason: str
    urgency: str
    suggested_action: Optional[str] = Field(None, alias="suggestedAction")
    extracted_deadline: Optional[str] = Field(None, alias="extractedDeadline")
    extracted_task: Optional[str] = Field(None, alias="extractedTask")


class AddRuleRequest(BaseModel):
    """Request body for adding a filter rule."""
    model_config = {"populate_by_name": True}
    
    email_account: str = Field(..., alias="emailAccount")
    order: int = Field(1, ge=1, le=7)
    category: str
    field: str
    operator: str
    value: str
    action: str = "Add"


class SyncRulesRequest(BaseModel):
    """Request body for syncing rules to Google Sheet."""
    model_config = {"populate_by_name": True}
    
    email_account: str = Field(..., alias="emailAccount")
    rules: List[FilterRuleModel]


@app.get("/email/rules/{account}")
def get_filter_rules(
    account: Literal["church", "personal"],
    user: str = Depends(get_current_user),
) -> dict:
    """Get filter rules for an email account from Google Sheets.
    
    Returns the current filter rules that App Script uses for labeling.
    """
    from daily_task_assistant.sheets import FilterRulesManager, SheetsError
    from daily_task_assistant.mailer import GmailError, load_account_from_env
    
    # Get the email address for this account
    try:
        gmail_config = load_account_from_env(account)
        email_address = gmail_config.from_address
    except GmailError as exc:
        raise HTTPException(status_code=400, detail=f"Gmail config error: {exc}")
    
    # Load rules from Google Sheets
    try:
        manager = FilterRulesManager.from_env(account.upper())
        rules = manager.get_rules_for_account(email_address)
    except SheetsError as exc:
        raise HTTPException(status_code=502, detail=f"Google Sheets error: {exc}")
    
    return {
        "account": account,
        "email": email_address,
        "ruleCount": len(rules),
        "rules": [
            {
                "emailAccount": r.email_account,
                "order": r.order,
                "category": r.category,
                "field": r.field,
                "operator": r.operator,
                "value": r.value,
                "action": r.action,
                "rowNumber": r.row_number,
            }
            for r in rules
        ],
    }


@app.post("/email/rules/{account}")
def add_filter_rule(
    account: Literal["church", "personal"],
    request: AddRuleRequest,
    user: str = Depends(get_current_user),
) -> dict:
    """Add a new filter rule to Google Sheets.
    
    This immediately adds the rule to the Gmail_Filter_Index sheet.
    App Script will pick it up on its next run.
    """
    from daily_task_assistant.sheets import FilterRulesManager, FilterRule, SheetsError
    
    try:
        manager = FilterRulesManager.from_env(account.upper())
        
        rule = FilterRule(
            email_account=request.email_account,
            order=request.order,
            category=request.category,
            field=request.field,
            operator=request.operator,
            value=request.value,
            action=request.action,
        )
        
        added_rule = manager.add_rule(rule)
        
    except SheetsError as exc:
        raise HTTPException(status_code=502, detail=f"Google Sheets error: {exc}")
    
    return {
        "status": "added",
        "account": account,
        "rule": {
            "emailAccount": added_rule.email_account,
            "order": added_rule.order,
            "category": added_rule.category,
            "field": added_rule.field,
            "operator": added_rule.operator,
            "value": added_rule.value,
            "action": added_rule.action,
            "rowNumber": added_rule.row_number,
        },
    }


@app.delete("/email/rules/{account}/{row_number}")
def delete_filter_rule(
    account: Literal["church", "personal"],
    row_number: int,
    user: str = Depends(get_current_user),
) -> dict:
    """Delete a filter rule from Google Sheets.
    
    Clears the row content rather than deleting to preserve row structure.
    """
    from daily_task_assistant.sheets import FilterRulesManager, SheetsError
    
    try:
        manager = FilterRulesManager.from_env(account.upper())
        manager.delete_rule(row_number)
    except SheetsError as exc:
        raise HTTPException(status_code=502, detail=f"Google Sheets error: {exc}")
    
    return {
        "status": "deleted",
        "account": account,
        "rowNumber": row_number,
    }


def _confidence_level_to_float(confidence_value: str) -> float:
    """Convert ConfidenceLevel enum value to float for storage.

    Args:
        confidence_value: The .value of a ConfidenceLevel enum ("high", "medium", "low")

    Returns:
        Float confidence score 0.0-1.0
    """
    return {"high": 0.9, "medium": 0.7, "low": 0.5}.get(confidence_value, 0.5)


@app.get("/email/analyze/{account}")
def analyze_inbox(
    account: Literal["church", "personal"],
    max_messages: int = Query(50, ge=10, le=100),
    user: str = Depends(get_current_user),
) -> dict:
    """Analyze inbox patterns and suggest filter rules.

    Reads recent emails and identifies:
    - New senders not covered by existing rules
    - Promotional/transactional patterns
    - Emails requiring David's attention

    Uses persistence to:
    - Skip already-analyzed emails
    - Filter out dismissed attention items
    - Save new attention items for future sessions

    Returns suggestions that can be approved to add as rules.
    """
    from daily_task_assistant.mailer import (
        GmailError,
        load_account_from_env,
        get_unread_messages,
        search_messages,
    )
    from daily_task_assistant.sheets import FilterRulesManager, SheetsError
    from daily_task_assistant.email import (
        EmailAnalyzer,
        AttentionRecord,
        save_attention,
        list_active_attention,
        get_dismissed_email_ids,
        purge_expired_records,
        detect_attention_with_haiku,
        get_haiku_usage_summary,
        generate_rule_suggestions_with_haiku,
        generate_action_suggestions_with_haiku,
        create_suggestion,
        has_pending_suggestion_for_email,
        create_rule_suggestion,
        has_pending_rule_for_pattern,
        list_pending_rules,
        LastAnalysisRecord,
        save_last_analysis,
    )
    from daily_task_assistant.memory.profile import get_or_create_profile

    # Load Gmail config
    try:
        gmail_config = load_account_from_env(account)
        email_address = gmail_config.from_address
    except GmailError as exc:
        raise HTTPException(status_code=400, detail=f"Gmail config error: {exc}")

    # Purge expired records (opportunistic cleanup)
    try:
        purge_expired_records(account)
    except Exception as e:
        logger.warning(f"[analyze_inbox] Failed to purge expired records: {e}")

    # Get set of dismissed email IDs to filter out
    dismissed_ids = get_dismissed_email_ids(account)

    # Get already-active attention items from persistence
    persisted_attention = list_active_attention(account)
    persisted_email_ids = {r.email_id for r in persisted_attention}

    # Build account-specific query to scan beyond just inbox
    # This catches action items that automations have filed to labels
    config = ATTENTION_SCAN_CONFIG.get(account, {"include": [], "exclude": []})

    # Build label inclusion part (inbox + action-oriented labels)
    label_parts = ["in:inbox"]
    for label in config["include"]:
        # Handle labels with spaces
        if " " in label:
            label_parts.append(f'label:"{label}"')
        else:
            label_parts.append(f"label:{label}")

    # Build exclusion part (skip junk/promotional)
    exclude_parts = ["-in:spam"]
    for label in config["exclude"]:
        exclude_parts.append(f"-label:{label}")

    # Combine into query: recent emails in action-oriented locations
    action_labels_query = (
        f"newer_than:7d {' '.join(exclude_parts)} ({' OR '.join(label_parts)})"
    )

    logger.info(f"[analyze_inbox] Query for {account}: {action_labels_query}")

    # Get recent messages for analysis
    # Use format="full" to fetch email bodies for Haiku analysis of short-snippet emails
    try:
        messages = search_messages(
            gmail_config,
            query=action_labels_query,
            max_results=max_messages,
            format="full",
        )
    except GmailError as exc:
        raise HTTPException(status_code=502, detail=f"Gmail API error: {exc}")

    # Filter out dismissed and already-persisted emails before analysis
    messages_to_analyze = [
        m for m in messages
        if m.id not in dismissed_ids and m.id not in persisted_email_ids
    ]

    logger.info(
        f"[analyze_inbox] {len(messages)} fetched, "
        f"{len(dismissed_ids)} dismissed, "
        f"{len(persisted_email_ids)} already tracked, "
        f"{len(messages_to_analyze)} to analyze"
    )

    # Load existing rules
    existing_rules = []
    try:
        manager = FilterRulesManager.from_env(account.upper())
        existing_rules = manager.get_rules_for_account(email_address)
    except SheetsError:
        # Continue without existing rules
        pass

    # Load GLOBAL profile for role-aware analysis
    profile = get_or_create_profile()
    logger.info(
        f"[analyze_inbox] Loaded profile with {len(profile.church_roles)} church roles, "
        f"{len(profile.personal_contexts)} personal contexts"
    )

    # Use Haiku-enhanced analysis for attention detection (with automatic fallback)
    # This also returns haiku_results for use in rule/action suggestions
    new_attention_items, haiku_results = detect_attention_with_haiku(
        messages=messages_to_analyze,
        email_account=account,
        user_id=user,  # Required for usage tracking
        church_roles=profile.church_roles,
        personal_contexts=profile.personal_contexts,
        vip_senders=profile.vip_senders,
        church_attention_patterns=profile.church_attention_patterns,
        personal_attention_patterns=profile.personal_attention_patterns,
        not_actionable_patterns=profile.not_actionable_patterns,
    )

    # Log Haiku analysis results
    haiku_analyzed = sum(1 for r in haiku_results.values() if r.analysis_method == "haiku")
    logger.info(
        f"[analyze_inbox] Haiku analyzed {haiku_analyzed}/{len(messages_to_analyze)} emails"
    )

    # Generate rule suggestions using Haiku results (with fallback to regex)
    suggestions = generate_rule_suggestions_with_haiku(
        messages=messages_to_analyze,
        email_account=account,
        haiku_results=haiku_results,
        existing_rules=existing_rules,
    )

    # Persist rule suggestions (for Trust Gradient tracking)
    # Skip duplicates (already pending or matches existing rule in Sheets)
    persisted_rule_suggestions = []
    for s in suggestions:
        # Check for duplicate pending suggestions
        if has_pending_rule_for_pattern(
            account,
            field=s.suggested_rule.field,
            value=s.suggested_rule.value,
        ):
            logger.debug(f"[analyze_inbox] Skipping duplicate rule: {s.suggested_rule.value}")
            continue

        try:
            # Convert FilterRule to dict for storage
            rule_dict = {
                "field": s.suggested_rule.field,
                "operator": s.suggested_rule.operator,
                "value": s.suggested_rule.value,
                "action": s.suggested_rule.action,
                "category": s.suggested_rule.category,
                "email_account": s.suggested_rule.email_account,
                "order": s.suggested_rule.order,
            }

            record = create_rule_suggestion(
                account=account,
                user_id=user,
                suggestion_type=s.type.value,  # SuggestionType enum value
                suggested_rule=rule_dict,
                reason=s.reason,
                examples=s.examples[:5],
                email_count=s.email_count,
                confidence=_confidence_level_to_float(s.confidence.value),
                analysis_method="haiku" if any(
                    haiku_results.get(ex, None) and haiku_results[ex].analysis_method == "haiku"
                    for ex in s.examples[:5] if ex in haiku_results
                ) else "regex",
                category=s.suggested_rule.category,
            )
            # Build suggestion dict with ruleId for frontend
            suggestion_dict = s.to_dict()
            suggestion_dict["ruleId"] = record.rule_id
            persisted_rule_suggestions.append(suggestion_dict)
        except Exception as e:
            logger.warning(f"[analyze_inbox] Failed to persist rule suggestion: {e}")
            # Still include in response even if persistence fails
            persisted_rule_suggestions.append(s.to_dict())

    logger.info(
        f"[analyze_inbox] Persisted {len(persisted_rule_suggestions)} rule suggestions "
        f"(skipped {len(suggestions) - len(persisted_rule_suggestions)} duplicates)"
    )

    # Save new attention items to persistence
    for item in new_attention_items:
        record = AttentionRecord(
            email_id=item.email.id,
            email_account=account,
            user_id=user,
            subject=item.email.subject,
            from_address=item.email.from_address,
            from_name=item.email.from_name,
            date=item.email.date,
            snippet=item.email.snippet,
            labels=item.email.labels,
            reason=item.reason,
            urgency=item.urgency,
            confidence=item.confidence,
            suggested_action=item.suggested_action,
            extracted_task=item.extracted_task,
            matched_role=item.matched_role,
            analysis_method=item.analysis_method,
        )
        try:
            save_attention(account, record)
        except Exception as e:
            logger.warning(f"[analyze_inbox] Failed to save attention record: {e}")

    # Combine persisted attention items with new ones for response
    # Convert persisted records to API format
    all_attention = [r.to_api_dict() for r in persisted_attention]
    # Add new items (using the analyzer's format for consistency)
    all_attention.extend([a.to_dict() for a in new_attention_items])

    # Sort by urgency: high > medium > low
    urgency_order = {"high": 0, "medium": 1, "low": 2}
    all_attention.sort(key=lambda x: urgency_order.get(x.get("urgency", "low"), 2))

    # Get current Haiku usage stats for response (GLOBAL - no user param)
    haiku_usage = get_haiku_usage_summary()

    # Generate action suggestions using Haiku results (with fallback to regex)
    action_suggestions = generate_action_suggestions_with_haiku(
        messages=messages_to_analyze,
        email_account=account,
        haiku_results=haiku_results,
        available_labels=None,  # TODO: Fetch user labels if needed
    )

    # Persist action suggestions to storage (for Trust Gradient tracking)
    # Build set of email IDs that were analyzed by Haiku
    haiku_analyzed_ids = {
        email_id for email_id, result in haiku_results.items()
        if result.analysis_method == "haiku"
    }

    persisted_action_suggestions = []
    skipped_duplicates = 0
    for s in action_suggestions:
        # Skip if a pending suggestion already exists for this email
        if has_pending_suggestion_for_email(account, s.email.id):
            skipped_duplicates += 1
            continue

        # Determine analysis method
        analysis_method = "haiku" if s.email.id in haiku_analyzed_ids else "regex"

        try:
            record = create_suggestion(
                account=account,
                email_id=s.email.id,
                user_id=user,
                action=s.action.value,  # EmailActionType enum value
                rationale=s.rationale,
                confidence=_confidence_level_to_float(s.confidence.value),
                label_name=s.label_name,
                label_id=s.label_id,
                task_title=s.task_title,
                analysis_method=analysis_method,
                # Email metadata for UI display after refresh
                email_subject=s.email.subject,
                email_from=s.email.from_address,
                email_from_name=s.email.from_name,
                email_to=s.email.to_address,
                email_snippet=s.email.snippet,
                email_date=s.email.date.isoformat() if s.email.date else None,
                email_is_unread=s.email.is_unread,
                email_is_important=s.email.is_important,
                email_is_starred=s.email.is_starred,
            )
            # Build suggestion dict with suggestionId for frontend
            suggestion_dict = s.to_dict()
            suggestion_dict["suggestionId"] = record.suggestion_id
            persisted_action_suggestions.append(suggestion_dict)
        except Exception as e:
            logger.warning(f"[analyze_inbox] Failed to persist action suggestion: {e}")
            # Still include in response even if persistence fails
            persisted_action_suggestions.append(s.to_dict())

    logger.info(
        f"[analyze_inbox] Persisted {len(persisted_action_suggestions)} action suggestions "
        f"(skipped {skipped_duplicates} duplicates)"
    )

    # Save last analysis result for auditing (persists across machines)
    last_analysis = LastAnalysisRecord(
        account=account,
        timestamp=datetime.now(timezone.utc).isoformat(),
        emails_fetched=len(messages),
        emails_analyzed=len(messages_to_analyze),
        already_tracked=len(persisted_email_ids),
        dismissed=len(dismissed_ids),
        suggestions_generated=len(persisted_action_suggestions),
        rules_generated=len(persisted_rule_suggestions),
        attention_items=len(all_attention),
        haiku_analyzed=haiku_analyzed,
        haiku_remaining_daily=haiku_usage.get("dailyRemaining") if haiku_usage else None,
        haiku_remaining_weekly=haiku_usage.get("weeklyRemaining") if haiku_usage else None,
    )
    save_last_analysis(account, last_analysis)
    logger.info(f"[analyze_inbox] Saved last analysis result for {account}")

    return {
        "account": account,
        "email": email_address,
        # Analysis breakdown for auditing
        "emailsFetched": len(messages),
        "emailsDismissed": len(dismissed_ids),
        "emailsAlreadyTracked": len(persisted_email_ids),
        "messagesAnalyzed": len(messages_to_analyze),
        "existingRulesCount": len(existing_rules),
        "suggestions": persisted_rule_suggestions,  # Rule suggestions with IDs (New Rules tab)
        "actionSuggestions": persisted_action_suggestions,  # Action suggestions with IDs (Suggestions tab)
        "attentionItems": all_attention,
        "persistedCount": len(persisted_attention),
        "newCount": len(new_attention_items),
        "haikuAnalyzed": haiku_analyzed,
        "haikuUsage": haiku_usage,
    }


@app.get("/email/attention/{account}")
def get_attention_items(
    account: Literal["church", "personal"],
    user: str = Depends(get_current_user),
) -> dict:
    """Get persisted attention items for an account.

    Returns active attention items from storage without re-analyzing emails.
    Use this for quick refresh of the attention tab.
    """
    from daily_task_assistant.email import list_active_attention

    attention_items = list_active_attention(account)

    # Convert to API format and sort by urgency: high > medium > low
    api_items = [r.to_api_dict() for r in attention_items]
    urgency_order = {"high": 0, "medium": 1, "low": 2}
    api_items.sort(key=lambda x: urgency_order.get(x.get("urgency", "low"), 2))

    return {
        "account": account,
        "attentionItems": api_items,
        "count": len(api_items),
    }


@app.get("/email/last-analysis/{account}")
def get_last_analysis_endpoint(
    account: Literal["church", "personal"],
    user: str = Depends(get_current_user),
) -> dict:
    """Get the last analysis result for an account.

    Returns the audit data from the most recent Analyze Inbox run.
    Useful for checking if analysis needs to be re-run on another machine.
    """
    from daily_task_assistant.email import get_last_analysis

    result = get_last_analysis(account)

    if result is None:
        return {
            "account": account,
            "lastAnalysis": None,
        }

    return {
        "account": account,
        "lastAnalysis": {
            "timestamp": result.timestamp,
            "emailsFetched": result.emails_fetched,
            "emailsAnalyzed": result.emails_analyzed,
            "alreadyTracked": result.already_tracked,
            "dismissed": result.dismissed,
            "suggestionsGenerated": result.suggestions_generated,
            "rulesGenerated": result.rules_generated,
            "attentionItems": result.attention_items,
            "haikuAnalyzed": result.haiku_analyzed,
            "haikuRemaining": {
                "daily": result.haiku_remaining_daily,
                "weekly": result.haiku_remaining_weekly,
            } if result.haiku_remaining_daily is not None else None,
        },
    }


class DismissRequest(BaseModel):
    """Request body for dismissing an attention item."""

    reason: Literal["not_actionable", "handled", "false_positive"] = Field(
        alias="reason",
        description="Why the item is being dismissed",
    )

    model_config = ConfigDict(populate_by_name=True)


@app.post("/email/attention/{account}/{email_id}/dismiss")
def dismiss_attention_item(
    account: Literal["church", "personal"],
    email_id: str,
    request: DismissRequest,
    user: str = Depends(get_current_user),
) -> dict:
    """Dismiss an attention item.

    Marks the item as dismissed so it won't appear in future analyses.
    Dismissed items are kept for 7 days for audit purposes.
    """
    from daily_task_assistant.email import dismiss_attention

    success = dismiss_attention(account, email_id, request.reason)

    if not success:
        raise HTTPException(status_code=404, detail="Attention item not found")

    return {
        "success": True,
        "emailId": email_id,
        "account": account,
        "reason": request.reason,
    }


class SnoozeRequest(BaseModel):
    """Request body for snoozing an attention item."""

    until: datetime = Field(
        alias="until",
        description="When to resurface the item (ISO timestamp)",
    )

    model_config = ConfigDict(populate_by_name=True)


@app.post("/email/attention/{account}/{email_id}/snooze")
def snooze_attention_item(
    account: Literal["church", "personal"],
    email_id: str,
    request: SnoozeRequest,
    user: str = Depends(get_current_user),
) -> dict:
    """Snooze an attention item until a specific time.

    The item will reappear after the snooze period expires.
    """
    from daily_task_assistant.email import snooze_attention

    success = snooze_attention(account, email_id, request.until)

    if not success:
        raise HTTPException(status_code=404, detail="Attention item not found")

    return {
        "success": True,
        "emailId": email_id,
        "account": account,
        "snoozedUntil": request.until.isoformat(),
    }


# --- Suggestion Tracking (Sprint 5: Learning Foundation) ---


class SuggestionDecisionRequest(BaseModel):
    """Request body for approving or rejecting a suggestion."""

    approved: bool = Field(
        description="Whether the suggestion was approved (True) or rejected (False)",
    )

    model_config = ConfigDict(populate_by_name=True)


@app.post("/email/suggestions/{account}/{suggestion_id}/decide")
def decide_suggestion(
    account: Literal["church", "personal"],
    suggestion_id: str,
    request: SuggestionDecisionRequest,
    user: str = Depends(get_current_user),
) -> dict:
    """Record user's decision on a suggestion.

    This feedback is critical for the Trust Gradient system.
    Approvals increase DATA's confidence in similar suggestions.
    Rejections help DATA learn what NOT to suggest.

    Note: Account is required in URL path (storage is by account, not user).
    """
    from daily_task_assistant.email import record_suggestion_decision, get_suggestion

    # Record the decision (keyed by account, not user)
    success = record_suggestion_decision(account, suggestion_id, request.approved)

    if not success:
        raise HTTPException(status_code=404, detail="Suggestion not found")

    # Get the updated suggestion for confirmation
    suggestion = get_suggestion(account, suggestion_id)

    return {
        "success": True,
        "suggestionId": suggestion_id,
        "status": suggestion.status if suggestion else ("approved" if request.approved else "rejected"),
        "decidedAt": suggestion.decided_at.isoformat() if suggestion and suggestion.decided_at else None,
    }


@app.get("/email/suggestions/{account}/stats")
def get_suggestion_stats(
    account: Literal["church", "personal"],
    days: int = Query(30, ge=1, le=365, description="Number of days to look back"),
    user: str = Depends(get_current_user),
) -> dict:
    """Get suggestion approval statistics for Trust Gradient.

    Returns approval rates by action type and analysis method.
    This data helps track DATA's learning progress.
    Account is required (storage is by account, not user).
    """
    from daily_task_assistant.email import get_approval_stats

    stats = get_approval_stats(account, days)

    return {
        "days": days,
        "total": stats["total"],
        "approved": stats["approved"],
        "rejected": stats["rejected"],
        "expired": stats["expired"],
        "pending": stats["pending"],
        "approvalRate": stats["approval_rate"],
        "byAction": stats["by_action"],
        "byMethod": stats["by_method"],
    }


@app.get("/email/suggestions/rejection-patterns")
def get_rejection_patterns(
    days: int = Query(30, ge=1, le=365, description="Number of days to look back"),
    min_rejections: int = Query(3, ge=2, le=10, description="Minimum rejections to suggest as pattern"),
    user: str = Depends(get_current_user),
) -> dict:
    """Get frequently rejected patterns that could be added to not-actionable.

    Analyzes rejection history to find patterns that should be skipped
    in future suggestions. Use with add-pattern endpoint to teach DATA.
    Note: Analysis is GLOBAL across both accounts.
    """
    from daily_task_assistant.memory import get_rejection_candidates

    candidates = get_rejection_candidates(days, min_rejections)

    return {
        "days": days,
        "minRejections": min_rejections,
        "candidates": candidates,
    }


# =============================================================================
# Action Suggestion Endpoints
# =============================================================================


@app.get("/email/suggestions/{account}/pending")
def get_pending_suggestions(
    account: Literal["church", "personal"],
    user: str = Depends(get_current_user),
) -> dict:
    """Get all pending action suggestions for the specified account.

    Returns action suggestions that haven't been approved or rejected yet.
    These are suggestions with full email metadata for UI display after refresh.
    """
    from daily_task_assistant.email import list_pending_suggestions

    suggestions = list_pending_suggestions(account)

    # Convert to API format with numbering
    api_suggestions = [
        record.to_api_dict(number=idx + 1)
        for idx, record in enumerate(suggestions)
    ]

    return {
        "account": account,
        "suggestions": api_suggestions,
        "count": len(api_suggestions),
    }


# =============================================================================
# Rule Suggestion Endpoints
# =============================================================================


@app.get("/email/rules/{account}/pending")
def get_pending_rules(
    account: Literal["church", "personal"],
    user: str = Depends(get_current_user),
) -> dict:
    """Get all pending rule suggestions for the specified account.

    Returns rule suggestions that haven't been approved or rejected yet.
    Account is required (storage is by account, not user).
    """
    from daily_task_assistant.email import list_pending_rules

    rules = list_pending_rules(account)

    return {
        "account": account,
        "rules": [r.to_api_dict() for r in rules],
        "count": len(rules),
    }


class RuleDecisionRequest(BaseModel):
    """Request body for deciding on a rule suggestion."""

    approved: bool = Field(
        description="True to approve the rule, False to reject"
    )
    rejection_reason: Optional[str] = Field(
        None,
        alias="rejectionReason",
        description="Reason for rejection (optional, for learning)"
    )

    model_config = ConfigDict(populate_by_name=True)


@app.post("/email/rules/{account}/{rule_id}/decide")
def decide_rule(
    account: Literal["church", "personal"],
    rule_id: str,
    request: RuleDecisionRequest,
    user: str = Depends(get_current_user),
) -> dict:
    """Approve or reject a rule suggestion.

    Records the decision for Trust Gradient tracking.
    If approved, the rule can be added to Google Sheets.
    """
    from daily_task_assistant.email import decide_rule_suggestion, get_rule_suggestion

    success = decide_rule_suggestion(
        account=account,
        rule_id=rule_id,
        approved=request.approved,
        rejection_reason=request.rejection_reason,
    )

    if not success:
        raise HTTPException(status_code=404, detail=f"Rule suggestion not found: {rule_id}")

    # Get the updated record to return
    updated = get_rule_suggestion(account, rule_id)
    if updated:
        return {
            "status": "approved" if request.approved else "rejected",
            "ruleId": rule_id,
            "rule": updated.to_api_dict(),
        }
    else:
        return {
            "status": "approved" if request.approved else "rejected",
            "ruleId": rule_id,
        }


@app.get("/email/rules/{account}/stats")
def get_rule_stats(
    account: Literal["church", "personal"],
    days: int = Query(30, ge=1, le=365, description="Number of days to look back"),
    user: str = Depends(get_current_user),
) -> dict:
    """Get rule approval statistics for Trust Gradient.

    Returns approval rates by analysis method and category.
    This data helps track DATA's learning progress for rule suggestions.
    """
    from daily_task_assistant.email import get_rule_approval_stats

    stats = get_rule_approval_stats(account, days)

    return {
        "account": account,
        "days": days,
        "total": stats["total"],
        "approved": stats["approved"],
        "rejected": stats["rejected"],
        "pending": stats["pending"],
        "approvalRate": stats["approvalRate"],
        "byMethod": stats["byMethod"],
        "byCategory": stats["byCategory"],
    }


@app.get("/email/trust-metrics")
def get_trust_metrics(
    days: int = Query(30, ge=1, le=365, description="Number of days to look back"),
    user: str = Depends(get_current_user),
) -> dict:
    """Get combined trust metrics for Trust Gradient tracking.

    Returns aggregate approval rates across both accounts and both types
    (action suggestions and rule suggestions). Used to track DATA's
    progress toward higher autonomy levels.

    Trust Levels:
        Level 0: Surface attention items
        Level 1: Suggest with rationale, receive vote (current)
        Level 2: Small autonomous actions (requires 90%+ approval)
        Level 3: Larger scope autonomy
    """
    from daily_task_assistant.email import get_approval_stats, get_rule_approval_stats

    # Aggregate stats from both accounts
    church_action_stats = get_approval_stats("church", days)
    personal_action_stats = get_approval_stats("personal", days)
    church_rule_stats = get_rule_approval_stats("church", days)
    personal_rule_stats = get_rule_approval_stats("personal", days)

    # Combine action suggestion stats
    action_approved = church_action_stats["approved"] + personal_action_stats["approved"]
    action_rejected = church_action_stats["rejected"] + personal_action_stats["rejected"]
    action_total = action_approved + action_rejected

    # Combine rule suggestion stats
    rule_approved = church_rule_stats["approved"] + personal_rule_stats["approved"]
    rule_rejected = church_rule_stats["rejected"] + personal_rule_stats["rejected"]
    rule_total = rule_approved + rule_rejected

    # Overall approval rate
    total_decided = action_total + rule_total
    total_approved = action_approved + rule_approved
    overall_rate = total_approved / total_decided if total_decided > 0 else 0.0

    # Aggregate by analysis method
    by_method = {}
    for stats in [church_action_stats, personal_action_stats]:
        for method, data in stats.get("by_method", {}).items():
            if method not in by_method:
                by_method[method] = {"approved": 0, "rejected": 0, "total": 0}
            by_method[method]["approved"] += data.get("approved", 0)
            by_method[method]["rejected"] += data.get("rejected", 0)
            by_method[method]["total"] += data.get("approved", 0) + data.get("rejected", 0)

    for stats in [church_rule_stats, personal_rule_stats]:
        for method, data in stats.get("byMethod", {}).items():
            if method not in by_method:
                by_method[method] = {"approved": 0, "rejected": 0, "total": 0}
            by_method[method]["approved"] += data.get("approved", 0)
            by_method[method]["rejected"] += data.get("rejected", 0)
            by_method[method]["total"] += data.get("total", 0)

    # Calculate rates for each method
    for method_data in by_method.values():
        decided = method_data["approved"] + method_data["rejected"]
        method_data["rate"] = method_data["approved"] / decided if decided > 0 else 0.0

    # Trust level calculation
    # Level 2 requires 90%+ approval rate
    trust_level = 1  # Current: Suggest with rationale
    if overall_rate >= 0.90 and total_decided >= 20:
        trust_level = 2  # Ready for small autonomous actions

    progress_to_level_2 = min(1.0, overall_rate / 0.90)

    # Generate recommendation
    if trust_level == 2:
        recommendation = "DATA has earned Level 2 trust. Consider enabling small autonomous actions."
    elif overall_rate >= 0.85:
        needed = 0.90 - overall_rate
        recommendation = f"{needed * 100:.1f}% more approval rate needed for Level 2 autonomy"
    elif total_decided < 20:
        recommendation = f"{20 - total_decided} more decisions needed before trust level can increase"
    else:
        recommendation = "Continue voting on suggestions to help DATA learn your preferences"

    return {
        "days": days,
        "overallApprovalRate": round(overall_rate, 4),
        "totalDecided": total_decided,
        "totalApproved": total_approved,
        "actionSuggestions": {
            "approved": action_approved,
            "rejected": action_rejected,
            "rate": action_approved / action_total if action_total > 0 else 0.0,
        },
        "ruleSuggestions": {
            "approved": rule_approved,
            "rejected": rule_rejected,
            "rate": rule_approved / rule_total if rule_total > 0 else 0.0,
        },
        "byMethod": by_method,
        "trustLevel": trust_level,
        "progressToLevel2": round(progress_to_level_2, 4),
        "recommendation": recommendation,
    }


class AddPatternRequest(BaseModel):
    """Request body for adding a not-actionable pattern."""

    account: Literal["church", "personal"] = Field(
        description="Email account to add pattern to",
    )
    pattern: str = Field(
        description="Pattern to mark as not actionable",
        min_length=3,
        max_length=100,
    )

    model_config = ConfigDict(populate_by_name=True)


@app.post("/profile/not-actionable/add")
def add_not_actionable(
    request: AddPatternRequest,
    user: str = Depends(get_current_user),
) -> dict:
    """Add a pattern to not-actionable list.

    This teaches DATA to skip emails matching this pattern in the future.
    Profile is GLOBAL (shared across login identities).
    """
    from daily_task_assistant.memory import add_not_actionable_pattern

    success = add_not_actionable_pattern(request.account, request.pattern)

    if not success:
        # Pattern already exists
        return {
            "success": False,
            "account": request.account,
            "pattern": request.pattern,
            "message": "Pattern already exists in not-actionable list",
        }

    return {
        "success": True,
        "account": request.account,
        "pattern": request.pattern,
        "message": "Pattern added to not-actionable list",
    }


@app.post("/profile/not-actionable/remove")
def remove_not_actionable(
    request: AddPatternRequest,
    user: str = Depends(get_current_user),
) -> dict:
    """Remove a pattern from not-actionable list.

    Allows user to re-enable attention for previously skipped patterns.
    Profile is GLOBAL (shared across login identities).
    """
    from daily_task_assistant.memory import remove_not_actionable_pattern

    success = remove_not_actionable_pattern(request.account, request.pattern)

    if not success:
        return {
            "success": False,
            "account": request.account,
            "pattern": request.pattern,
            "message": "Pattern not found in not-actionable list",
        }

    return {
        "success": True,
        "account": request.account,
        "pattern": request.pattern,
        "message": "Pattern removed from not-actionable list",
    }


@app.post("/email/sync/{account}")
def sync_rules_to_sheet(
    account: Literal["church", "personal"],
    request: SyncRulesRequest,
    user: str = Depends(get_current_user),
) -> dict:
    """Sync a batch of rules to Google Sheets.
    
    Replaces all rules for the account with the provided list.
    Use for bi-weekly sync after accumulating approved changes.
    """
    from daily_task_assistant.sheets import FilterRulesManager, FilterRule, SheetsError
    
    try:
        manager = FilterRulesManager.from_env(account.upper())
        
        # Convert request rules to FilterRule objects
        rules = [
            FilterRule(
                email_account=r.email_account,
                order=r.order,
                category=r.category,
                field=r.field,
                operator=r.operator,
                value=r.value,
                action=r.action,
            )
            for r in request.rules
        ]
        
        synced_count = manager.sync_rules(rules, request.email_account)
        
    except SheetsError as exc:
        raise HTTPException(status_code=502, detail=f"Google Sheets error: {exc}")
    
    return {
        "status": "synced",
        "account": account,
        "emailAccount": request.email_account,
        "rulesSynced": synced_count,
    }


@app.post("/email/task-from-email/{account}")
def create_task_from_email(
    account: Literal["church", "personal"],
    email_id: str = Query(..., description="Gmail message ID"),
    task_title: Optional[str] = Query(None, description="Override task title"),
    due_date: Optional[str] = Query(None, description="Task due date (YYYY-MM-DD)"),
    project: Optional[str] = Query(None, description="Target project"),
    user: str = Depends(get_current_user),
) -> dict:
    """Create a Smartsheet task from an email.
    
    Extracts task details from the email and creates a new task.
    Optionally allows overriding the auto-extracted values.
    """
    from daily_task_assistant.mailer import GmailError, load_account_from_env, get_message
    from daily_task_assistant.smartsheet_client import SmartsheetClient, SmartsheetAPIError
    from daily_task_assistant.email.analyzer import EmailAnalyzer
    from datetime import datetime, timedelta
    
    settings = _get_settings()
    
    # Load Gmail config and fetch the email
    try:
        gmail_config = load_account_from_env(account)
        message = get_message(gmail_config, email_id)
    except GmailError as exc:
        raise HTTPException(status_code=502, detail=f"Gmail API error: {exc}")
    
    # Extract task details from email
    analyzer = EmailAnalyzer(gmail_config.from_address)
    extracted_task = analyzer._extract_task(message)
    
    # Use provided values or defaults
    final_title = task_title or extracted_task or message.subject
    final_due = due_date or (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
    final_project = project or ("Church Tasks" if account == "church" else "Sm. Projects & Tasks")
    
    # Determine source based on account
    source = "work" if account == "church" else "personal"
    
    # Create the task
    try:
        client = SmartsheetClient(settings)
        # Note: This would need a create_task method in SmartsheetClient
        # For now, return a preview of what would be created
        task_data = {
            "title": final_title,
            "dueDate": final_due,
            "project": final_project,
            "source": source,
            "notes": f"Created from email: {message.subject}\nFrom: {message.from_name} <{message.from_address}>",
            "status": "Scheduled",
            "priority": "Standard",
        }
        
        # TODO: Implement client.create_task() when ready
        # result = client.create_task(task_data)
        
    except SmartsheetAPIError as exc:
        raise HTTPException(status_code=502, detail=f"Smartsheet error: {exc}")
    
    return {
        "status": "preview",  # Change to "created" when implemented
        "account": account,
        "emailId": email_id,
        "emailSubject": message.subject,
        "taskPreview": task_data,
        "message": "Task creation preview. Full implementation coming soon.",
    }


# --- Email Action Endpoints (Phase 3) ---

@app.post("/email/{account}/archive/{message_id}")
def archive_email(
    account: Literal["church", "personal"],
    message_id: str,
    user: str = Depends(get_current_user),
) -> dict:
    """Archive an email (remove from Inbox).
    
    Removes the INBOX label, moving the email to All Mail.
    """
    from daily_task_assistant.mailer import (
        GmailError,
        load_account_from_env,
        archive_message,
    )
    
    try:
        gmail_config = load_account_from_env(account)
        result = archive_message(gmail_config, message_id)
    except GmailError as exc:
        raise HTTPException(status_code=502, detail=f"Gmail API error: {exc}")
    
    return {
        "status": "archived",
        "account": account,
        "messageId": message_id,
        "labels": result.get("labelIds", []),
    }


@app.post("/email/{account}/delete/{message_id}")
def trash_email(
    account: Literal["church", "personal"],
    message_id: str,
    user: str = Depends(get_current_user),
) -> dict:
    """Move an email to trash.
    
    Emails in trash are automatically deleted after 30 days.
    """
    from daily_task_assistant.mailer import (
        GmailError,
        load_account_from_env,
        delete_message,
    )
    
    try:
        gmail_config = load_account_from_env(account)
        result = delete_message(gmail_config, message_id)
    except GmailError as exc:
        raise HTTPException(status_code=502, detail=f"Gmail API error: {exc}")
    
    return {
        "status": "trashed",
        "account": account,
        "messageId": message_id,
        "labels": result.get("labelIds", []),
    }


@app.post("/email/{account}/star/{message_id}")
def star_email(
    account: Literal["church", "personal"],
    message_id: str,
    starred: bool = Query(True, description="True to star, False to unstar"),
    user: str = Depends(get_current_user),
) -> dict:
    """Star or unstar an email.
    
    Starred emails appear in the Starred folder for quick access.
    """
    from daily_task_assistant.mailer import (
        GmailError,
        load_account_from_env,
        star_message,
    )
    
    try:
        gmail_config = load_account_from_env(account)
        result = star_message(gmail_config, message_id, starred=starred)
    except GmailError as exc:
        raise HTTPException(status_code=502, detail=f"Gmail API error: {exc}")
    
    return {
        "status": "starred" if starred else "unstarred",
        "account": account,
        "messageId": message_id,
        "labels": result.get("labelIds", []),
    }


@app.post("/email/{account}/important/{message_id}")
def mark_email_important(
    account: Literal["church", "personal"],
    message_id: str,
    important: bool = Query(True, description="True to mark important, False to remove"),
    user: str = Depends(get_current_user),
) -> dict:
    """Mark an email as important or remove importance.
    
    Important emails appear in the Important folder.
    """
    from daily_task_assistant.mailer import (
        GmailError,
        load_account_from_env,
        mark_important,
    )
    
    try:
        gmail_config = load_account_from_env(account)
        result = mark_important(gmail_config, message_id, important=important)
    except GmailError as exc:
        raise HTTPException(status_code=502, detail=f"Gmail API error: {exc}")
    
    return {
        "status": "important" if important else "not_important",
        "account": account,
        "messageId": message_id,
        "labels": result.get("labelIds", []),
    }


@app.post("/email/{account}/read/{message_id}")
def mark_email_read(
    account: Literal["church", "personal"],
    message_id: str,
    read: bool = Query(True, description="True to mark read, False to mark unread"),
    user: str = Depends(get_current_user),
) -> dict:
    """Mark an email as read or unread.
    """
    from daily_task_assistant.mailer import (
        GmailError,
        load_account_from_env,
        mark_read,
        mark_unread,
    )
    
    try:
        gmail_config = load_account_from_env(account)
        if read:
            result = mark_read(gmail_config, message_id)
        else:
            result = mark_unread(gmail_config, message_id)
    except GmailError as exc:
        raise HTTPException(status_code=502, detail=f"Gmail API error: {exc}")
    
    return {
        "status": "read" if read else "unread",
        "account": account,
        "messageId": message_id,
        "labels": result.get("labelIds", []),
    }


# --- Email Reply Endpoints ---

class ReplyDraftRequest(BaseModel):
    """Request body for generating a reply draft."""
    model_config = {"populate_by_name": True}
    
    message_id: str = Field(..., alias="messageId")
    reply_all: bool = Field(False, alias="replyAll")
    user_context: Optional[str] = Field(None, alias="userContext", description="Optional notes about what to include in the reply")


class ReplySendRequest(BaseModel):
    """Request body for sending a reply."""
    model_config = {"populate_by_name": True}
    
    message_id: str = Field(..., alias="messageId")
    reply_all: bool = Field(False, alias="replyAll")
    subject: str
    body: str
    cc: Optional[List[str]] = None


@app.post("/email/{account}/reply-draft")
def generate_reply_draft(
    account: Literal["church", "personal"],
    request: ReplyDraftRequest,
    user: str = Depends(get_current_user),
) -> dict:
    """Generate a human-like reply draft using DATA.
    
    Fetches the original email, optional thread context, and generates
    a natural reply that matches David's communication style.
    
    Returns:
        Draft with subject, body (plain and HTML), and recipient lists.
    """
    from daily_task_assistant.mailer import (
        GmailError,
        load_account_from_env,
        get_message,
    )
    from daily_task_assistant.llm.anthropic_client import (
        generate_email_reply_draft,
        AnthropicError,
    )
    
    # Load Gmail config
    try:
        gmail_config = load_account_from_env(account)
    except GmailError as exc:
        raise HTTPException(status_code=400, detail=f"Gmail config error: {exc}")
    
    # Fetch the original email with full body
    try:
        original_msg = get_message(gmail_config, request.message_id, format="full")
    except GmailError as exc:
        raise HTTPException(status_code=502, detail=f"Gmail API error: {exc}")
    
    # Build email context dict
    email_context = {
        "fromAddress": original_msg.from_address,
        "fromName": original_msg.from_name,
        "toAddress": original_msg.to_address,
        "ccAddress": original_msg.cc_address,
        "subject": original_msg.subject,
        "body": original_msg.body or original_msg.snippet,
        "date": original_msg.date.isoformat(),
    }
    
    # Get thread context for multi-message threads
    thread_summary = None
    if original_msg.thread_id:
        # Fetch thread to check if there are multiple messages
        try:
            import json
            from urllib import request as urlrequest
            from urllib import error as urlerror
            from daily_task_assistant.mailer.gmail import _fetch_access_token
            
            access_token = _fetch_access_token(gmail_config)
            thread_url = f"https://gmail.googleapis.com/gmail/v1/users/me/threads/{original_msg.thread_id}?format=metadata"
            headers = {"Authorization": f"Bearer {access_token}"}
            
            req = urlrequest.Request(thread_url, headers=headers, method="GET")
            with urlrequest.urlopen(req, timeout=15) as resp:
                thread_data = json.loads(resp.read().decode("utf-8"))
                
            message_count = len(thread_data.get("messages", []))
            if message_count > 1:
                # Fetch full thread context
                thread_response = get_thread_context(account, original_msg.thread_id, user)
                thread_summary = thread_response.get("summary")
        except Exception:
            pass  # Continue without thread context
    
    # Generate reply draft
    try:
        draft = generate_email_reply_draft(
            original_email=email_context,
            thread_context=thread_summary,
            user_instructions=request.user_context,
            reply_all=request.reply_all,
        )
    except AnthropicError as exc:
        raise HTTPException(status_code=502, detail=f"AI generation error: {exc}")
    
    return {
        "account": account,
        "originalMessageId": request.message_id,
        "draft": {
            "subject": draft.subject,
            "body": draft.body,
            "bodyHtml": draft.body_html,
            "to": draft.to_addresses,
            "cc": draft.cc_addresses,
        },
    }


@app.post("/email/{account}/reply-send")
def send_reply(
    account: Literal["church", "personal"],
    request: ReplySendRequest,
    user: str = Depends(get_current_user),
) -> dict:
    """Send a reply to an email with proper threading headers.
    
    Uses the original message's Message-ID and References headers
    to maintain proper email thread structure in Gmail.
    """
    from daily_task_assistant.mailer import (
        GmailError,
        load_account_from_env,
        get_message,
        send_email,
    )
    
    # Load Gmail config
    try:
        gmail_config = load_account_from_env(account)
    except GmailError as exc:
        raise HTTPException(status_code=400, detail=f"Gmail config error: {exc}")
    
    # Fetch original message to get threading headers
    try:
        original_msg = get_message(gmail_config, request.message_id, format="full")
    except GmailError as exc:
        raise HTTPException(status_code=502, detail=f"Gmail API error: {exc}")
    
    # Build recipient list
    to_address = original_msg.from_address
    cc_address = None
    
    if request.reply_all:
        # Include original CC recipients
        cc_parts = []
        if original_msg.cc_address:
            cc_parts.append(original_msg.cc_address)
        if request.cc:
            cc_parts.extend(request.cc)
        if cc_parts:
            cc_address = ", ".join(cc_parts)
    elif request.cc:
        cc_address = ", ".join(request.cc)
    
    # Build References header (existing references + original Message-ID)
    references = original_msg.references
    if original_msg.message_id_header:
        if references:
            references = f"{references} {original_msg.message_id_header}"
        else:
            references = original_msg.message_id_header
    
    # Send the reply
    try:
        sent_id = send_email(
            gmail_config,
            to_address=to_address,
            subject=request.subject,
            body=request.body,
            cc_address=cc_address,
            in_reply_to=original_msg.message_id_header,
            references=references,
            thread_id=original_msg.thread_id,
        )
    except GmailError as exc:
        raise HTTPException(status_code=502, detail=f"Gmail send error: {exc}")
    
    return {
        "status": "sent",
        "account": account,
        "sentMessageId": sent_id,
        "originalMessageId": request.message_id,
        "threadId": original_msg.thread_id,
        "to": to_address,
        "cc": cc_address,
    }


# --- Email Action Suggestions (Phase A3) ---

@app.get("/email/{account}/suggestions")
def get_email_action_suggestions(
    account: Literal["church", "personal"],
    max_messages: int = Query(30, ge=10, le=50),
    user: str = Depends(get_current_user),
) -> dict:
    """Get DATA's suggested actions for recent emails.
    
    Returns numbered suggestions for actions like:
    - Applying labels
    - Archiving old promotional emails
    - Starring urgent emails
    - Creating tasks from action items
    
    Users can reference suggestions by number in chat (e.g., "approve #1").
    """
    from daily_task_assistant.mailer import (
        GmailError,
        load_account_from_env,
        search_messages,
        list_labels,
    )
    from daily_task_assistant.email.analyzer import generate_action_suggestions
    
    # Load Gmail config
    try:
        gmail_config = load_account_from_env(account)
    except GmailError as exc:
        raise HTTPException(status_code=400, detail=f"Gmail config error: {exc}")
    
    # Get recent inbox messages
    try:
        messages = search_messages(
            gmail_config,
            query="in:inbox",
            max_results=max_messages,
        )
    except GmailError as exc:
        raise HTTPException(status_code=502, detail=f"Gmail API error: {exc}")
    
    # Get available labels for matching
    available_labels = []
    try:
        labels = list_labels(gmail_config)
        available_labels = [
            {"id": l.id, "name": l.name, "color": l.color}
            for l in labels
            if l.label_type == "user"  # Only user-created labels
        ]
    except GmailError:
        pass  # Continue without labels
    
    # Generate action suggestions
    suggestions = generate_action_suggestions(
        messages,
        gmail_config.from_address,
        available_labels=available_labels,
    )

    # Persist suggestions for approval tracking (Sprint 5)
    from daily_task_assistant.email import create_suggestion

    persisted_suggestions = []
    for s in suggestions:
        # Create a persistent record for this suggestion (keyed by account, not user)
        record = create_suggestion(
            account=account,
            email_id=s.email.id,
            user_id=user,
            action=s.action.value,
            rationale=s.rationale,
            confidence=0.5 if s.confidence.value == "medium" else (0.8 if s.confidence.value == "high" else 0.3),
            label_name=s.label_name,
            label_id=s.label_id,
            task_title=s.task_title,
            analysis_method="regex",  # Current implementation uses regex patterns
            # Email metadata for UI display after refresh
            email_subject=s.email.subject,
            email_from=s.email.from_address,
            email_from_name=s.email.from_name,
            email_to=s.email.to_address,
            email_snippet=s.email.snippet,
            email_date=s.email.date.isoformat() if s.email.date else None,
            email_is_unread=s.email.is_unread,
            email_is_important=s.email.is_important,
            email_is_starred=s.email.is_starred,
        )
        # Add suggestion_id to the response for tracking
        suggestion_dict = s.to_dict()
        suggestion_dict["suggestionId"] = record.suggestion_id
        persisted_suggestions.append(suggestion_dict)

    return {
        "account": account,
        "email": gmail_config.from_address,
        "messagesAnalyzed": len(messages),
        "availableLabels": available_labels,
        "suggestions": persisted_suggestions,
    }


# --- Custom Label Endpoints (Phase A2) ---

@app.get("/email/{account}/labels")
def get_email_labels(
    account: Literal["church", "personal"],
    user: str = Depends(get_current_user),
) -> dict:
    """List all Gmail labels for the account.
    
    Returns both system labels (INBOX, STARRED, etc.) and user-created labels.
    """
    from daily_task_assistant.mailer import (
        GmailError,
        load_account_from_env,
        list_labels,
    )
    
    try:
        gmail_config = load_account_from_env(account)
        labels = list_labels(gmail_config)
    except GmailError as exc:
        raise HTTPException(status_code=502, detail=f"Gmail API error: {exc}")
    
    return {
        "account": account,
        "labels": [
            {
                "id": label.id,
                "name": label.name,
                "type": label.label_type,
                "messagesTotal": label.messages_total,
                "messagesUnread": label.messages_unread,
                "color": label.color,
            }
            for label in labels
        ],
    }


class ApplyLabelRequest(BaseModel):
    """Request body for applying/removing a label."""
    label_id: Optional[str] = Field(None, description="Gmail label ID")
    label_name: Optional[str] = Field(None, description="Gmail label name (alternative to ID)")
    action: Literal["apply", "remove"] = Field("apply", description="Action to perform")


@app.post("/email/{account}/label/{message_id}")
def modify_email_label(
    account: Literal["church", "personal"],
    message_id: str,
    request: ApplyLabelRequest,
    user: str = Depends(get_current_user),
) -> dict:
    """Apply or remove a custom label on an email.
    
    Can use either label_id (more efficient) or label_name (convenience).
    """
    from daily_task_assistant.mailer import (
        GmailError,
        load_account_from_env,
        apply_label,
        remove_label,
        apply_label_by_name,
        remove_label_by_name,
    )
    
    if not request.label_id and not request.label_name:
        raise HTTPException(
            status_code=400,
            detail="Either label_id or label_name must be provided"
        )
    
    try:
        gmail_config = load_account_from_env(account)
        
        if request.action == "apply":
            if request.label_id:
                result = apply_label(gmail_config, message_id, request.label_id)
            else:
                result = apply_label_by_name(gmail_config, message_id, request.label_name)
        else:  # remove
            if request.label_id:
                result = remove_label(gmail_config, message_id, request.label_id)
            else:
                result = remove_label_by_name(gmail_config, message_id, request.label_name)
                
    except GmailError as exc:
        raise HTTPException(status_code=502, detail=f"Gmail API error: {exc}")
    
    return {
        "status": f"label_{request.action}d",
        "account": account,
        "messageId": message_id,
        "labelId": request.label_id,
        "labelName": request.label_name,
        "labels": result.get("labelIds", []),
    }


# --- Email Chat Endpoint (Phase 4) ---

class EmailChatRequest(BaseModel):
    """Request body for email chat."""
    message: str = Field(..., description="User's message about the email")
    email_id: str = Field(..., description="Gmail message ID")
    history: Optional[List[Dict[str, str]]] = Field(default=None, description="Previous conversation")


@app.post("/email/{account}/chat")
def chat_about_email(
    account: Literal["church", "personal"],
    request: EmailChatRequest,
    user: str = Depends(get_current_user),
) -> dict:
    """Chat with DATA about an email.
    
    DATA can help analyze, summarize, or suggest actions for the email.
    If DATA detects an action request, returns a pending_action.
    """
    from daily_task_assistant.llm.anthropic_client import chat_with_email, AnthropicError
    from daily_task_assistant.mailer import GmailError, load_account_from_env, get_message
    
    # Load the email
    try:
        gmail_config = load_account_from_env(account)
        email = get_message(gmail_config, request.email_id)
    except GmailError as exc:
        raise HTTPException(status_code=502, detail=f"Gmail API error: {exc}")
    
    # Build email context for DATA
    email_context = f"""Email Details:
- From: {email.from_name} <{email.from_address}>
- To: {email.to_address}
- Subject: {email.subject}
- Date: {email.date.strftime("%Y-%m-%d %H:%M")}
- Preview: {email.snippet}
- Status: {"Unread" if email.is_unread else "Read"}
- Important: {"Yes" if email.is_important else "No"}
- Starred: {"Yes" if email.is_starred else "No"}"""

    # Chat with DATA
    try:
        chat_response = chat_with_email(
            email_context=email_context,
            user_message=request.message,
            history=request.history,
        )
    except AnthropicError as exc:
        raise HTTPException(status_code=502, detail=f"AI service error: {exc}")
    
    # Build response
    response_data = {
        "response": chat_response.message,
        "account": account,
        "emailId": request.email_id,
    }
    
    # Include pending action if DATA detected one
    if chat_response.pending_action:
        action = chat_response.pending_action
        pending_action_data = {
            "action": action.action,
            "reason": action.reason,
        }
        if action.task_title:
            pending_action_data["taskTitle"] = action.task_title
        if action.draft_body:
            pending_action_data["draftBody"] = action.draft_body
        if action.draft_subject:
            pending_action_data["draftSubject"] = action.draft_subject
        if action.label_name:
            pending_action_data["labelName"] = action.label_name
        response_data["pendingAction"] = pending_action_data
    
    return response_data


# --- Email-to-Task Endpoints (Phase B) ---

class TaskPreviewRequest(BaseModel):
    """Request to preview task creation from email."""
    email_id: str = Field(..., description="Gmail message ID")


class TaskCreateRequest(BaseModel):
    """Request to create a task from email."""
    email_id: str = Field(..., description="Gmail message ID")
    title: str = Field(..., description="Task title")
    due_date: Optional[str] = Field(None, description="Due date (YYYY-MM-DD)")
    priority: str = Field("Standard", description="Task priority")
    domain: str = Field("personal", description="Task domain")
    project: Optional[str] = Field(None, description="Project category")
    notes: Optional[str] = Field(None, description="Task notes")


@app.post("/email/{account}/task-preview")
def preview_task_from_email(
    account: Literal["church", "personal"],
    request: TaskPreviewRequest,
    user: str = Depends(get_current_user),
) -> dict:
    """Get DATA's suggested task details from an email.
    
    DATA analyzes the email and suggests:
    - Task title
    - Due date (if mentioned)
    - Priority
    - Domain
    
    Returns preview data for the Smart mode form.
    """
    from daily_task_assistant.mailer import GmailError, load_account_from_env, get_message
    from daily_task_assistant.llm.anthropic_client import extract_task_from_email, AnthropicError
    
    # Load the email
    try:
        gmail_config = load_account_from_env(account)
        email = get_message(gmail_config, request.email_id)
    except GmailError as exc:
        raise HTTPException(status_code=502, detail=f"Gmail API error: {exc}")
    
    # Use DATA to extract task details
    try:
        task_preview = extract_task_from_email(
            from_address=email.from_address,
            from_name=email.from_name,
            subject=email.subject,
            snippet=email.snippet,
            email_account=account,
        )
    except AnthropicError as exc:
        # Fallback to simple extraction
        domain = "church" if account == "church" else "personal"
        task_preview = {
            "title": email.subject.replace("Re:", "").replace("Fwd:", "").strip(),
            "dueDate": None,
            "priority": "Standard",
            "domain": domain,
            "project": "Church Tasks" if domain == "church" else "Sm. Projects & Tasks",
            "notes": f"From: {email.from_name or email.from_address}",
        }
    
    return {
        "account": account,
        "emailId": request.email_id,
        "emailSubject": email.subject,
        "emailFrom": email.from_address,
        "emailFromName": email.from_name,
        "preview": task_preview,
    }


@app.post("/email/{account}/task-create")
def create_task_from_email_endpoint(
    account: Literal["church", "personal"],
    request: TaskCreateRequest,
    user: str = Depends(get_current_user),
) -> dict:
    """Create a task in Firestore from an email.
    
    Creates the task with the user-confirmed details and links
    it back to the source email.
    """
    from datetime import date
    from daily_task_assistant.mailer import GmailError, load_account_from_env, get_message
    from daily_task_assistant.task_store import create_task_from_email, FirestoreTask
    
    # Load the email for subject reference
    try:
        gmail_config = load_account_from_env(account)
        email = get_message(gmail_config, request.email_id)
    except GmailError as exc:
        raise HTTPException(status_code=502, detail=f"Gmail API error: {exc}")
    
    # Parse due date if provided
    due_date = None
    if request.due_date:
        try:
            due_date = date.fromisoformat(request.due_date)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid due_date format (use YYYY-MM-DD)")
    
    # Create the task
    try:
        task = create_task_from_email(
            user_id=user,
            email_id=request.email_id,
            email_account=account,
            email_subject=email.subject,
            title=request.title,
            due_date=due_date,
            priority=request.priority,
            domain=request.domain,
            project=request.project,
            notes=request.notes,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to create task: {exc}")
    
    return {
        "status": "created",
        "account": account,
        "emailId": request.email_id,
        "task": task.to_api_dict(),
    }


class EmailTaskCheckRequest(BaseModel):
    """Request to check which emails have linked tasks."""
    email_ids: List[str] = Field(..., description="List of Gmail message IDs to check")


@app.post("/email/{account}/check-tasks")
def check_emails_have_tasks(
    account: Literal["church", "personal"],
    request: EmailTaskCheckRequest,
    user: str = Depends(get_current_user),
) -> dict:
    """Check which emails already have tasks linked to them.
    
    Returns a mapping of email_id -> task info (id, status, title) for emails
    that have tasks. Emails without tasks are not included in the response.
    """
    from daily_task_assistant.task_store import list_tasks
    
    # Get all email-sourced tasks for this user
    all_tasks = list_tasks(user, limit=500)
    
    # Build lookup by source email ID
    email_to_task = {}
    for task in all_tasks:
        if task.source_email_id and task.source_email_account == account:
            email_to_task[task.source_email_id] = {
                "taskId": task.id,
                "title": task.title,
                "status": task.status,
                "priority": task.priority,
            }
    
    # Filter to only requested email IDs
    result = {}
    for email_id in request.email_ids:
        if email_id in email_to_task:
            result[email_id] = email_to_task[email_id]
    
    return {
        "account": account,
        "emailsChecked": len(request.email_ids),
        "emailsWithTasks": len(result),
        "tasks": result,
    }


@app.get("/tasks/firestore")
def list_firestore_tasks(
    domain: Optional[str] = Query(None, description="Filter by domain"),
    status: Optional[str] = Query(None, description="Filter by status"),
    source: Optional[str] = Query(None, description="Filter by source"),
    limit: int = Query(50, ge=1, le=200, description="Maximum tasks to return"),
    user: str = Depends(get_current_user),
) -> dict:
    """List tasks from the Firestore task store.
    
    This is the native DATA task store, separate from Smartsheet.
    Used primarily for email-created tasks.
    """
    from daily_task_assistant.task_store import list_tasks, TaskFilters
    
    # Build filters
    filters = TaskFilters(
        domain=domain,
        status=[status] if status else None,
        source=source,
    )
    
    tasks = list_tasks(user, filters=filters, limit=limit)
    
    return {
        "count": len(tasks),
        "tasks": [t.to_api_dict() for t in tasks],
    }


@app.get("/tasks/firestore/{task_id}")
def get_firestore_task(
    task_id: str,
    user: str = Depends(get_current_user),
) -> dict:
    """Get a single task from Firestore."""
    from daily_task_assistant.tasks import get_task
    
    task = get_task(user, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    return {"task": task.to_api_dict()}


@app.patch("/tasks/firestore/{task_id}")
def update_firestore_task(
    task_id: str,
    updates: Dict[str, Any],
    user: str = Depends(get_current_user),
) -> dict:
    """Update a task in Firestore."""
    from daily_task_assistant.task_store import update_task
    
    task = update_task(user, task_id, updates)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    return {"task": task.to_api_dict()}


@app.delete("/tasks/firestore/{task_id}")
def delete_firestore_task(
    task_id: str,
    user: str = Depends(get_current_user),
) -> dict:
    """Delete a task from Firestore."""
    from daily_task_assistant.task_store import delete_task
    
    deleted = delete_task(user, task_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Task not found")
    
    return {"status": "deleted", "taskId": task_id}


# --- Email Memory Endpoints (Phase C) ---
# Note: All memory endpoints are now keyed by account (church/personal), not user login.

@app.get("/email/{account}/memory/sender-profiles")
def get_sender_profiles(
    account: Literal["church", "personal"],
    vip_only: bool = Query(False, description="Only return VIP senders"),
    limit: int = Query(50, ge=1, le=200),
    user: str = Depends(get_current_user),
) -> dict:
    """List sender profiles from email memory for the specified account."""
    from daily_task_assistant.email import list_sender_profiles

    profiles = list_sender_profiles(account, vip_only=vip_only, limit=limit)

    return {
        "account": account,
        "count": len(profiles),
        "profiles": [p.to_dict() for p in profiles],
    }


@app.get("/email/{account}/memory/sender/{email}")
def get_sender_profile_endpoint(
    account: Literal["church", "personal"],
    email: str,
    user: str = Depends(get_current_user),
) -> dict:
    """Get a specific sender profile for the specified account."""
    from daily_task_assistant.email import get_sender_profile

    profile = get_sender_profile(account, email)
    if not profile:
        raise HTTPException(status_code=404, detail="Sender profile not found")

    return {"account": account, "profile": profile.to_dict()}


@app.post("/email/{account}/memory/seed")
def seed_email_memory(
    account: Literal["church", "personal"],
    user: str = Depends(get_current_user),
) -> dict:
    """Seed sender profiles from the memory graph for the specified account.

    Creates initial profiles for known contacts (family, work colleagues).
    Safe to call multiple times - will update existing profiles.
    """
    from daily_task_assistant.email import seed_sender_profiles_from_memory_graph

    count = seed_sender_profiles_from_memory_graph(account)

    return {
        "account": account,
        "status": "seeded",
        "profilesCreated": count,
    }


@app.get("/email/{account}/memory/category-patterns")
def get_category_patterns_endpoint(
    account: Literal["church", "personal"],
    limit: int = Query(50, ge=1, le=200),
    user: str = Depends(get_current_user),
) -> dict:
    """List learned category patterns for the specified account."""
    from daily_task_assistant.email import get_category_patterns

    patterns = get_category_patterns(account, limit=limit)

    return {
        "account": account,
        "count": len(patterns),
        "patterns": [p.to_dict() for p in patterns],
    }


@app.post("/email/{account}/memory/category-approval")
def record_category_approval_endpoint(
    account: Literal["church", "personal"],
    pattern: str = Query(..., description="Domain or email address pattern"),
    pattern_type: str = Query(..., description="'domain' or 'sender'"),
    category: str = Query(..., description="Category/label to associate"),
    user: str = Depends(get_current_user),
) -> dict:
    """Record that a category suggestion was approved for the specified account.

    This reinforces the pattern for future suggestions.
    """
    from daily_task_assistant.email import record_category_approval

    updated = record_category_approval(account, pattern, pattern_type, category)

    return {
        "account": account,
        "status": "recorded",
        "pattern": updated.to_dict(),
    }


@app.post("/email/{account}/memory/category-dismissal")
def record_category_dismissal_endpoint(
    account: Literal["church", "personal"],
    pattern: str = Query(..., description="Domain or email address pattern"),
    pattern_type: str = Query(..., description="'domain' or 'sender'"),
    user: str = Depends(get_current_user),
) -> dict:
    """Record that a category suggestion was dismissed for the specified account.

    This decreases confidence in the pattern.
    """
    from daily_task_assistant.email import record_category_dismissal

    record_category_dismissal(account, pattern, pattern_type)

    return {"account": account, "status": "recorded"}


@app.get("/email/{account}/memory/timing")
def get_timing_patterns_endpoint(
    account: Literal["church", "personal"],
    user: str = Depends(get_current_user),
) -> dict:
    """Get email processing timing patterns for the specified account."""
    from daily_task_assistant.email import get_timing_patterns

    patterns = get_timing_patterns(account)

    if not patterns:
        return {
            "account": account,
            "patterns": None,
            "message": "No timing patterns recorded yet",
        }

    return {"account": account, "patterns": patterns.to_dict()}


@app.get("/email/{account}/memory/response-warning")
def check_response_warning(
    account: Literal["church", "personal"],
    sender_email: str = Query(..., description="Sender's email address"),
    received_hours_ago: float = Query(..., description="Hours since email was received"),
    user: str = Depends(get_current_user),
) -> dict:
    """Check if David should be warned about a delayed response.

    Compares current response time against average for that sender type.
    Account is required (memory data is per-account).
    """
    from daily_task_assistant.email import (
        get_sender_profile,
        get_average_response_time,
    )

    profile = get_sender_profile(account, sender_email)

    if not profile:
        return {
            "account": account,
            "warning": False,
            "message": "Unknown sender - no expectations set",
        }

    avg_time = get_average_response_time(account, profile.relationship)

    if avg_time is None:
        return {
            "account": account,
            "warning": False,
            "message": f"No historical data for {profile.relationship} senders",
        }

    if received_hours_ago > avg_time * 1.5:  # 50% over average
        return {
            "account": account,
            "warning": True,
            "message": f"Email from {profile.name} has been waiting {received_hours_ago:.1f} hours. "
                      f"You typically respond to {profile.relationship} senders within {avg_time:.1f} hours.",
            "averageResponseTime": avg_time,
            "currentWaitTime": received_hours_ago,
            "senderName": profile.name,
            "senderRelationship": profile.relationship,
        }

    return {
        "account": account,
        "warning": False,
        "averageResponseTime": avg_time,
        "currentWaitTime": received_hours_ago,
    }


# --- Haiku Intelligence Layer endpoints ---

class HaikuSettingsRequest(BaseModel):
    """Request body for updating Haiku settings."""
    enabled: Optional[bool] = Field(None, description="Enable/disable Haiku analysis")
    daily_limit: Optional[int] = Field(None, ge=0, le=500, description="Daily analysis limit")
    weekly_limit: Optional[int] = Field(None, ge=0, le=2000, description="Weekly analysis limit")


@app.get("/email/haiku/settings")
def get_haiku_settings(
    user: str = Depends(get_current_user),
) -> dict:
    """Get current Haiku analysis settings.

    Settings are GLOBAL (shared across all login identities).
    Returns the enabled flag and usage limits.
    """
    from daily_task_assistant.email import (
        get_haiku_settings as get_settings,
    )

    # GLOBAL settings - no user parameter needed
    settings = get_settings()
    return {
        "settings": settings.to_api_dict(),
    }


@app.put("/email/haiku/settings")
def update_haiku_settings(
    request: HaikuSettingsRequest,
    user: str = Depends(get_current_user),
) -> dict:
    """Update Haiku analysis settings.

    Settings are GLOBAL (shared across all login identities).
    Allows toggling Haiku on/off and adjusting daily/weekly limits.
    """
    from daily_task_assistant.email import (
        get_haiku_settings as get_settings,
        save_haiku_settings as save_settings,
        HaikuSettings,
    )

    # GLOBAL settings - no user parameter needed
    current = get_settings()

    # Update only provided fields
    new_settings = HaikuSettings(
        enabled=request.enabled if request.enabled is not None else current.enabled,
        daily_limit=request.daily_limit if request.daily_limit is not None else current.daily_limit,
        weekly_limit=request.weekly_limit if request.weekly_limit is not None else current.weekly_limit,
    )

    # Save GLOBAL settings
    save_settings(new_settings)

    return {
        "status": "updated",
        "settings": new_settings.to_api_dict(),
    }


@app.get("/email/haiku/usage")
def get_haiku_usage(
    user: str = Depends(get_current_user),
) -> dict:
    """Get current Haiku usage statistics.

    Usage is GLOBAL (shared across all login identities).
    Returns daily/weekly counts, limits, and remaining capacity.
    Includes flags indicating if user can still use Haiku.
    """
    from daily_task_assistant.email import (
        get_haiku_usage_summary,
    )

    # GLOBAL usage - no user parameter needed
    summary = get_haiku_usage_summary()

    return {
        "usage": summary,
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
    source: Literal["personal", "work"] = "personal"  # Which Smartsheet to update
    action: Literal[
        "mark_complete", "update_status", "update_priority", "update_due_date", "add_comment",
        "update_number", "update_contact_flag", "update_recurring", "update_project",
        "update_task", "update_assigned_to", "update_notes", "update_estimated_hours"
    ]
    status: Optional[str] = Field(None, description="New status value (for update_status)")
    priority: Optional[str] = Field(None, description="New priority value (for update_priority)")
    due_date: Optional[str] = Field(None, description="New due date in YYYY-MM-DD format (for update_due_date)")
    comment: Optional[str] = Field(None, description="Comment text (for add_comment)")
    number: Optional[int] = Field(None, description="Task number (for update_number)")
    contact_flag: Optional[bool] = Field(None, description="Contact checkbox value (for update_contact_flag)")
    recurring: Optional[str] = Field(None, description="Recurring pattern (for update_recurring)")
    project: Optional[str] = Field(None, description="Project name (for update_project)")
    task_title: Optional[str] = Field(None, description="New task title (for update_task)")
    assigned_to: Optional[str] = Field(None, description="Assignee email (for update_assigned_to)")
    notes: Optional[str] = Field(None, description="Notes text (for update_notes)")
    estimated_hours: Optional[str] = Field(None, description="Estimated hours value (for update_estimated_hours)")
    confirmed: bool = Field(False, description="User has confirmed this action")


# Valid status values from Smartsheet (authoritative list)
# Active: Scheduled, Recurring, On Hold, In Progress, Follow-up, Awaiting Reply,
#         Delivered, Create ZD Ticket, Validation, Needs Approval
# Terminal (also marks Done): Ticket Created, Cancelled, Delegated, Completed
VALID_STATUSES = [
    "Scheduled", "Recurring", "On Hold", "In Progress", "Follow-up", "Awaiting Reply",
    "Delivered", "Create ZD Ticket", "Ticket Created", "Validation", "Needs Approval",
    "Cancelled", "Delegated", "Completed"
]
VALID_PRIORITIES = ["Critical", "Urgent", "Important", "Standard", "Low"]
VALID_PRIORITIES_WORK = ["5-Critical", "4-Urgent", "3-Important", "2-Standard", "1-Low"]
VALID_RECURRING = ["M", "T", "W", "H", "F", "Sa", "Monthly"]
VALID_PROJECTS_PERSONAL = [
    "Around The House", "Church Tasks", "Family Time", "Shopping", 
    "Sm. Projects & Tasks", "Zendesk Ticket"
]
VALID_PROJECTS_WORK = [
    "Atlassian (Jira/Confluence)", "Crafter Studio", "Internal Application Support",
    "Team Management", "Strategic Planning", "Stakeholder Relations", "Process Improvement",
    "Daily Operations", "Zendesk Support", "Intranet Management", "Vendor Management",
    "AI/Automation Projects", "DTS Transformation", "New Technology Evaluation", "Innovation"
]
VALID_ESTIMATED_HOURS = [".05", ".15", ".25", ".50", ".75", "1", "2", "3", "4", "5", "6", "7", "8"]
# Terminal statuses that should also mark Done checkbox
TERMINAL_STATUSES = ["Completed", "Cancelled", "Delegated", "Ticket Created"]


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
        all_valid_priorities = VALID_PRIORITIES + VALID_PRIORITIES_WORK
        if request.priority not in all_valid_priorities:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid priority '{request.priority}'. Valid: {all_valid_priorities}"
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
    elif request.action == "update_number":
        if request.number is None:
            raise HTTPException(status_code=400, detail="number field required for update_number action")
        if not isinstance(request.number, int) or request.number < 0:
            raise HTTPException(status_code=400, detail="number must be a non-negative integer")
    elif request.action == "update_contact_flag":
        if request.contact_flag is None:
            raise HTTPException(status_code=400, detail="contact_flag field required for update_contact_flag action")
    elif request.action == "update_recurring":
        if not request.recurring:
            raise HTTPException(status_code=400, detail="recurring field required for update_recurring action")
        if request.recurring not in VALID_RECURRING:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid recurring '{request.recurring}'. Valid: {VALID_RECURRING}"
            )
    elif request.action == "update_project":
        if not request.project:
            raise HTTPException(status_code=400, detail="project field required for update_project action")
        all_valid_projects = VALID_PROJECTS_PERSONAL + VALID_PROJECTS_WORK
        if request.project not in all_valid_projects:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid project '{request.project}'. Valid: {all_valid_projects}"
            )
    elif request.action == "update_task":
        if not request.task_title:
            raise HTTPException(status_code=400, detail="task_title field required for update_task action")
    elif request.action == "update_assigned_to":
        if not request.assigned_to:
            raise HTTPException(status_code=400, detail="assigned_to field required for update_assigned_to action")
        # Basic email validation
        if "@" not in request.assigned_to:
            raise HTTPException(status_code=400, detail="assigned_to must be a valid email address")
    elif request.action == "update_notes":
        if request.notes is None:
            raise HTTPException(status_code=400, detail="notes field required for update_notes action")
    elif request.action == "update_estimated_hours":
        if not request.estimated_hours:
            raise HTTPException(status_code=400, detail="estimated_hours field required for update_estimated_hours action")
        if request.estimated_hours not in VALID_ESTIMATED_HOURS:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid estimated_hours '{request.estimated_hours}'. Valid: {VALID_ESTIMATED_HOURS}"
            )
    
    # Build preview of proposed changes
    preview = {
        "taskId": task_id,
        "action": request.action,
        "changes": {},
    }
    
    if request.action == "mark_complete":
        preview["changes"] = {"done": True}
        preview["description"] = "Mark task as complete (Done → checked; for recurring tasks, status stays 'Recurring')"
    elif request.action == "update_status":
        # Determine if Done checkbox should be updated based on status
        if request.status in TERMINAL_STATUSES:
            preview["changes"] = {"status": request.status, "done": True}
            preview["description"] = f"Update status to '{request.status}' (Done → checked)"
        else:
            # Active status - only update status, don't touch Done
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
        comment_preview = request.comment[:50] + "..." if len(request.comment or "") > 50 else request.comment
        preview["description"] = f"Add comment: '{comment_preview}'"
    elif request.action == "update_number":
        preview["changes"] = {"number": request.number}
        preview["description"] = f"Update task number to {request.number}"
    elif request.action == "update_contact_flag":
        preview["changes"] = {"contact_flag": request.contact_flag}
        flag_text = "checked" if request.contact_flag else "unchecked"
        preview["description"] = f"Set contact flag to {flag_text}"
    elif request.action == "update_recurring":
        preview["changes"] = {"recurring_pattern": request.recurring}
        preview["description"] = f"Set recurring pattern to '{request.recurring}'"
    elif request.action == "update_project":
        preview["changes"] = {"project": request.project}
        preview["description"] = f"Move task to project '{request.project}'"
    elif request.action == "update_task":
        preview["changes"] = {"task": request.task_title}
        title_preview = request.task_title[:50] + "..." if len(request.task_title or "") > 50 else request.task_title
        preview["description"] = f"Rename task to '{title_preview}'"
    elif request.action == "update_assigned_to":
        preview["changes"] = {"assigned_to": request.assigned_to}
        preview["description"] = f"Assign task to '{request.assigned_to}'"
    elif request.action == "update_notes":
        preview["changes"] = {"notes": request.notes}
        notes_preview = request.notes[:50] + "..." if len(request.notes or "") > 50 else request.notes
        preview["description"] = f"Update notes to '{notes_preview}'"
    elif request.action == "update_estimated_hours":
        preview["changes"] = {"estimated_hours": request.estimated_hours}
        preview["description"] = f"Set estimated hours to {request.estimated_hours}"
    
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
            client.mark_complete(task_id, source=request.source)
        elif request.action == "update_status":
            # Terminal statuses also mark Done checkbox
            if request.status in TERMINAL_STATUSES:
                client.update_row(task_id, {"status": request.status, "done": True}, source=request.source)
            else:
                client.update_row(task_id, {"status": request.status}, source=request.source)
        elif request.action == "update_priority":
            client.update_row(task_id, {"priority": request.priority}, source=request.source)
        elif request.action == "update_due_date":
            client.update_row(task_id, {"due_date": request.due_date}, source=request.source)
        elif request.action == "add_comment":
            client.post_comment(task_id, request.comment, source=request.source)
        elif request.action == "update_number":
            client.update_row(task_id, {"number": request.number}, source=request.source)
        elif request.action == "update_contact_flag":
            client.update_row(task_id, {"contact_flag": request.contact_flag}, source=request.source)
        elif request.action == "update_recurring":
            client.update_row(task_id, {"recurring_pattern": request.recurring}, source=request.source)
        elif request.action == "update_project":
            client.update_row(task_id, {"project": request.project}, source=request.source)
        elif request.action == "update_task":
            client.update_row(task_id, {"task": request.task_title}, source=request.source)
        elif request.action == "update_assigned_to":
            client.update_row(task_id, {"assigned_to": request.assigned_to}, source=request.source)
        elif request.action == "update_notes":
            client.update_row(task_id, {"notes": request.notes}, source=request.source)
        elif request.action == "update_estimated_hours":
            client.update_row(task_id, {"estimated_hours": request.estimated_hours}, source=request.source)
        
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


# --- Contact Storage Endpoints (Phase 2 Foundation) ---

class SaveContactRequest(BaseModel):
    """Request body for saving a contact."""
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    title: Optional[str] = None
    organization: Optional[str] = None
    location: Optional[str] = None
    notes: Optional[str] = None
    sourceTaskId: Optional[str] = Field(None, alias="source_task_id")
    tags: Optional[List[str]] = None
    contactId: Optional[str] = Field(None, alias="contact_id")  # For updates


@app.post("/contacts")
def save_contact_endpoint(
    request: SaveContactRequest,
    user: str = Depends(get_current_user),
) -> dict:
    """Save or update a contact in the user's contact list."""
    from daily_task_assistant.contacts import save_contact
    
    contact = save_contact(
        name=request.name,
        email=request.email,
        phone=request.phone,
        title=request.title,
        organization=request.organization,
        location=request.location,
        notes=request.notes,
        source_task_id=request.sourceTaskId,
        user_email=user,
        tags=request.tags,
        contact_id=request.contactId,
    )
    
    return {
        "status": "success",
        "contact": contact.to_dict(),
    }


@app.get("/contacts")
def list_contacts_endpoint(
    limit: int = Query(100, ge=1, le=500),
    user: str = Depends(get_current_user),
) -> dict:
    """List saved contacts for the current user."""
    from daily_task_assistant.contacts import list_contacts
    
    contacts = list_contacts(user_email=user, limit=limit)
    
    return {
        "contacts": [c.to_dict() for c in contacts],
        "count": len(contacts),
    }


@app.get("/contacts/{contact_id}")
def get_contact_endpoint(
    contact_id: str,
    user: str = Depends(get_current_user),
) -> dict:
    """Get a specific contact by ID."""
    from daily_task_assistant.contacts import get_contact
    
    contact = get_contact(contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found.")
    
    return {
        "contact": contact.to_dict(),
    }


@app.delete("/contacts/{contact_id}")
def delete_contact_endpoint(
    contact_id: str,
    user: str = Depends(get_current_user),
) -> dict:
    """Delete a contact by ID."""
    from daily_task_assistant.contacts import delete_contact

    deleted = delete_contact(contact_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Contact not found.")

    return {
        "status": "success",
        "message": "Contact deleted.",
    }


# =============================================================================
# Profile Management Endpoints
# =============================================================================


class ProfileUpdateRequest(BaseModel):
    """Request body for updating user profile."""
    church_roles: Optional[List[str]] = Field(None, alias="churchRoles")
    personal_contexts: Optional[List[str]] = Field(None, alias="personalContexts")
    vip_senders: Optional[Dict[str, List[str]]] = Field(None, alias="vipSenders")
    church_attention_patterns: Optional[Dict[str, List[str]]] = Field(
        None, alias="churchAttentionPatterns"
    )
    personal_attention_patterns: Optional[Dict[str, List[str]]] = Field(
        None, alias="personalAttentionPatterns"
    )
    not_actionable_patterns: Optional[Dict[str, List[str]]] = Field(
        None, alias="notActionablePatterns"
    )

    class Config:
        populate_by_name = True


@app.get("/profile")
def get_profile_endpoint(
    user: str = Depends(get_current_user),
) -> dict:
    """Get the current user's profile.

    Profile is GLOBAL (shared across all login identities).
    Returns the profile with church roles, personal contexts, VIP senders,
    and attention patterns for role-aware email management.
    """
    from daily_task_assistant.memory import get_or_create_profile

    # GLOBAL profile - no user parameter needed
    profile = get_or_create_profile()

    return {
        "profile": {
            "userId": profile.user_id,
            "churchRoles": profile.church_roles,
            "personalContexts": profile.personal_contexts,
            "vipSenders": profile.vip_senders,
            "churchAttentionPatterns": profile.church_attention_patterns,
            "personalAttentionPatterns": profile.personal_attention_patterns,
            "notActionablePatterns": profile.not_actionable_patterns,
            "version": profile.version,
            "createdAt": profile.created_at,
            "updatedAt": profile.updated_at,
        }
    }


@app.put("/profile")
def update_profile_endpoint(
    request: ProfileUpdateRequest,
    user: str = Depends(get_current_user),
) -> dict:
    """Update the current user's profile.

    Profile is GLOBAL (shared across all login identities).
    Only provided fields are updated; omitted fields retain their current values.
    A versioned backup is created for audit purposes.
    """
    from daily_task_assistant.memory import get_or_create_profile, save_profile

    # GLOBAL profile - no user parameter needed
    profile = get_or_create_profile()

    # Update only provided fields
    if request.church_roles is not None:
        profile.church_roles = request.church_roles
    if request.personal_contexts is not None:
        profile.personal_contexts = request.personal_contexts
    if request.vip_senders is not None:
        profile.vip_senders = request.vip_senders
    if request.church_attention_patterns is not None:
        profile.church_attention_patterns = request.church_attention_patterns
    if request.personal_attention_patterns is not None:
        profile.personal_attention_patterns = request.personal_attention_patterns
    if request.not_actionable_patterns is not None:
        profile.not_actionable_patterns = request.not_actionable_patterns

    success = save_profile(profile)

    if not success:
        raise HTTPException(status_code=500, detail="Failed to save profile.")

    return {
        "status": "success",
        "message": "Profile updated.",
        "profile": {
            "userId": profile.user_id,
            "churchRoles": profile.church_roles,
            "personalContexts": profile.personal_contexts,
            "vipSenders": profile.vip_senders,
            "churchAttentionPatterns": profile.church_attention_patterns,
            "personalAttentionPatterns": profile.personal_attention_patterns,
            "notActionablePatterns": profile.not_actionable_patterns,
            "version": profile.version,
            "createdAt": profile.created_at,
            "updatedAt": profile.updated_at,
        }
    }

