"""Chat execution for DATA.

Executes LLM calls with assembled context and extracts structured responses.
Supports multi-LLM routing (Anthropic Claude, Google Gemini).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from anthropic import Anthropic, APIStatusError

from .anthropic_client import build_anthropic_client, resolve_config, AnthropicError
from .context_assembler import ContextBundle
from .gemini_client import chat_with_gemini, is_gemini_available, GeminiError
from .intent_classifier import ClassifiedIntent


@dataclass(slots=True)
class TaskUpdateAction:
    """Structured task update action detected from user intent."""
    action: str
    status: Optional[str] = None
    priority: Optional[str] = None
    due_date: Optional[str] = None
    comment: Optional[str] = None
    number: Optional[int] = None
    contact_flag: Optional[bool] = None
    recurring: Optional[str] = None
    project: Optional[str] = None
    task_title: Optional[str] = None
    assigned_to: Optional[str] = None
    notes: Optional[str] = None
    estimated_hours: Optional[str] = None
    reason: str = ""


@dataclass(slots=True)
class EmailDraftUpdate:
    """Structured email draft update from chat."""
    to: Optional[str] = None
    cc: Optional[str] = None
    subject: Optional[str] = None
    body: Optional[str] = None
    reason: str = ""


@dataclass(slots=True)
class ChatResponse:
    """Response from chat execution."""
    message: str
    pending_action: Optional[TaskUpdateAction] = None
    email_draft_update: Optional[EmailDraftUpdate] = None
    intent_used: str = ""
    tokens_used: int = 0


def execute_chat(
    context: ContextBundle,
    intent: ClassifiedIntent,
    *,
    client: Optional[Anthropic] = None,
    force_claude: bool = False,
) -> ChatResponse:
    """Execute a chat request with assembled context.
    
    Routes to appropriate LLM based on intent:
    - Claude Sonnet: Tool use, vision, research
    - Gemini Flash: Conversational, planning (when no tools needed)
    
    Args:
        context: Assembled context bundle
        intent: Classified intent
        client: Optional pre-built Anthropic client
        force_claude: Force using Claude even for Gemini intents
    
    Returns:
        ChatResponse with message and optional pending actions
    """
    # Adjust temperature based on intent
    temperature = 0.3 if intent.intent == "action" else 0.5
    
    # Adjust max tokens based on intent
    max_tokens = 400 if intent.intent == "action" else 800
    
    # Route to Gemini for conversational/planning intents without tools
    use_gemini = (
        intent.suggested_model == "gemini-flash"
        and not context.tools
        and not intent.include_images
        and is_gemini_available()
        and not force_claude
    )
    
    if use_gemini:
        print(f"[LLM Router] Using Gemini 2.5 Pro for intent: {intent.intent}")
        return _execute_with_gemini(context, intent, max_tokens, temperature)
    
    # Use Claude for everything else
    print(f"[LLM Router] Using Claude Sonnet for intent: {intent.intent}")
    return _execute_with_claude(context, intent, max_tokens, temperature, client)


def _execute_with_gemini(
    context: ContextBundle,
    intent: ClassifiedIntent,
    max_tokens: int,
    temperature: float,
) -> ChatResponse:
    """Execute chat using Gemini Flash."""
    try:
        response_text = chat_with_gemini(
            messages=context.messages,
            system_prompt=context.system_prompt,
            model="gemini-2.5-pro",  # Quality is king for DATA
            max_tokens=max_tokens,
            temperature=temperature,
        )
        
        # Handle visual intent with no selected images
        if intent.intent == "visual" and not intent.include_images:
            response_text = "Please select the image(s) you'd like me to analyze by checking the boxes on the thumbnails above."
        
        return ChatResponse(
            message=response_text,
            pending_action=None,
            email_draft_update=None,
            intent_used=intent.intent,
            tokens_used=0,  # Gemini doesn't report tokens the same way
        )
        
    except GeminiError as exc:
        # Fall back to Claude on Gemini error
        return _execute_with_claude(context, intent, max_tokens, temperature, None)


def _execute_with_claude(
    context: ContextBundle,
    intent: ClassifiedIntent,
    max_tokens: int,
    temperature: float,
    client: Optional[Anthropic],
) -> ChatResponse:
    """Execute chat using Claude."""
    client = client or build_anthropic_client()
    config = resolve_config()
    
    try:
        # Build request kwargs - only include tools if we have them
        request_kwargs = {
            "model": config.model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "system": context.system_prompt,
            "messages": context.messages,
        }
        if context.tools:
            request_kwargs["tools"] = context.tools
        
        response = client.messages.create(**request_kwargs)
    except APIStatusError as exc:
        raise AnthropicError(f"Anthropic API error: {exc}") from exc
    except Exception as exc:
        raise AnthropicError(f"Anthropic request failed: {exc}") from exc
    
    # Extract text and tool use from response
    text_content = []
    pending_action = None
    email_draft_update = None
    
    for block in getattr(response, "content", []):
        block_type = getattr(block, "type", None)
        if block_type == "text":
            text_content.append(getattr(block, "text", ""))
        elif block_type == "tool_use":
            tool_name = getattr(block, "name", "")
            tool_input = getattr(block, "input", {})
            
            if tool_name == "update_task":
                pending_action = TaskUpdateAction(
                    action=tool_input.get("action", ""),
                    status=tool_input.get("status"),
                    priority=tool_input.get("priority"),
                    due_date=tool_input.get("due_date"),
                    comment=tool_input.get("comment"),
                    number=tool_input.get("number"),
                    contact_flag=tool_input.get("contact_flag"),
                    recurring=tool_input.get("recurring"),
                    project=tool_input.get("project"),
                    task_title=tool_input.get("task_title"),
                    assigned_to=tool_input.get("assigned_to"),
                    notes=tool_input.get("notes"),
                    estimated_hours=tool_input.get("estimated_hours"),
                    reason=tool_input.get("reason", ""),
                )
            elif tool_name == "update_email_draft":
                email_draft_update = EmailDraftUpdate(
                    to=tool_input.get("to"),
                    cc=tool_input.get("cc"),
                    subject=tool_input.get("subject"),
                    body=tool_input.get("body"),
                    reason=tool_input.get("reason", ""),
                )
    
    message = "\n".join(text_content).strip()
    
    # Generate appropriate message if tool was called but no text
    if pending_action and not message:
        message = _describe_action(pending_action)
    
    if email_draft_update and not message:
        changes = []
        if email_draft_update.subject:
            changes.append("subject")
        if email_draft_update.body:
            changes.append("body")
        message = f"I've updated the email {' and '.join(changes)}. {email_draft_update.reason}"
    
    # Handle visual intent with no selected images
    if intent.intent == "visual" and not intent.include_images:
        message = "Please select the image(s) you'd like me to analyze by checking the boxes on the thumbnails above."
    
    # Estimate tokens used
    tokens_used = getattr(response, "usage", {})
    input_tokens = getattr(tokens_used, "input_tokens", 0)
    output_tokens = getattr(tokens_used, "output_tokens", 0)
    
    return ChatResponse(
        message=message,
        pending_action=pending_action,
        email_draft_update=email_draft_update,
        intent_used=intent.intent,
        tokens_used=input_tokens + output_tokens,
    )


def _describe_action(action: TaskUpdateAction) -> str:
    """Generate a human-readable description of a task update action."""
    descriptions = {
        "mark_complete": "Got it! Marking this task as complete.",
        "update_status": f"Updating status to '{action.status}'.",
        "update_priority": f"Changing priority to '{action.priority}'.",
        "update_due_date": f"Moving due date to {action.due_date}.",
        "add_comment": "Adding comment to the task.",
        "update_number": f"Setting task number to {action.number}.",
        "update_contact_flag": f"{'Setting' if action.contact_flag else 'Clearing'} the Contact flag.",
        "update_recurring": f"Setting recurring to '{action.recurring}'.",
        "update_project": f"Moving to project '{action.project}'.",
        "update_task": f"Updating task title.",
        "update_assigned_to": f"Assigning to '{action.assigned_to}'.",
        "update_notes": "Updating task notes.",
        "update_estimated_hours": f"Setting estimated hours to {action.estimated_hours}.",
    }
    return descriptions.get(action.action, f"Performing: {action.action}")

