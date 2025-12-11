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
from pydantic import BaseModel, Field

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
            # Build the update payload based on action
            update_data = {}
            
            if update.action == "mark_complete":
                # Check if task is recurring - if so, only set done
                update_data["done"] = True
                # Note: For recurring tasks, status should NOT change per user's requirements
                
            elif update.action == "update_status":
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
            client.update_row(update.row_id, update_data)
            
            results.append(BulkUpdateResult(row_id=update.row_id, success=True))
            success_count += 1
            
        except Exception as exc:
            results.append(BulkUpdateResult(
                row_id=update.row_id,
                success=False,
                error=str(exc)[:200]
            ))
    
    return {
        "success": success_count == len(request.updates),
        "totalUpdates": len(request.updates),
        "successCount": success_count,
        "failureCount": len(request.updates) - success_count,
        "results": [r.model_dump(by_alias=True) for r in results],
    }


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
        limit=None, source=request.source
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

    # Fetch conversation history to include in plan consideration (excluding struck messages)
    history = fetch_conversation_for_llm(task_id, limit=100)
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
        limit=None, source=request.source
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
        limit=None, source=request.source
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
        limit=None, source=request.source
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
        limit=None, source=request.source
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
            client.mark_complete(task_id)
        elif request.action == "update_status":
            # Terminal statuses also mark Done checkbox
            if request.status in TERMINAL_STATUSES:
                client.update_row(task_id, {"status": request.status, "done": True})
            else:
                client.update_row(task_id, {"status": request.status})
        elif request.action == "update_priority":
            client.update_row(task_id, {"priority": request.priority})
        elif request.action == "update_due_date":
            client.update_row(task_id, {"due_date": request.due_date})
        elif request.action == "add_comment":
            client.post_comment(task_id, request.comment)
        elif request.action == "update_number":
            client.update_row(task_id, {"number": request.number})
        elif request.action == "update_contact_flag":
            client.update_row(task_id, {"contact_flag": request.contact_flag})
        elif request.action == "update_recurring":
            client.update_row(task_id, {"recurring_pattern": request.recurring})
        elif request.action == "update_project":
            client.update_row(task_id, {"project": request.project})
        elif request.action == "update_task":
            client.update_row(task_id, {"task": request.task_title})
        elif request.action == "update_assigned_to":
            client.update_row(task_id, {"assigned_to": request.assigned_to})
        elif request.action == "update_notes":
            client.update_row(task_id, {"notes": request.notes})
        elif request.action == "update_estimated_hours":
            client.update_row(task_id, {"estimated_hours": request.estimated_hours})
        
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

