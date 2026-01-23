"""Email Router - Gmail inbox, attention, drafts, chat, and analysis.

Handles:
- Inbox browsing (get, search, unread)
- Message/thread retrieval
- Email actions (archive, delete, star, etc.)
- Attention items and analysis (Haiku)
- Suggestions and filter rules
- Reply drafts and sending
- Email chat with DATA
- Email memory system
- Haiku usage settings

Migrated from api/main.py as part of the API refactoring initiative.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from api.dependencies import get_current_user, ATTENTION_SCAN_CONFIG, ALLOWED_SUGGESTION_LABELS

logger = logging.getLogger(__name__)

router = APIRouter()


# =============================================================================
# Pydantic Models
# =============================================================================

class EmailMessageModel(BaseModel):
    """Model for email message data."""
    id: str
    thread_id: str = Field(..., alias="threadId")
    subject: Optional[str] = None
    sender: Optional[str] = Field(None, alias="from")
    snippet: Optional[str] = None
    date: Optional[str] = None
    labels: List[str] = []
    is_unread: bool = Field(False, alias="isUnread")
    is_important: bool = Field(False, alias="isImportant")
    is_starred: bool = Field(False, alias="isStarred")
    
    model_config = ConfigDict(populate_by_name=True)


class DismissRequest(BaseModel):
    """Request body for dismissing attention items."""
    reason: Optional[str] = None


class SnoozeRequest(BaseModel):
    """Request body for snoozing attention items."""
    until: str = Field(..., description="ISO date string when to resurface")


class PinEmailRequest(BaseModel):
    """Request body for pinning emails."""
    note: Optional[str] = Field(None, description="Optional note about why email is pinned")


class SuggestionDecisionRequest(BaseModel):
    """Request body for suggestion decisions."""
    decision: Literal["accept", "reject"]
    feedback: Optional[str] = None


class RuleDecisionRequest(BaseModel):
    """Request body for rule decisions."""
    decision: Literal["approve", "reject"]
    feedback: Optional[str] = None


class AddRuleRequest(BaseModel):
    """Request body for adding filter rules."""
    from_pattern: Optional[str] = Field(None, alias="fromPattern")
    subject_pattern: Optional[str] = Field(None, alias="subjectPattern")
    action: str
    label: Optional[str] = None
    
    model_config = ConfigDict(populate_by_name=True)


class ReplyDraftRequest(BaseModel):
    """Request body for creating reply drafts."""
    thread_id: str = Field(..., alias="threadId")
    message_id: str = Field(..., alias="messageId")
    to: List[str]
    subject: str
    body: str
    cc: Optional[List[str]] = None
    reply_all: bool = Field(False, alias="replyAll")
    
    model_config = ConfigDict(populate_by_name=True)


class ReplySendRequest(BaseModel):
    """Request body for sending replies."""
    thread_id: str = Field(..., alias="threadId")
    message_id: str = Field(..., alias="messageId")
    to: List[str]
    subject: str
    body: str
    cc: Optional[List[str]] = None
    reply_all: bool = Field(False, alias="replyAll")
    
    model_config = ConfigDict(populate_by_name=True)


class ApplyLabelRequest(BaseModel):
    """Request body for applying labels."""
    labels_to_add: List[str] = Field(default_factory=list, alias="labelsToAdd")
    labels_to_remove: List[str] = Field(default_factory=list, alias="labelsToRemove")
    
    model_config = ConfigDict(populate_by_name=True)


class EmailChatRequest(BaseModel):
    """Request body for email chat."""
    message: str
    email_context: Optional[Dict[str, Any]] = Field(None, alias="emailContext")
    history: Optional[List[Dict[str, str]]] = None
    
    model_config = ConfigDict(populate_by_name=True)


class TaskPreviewRequest(BaseModel):
    """Request body for task preview from email."""
    email_id: str = Field(..., alias="emailId")
    title: str
    domain: str = "personal"
    
    model_config = ConfigDict(populate_by_name=True)


class EmailTaskCreateRequest(BaseModel):
    """Request body for creating task from email."""
    email_id: str = Field(..., alias="emailId")
    title: str
    domain: str = "personal"
    priority: str = "Standard"
    due_date: Optional[str] = Field(None, alias="dueDate")
    notes: Optional[str] = None
    project: Optional[str] = None
    
    model_config = ConfigDict(populate_by_name=True)


class EmailTaskCheckRequest(BaseModel):
    """Request body for checking email tasks."""
    email_ids: List[str] = Field(..., alias="emailIds")
    
    model_config = ConfigDict(populate_by_name=True)


class HaikuSettingsRequest(BaseModel):
    """Request body for Haiku settings."""
    enabled: Optional[bool] = Field(None, description="Enable/disable Haiku analysis")
    daily_limit: Optional[int] = Field(None, ge=0, le=500, description="Daily analysis limit")
    weekly_limit: Optional[int] = Field(None, ge=0, le=2000, description="Weekly analysis limit")


class SyncRulesRequest(BaseModel):
    """Request body for syncing rules."""
    from_sheet: bool = Field(True, alias="fromSheet")
    
    model_config = ConfigDict(populate_by_name=True)


# =============================================================================
# Helper Functions
# =============================================================================

def _email_to_model(msg, include_body: bool = False) -> dict:
    """Convert an email message to API response format."""
    result = {
        "id": msg.id,
        "threadId": msg.thread_id,
        "subject": msg.subject,
        "from": msg.sender,
        "to": msg.to,
        "snippet": msg.snippet,
        "date": msg.date.isoformat() if msg.date else None,
        "labels": msg.labels,
        "isUnread": msg.is_unread,
        "isImportant": msg.is_important,
        "isStarred": msg.is_starred,
    }
    
    if include_body:
        result["body"] = msg.body
        result["bodyHtml"] = msg.body_html
        result["cc"] = msg.cc
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


# =============================================================================
# Inbox Endpoints
# =============================================================================

@router.get("/inbox/{account}")
def get_inbox(
    account: Literal["church", "personal"],
    max_results: int = Query(20, ge=1, le=100),
    page_token: Optional[str] = Query(None, description="Gmail pagination token"),
    user: str = Depends(get_current_user),
) -> dict:
    """Get inbox summary for a Gmail account."""
    from daily_task_assistant.mailer import GmailError, load_account_from_env, get_inbox_summary

    try:
        gmail_config = load_account_from_env(account)
    except GmailError as exc:
        raise HTTPException(status_code=400, detail=f"Gmail config error: {exc}")

    try:
        summary = get_inbox_summary(gmail_config, max_recent=max_results, page_token=page_token)
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
        "nextPageToken": summary.next_page_token,
    }


@router.get("/inbox/{account}/unread")
def get_unread(
    account: Literal["church", "personal"],
    max_results: int = Query(20, ge=1, le=100),
    from_filter: Optional[str] = Query(None, description="Filter by sender"),
    user: str = Depends(get_current_user),
) -> dict:
    """Get unread messages from a Gmail account."""
    from daily_task_assistant.mailer import GmailError, load_account_from_env, get_unread_messages

    try:
        gmail_config = load_account_from_env(account)
    except GmailError as exc:
        raise HTTPException(status_code=400, detail=f"Gmail config error: {exc}")

    try:
        messages = get_unread_messages(gmail_config, max_results=max_results, from_filter=from_filter)
    except GmailError as exc:
        raise HTTPException(status_code=502, detail=f"Gmail API error: {exc}")

    return {
        "account": account,
        "email": gmail_config.from_address,
        "count": len(messages),
        "messages": [_email_to_model(m) for m in messages],
    }


@router.get("/inbox/{account}/search")
def search_inbox(
    account: Literal["church", "personal"],
    q: str = Query(..., description="Gmail search query"),
    max_results: int = Query(20, ge=1, le=100),
    user: str = Depends(get_current_user),
) -> dict:
    """Search messages in a Gmail account."""
    from daily_task_assistant.mailer import GmailError, load_account_from_env, search_messages

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


# =============================================================================
# Message/Thread Endpoints
# =============================================================================

@router.get("/email/{account}/message/{message_id}")
def get_email_full(
    account: Literal["church", "personal"],
    message_id: str,
    full: bool = Query(True, description="Include full body content"),
    user: str = Depends(get_current_user),
) -> dict:
    """Get a single email message with full content."""
    from daily_task_assistant.mailer import GmailError, load_account_from_env, get_message

    try:
        gmail_config = load_account_from_env(account)
    except GmailError as exc:
        raise HTTPException(status_code=400, detail=f"Gmail config error: {exc}")

    try:
        msg = get_message(gmail_config, message_id, include_body=full)
    except GmailError as exc:
        raise HTTPException(status_code=502, detail=f"Gmail API error: {exc}")

    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")

    return {"message": _email_to_model(msg, include_body=full)}


@router.get("/email/{account}/thread/{thread_id}")
def get_email_thread(
    account: Literal["church", "personal"],
    thread_id: str,
    user: str = Depends(get_current_user),
) -> dict:
    """Get full thread with all messages."""
    from daily_task_assistant.mailer import GmailError, load_account_from_env, get_thread

    try:
        gmail_config = load_account_from_env(account)
    except GmailError as exc:
        raise HTTPException(status_code=400, detail=f"Gmail config error: {exc}")

    try:
        thread = get_thread(gmail_config, thread_id)
    except GmailError as exc:
        raise HTTPException(status_code=502, detail=f"Gmail API error: {exc}")

    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")

    return {
        "threadId": thread.thread_id,
        "subject": thread.subject,
        "messageCount": thread.message_count,
        "messages": [_email_to_model(m, include_body=True) for m in thread.messages],
    }


# =============================================================================
# Email Actions
# =============================================================================

@router.post("/email/{account}/archive/{message_id}")
def archive_email(
    account: Literal["church", "personal"],
    message_id: str,
    user: str = Depends(get_current_user),
) -> dict:
    """Archive an email (remove from inbox)."""
    from daily_task_assistant.mailer import GmailError, load_account_from_env, archive_message

    try:
        gmail_config = load_account_from_env(account)
        archive_message(gmail_config, message_id)
    except GmailError as exc:
        raise HTTPException(status_code=502, detail=f"Gmail API error: {exc}")

    return {"archived": True, "messageId": message_id}


@router.post("/email/{account}/delete/{message_id}")
def delete_email(
    account: Literal["church", "personal"],
    message_id: str,
    user: str = Depends(get_current_user),
) -> dict:
    """Move an email to trash."""
    from daily_task_assistant.mailer import GmailError, load_account_from_env, trash_message

    try:
        gmail_config = load_account_from_env(account)
        trash_message(gmail_config, message_id)
    except GmailError as exc:
        raise HTTPException(status_code=502, detail=f"Gmail API error: {exc}")

    return {"deleted": True, "messageId": message_id}


@router.post("/email/{account}/star/{message_id}")
def toggle_star(
    account: Literal["church", "personal"],
    message_id: str,
    starred: bool = Query(True, description="True to star, False to unstar"),
    user: str = Depends(get_current_user),
) -> dict:
    """Star or unstar an email."""
    from daily_task_assistant.mailer import GmailError, load_account_from_env, star_message, unstar_message

    try:
        gmail_config = load_account_from_env(account)
        if starred:
            star_message(gmail_config, message_id)
        else:
            unstar_message(gmail_config, message_id)
    except GmailError as exc:
        raise HTTPException(status_code=502, detail=f"Gmail API error: {exc}")

    return {"starred": starred, "messageId": message_id}


@router.post("/email/{account}/important/{message_id}")
def toggle_important(
    account: Literal["church", "personal"],
    message_id: str,
    important: bool = Query(True, description="True to mark important, False to unmark"),
    user: str = Depends(get_current_user),
) -> dict:
    """Mark or unmark an email as important."""
    from daily_task_assistant.mailer import GmailError, load_account_from_env, mark_important, unmark_important

    try:
        gmail_config = load_account_from_env(account)
        if important:
            mark_important(gmail_config, message_id)
        else:
            unmark_important(gmail_config, message_id)
    except GmailError as exc:
        raise HTTPException(status_code=502, detail=f"Gmail API error: {exc}")

    return {"important": important, "messageId": message_id}


@router.post("/email/{account}/read/{message_id}")
def toggle_read(
    account: Literal["church", "personal"],
    message_id: str,
    read: bool = Query(True, description="True to mark read, False to mark unread"),
    user: str = Depends(get_current_user),
) -> dict:
    """Mark or unmark an email as read."""
    from daily_task_assistant.mailer import GmailError, load_account_from_env, mark_read, mark_unread

    try:
        gmail_config = load_account_from_env(account)
        if read:
            mark_read(gmail_config, message_id)
        else:
            mark_unread(gmail_config, message_id)
    except GmailError as exc:
        raise HTTPException(status_code=502, detail=f"Gmail API error: {exc}")

    return {"read": read, "messageId": message_id}


@router.get("/email/{account}/labels")
def get_labels(
    account: Literal["church", "personal"],
    user: str = Depends(get_current_user),
) -> dict:
    """Get available labels for an account."""
    from daily_task_assistant.mailer import GmailError, load_account_from_env, list_labels

    try:
        gmail_config = load_account_from_env(account)
        labels = list_labels(gmail_config)
    except GmailError as exc:
        raise HTTPException(status_code=502, detail=f"Gmail API error: {exc}")

    return {"account": account, "labels": labels}


@router.post("/email/{account}/label/{message_id}")
def apply_labels(
    account: Literal["church", "personal"],
    message_id: str,
    request: ApplyLabelRequest,
    user: str = Depends(get_current_user),
) -> dict:
    """Apply or remove labels from an email."""
    from daily_task_assistant.mailer import GmailError, load_account_from_env, modify_labels

    try:
        gmail_config = load_account_from_env(account)
        modify_labels(gmail_config, message_id, request.labels_to_add, request.labels_to_remove)
    except GmailError as exc:
        raise HTTPException(status_code=502, detail=f"Gmail API error: {exc}")

    return {
        "messageId": message_id,
        "labelsAdded": request.labels_to_add,
        "labelsRemoved": request.labels_to_remove,
    }


# =============================================================================
# Pin Endpoints
# =============================================================================

@router.post("/email/{account}/pin/{message_id}")
def pin_email(
    account: Literal["church", "personal"],
    message_id: str,
    request: PinEmailRequest,
    user: str = Depends(get_current_user),
) -> dict:
    """Pin an email for later reference."""
    from daily_task_assistant.email.pinned_store import pin_email as store_pin

    store_pin(account, message_id, note=request.note)
    return {"pinned": True, "messageId": message_id}


@router.delete("/email/{account}/pin/{message_id}")
def unpin_email(
    account: Literal["church", "personal"],
    message_id: str,
    user: str = Depends(get_current_user),
) -> dict:
    """Unpin an email."""
    from daily_task_assistant.email.pinned_store import unpin_email as store_unpin

    store_unpin(account, message_id)
    return {"unpinned": True, "messageId": message_id}


@router.get("/email/{account}/pinned")
def get_pinned_emails(
    account: Literal["church", "personal"],
    user: str = Depends(get_current_user),
) -> dict:
    """Get all pinned emails for an account."""
    from daily_task_assistant.email.pinned_store import get_pinned_emails as fetch_pinned

    pinned = fetch_pinned(account)
    return {
        "account": account,
        "count": len(pinned),
        "pinned": [p.to_api_dict() for p in pinned],
    }


# =============================================================================
# Attention/Analysis Endpoints
# =============================================================================

@router.get("/email/attention/{account}")
def get_attention_items(
    account: Literal["church", "personal"],
    user: str = Depends(get_current_user),
) -> dict:
    """Get emails that need attention."""
    from daily_task_assistant.email.attention_store import get_attention_items as fetch_attention

    items = fetch_attention(account)
    return {
        "account": account,
        "count": len(items),
        "items": [item.to_api_dict() for item in items],
    }


@router.post("/email/attention/{account}/{email_id}/dismiss")
def dismiss_attention(
    account: Literal["church", "personal"],
    email_id: str,
    request: DismissRequest,
    user: str = Depends(get_current_user),
) -> dict:
    """Dismiss an attention item."""
    from daily_task_assistant.email.attention_store import dismiss_attention_item

    dismiss_attention_item(account, email_id, reason=request.reason)
    return {"dismissed": True, "emailId": email_id}


@router.post("/email/attention/{account}/{email_id}/snooze")
def snooze_attention(
    account: Literal["church", "personal"],
    email_id: str,
    request: SnoozeRequest,
    user: str = Depends(get_current_user),
) -> dict:
    """Snooze an attention item until a specific date."""
    from daily_task_assistant.email.attention_store import snooze_attention_item

    snooze_attention_item(account, email_id, until=request.until)
    return {"snoozed": True, "emailId": email_id, "until": request.until}


@router.post("/email/attention/{account}/{email_id}/viewed")
def mark_attention_viewed(
    account: Literal["church", "personal"],
    email_id: str,
    user: str = Depends(get_current_user),
) -> dict:
    """Mark an attention item as viewed."""
    from daily_task_assistant.email.attention_store import mark_viewed

    mark_viewed(account, email_id)
    return {"viewed": True, "emailId": email_id}


@router.get("/email/attention/{account}/quality-metrics")
def get_attention_quality(
    account: Literal["church", "personal"],
    user: str = Depends(get_current_user),
) -> dict:
    """Get quality metrics for attention analysis."""
    from daily_task_assistant.email.attention_store import get_quality_metrics

    metrics = get_quality_metrics(account)
    return {"account": account, "metrics": metrics}


@router.get("/email/last-analysis/{account}")
def get_last_analysis(
    account: Literal["church", "personal"],
    user: str = Depends(get_current_user),
) -> dict:
    """Get last analysis timestamp and summary."""
    from daily_task_assistant.email.analysis_store import get_last_analysis

    analysis = get_last_analysis(account)
    return {"account": account, "analysis": analysis}


@router.get("/email/analyze/{account}")
def analyze_emails(
    account: Literal["church", "personal"],
    user: str = Depends(get_current_user),
) -> dict:
    """Run Haiku email analysis."""
    from daily_task_assistant.email.haiku_analyzer import analyze_inbox, HaikuAnalysisError

    try:
        result = analyze_inbox(account)
    except HaikuAnalysisError as exc:
        raise HTTPException(status_code=502, detail=f"Analysis error: {exc}")

    return {"account": account, "result": result}


# =============================================================================
# Suggestions Endpoints
# =============================================================================

@router.get("/email/{account}/suggestions")
def get_suggestions(
    account: Literal["church", "personal"],
    user: str = Depends(get_current_user),
) -> dict:
    """Get pending action suggestions for an account."""
    from daily_task_assistant.email.suggestion_store import get_suggestions as fetch_suggestions

    suggestions = fetch_suggestions(account)
    return {
        "account": account,
        "count": len(suggestions),
        "suggestions": [s.to_api_dict() for s in suggestions],
    }


@router.get("/email/suggestions/{account}/pending")
def get_pending_suggestions(
    account: Literal["church", "personal"],
    user: str = Depends(get_current_user),
) -> dict:
    """Get pending suggestions awaiting decision."""
    from daily_task_assistant.email.suggestion_store import get_pending_suggestions

    suggestions = get_pending_suggestions(account)
    return {
        "account": account,
        "count": len(suggestions),
        "suggestions": [s.to_api_dict() for s in suggestions],
    }


@router.post("/email/suggestions/{account}/{suggestion_id}/decide")
def decide_suggestion(
    account: Literal["church", "personal"],
    suggestion_id: str,
    request: SuggestionDecisionRequest,
    user: str = Depends(get_current_user),
) -> dict:
    """Accept or reject a suggestion."""
    from daily_task_assistant.email.suggestion_store import decide_suggestion as store_decide

    store_decide(account, suggestion_id, request.decision, feedback=request.feedback)
    return {"decided": True, "suggestionId": suggestion_id, "decision": request.decision}


@router.get("/email/suggestions/{account}/stats")
def get_suggestion_stats(
    account: Literal["church", "personal"],
    user: str = Depends(get_current_user),
) -> dict:
    """Get suggestion statistics for an account."""
    from daily_task_assistant.email.suggestion_store import get_stats

    stats = get_stats(account)
    return {"account": account, "stats": stats}


@router.get("/email/suggestions/rejection-patterns")
def get_rejection_patterns(
    user: str = Depends(get_current_user),
) -> dict:
    """Get patterns from rejected suggestions."""
    from daily_task_assistant.email.suggestion_store import get_rejection_patterns

    patterns = get_rejection_patterns()
    return {"patterns": patterns}


# =============================================================================
# Rules Endpoints
# =============================================================================

@router.get("/email/rules/{account}")
def get_rules(
    account: Literal["church", "personal"],
    user: str = Depends(get_current_user),
) -> dict:
    """Get filter rules for an account."""
    from daily_task_assistant.email.rule_store import get_rules as fetch_rules

    rules = fetch_rules(account)
    return {"account": account, "rules": [r.to_api_dict() for r in rules]}


@router.post("/email/rules/{account}")
def add_rule(
    account: Literal["church", "personal"],
    request: AddRuleRequest,
    user: str = Depends(get_current_user),
) -> dict:
    """Add a new filter rule."""
    from daily_task_assistant.email.rule_store import add_rule as store_rule

    rule = store_rule(
        account,
        from_pattern=request.from_pattern,
        subject_pattern=request.subject_pattern,
        action=request.action,
        label=request.label,
    )
    return {"added": True, "rule": rule.to_api_dict()}


@router.delete("/email/rules/{account}/{row_number}")
def delete_rule(
    account: Literal["church", "personal"],
    row_number: int,
    user: str = Depends(get_current_user),
) -> dict:
    """Delete a filter rule."""
    from daily_task_assistant.email.rule_store import delete_rule as store_delete

    store_delete(account, row_number)
    return {"deleted": True, "rowNumber": row_number}


@router.get("/email/rules/{account}/pending")
def get_pending_rules(
    account: Literal["church", "personal"],
    user: str = Depends(get_current_user),
) -> dict:
    """Get pending rule suggestions."""
    from daily_task_assistant.email.rule_store import get_pending_rules

    rules = get_pending_rules(account)
    return {"account": account, "count": len(rules), "rules": [r.to_api_dict() for r in rules]}


@router.post("/email/rules/{account}/{rule_id}/decide")
def decide_rule(
    account: Literal["church", "personal"],
    rule_id: str,
    request: RuleDecisionRequest,
    user: str = Depends(get_current_user),
) -> dict:
    """Approve or reject a rule suggestion."""
    from daily_task_assistant.email.rule_store import decide_rule as store_decide

    store_decide(account, rule_id, request.decision, feedback=request.feedback)
    return {"decided": True, "ruleId": rule_id, "decision": request.decision}


@router.get("/email/rules/{account}/stats")
def get_rule_stats(
    account: Literal["church", "personal"],
    user: str = Depends(get_current_user),
) -> dict:
    """Get rule statistics."""
    from daily_task_assistant.email.rule_store import get_stats

    stats = get_stats(account)
    return {"account": account, "stats": stats}


@router.get("/email/rules/{account}/allowed-labels")
def get_allowed_labels(
    account: Literal["church", "personal"],
    user: str = Depends(get_current_user),
) -> dict:
    """Get allowed labels for rule suggestions."""
    account_key = "church" if account == "church" else "personal"
    labels = list(ALLOWED_SUGGESTION_LABELS.get(account_key, set()))
    return {"account": account, "labels": sorted(labels)}


# =============================================================================
# Reply/Send Endpoints
# =============================================================================

@router.post("/email/{account}/reply-draft")
def create_reply_draft(
    account: Literal["church", "personal"],
    request: ReplyDraftRequest,
    user: str = Depends(get_current_user),
) -> dict:
    """Create a reply draft."""
    from daily_task_assistant.mailer import GmailError, load_account_from_env, create_draft

    try:
        gmail_config = load_account_from_env(account)
        draft = create_draft(
            gmail_config,
            to=request.to,
            subject=request.subject,
            body=request.body,
            thread_id=request.thread_id,
            in_reply_to=request.message_id,
            cc=request.cc,
        )
    except GmailError as exc:
        raise HTTPException(status_code=502, detail=f"Gmail API error: {exc}")

    return {"draftId": draft.id, "threadId": request.thread_id}


@router.post("/email/{account}/reply-send")
def send_reply(
    account: Literal["church", "personal"],
    request: ReplySendRequest,
    user: str = Depends(get_current_user),
) -> dict:
    """Send a reply email."""
    from daily_task_assistant.mailer import GmailError, load_account_from_env, send_message

    try:
        gmail_config = load_account_from_env(account)
        result = send_message(
            gmail_config,
            to=request.to,
            subject=request.subject,
            body=request.body,
            thread_id=request.thread_id,
            in_reply_to=request.message_id,
            cc=request.cc,
        )
    except GmailError as exc:
        raise HTTPException(status_code=502, detail=f"Gmail API error: {exc}")

    return {"sent": True, "messageId": result.id, "threadId": request.thread_id}


# =============================================================================
# Chat Endpoints
# =============================================================================

@router.post("/email/{account}/chat")
def email_chat(
    account: Literal["church", "personal"],
    request: EmailChatRequest,
    user: str = Depends(get_current_user),
) -> dict:
    """Chat with DATA about an email."""
    from daily_task_assistant.email.chat import handle_email_chat, EmailChatError

    try:
        response = handle_email_chat(
            account=account,
            message=request.message,
            email_context=request.email_context,
            history=request.history,
            user_email=user,
        )
    except EmailChatError as exc:
        raise HTTPException(status_code=502, detail=f"Chat error: {exc}")

    return {
        "response": response.message,
        "toolResults": response.tool_results,
        "pendingAction": response.pending_action,
    }


@router.get("/email/{account}/conversation/{thread_id}")
def get_email_conversation(
    account: Literal["church", "personal"],
    thread_id: str,
    user: str = Depends(get_current_user),
) -> dict:
    """Get conversation history for an email thread."""
    from daily_task_assistant.conversations.email_history import get_conversation

    history = get_conversation(account, thread_id)
    return {"threadId": thread_id, "history": history}


@router.delete("/email/{account}/conversation/{thread_id}")
def clear_email_conversation(
    account: Literal["church", "personal"],
    thread_id: str,
    user: str = Depends(get_current_user),
) -> dict:
    """Clear conversation history for an email thread."""
    from daily_task_assistant.conversations.email_history import clear_conversation

    clear_conversation(account, thread_id)
    return {"threadId": thread_id, "cleared": True}


# =============================================================================
# Task Creation from Email
# =============================================================================

@router.post("/email/{account}/task-preview")
def preview_task_from_email(
    account: Literal["church", "personal"],
    request: TaskPreviewRequest,
    user: str = Depends(get_current_user),
) -> dict:
    """Preview task creation from email."""
    from daily_task_assistant.email.task_creator import preview_task

    preview = preview_task(account, request.email_id, request.title, request.domain)
    return {"preview": preview}


@router.post("/email/{account}/task-create")
def create_task_from_email(
    account: Literal["church", "personal"],
    request: EmailTaskCreateRequest,
    user: str = Depends(get_current_user),
) -> dict:
    """Create a task from an email."""
    from daily_task_assistant.email.task_creator import create_task_from_email as create_task

    task = create_task(
        account=account,
        email_id=request.email_id,
        title=request.title,
        domain=request.domain,
        priority=request.priority,
        due_date=request.due_date,
        notes=request.notes,
        project=request.project,
        user_email=user,
    )
    return {"task": task.to_api_dict()}


@router.post("/email/{account}/check-tasks")
def check_email_tasks(
    account: Literal["church", "personal"],
    request: EmailTaskCheckRequest,
    user: str = Depends(get_current_user),
) -> dict:
    """Check which emails already have tasks."""
    from daily_task_assistant.email.task_creator import check_tasks_for_emails

    result = check_tasks_for_emails(account, request.email_ids, user)
    return {
        "emailsChecked": len(request.email_ids),
        "emailsWithTasks": len(result),
        "tasks": result,
    }


# =============================================================================
# Sync Endpoint
# =============================================================================

@router.post("/email/sync/{account}")
def sync_email_rules(
    account: Literal["church", "personal"],
    request: SyncRulesRequest,
    user: str = Depends(get_current_user),
) -> dict:
    """Sync filter rules with Google Sheet."""
    from daily_task_assistant.email.rule_store import sync_rules

    result = sync_rules(account, from_sheet=request.from_sheet)
    return {"synced": True, "result": result}


# =============================================================================
# Privacy Endpoint
# =============================================================================

@router.get("/email/{account}/privacy/{email_id}")
def get_email_privacy(
    account: Literal["church", "personal"],
    email_id: str,
    user: str = Depends(get_current_user),
) -> dict:
    """Get privacy settings for an email."""
    from daily_task_assistant.email.privacy import get_privacy_info

    info = get_privacy_info(account, email_id)
    return {"emailId": email_id, "privacy": info}


# =============================================================================
# Memory System Endpoints
# =============================================================================

@router.get("/email/{account}/memory/sender-profiles")
def get_sender_profiles(
    account: Literal["church", "personal"],
    user: str = Depends(get_current_user),
) -> dict:
    """Get all sender profiles."""
    from daily_task_assistant.email.memory import get_sender_profiles as fetch_profiles

    profiles = fetch_profiles(account)
    return {"account": account, "profiles": [p.to_api_dict() for p in profiles]}


@router.get("/email/{account}/memory/sender/{email}")
def get_sender_profile(
    account: Literal["church", "personal"],
    email: str,
    user: str = Depends(get_current_user),
) -> dict:
    """Get profile for a specific sender."""
    from daily_task_assistant.email.memory import get_sender_profile as fetch_profile

    profile = fetch_profile(account, email)
    return {"account": account, "profile": profile.to_api_dict() if profile else None}


@router.post("/email/{account}/memory/seed")
def seed_email_memory(
    account: Literal["church", "personal"],
    user: str = Depends(get_current_user),
) -> dict:
    """Seed email memory from inbox history."""
    from daily_task_assistant.email.memory import seed_memory

    result = seed_memory(account)
    return {"account": account, "result": result}


@router.get("/email/{account}/memory/category-patterns")
def get_category_patterns(
    account: Literal["church", "personal"],
    user: str = Depends(get_current_user),
) -> dict:
    """Get learned category patterns."""
    from daily_task_assistant.email.memory import get_category_patterns as fetch_patterns

    patterns = fetch_patterns(account)
    return {"account": account, "patterns": [p.to_api_dict() for p in patterns]}


@router.post("/email/{account}/memory/category-approval")
def approve_category_pattern(
    account: Literal["church", "personal"],
    pattern_id: str = Query(...),
    user: str = Depends(get_current_user),
) -> dict:
    """Approve a category pattern."""
    from daily_task_assistant.email.memory import approve_pattern

    approve_pattern(account, pattern_id)
    return {"approved": True, "patternId": pattern_id}


@router.post("/email/{account}/memory/category-dismissal")
def dismiss_category_pattern(
    account: Literal["church", "personal"],
    pattern_id: str = Query(...),
    user: str = Depends(get_current_user),
) -> dict:
    """Dismiss a category pattern."""
    from daily_task_assistant.email.memory import dismiss_pattern

    dismiss_pattern(account, pattern_id)
    return {"dismissed": True, "patternId": pattern_id}


@router.get("/email/{account}/memory/timing")
def get_timing_patterns(
    account: Literal["church", "personal"],
    user: str = Depends(get_current_user),
) -> dict:
    """Get email timing patterns."""
    from daily_task_assistant.email.memory import get_timing_patterns as fetch_timing

    timing = fetch_timing(account)
    return {"account": account, "timing": timing}


@router.get("/email/{account}/memory/response-warning")
def get_response_warnings(
    account: Literal["church", "personal"],
    user: str = Depends(get_current_user),
) -> dict:
    """Get response time warnings."""
    from daily_task_assistant.email.memory import get_response_warnings as fetch_warnings

    warnings = fetch_warnings(account)
    return {"account": account, "warnings": warnings}


# =============================================================================
# Haiku Settings Endpoints
# =============================================================================

@router.get("/email/haiku/settings")
def get_haiku_settings(
    user: str = Depends(get_current_user),
) -> dict:
    """Get Haiku analyzer settings (GLOBAL - shared across all logins)."""
    from daily_task_assistant.email import get_haiku_settings as get_settings

    settings = get_settings()
    return {"settings": settings.to_api_dict()}


@router.put("/email/haiku/settings")
def update_haiku_settings(
    request: HaikuSettingsRequest,
    user: str = Depends(get_current_user),
) -> dict:
    """Update Haiku analyzer settings (GLOBAL - shared across all logins)."""
    from daily_task_assistant.email import (
        get_haiku_settings as get_settings,
        save_haiku_settings as save_settings,
        HaikuSettings,
    )

    current = get_settings()
    new_settings = HaikuSettings(
        enabled=request.enabled if request.enabled is not None else current.enabled,
        daily_limit=request.daily_limit if request.daily_limit is not None else current.daily_limit,
        weekly_limit=request.weekly_limit if request.weekly_limit is not None else current.weekly_limit,
    )
    save_settings(new_settings)

    return {"status": "updated", "settings": new_settings.to_api_dict()}


@router.get("/email/haiku/usage")
def get_haiku_usage(
    user: str = Depends(get_current_user),
) -> dict:
    """Get Haiku usage statistics (GLOBAL - shared across all logins)."""
    from daily_task_assistant.email import get_haiku_usage_summary

    summary = get_haiku_usage_summary()
    return {"usage": summary}


# =============================================================================
# Trust Metrics Endpoint
# =============================================================================

@router.get("/email/trust-metrics")
def get_trust_metrics(
    user: str = Depends(get_current_user),
) -> dict:
    """Get email trust metrics across accounts."""
    from daily_task_assistant.trust import get_email_trust_metrics

    metrics = get_email_trust_metrics()
    return {"metrics": metrics}
