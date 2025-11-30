"""Shared assist workflow helpers for CLI/API."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from ..actions import AssistPlan, plan_assist
from ..config import Settings
from ..logs import log_assist_event
from ..mailer import GmailError, load_account_from_env, send_email
from ..smartsheet_client import SmartsheetClient
from ..tasks import TaskDetail


@dataclass(slots=True)
class AssistExecutionResult:
    """Result of running the assist workflow."""

    plan: AssistPlan
    message_id: Optional[str] = None
    comment_posted: bool = False
    warnings: List[str] = field(default_factory=list)


def execute_assist(
    task: TaskDetail,
    *,
    settings: Settings,
    source: str,
    anthropic_model: Optional[str],
    send_email_account: Optional[str],
    live_tasks: bool,
    conversation_history: Optional[List[dict]] = None,
) -> AssistExecutionResult:
    """Run the assist workflow and return metadata."""

    warnings: List[str] = []
    plan = plan_assist(
        task,
        model_override=anthropic_model,
        history=conversation_history,
    )
    message_id: Optional[str] = None
    comment_posted = False

    # Email sending is now triggered separately via the action picker
    # The send_email_account parameter is kept for backward compatibility
    # but email drafts must be explicitly requested first
    if send_email_account:
        warnings.append(
            "Email sending requires an explicit draft request. "
            "Use the 'draft_email' action first, then send."
        )

    if message_id:
        if live_tasks:
            try:
                client = SmartsheetClient(settings=settings)
                client.post_comment(
                    row_id=plan.task.row_id,
                    text=(
                        f"Assistant sent email via {send_email_account or 'unknown'} "
                        f"(message id {message_id})."
                    ),
                )
                comment_posted = True
            except Exception as exc:  # pragma: no cover - network path
                warnings.append(f"Smartsheet comment failed: {exc}")
        else:
            warnings.append(
                "Skipped Smartsheet comment because data source used stubbed tasks."
            )

    try:
        log_assist_event(
            plan=plan,
            account_name=send_email_account,
            message_id=message_id,
            anthropic_model=anthropic_model,
            environment=settings.environment,
            source="live" if live_tasks else source,
        )
    except Exception as exc:  # pragma: no cover - file I/O errors
        warnings.append(f"Activity log error: {exc}")

    return AssistExecutionResult(
        plan=plan,
        message_id=message_id,
        comment_posted=comment_posted,
        warnings=warnings,
    )

