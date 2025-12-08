"""FastAPI service for Daily Task Assistant."""
from __future__ import annotations

import os
from dataclasses import asdict
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional
from datetime import datetime, timezone

# Load .env file early (for local development - staging uses Cloud Run secrets)
try:
    from dotenv import load_dotenv
    # Load from the daily-task-assistant directory
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    pass  # dotenv not installed, rely on environment variables

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
    "http://localhost:5174",  # Vite fallback port
    "http://127.0.0.1:5173",
    "http://127.0.0.1:5174",
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
    """Health check endpoint with service status information.
    
    Returns status of critical services including Anthropic API and Gmail configuration.
    Used by CI/CD pipeline to verify deployment success.
    
    Note: This endpoint must NOT call _get_settings() as it may raise ConfigError
    if required env vars are missing. We read env vars directly instead.
    """
    # Get environment directly - don't use _get_settings() as it may throw
    environment = os.getenv("DTA_ENV", "local")
    errors = {}
    
    # Check Anthropic configuration
    anthropic_status = "not_configured"
    try:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if api_key and len(api_key) > 10:
            anthropic_status = "configured"
        else:
            errors["anthropic"] = "ANTHROPIC_API_KEY not set or invalid"
    except Exception as e:
        errors["anthropic"] = str(e)
    
    # Check Smartsheet configuration
    smartsheet_status = "not_configured"
    try:
        smartsheet_token = os.getenv("SMARTSHEET_API_TOKEN")
        if smartsheet_token and len(smartsheet_token) > 10:
            smartsheet_status = "configured"
        else:
            errors["smartsheet"] = "SMARTSHEET_API_TOKEN not set or invalid"
    except Exception as e:
        errors["smartsheet"] = str(e)
    
    # Check Church Gmail configuration
    church_gmail_status = "not_configured"
    try:
        church_client_id = os.getenv("CHURCH_GMAIL_CLIENT_ID")
        church_client_secret = os.getenv("CHURCH_GMAIL_CLIENT_SECRET")
        church_refresh_token = os.getenv("CHURCH_GMAIL_REFRESH_TOKEN")
        if all([church_client_id, church_client_secret, church_refresh_token]):
            church_gmail_status = "configured"
        else:
            missing = []
            if not church_client_id:
                missing.append("CHURCH_GMAIL_CLIENT_ID")
            if not church_client_secret:
                missing.append("CHURCH_GMAIL_CLIENT_SECRET")
            if not church_refresh_token:
                missing.append("CHURCH_GMAIL_REFRESH_TOKEN")
            errors["church_gmail"] = f"Missing: {', '.join(missing)}"
    except Exception as e:
        errors["church_gmail"] = str(e)
    
    # Check Personal Gmail configuration
    personal_gmail_status = "not_configured"
    try:
        personal_client_id = os.getenv("PERSONAL_GMAIL_CLIENT_ID")
        personal_client_secret = os.getenv("PERSONAL_GMAIL_CLIENT_SECRET")
        personal_refresh_token = os.getenv("PERSONAL_GMAIL_REFRESH_TOKEN")
        if all([personal_client_id, personal_client_secret, personal_refresh_token]):
            personal_gmail_status = "configured"
        else:
            missing = []
            if not personal_client_id:
                missing.append("PERSONAL_GMAIL_CLIENT_ID")
            if not personal_client_secret:
                missing.append("PERSONAL_GMAIL_CLIENT_SECRET")
            if not personal_refresh_token:
                missing.append("PERSONAL_GMAIL_REFRESH_TOKEN")
            errors["personal_gmail"] = f"Missing: {', '.join(missing)}"
    except Exception as e:
        errors["personal_gmail"] = str(e)
    
    return {
        "status": "ok",
        "time": datetime.now(timezone.utc).isoformat(),
        "environment": environment,
        "services": {
            "anthropic": anthropic_status,
            "smartsheet": smartsheet_status,
            "church_gmail": church_gmail_status,
            "personal_gmail": personal_gmail_status,
        },
        "errors": errors if errors else None,
    }


@app.get("/health/anthropic-test")
def anthropic_test() -> dict:
    """Test endpoint to verify Anthropic API connection works.
    
    Makes a simple API call to verify the connection is working.
    This helps diagnose issues where config looks correct but calls fail.
    """
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        from daily_task_assistant.llm.anthropic_client import build_anthropic_client, resolve_config
        logger.info("Imported anthropic_client successfully")
        
        client = build_anthropic_client()
        logger.info("Built anthropic client successfully")
        
        config = resolve_config()
        logger.info(f"Using model: {config.model}")
        
        # Make a minimal API call
        response = client.messages.create(
            model=config.model,
            max_tokens=50,
            messages=[{"role": "user", "content": "Say 'OK' if you can hear me."}],
        )
        logger.info("API call succeeded")
        
        # Extract response text
        text = ""
        for block in response.content:
            if hasattr(block, "text"):
                text += block.text
        
        return {
            "status": "ok",
            "model": config.model,
            "response": text[:100],
            "stop_reason": response.stop_reason,
        }
    except Exception as e:
        logger.exception("Anthropic test failed")
        return {
            "status": "error",
            "error_type": type(e).__name__,
            "error_message": str(e),
        }


@app.get("/tasks")
def list_tasks(
    source: Literal["auto", "live", "stub"] = Query("auto"),
    limit: Optional[int] = Query(None, ge=1, le=500),
    sources: Optional[str] = Query(
        None,
        description="Comma-separated list of source keys to fetch (e.g., 'personal,work'). "
                    "If not specified, fetches from sources included in 'ALL' filter (excludes work).",
    ),
    include_work: bool = Query(
        False,
        alias="includeWork",
        description="If true, include work tasks in the response (overrides sources).",
    ),
    user: str = Depends(get_current_user),
) -> dict:
    # Parse sources parameter
    source_list = None
    if sources:
        source_list = [s.strip() for s in sources.split(",") if s.strip()]

    tasks, live_tasks, settings, warning = fetch_task_dataset(
        limit=limit,
        source=source,
        sources=source_list,
        include_work_in_all=include_work,
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
    """Get work task counts for the badge indicator.

    Returns counts of urgent, due_soon, and overdue work tasks
    to display as a notification badge in the UI.
    """
    from daily_task_assistant.smartsheet_client import SmartsheetClient

    try:
        settings = _get_settings()
        client = SmartsheetClient(settings)
        counts = client.get_work_tasks_count()
        return {
            "urgent": counts["urgent"],
            "dueSoon": counts["due_soon"],
            "overdue": counts["overdue"],
            "total": counts["total"],
            "needsAttention": counts["urgent"] + counts["overdue"],
        }
    except Exception as e:
        return {
            "urgent": 0,
            "dueSoon": 0,
            "overdue": 0,
            "total": 0,
            "needsAttention": 0,
            "error": str(e),
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
    
    # Include work tasks when searching by specific task_id
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
    model_config = {"populate_by_name": True}
    
    source: Literal["auto", "live", "stub"] = "auto"
    anthropic_model: Optional[str] = Field(
        None, alias="anthropicModel", description="Override Anthropic model name."
    )
    workspace_context: Optional[str] = Field(
        None, alias="workspaceContext", description="Additional context from workspace selections."
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
    # Include work tasks when searching by specific task_id
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

    result = execute_assist(
        task=target,
        settings=settings,
        source=request.source,
        anthropic_model=request.anthropic_model,
        send_email_account=None,
        live_tasks=live_tasks,
        conversation_history=llm_history if llm_history else None,
        workspace_context=request.workspace_context,
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
    selected_attachments: Optional[List[str]] = Field(
        None, 
        alias="selectedAttachments",
        description="IDs of attachments user selected to include"
    )
    workspace_context: Optional[str] = Field(
        None,
        alias="workspaceContext", 
        description="Checked workspace content to include"
    )
    
    model_config = {"populate_by_name": True}


@app.post("/assist/{task_id}/chat")
def chat_with_task(
    task_id: str,
    request: ChatRequest,
    user: str = Depends(get_current_user),
) -> dict:
    """Send a conversational message about a task and get a response from DATA.
    
    Uses intent classification to determine what context to load, optimizing
    token usage. If DATA detects a task update intent, returns a pending_action.
    """
    from daily_task_assistant.llm.anthropic_client import AnthropicError
    from daily_task_assistant.llm.intent_classifier import classify_intent
    from daily_task_assistant.llm.context_assembler import assemble_context
    from daily_task_assistant.llm.chat_executor import execute_chat
    from daily_task_assistant.smartsheet_client import SmartsheetClient

    settings = _get_settings()
    
    # Include work tasks when searching by specific task_id
    tasks, live_tasks, _, warning = fetch_task_dataset(
        limit=None, source=request.source, include_work_in_all=True
    )
    target = next((task for task in tasks if task.row_id == task_id), None)
    if not target:
        raise HTTPException(status_code=404, detail="Task not found.")

    # Fetch conversation history
    llm_history_messages = fetch_conversation_for_llm(task_id, limit=50)
    llm_history: List[Dict[str, str]] = [
        {"role": msg.role, "content": msg.content} for msg in llm_history_messages
    ]

    # Determine if user selected any images
    has_selected_images = bool(request.selected_attachments)
    has_workspace = bool(request.workspace_context)

    # Step 1: Classify intent to determine what context is needed
    intent = classify_intent(
        message=request.message,
        task_title=target.title,
        has_selected_images=has_selected_images,
        has_workspace_content=has_workspace,
    )

    # Step 2: Fetch selected attachments only if needed
    selected_attachment_details = []
    if intent.include_images and request.selected_attachments:
        try:
            client = SmartsheetClient(settings)
            for att_id in request.selected_attachments:
                detail = client.get_attachment_url(att_id, source=target.source)
                if detail:
                    selected_attachment_details.append(detail)
        except Exception as e:
            print(f"Warning: Failed to fetch selected attachments: {e}")

    # Step 3: Assemble context based on intent
    context = assemble_context(
        intent=intent,
        task=target,
        user_message=request.message,
        history=llm_history if intent.include_history else None,
        selected_images=selected_attachment_details if intent.include_images else None,
        workspace_content=request.workspace_context if intent.include_workspace else None,
    )

    # Log the user message
    log_user_message(
        task_id,
        content=request.message,
        user_email=user,
        metadata={
            "source": request.source,
            "intent": intent.intent,
            "estimated_tokens": context.estimated_tokens,
        },
    )

    # Step 4: Execute chat with assembled context
    try:
        chat_response = execute_chat(context, intent)
    except AnthropicError as exc:
        raise HTTPException(status_code=502, detail=f"AI service error: {exc}")

    # Log the assistant response
    log_assistant_message(
        task_id,
        content=chat_response.message,
        plan=None,  # No structured plan for chat responses
        metadata={
            "source": "chat",
            "intent": chat_response.intent_used,
            "tokens_used": chat_response.tokens_used,
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
        "intent": chat_response.intent_used,
        "tokensUsed": chat_response.tokens_used,
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
            "number": action.number,
            "contactFlag": action.contact_flag,
            "recurring": action.recurring,
            "project": action.project,
            "taskTitle": action.task_title,
            "assignedTo": action.assigned_to,
            "notes": action.notes,
            "estimatedHours": action.estimated_hours,
            "reason": action.reason,
        }
    
    # Include email draft update if DATA suggested changes
    if chat_response.email_draft_update:
        update = chat_response.email_draft_update
        response_data["emailDraftUpdate"] = {
            "to": update.to,
            "cc": update.cc,
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

    # Include work tasks when searching by specific task_id
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

    # Include work tasks when searching by specific task_id
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

    # Include work tasks when searching by specific task_id
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

    # Include work tasks when searching by specific task_id
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

    # Include work tasks when searching by specific task_id
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

    # Build recipient addresses
    to_address = ", ".join(request.to)
    cc_address = ", ".join(request.cc) if request.cc else None

    try:
        message_id = send_email(
            account=gmail_config,
            to_address=to_address,
            subject=request.subject,
            body=request.body,
            cc_address=cc_address,
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
                source=target.source,
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


@app.get("/assist/{task_id}/attachments")
def get_task_attachments(
    task_id: str,
    user: str = Depends(get_current_user),
) -> dict:
    """Fetch attachments for a specific task from Smartsheet.
    
    Returns a list of attachment metadata. Use the /attachment/{id}/url endpoint
    to get fresh download URLs (Smartsheet URLs expire in ~2 minutes).
    """
    from daily_task_assistant.smartsheet_client import SmartsheetClient
    
    settings = _get_settings()
    
    # Get the task to determine which sheet it belongs to
    tasks, _, _, _ = fetch_task_dataset(
        limit=None, source="auto", include_work_in_all=True
    )
    target = next((task for task in tasks if task.row_id == task_id), None)
    if not target:
        raise HTTPException(status_code=404, detail="Task not found.")
    
    task_source = target.source
    client = SmartsheetClient(settings)
    
    # Fetch attachment list
    attachments = client.list_attachments(task_id, source=task_source)
    
    # Fetch download URLs for each attachment (for initial display)
    attachment_details = []
    for att in attachments:
        detail = client.get_attachment_url(att.attachment_id, source=task_source)
        if detail:
            attachment_details.append({
                "attachmentId": detail.attachment_id,
                "name": detail.name,
                "mimeType": detail.mime_type,
                "sizeBytes": detail.size_bytes,
                "createdAt": detail.created_at,
                "attachmentType": detail.attachment_type,
                "downloadUrl": detail.download_url,
                "isImage": detail.mime_type.startswith("image/"),
                "source": task_source,  # Include source for fresh URL fetching
            })
    
    return {
        "taskId": task_id,
        "attachments": attachment_details,
    }


@app.get("/assist/{task_id}/attachment/{attachment_id}/download")
def download_attachment(
    task_id: str,
    attachment_id: str,
    user: str = Depends(get_current_user),
):
    """Download an attachment by proxying through the backend.
    
    This avoids CORS issues by fetching from Smartsheet/S3 server-side
    and returning the file content directly.
    """
    from daily_task_assistant.smartsheet_client import SmartsheetClient
    from fastapi.responses import Response
    import urllib.request
    
    settings = _get_settings()
    
    # Get the task to determine which sheet it belongs to
    tasks, _, _, _ = fetch_task_dataset(
        limit=None, source="auto", include_work_in_all=True
    )
    target = next((task for task in tasks if task.row_id == task_id), None)
    if not target:
        raise HTTPException(status_code=404, detail="Task not found.")
    
    task_source = target.source
    client = SmartsheetClient(settings)
    
    # Get fresh download URL
    detail = client.get_attachment_url(attachment_id, source=task_source)
    if not detail or not detail.download_url:
        raise HTTPException(status_code=404, detail="Attachment not found.")
    
    # Fetch the file from S3 and return it
    try:
        with urllib.request.urlopen(detail.download_url, timeout=30) as response:
            content = response.read()
            return Response(
                content=content,
                media_type=detail.mime_type,
                headers={
                    "Content-Disposition": f'attachment; filename="{detail.name}"'
                }
            )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to download attachment: {e}")


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
    number: Optional[int] = Field(None, description="New task number (for update_number)")
    contact_flag: Optional[bool] = Field(None, alias="contactFlag", description="Contact flag value (for update_contact_flag)")
    recurring: Optional[str] = Field(None, description="Recurring pattern (for update_recurring)")
    project: Optional[str] = Field(None, description="Project name (for update_project)")
    task_title: Optional[str] = Field(None, alias="taskTitle", description="Task title (for update_task)")
    assigned_to: Optional[str] = Field(None, alias="assignedTo", description="Assigned to email (for update_assigned_to)")
    notes: Optional[str] = Field(None, description="Notes text (for update_notes)")
    estimated_hours: Optional[str] = Field(None, alias="estimatedHours", description="Estimated hours (for update_estimated_hours)")
    confirmed: bool = Field(False, description="User has confirmed this action")


# Valid values from smartsheet.yml
VALID_STATUSES = [
    "Scheduled", "In Progress", "Blocked", "Waiting", "Complete", "Recurring",
    "On Hold", "Follow-up", "Awaiting Reply", "Delivered", "Create ZD Ticket",
    "Ticket Created", "Validation", "Needs Approval", "Cancelled", "Delegated", "Completed"
]
VALID_PRIORITIES_PERSONAL = ["Critical", "Urgent", "Important", "Standard", "Low"]
VALID_PRIORITIES_WORK = ["5-Critical", "4-Urgent", "3-Important", "2-Standard", "1-Low"]
VALID_RECURRING = ["M", "T", "W", "H", "F", "Sa", "Monthly"]
VALID_ESTIMATED_HOURS = [".05", ".15", ".25", ".50", ".75", "1", "2", "3", "4", "5", "6", "7", "8"]
VALID_PROJECTS_PERSONAL = [
    "Around The House", "Church Tasks", "Family Time", 
    "Shopping", "Sm. Projects & Tasks", "Zendesk Ticket"
]
VALID_PROJECTS_WORK = [
    "Atlassian (Jira/Confluence)", "Crafter Studio", "Internal Application Support",
    "Team Management", "Strategic Planning", "Stakeholder Relations",
    "Process Improvement", "Daily Operations", "Zendesk Support",
    "Intranet Management", "Vendor Management", "AI/Automation Projects",
    "DTS Transformation", "New Technology Evaluation"
]


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
    
    # Get the task to determine which sheet it belongs to
    tasks, _, _, _ = fetch_task_dataset(
        limit=None, source="auto", include_work_in_all=True
    )
    target = next((task for task in tasks if task.row_id == task_id), None)
    task_source = target.source if target else "personal"
    
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
        # Use different priority values for work vs personal sheets
        valid_priorities = VALID_PRIORITIES_WORK if task_source == "work" else VALID_PRIORITIES_PERSONAL
        if request.priority not in valid_priorities:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid priority '{request.priority}'. Valid for {task_source}: {valid_priorities}"
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
        if not isinstance(request.number, int) or request.number < 1:
            raise HTTPException(status_code=400, detail="number must be a positive integer")
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
        # Validate based on sheet source
        valid_projects = VALID_PROJECTS_WORK if task_source == "work" else VALID_PROJECTS_PERSONAL
        if request.project not in valid_projects:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid project '{request.project}'. Valid for {task_source}: {valid_projects}"
            )
    elif request.action == "update_task":
        if not request.task_title:
            raise HTTPException(status_code=400, detail="taskTitle field required for update_task action")
    elif request.action == "update_assigned_to":
        if not request.assigned_to:
            raise HTTPException(status_code=400, detail="assignedTo field required for update_assigned_to action")
        # Basic email validation
        if "@" not in request.assigned_to:
            raise HTTPException(status_code=400, detail="assignedTo must be a valid email address")
    elif request.action == "update_notes":
        if request.notes is None:
            raise HTTPException(status_code=400, detail="notes field required for update_notes action")
    elif request.action == "update_estimated_hours":
        if not request.estimated_hours:
            raise HTTPException(status_code=400, detail="estimatedHours field required for update_estimated_hours action")
        if request.estimated_hours not in VALID_ESTIMATED_HOURS:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid estimatedHours '{request.estimated_hours}'. Valid: {VALID_ESTIMATED_HOURS}"
            )
    
    # Check if task is recurring (for smart mark_complete behavior)
    is_recurring = target and target.status and target.status.lower() == "recurring"
    
    # Build preview of proposed changes
    preview = {
        "taskId": task_id,
        "action": request.action,
        "changes": {},
    }
    
    if request.action == "mark_complete":
        if is_recurring:
            # For recurring tasks, only check Done box - don't change status
            preview["changes"] = {"done": True}
            preview["description"] = "Check Done box (status stays 'Recurring' to preserve recurrence)"
        else:
            # For non-recurring tasks, set status to Completed and check Done
            preview["changes"] = {"status": "Completed", "done": True}
            preview["description"] = "Mark task as complete (Status → Completed, Done → checked)"
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
    elif request.action == "update_number":
        preview["changes"] = {"number": request.number}
        preview["description"] = f"Update # to {request.number}"
    elif request.action == "update_contact_flag":
        preview["changes"] = {"contact_flag": request.contact_flag}
        preview["description"] = f"Set Contact flag to {'checked' if request.contact_flag else 'unchecked'}"
    elif request.action == "update_recurring":
        preview["changes"] = {"recurring_pattern": request.recurring}
        preview["description"] = f"Set Recurring pattern to '{request.recurring}'"
    elif request.action == "update_project":
        preview["changes"] = {"project": request.project}
        preview["description"] = f"Update Project to '{request.project}'"
    elif request.action == "update_task":
        preview["changes"] = {"task": request.task_title}
        preview["description"] = f"Update Task title to '{request.task_title[:50]}...'" if len(request.task_title or "") > 50 else f"Update Task title to '{request.task_title}'"
    elif request.action == "update_assigned_to":
        preview["changes"] = {"assigned_to": request.assigned_to}
        preview["description"] = f"Assign to '{request.assigned_to}'"
    elif request.action == "update_notes":
        preview["changes"] = {"notes": request.notes}
        preview["description"] = f"Update Notes to '{request.notes[:50]}...'" if len(request.notes or "") > 50 else f"Update Notes to '{request.notes}'"
    elif request.action == "update_estimated_hours":
        preview["changes"] = {"estimated_hours": request.estimated_hours}
        preview["description"] = f"Set Estimated Hours to {request.estimated_hours}"
    
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
            if is_recurring:
                # For recurring tasks, only check Done box - preserve status
                client.update_row(task_id, {"done": True}, source=task_source)
            else:
                # For non-recurring tasks, full mark_complete (status + done)
                client.mark_complete(task_id, source=task_source)
        elif request.action == "update_status":
            client.update_row(task_id, {"status": request.status}, source=task_source)
        elif request.action == "update_priority":
            client.update_row(task_id, {"priority": request.priority}, source=task_source)
        elif request.action == "update_due_date":
            client.update_row(task_id, {"due_date": request.due_date}, source=task_source)
        elif request.action == "add_comment":
            client.post_comment(task_id, request.comment, source=task_source)
        elif request.action == "update_number":
            client.update_row(task_id, {"number": request.number}, source=task_source)
        elif request.action == "update_contact_flag":
            client.update_row(task_id, {"contact_flag": request.contact_flag}, source=task_source)
        elif request.action == "update_recurring":
            client.update_row(task_id, {"recurring_pattern": request.recurring}, source=task_source)
        elif request.action == "update_project":
            client.update_row(task_id, {"project": request.project}, source=task_source)
        elif request.action == "update_task":
            client.update_row(task_id, {"task": request.task_title}, source=task_source)
        elif request.action == "update_assigned_to":
            client.update_row(task_id, {"assigned_to": request.assigned_to}, source=task_source)
        elif request.action == "update_notes":
            client.update_row(task_id, {"notes": request.notes}, source=task_source)
        elif request.action == "update_estimated_hours":
            client.update_row(task_id, {"estimated_hours": request.estimated_hours}, source=task_source)
        
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

