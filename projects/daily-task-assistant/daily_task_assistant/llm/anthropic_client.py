"""Anthropic client wrappers for Daily Task Assistant."""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

try:  # Optional dependency loaded via requirements.txt
    from anthropic import Anthropic, APIStatusError  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - handled at runtime
    Anthropic = None  # type: ignore
    APIStatusError = Exception  # type: ignore

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:  # pragma: no cover
    load_dotenv = None

from ..tasks import TaskDetail


# Load DATA preferences from markdown file
def _load_data_preferences() -> str:
    """Load DATA_PREFERENCES.md and extract relevant sections for prompts."""
    preferences_path = Path(__file__).parent.parent.parent / "DATA_PREFERENCES.md"
    if not preferences_path.exists():
        return ""
    
    try:
        content = preferences_path.read_text(encoding="utf-8")
        # Extract content after the YAML frontmatter
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                content = parts[2].strip()
        return content
    except Exception:
        return ""


# Cache the preferences at module load
_DATA_PREFERENCES = _load_data_preferences()

DEFAULT_MODEL = "claude-sonnet-4-20250514"
SYSTEM_PROMPT = """You are the Daily Task Assistant, a diligent chief of staff.
Produce concise, actionable guidance and respect the user's time.
Respond ONLY with compact JSON and no markdown."""

USER_PROMPT_TEMPLATE = """Task Context:
Title: {title}
Priority: {priority}
Status: {status}
Due: {due}
Project: {project}
Assigned To: {assigned_to}
Estimated Hours: {estimated_hours}
Next Step: {next_step}
Notes: {notes}
Automation Hints: {automation_hint}

Outputs:
1. summary: single sentence describing urgency + outcome.
2. next_steps: array of 2-4 imperative bullet strings tailored to the task.
3. efficiency_tips: array of 1-3 tips for accelerating execution.
4. suggested_actions: array of 1-3 action types relevant to THIS task (e.g., "research", "draft_email", "schedule", "follow_up", "delegate"). Only suggest "draft_email" if there's a clear external recipient mentioned in the task or notes.

Rules:
- JSON only. Keys: summary, next_steps, efficiency_tips, suggested_actions.
- Steps and tips must be strings without numbering prefixes.
- Reference provided context; do not invent data.
- The assignee (david.a.royes@gmail.com or davidroyes@southpointsda.org) is the OWNER, not a recipient. Never suggest emailing the owner.
"""

EMAIL_DRAFT_PROMPT = """Based on this task, draft a professional email to help the owner complete it.

Task: {title}
Project: {project}
Notes: {notes}
Recipient: {recipient}

Rules:
- The email is FROM the owner (David), TO the recipient specified.
- Be concise and professional.
- If no recipient is specified, ask who should receive the email.
- Return JSON with keys: subject, body, needs_recipient (boolean).
"""


class AnthropicError(RuntimeError):
    """Base error for Anthropic failures."""


class AnthropicNotConfigured(AnthropicError):
    """Raised when the API key or SDK is missing."""


@dataclass(slots=True)
class AnthropicConfig:
    model: str = DEFAULT_MODEL
    max_output_tokens: int = 800
    temperature: float = 0.3


@dataclass(slots=True)
class AnthropicSuggestion:
    summary: str
    next_steps: List[str]
    efficiency_tips: List[str]
    suggested_actions: List[str]
    raw: str


@dataclass(slots=True)
class EmailDraftResult:
    subject: str
    body: str
    needs_recipient: bool
    raw: str


def build_anthropic_client() -> Anthropic:
    """Instantiate the Anthropics SDK client."""

    if load_dotenv is not None:
        load_dotenv()

    if Anthropic is None:
        raise AnthropicNotConfigured(
            "anthropic package is not installed. Install dependencies first."
        )

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise AnthropicNotConfigured(
            "ANTHROPIC_API_KEY is missing. Add it to your environment or .env file."
        )

    return Anthropic(api_key=api_key)


def resolve_config(model_override: Optional[str] = None) -> AnthropicConfig:
    env_model = os.getenv("ANTHROPIC_MODEL")
    model = model_override or env_model or DEFAULT_MODEL
    return AnthropicConfig(model=model)


def generate_assist_suggestion(
    task: TaskDetail,
    *,
    client: Optional[Anthropic] = None,
    config: Optional[AnthropicConfig] = None,
    model_override: Optional[str] = None,
    history: Optional[List[Dict[str, str]]] = None,
) -> AnthropicSuggestion:
    """Call Anthropic Messages API for an assist suggestion."""

    client = client or build_anthropic_client()
    config = config or resolve_config(model_override)
    prompt = USER_PROMPT_TEMPLATE.format(
        title=task.title,
        priority=task.priority,
        status=task.status,
        due=task.due.strftime("%Y-%m-%d"),
        project=task.project,
        assigned_to=task.assigned_to or "Unassigned",
        estimated_hours=_format_hours(task.estimated_hours),
        next_step=task.next_step,
        notes=task.notes or "No additional notes",
        automation_hint=task.automation_hint,
    )

    try:
        messages = [
            {
                "role": "user",
                "content": [{"type": "text", "text": prompt}],
            }
        ]

        for turn in history or []:
            content = (turn.get("content") or "").strip()
            if not content:
                continue
            role = "assistant" if turn.get("role") == "assistant" else "user"
            messages.append(
                {
                    "role": role,
                    "content": [{"type": "text", "text": content}],
                }
            )

        response = client.messages.create(
            model=config.model,
            max_tokens=config.max_output_tokens,
            temperature=config.temperature,
            system=SYSTEM_PROMPT,
            messages=messages,
        )
    except APIStatusError as exc:  # pragma: no cover - network behaviour
        raise AnthropicError(f"Anthropic API error: {exc}") from exc
    except Exception as exc:  # pragma: no cover - network behaviour
        raise AnthropicError(f"Anthropic request failed: {exc}") from exc

    text = _extract_text(response)
    data = _parse_json(text)

    return AnthropicSuggestion(
        summary=_coerce_string(data.get("summary")),
        next_steps=_coerce_list(data.get("next_steps")),
        efficiency_tips=_coerce_list(data.get("efficiency_tips")),
        suggested_actions=_coerce_list(data.get("suggested_actions")),
        raw=text,
    )


def _extract_text(response) -> str:
    """Extract text content from Anthropic response, handling various block types."""
    chunks = []
    for block in getattr(response, "content", []):
        block_type = getattr(block, "type", None)
        if block_type == "text":
            chunks.append(getattr(block, "text", ""))
        # Web search results are automatically incorporated into the text response
        # by Anthropic, so we just need to extract the text blocks
    text = "\n".join(chunks).strip()
    if not text:
        raise AnthropicError("Anthropic response did not contain text content.")
    return text


def _parse_json(text: str) -> dict:
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise AnthropicError(
            f"Anthropic response was not valid JSON: {text[:200]}"
        ) from exc


def _coerce_list(value) -> List[str]:
    if not value:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()]


def _coerce_string(value) -> str:
    if not value:
        return ""
    return str(value).strip()


def _format_hours(value: float | None) -> str:
    if value is None:
        return "unknown"
    if float(value).is_integer():
        return f"{int(value)}h"
    return f"{value:.1f}h"


def generate_email_draft(
    task: TaskDetail,
    recipient: Optional[str] = None,
    *,
    client: Optional[Anthropic] = None,
    config: Optional[AnthropicConfig] = None,
) -> EmailDraftResult:
    """Generate an email draft for a specific task, targeting an external recipient."""

    client = client or build_anthropic_client()
    config = config or resolve_config()

    prompt = EMAIL_DRAFT_PROMPT.format(
        title=task.title,
        project=task.project,
        notes=task.notes or "No additional notes",
        recipient=recipient or "Not specified - please ask who should receive this email",
    )

    try:
        response = client.messages.create(
            model=config.model,
            max_tokens=config.max_output_tokens,
            temperature=config.temperature,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": [{"type": "text", "text": prompt}]}],
        )
    except APIStatusError as exc:
        raise AnthropicError(f"Anthropic API error: {exc}") from exc
    except Exception as exc:
        raise AnthropicError(f"Anthropic request failed: {exc}") from exc

    text = _extract_text(response)
    data = _parse_json(text)

    return EmailDraftResult(
        subject=_coerce_string(data.get("subject")),
        body=_coerce_string(data.get("body")),
        needs_recipient=bool(data.get("needs_recipient", not recipient)),
        raw=text,
    )


CHAT_SYSTEM_PROMPT = """You are DATA (Daily Autonomous Task Assistant), David's proactive AI chief of staff.

Your role is to help David accomplish tasks efficiently. You are action-oriented and solution-focused.

CAPABILITIES:
- Draft emails, messages, and communications
- Create action plans and checklists
- Provide research summaries based on your knowledge
- Suggest specific next steps
- Help organize and prioritize work

CAPABILITIES:
- You CAN search the web for current information when needed
- You can draft emails, messages, and communications
- You can create action plans and checklists

LIMITATIONS:
- You cannot make phone calls or send emails directly (but you can draft them)
- You cannot access David's personal accounts or files

STYLE:
- Be concise and actionable
- Use web search when you need current/specific information (contact details, business hours, etc.)
- Offer to take the next concrete step (draft something, create a checklist, etc.)
- Ask clarifying questions when needed to provide better help
- When you search the web, summarize findings clearly with sources
"""

# Web search tool definition for Anthropic API
WEB_SEARCH_TOOL = {
    "type": "web_search_20250305",
    "name": "web_search",
    "max_uses": 3,  # Limit searches per request to control costs
}


def chat_with_context(
    task: TaskDetail,
    user_message: str,
    history: Optional[List[Dict[str, str]]] = None,
    *,
    client: Optional[Anthropic] = None,
    config: Optional[AnthropicConfig] = None,
) -> str:
    """Have a conversational exchange with context about the task.
    
    Args:
        task: The current task being discussed
        user_message: The user's latest message
        history: Previous conversation messages [{"role": "user"|"assistant", "content": "..."}]
        client: Optional pre-built Anthropic client
        config: Optional configuration override
    
    Returns:
        The assistant's response as a string
    """
    client = client or build_anthropic_client()
    config = config or resolve_config()

    # Build task context as the first message
    task_context = f"""Current Task Context:
- Title: {task.title}
- Project: {task.project}
- Status: {task.status}
- Priority: {task.priority}
- Due: {task.due.strftime("%Y-%m-%d")}
- Owner: {task.assigned_to or "David"} (this is who you're helping, not a recipient)
- Notes: {task.notes or "No additional notes"}

Help David accomplish this task. Be proactive - offer to draft communications, create checklists, or take other concrete actions."""

    # Build message history
    messages: List[Dict[str, Any]] = []
    
    # Add task context as first user message (priming)
    messages.append({
        "role": "user",
        "content": [{"type": "text", "text": task_context}]
    })
    messages.append({
        "role": "assistant", 
        "content": [{"type": "text", "text": "I understand. I'm ready to help you with this task. What would you like to do?"}]
    })

    # Add conversation history
    if history:
        for msg in history:
            messages.append({
                "role": msg["role"],
                "content": [{"type": "text", "text": msg["content"]}]
            })

    # Add the current user message
    messages.append({
        "role": "user",
        "content": [{"type": "text", "text": user_message}]
    })

    try:
        response = client.messages.create(
            model=config.model,
            max_tokens=config.max_output_tokens,
            temperature=0.7,  # Slightly higher for more natural conversation
            system=CHAT_SYSTEM_PROMPT,
            messages=messages,
            tools=[WEB_SEARCH_TOOL],  # Enable web search capability
        )
    except APIStatusError as exc:
        raise AnthropicError(f"Anthropic API error: {exc}") from exc
    except Exception as exc:
        raise AnthropicError(f"Anthropic request failed: {exc}") from exc

    return _extract_text(response)


# Tool definition for task updates
TASK_UPDATE_TOOL = {
    "name": "update_task",
    "description": "Update a task in Smartsheet when the user indicates they want to change the task status, mark it complete, change priority, update due date, or add a comment. Always use this tool when the user's intent is to modify the task.",
    "input_schema": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["mark_complete", "update_status", "update_priority", "update_due_date", "add_comment"],
                "description": "The type of update to perform"
            },
            "status": {
                "type": "string",
                "enum": ["Scheduled", "In Progress", "Blocked", "Waiting", "Complete", "Recurring", "On Hold", "Follow-up", "Awaiting Reply", "Delivered", "Cancelled", "Delegated"],
                "description": "New status value (required for update_status)"
            },
            "priority": {
                "type": "string",
                "enum": ["Critical", "Urgent", "Important", "Standard", "Low"],
                "description": "New priority value (required for update_priority)"
            },
            "due_date": {
                "type": "string",
                "description": "New due date in YYYY-MM-DD format (required for update_due_date)"
            },
            "comment": {
                "type": "string",
                "description": "Comment text to add (required for add_comment)"
            },
            "reason": {
                "type": "string",
                "description": "Brief explanation of why this update is being made"
            }
        },
        "required": ["action", "reason"]
    }
}

def _build_chat_system_prompt() -> str:
    """Build the chat system prompt, incorporating DATA preferences if available."""
    base_prompt = """You are DATA (Daily Autonomous Task Assistant), David's proactive AI chief of staff.

YOU HAVE THE ABILITY TO UPDATE SMARTSHEET TASKS. You have an update_task tool that lets you:
- Mark tasks complete
- Change status (Scheduled, In Progress, Blocked, Waiting, Complete, etc.)
- Change priority (Critical, Urgent, Important, Standard, Low)
- Update due dates
- Add comments

CRITICAL INSTRUCTION: When David asks you to close, complete, finish, or update a task, you MUST call the update_task tool. Do NOT say "I can't do that" or "I don't have access" - YOU DO HAVE ACCESS through the update_task tool.

TASK UPDATE TRIGGERS - CALL THE TOOL IMMEDIATELY:
- "done", "finished", "complete", "close it", "mark it done", "close the task", "close this" → update_task(action="mark_complete", reason="User indicated task is complete")
- "blocked", "stuck", "waiting on..." → update_task(action="update_status", status="Blocked", reason="User indicated blocker")
- "push to...", "change due date", "move to next week" → update_task(action="update_due_date", due_date="YYYY-MM-DD", reason="User requested date change")
- "make this urgent", "lower priority" → update_task(action="update_priority", priority="...", reason="User requested priority change")
- "add note:", "note that...", "record that..." → update_task(action="add_comment", comment="...", reason="User added note")

EXAMPLE - User says "close this task please":
1. Call update_task(action="mark_complete", reason="User requested task closure")
2. Respond: "Got it! Marking this task as complete."

WHAT NOT TO DO:
- Do NOT say "I can't directly close tasks" - you CAN via the update_task tool
- Do NOT say "I don't have access to Smartsheet" - you DO via the update_task tool
- Do NOT give a checklist of steps for the user to do manually
- Do NOT ask "would you like me to..." when intent is clear - just call the tool

The UI will show a confirmation card with Confirm/Cancel buttons after you call the tool.

OTHER CAPABILITIES:
- Draft emails (but NEVER email the task owner about their own task)
- Create action plans
- Research and summarize information
- Web search for current information

STYLE:
- Be concise - 1-2 sentences when taking action
- Use tools proactively when intent is clear
- Don't summarize or recap before acting
"""
    
    # Append preferences if loaded
    if _DATA_PREFERENCES:
        base_prompt += f"\n\n--- DATA PREFERENCES ---\n{_DATA_PREFERENCES[:4000]}"
    
    return base_prompt


# Build the prompt - note: this is cached at module load time
# If DATA_PREFERENCES.md changes, restart the server to pick up changes
CHAT_WITH_TOOLS_SYSTEM_PROMPT = _build_chat_system_prompt()


def get_chat_system_prompt() -> str:
    """Get the chat system prompt. Can be called to rebuild if needed."""
    return _build_chat_system_prompt()


@dataclass(slots=True)
class TaskUpdateAction:
    """Structured task update action detected from user intent."""
    action: str
    status: Optional[str] = None
    priority: Optional[str] = None
    due_date: Optional[str] = None
    comment: Optional[str] = None
    reason: str = ""


@dataclass(slots=True)
class ChatResponse:
    """Response from chat_with_tools, may include a pending action."""
    message: str
    pending_action: Optional[TaskUpdateAction] = None


def chat_with_tools(
    task: TaskDetail,
    user_message: str,
    history: Optional[List[Dict[str, str]]] = None,
    *,
    client: Optional[Anthropic] = None,
    config: Optional[AnthropicConfig] = None,
) -> ChatResponse:
    """Chat with task update tool support.
    
    This function enables DATA to recognize task update intents and return
    structured actions that can be confirmed and executed.
    
    Args:
        task: The current task being discussed
        user_message: The user's latest message
        history: Previous conversation messages
        client: Optional pre-built Anthropic client
        config: Optional configuration override
    
    Returns:
        ChatResponse with message and optional pending_action
    """
    client = client or build_anthropic_client()
    config = config or resolve_config()

    # Build task context
    task_context = f"""Current Task:
- Title: {task.title}
- Status: {task.status}
- Priority: {task.priority}
- Due: {task.due.strftime("%Y-%m-%d")}
- Project: {task.project}
- Notes: {task.notes or "None"}"""

    # Build messages
    messages: List[Dict[str, Any]] = []
    
    # Task context as priming
    messages.append({
        "role": "user",
        "content": [{"type": "text", "text": task_context}]
    })
    messages.append({
        "role": "assistant",
        "content": [{"type": "text", "text": "I'm ready to help with this task. What would you like to do?"}]
    })

    # Add history
    if history:
        for msg in history:
            messages.append({
                "role": msg["role"],
                "content": [{"type": "text", "text": msg["content"]}]
            })

    # Add current message
    messages.append({
        "role": "user",
        "content": [{"type": "text", "text": user_message}]
    })

    try:
        response = client.messages.create(
            model=config.model,
            max_tokens=config.max_output_tokens,
            temperature=0.5,
            system=CHAT_WITH_TOOLS_SYSTEM_PROMPT,
            messages=messages,
            tools=[TASK_UPDATE_TOOL, WEB_SEARCH_TOOL],
        )
    except APIStatusError as exc:
        raise AnthropicError(f"Anthropic API error: {exc}") from exc
    except Exception as exc:
        raise AnthropicError(f"Anthropic request failed: {exc}") from exc

    # Extract text and tool use from response
    text_content = []
    pending_action = None
    
    for block in getattr(response, "content", []):
        block_type = getattr(block, "type", None)
        if block_type == "text":
            text_content.append(getattr(block, "text", ""))
        elif block_type == "tool_use":
            tool_name = getattr(block, "name", "")
            if tool_name == "update_task":
                tool_input = getattr(block, "input", {})
                pending_action = TaskUpdateAction(
                    action=tool_input.get("action", ""),
                    status=tool_input.get("status"),
                    priority=tool_input.get("priority"),
                    due_date=tool_input.get("due_date"),
                    comment=tool_input.get("comment"),
                    reason=tool_input.get("reason", ""),
                )

    message = "\n".join(text_content).strip()
    
    # If there's a pending action but no message, generate a confirmation message
    if pending_action and not message:
        action_desc = _describe_action(pending_action)
        message = f"I'll {action_desc}. Should I proceed?"

    return ChatResponse(message=message, pending_action=pending_action)


def _describe_action(action: TaskUpdateAction) -> str:
    """Generate a human-readable description of a task update action."""
    if action.action == "mark_complete":
        return "mark this task as complete"
    elif action.action == "update_status":
        return f"update the status to '{action.status}'"
    elif action.action == "update_priority":
        return f"change the priority to '{action.priority}'"
    elif action.action == "update_due_date":
        return f"update the due date to {action.due_date}"
    elif action.action == "add_comment":
        preview = (action.comment or "")[:50]
        return f"add a comment: '{preview}...'" if len(action.comment or "") > 50 else f"add a comment: '{action.comment}'"
    return f"perform action: {action.action}"


RESEARCH_SYSTEM_PROMPT = """You are DATA, helping David research information for his tasks.

FORMAT YOUR RESPONSE AS:

## Key Findings
- 3-5 bullet points with the most important discoveries
- Include specific details inline (phone, address, hours)

## Action Items
- 2-3 concrete next steps David should take
- Be specific (e.g., "Call [number]" not "Contact them")

## Sources
- Brief list of where info came from

RULES:
- Be CONCISE - bullet points only, no paragraphs
- Put contact info (phone, email, address) directly in bullets
- Skip sections if no relevant info found
- No filler text or verbose explanations
"""


def research_task(
    task: TaskDetail,
    next_steps: Optional[List[str]] = None,
    *,
    client: Optional[Anthropic] = None,
    config: Optional[AnthropicConfig] = None,
) -> str:
    """Research information related to a task using web search.
    
    Args:
        task: The task to research
        next_steps: Optional list of next steps to inform the research
        client: Optional pre-built Anthropic client
        config: Optional configuration override
    
    Returns:
        Formatted research results as a string
    """
    client = client or build_anthropic_client()
    config = config or resolve_config()

    # Build the research prompt from task context
    next_steps_text = ""
    if next_steps:
        next_steps_text = "\n".join(f"- {step}" for step in next_steps[:5])
    
    research_prompt = f"""Research this task:

**Task:** {task.title}
**Notes:** {task.notes or "None"}
{f"**Context:** {next_steps_text}" if next_steps_text else ""}

Find: contact info, hours, procedures, requirements. Be concise - bullets only."""

    messages = [
        {
            "role": "user",
            "content": [{"type": "text", "text": research_prompt}]
        }
    ]

    try:
        response = client.messages.create(
            model=config.model,
            max_tokens=1500,  # Allow longer responses for research
            temperature=0.3,  # Lower temperature for factual research
            system=RESEARCH_SYSTEM_PROMPT,
            messages=messages,
            tools=[WEB_SEARCH_TOOL],
        )
    except APIStatusError as exc:
        raise AnthropicError(f"Anthropic API error: {exc}") from exc
    except Exception as exc:
        raise AnthropicError(f"Anthropic request failed: {exc}") from exc

    return _extract_text(response)


SUMMARIZE_SYSTEM_PROMPT = """You are DATA, David's task assistant. Create a concise summary of the current state of a task.

FORMAT YOUR RESPONSE AS:

## Task Overview
- 1-2 sentences: What is this task about and its current status

## Current Plan
- Brief summary of the planned approach (if a plan exists)
- Key next steps that are pending

## Progress & Decisions
- What has been discussed or decided
- Any important context from the conversation
- Note if task is blocked, waiting, or ready to proceed

## Recommendations
- 1-2 actionable recommendations for moving forward

RULES:
- Be CONCISE - use bullet points, not paragraphs
- Focus on actionable information
- If no plan or conversation exists, say so briefly
- Highlight any blockers or urgent items
- Keep the entire summary under 200 words
"""


def summarize_task(
    task: TaskDetail,
    plan_summary: Optional[str] = None,
    next_steps: Optional[List[str]] = None,
    efficiency_tips: Optional[List[str]] = None,
    conversation_history: Optional[List[Dict[str, str]]] = None,
    *,
    client: Optional[Anthropic] = None,
    config: Optional[AnthropicConfig] = None,
) -> str:
    """Generate a summary of the task, plan, and conversation progress.
    
    Args:
        task: The task to summarize
        plan_summary: The current plan summary (if any)
        next_steps: List of next steps from the plan
        efficiency_tips: List of efficiency tips from the plan
        conversation_history: Previous conversation messages
        client: Optional pre-built Anthropic client
        config: Optional configuration override
    
    Returns:
        Formatted summary as a string
    """
    client = client or build_anthropic_client()
    config = config or resolve_config()

    # Build task context
    task_context = f"""**Task:** {task.title}
**Status:** {task.status}
**Priority:** {task.priority}
**Due:** {task.due.strftime("%Y-%m-%d") if task.due else "Not set"}
**Project:** {task.project}
**Notes:** {task.notes or "None"}"""

    # Build plan context
    plan_context = ""
    if plan_summary or next_steps:
        plan_parts = []
        if plan_summary:
            plan_parts.append(f"**Plan Summary:** {plan_summary}")
        if next_steps:
            steps_text = "\n".join(f"  - {step}" for step in next_steps)
            plan_parts.append(f"**Next Steps:**\n{steps_text}")
        if efficiency_tips:
            tips_text = "\n".join(f"  - {tip}" for tip in efficiency_tips)
            plan_parts.append(f"**Efficiency Tips:**\n{tips_text}")
        plan_context = "\n".join(plan_parts)
    else:
        plan_context = "No plan has been generated yet."

    # Build conversation context
    conversation_context = ""
    if conversation_history and len(conversation_history) > 0:
        # Get recent conversation (last 10 messages)
        recent = conversation_history[-10:]
        conv_parts = []
        for msg in recent:
            role = "David" if msg["role"] == "user" else "DATA"
            # Truncate long messages
            content = msg["content"][:200] + "..." if len(msg["content"]) > 200 else msg["content"]
            conv_parts.append(f"**{role}:** {content}")
        conversation_context = "\n\n".join(conv_parts)
    else:
        conversation_context = "No conversation history yet."

    summarize_prompt = f"""Please summarize the current state of this task:

{task_context}

---
CURRENT PLAN:
{plan_context}

---
CONVERSATION HISTORY:
{conversation_context}

---
Provide a concise summary following the format specified."""

    messages = [
        {
            "role": "user",
            "content": [{"type": "text", "text": summarize_prompt}]
        }
    ]

    try:
        response = client.messages.create(
            model=config.model,
            max_tokens=800,
            temperature=0.3,
            system=SUMMARIZE_SYSTEM_PROMPT,
            messages=messages,
        )
    except APIStatusError as exc:
        raise AnthropicError(f"Anthropic API error: {exc}") from exc
    except Exception as exc:
        raise AnthropicError(f"Anthropic request failed: {exc}") from exc

    return _extract_text(response)

