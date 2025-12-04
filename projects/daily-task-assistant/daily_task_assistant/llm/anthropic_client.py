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

EMAIL_DRAFT_PROMPT = """Draft a professional email based on the provided content and task context.

Task: {title}
Project: {project}
Task Notes: {notes}

Source Content to transform into email:
{source_content}

Recipient: {recipient}

Rules:
- The email is FROM David (the task owner), TO the recipient specified.
- Transform the source content into a well-structured, professional email.
- Be concise and clear - get to the point quickly.
- If the source content contains key information, include it in the email body.
- Generate an appropriate subject line that summarizes the email purpose.
- End with "Best regards,\nDavid"
- Return JSON with keys: subject, body, needs_recipient (boolean).
- needs_recipient should be true ONLY if no recipient email was provided.
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


def _extract_text(response, extract_formatted_only: bool = False) -> str:
    """Extract text content from Anthropic response, handling various block types.
    
    Args:
        response: The Anthropic API response
        extract_formatted_only: If True, try to extract only the formatted markdown
            section (starting from ## headers), filtering out reasoning/thinking text.
            Useful for web search responses that include verbose reasoning.
    """
    import re
    
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
    
    # If requested, try to extract only the formatted section
    if extract_formatted_only:
        # Find the first ## header (Key Findings, Task Overview, etc.)
        match = re.search(r'^(##\s+\w)', text, re.MULTILINE)
        if match:
            text = text[match.start():].strip()
    
    # Fix bullet point formatting: "- \n\nText" should become "- Text"
    # This handles cases where Anthropic adds extra newlines after bullet markers
    text = re.sub(r'^-\s*\n+', '- ', text, flags=re.MULTILINE)
    
    # Also fix numbered lists with same issue: "1. \n\nText" -> "1. Text"
    text = re.sub(r'^(\d+\.)\s*\n+', r'\1 ', text, flags=re.MULTILINE)
    
    # Collapse multiple blank lines into single blank line
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    return text


def _parse_json(text: str) -> dict:
    """Parse JSON from text, handling markdown code fences if present."""
    import re
    
    # Strip markdown code fences if present (```json ... ``` or ``` ... ```)
    cleaned = text.strip()
    fence_match = re.match(r'^```(?:json)?\s*\n?(.*?)\n?```$', cleaned, re.DOTALL)
    if fence_match:
        cleaned = fence_match.group(1).strip()
    
    try:
        return json.loads(cleaned)
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
    source_content: Optional[str] = None,
    *,
    client: Optional[Anthropic] = None,
    config: Optional[AnthropicConfig] = None,
) -> EmailDraftResult:
    """Generate an email draft for a specific task, optionally using workspace content as source."""

    client = client or build_anthropic_client()
    config = config or resolve_config()

    # Use source content if provided, otherwise use task notes
    content_for_email = source_content if source_content else (task.notes or "No specific content provided")

    prompt = EMAIL_DRAFT_PROMPT.format(
        title=task.title,
        project=task.project,
        notes=task.notes or "No additional notes",
        source_content=content_for_email,
        recipient=recipient or "Not specified - recipient will be added manually",
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
    "description": "Update a task in Smartsheet when the user indicates they want to modify any task field. Always use this tool when the user's intent is to modify the task.",
    "input_schema": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": [
                    "mark_complete", "update_status", "update_priority", "update_due_date", "add_comment",
                    "update_number", "update_contact_flag", "update_recurring", "update_project",
                    "update_task", "update_assigned_to", "update_notes", "update_estimated_hours"
                ],
                "description": "The type of update to perform"
            },
            "status": {
                "type": "string",
                "enum": ["Scheduled", "In Progress", "Blocked", "Waiting", "Complete", "Recurring", "On Hold", "Follow-up", "Awaiting Reply", "Delivered", "Cancelled", "Delegated", "Completed"],
                "description": "New status value (required for update_status)"
            },
            "priority": {
                "type": "string",
                "enum": [
                    "Critical", "Urgent", "Important", "Standard", "Low",
                    "5-Critical", "4-Urgent", "3-Important", "2-Standard", "1-Low"
                ],
                "description": "New priority value (required for update_priority). Use numbered format (5-Critical, etc.) for work tasks, simple format (Critical, etc.) for personal tasks."
            },
            "due_date": {
                "type": "string",
                "description": "New due date in YYYY-MM-DD format (required for update_due_date)"
            },
            "comment": {
                "type": "string",
                "description": "Comment text to add (required for add_comment)"
            },
            "number": {
                "type": "integer",
                "description": "Task number (positive integer, required for update_number)"
            },
            "contact_flag": {
                "type": "boolean",
                "description": "Contact checkbox value (required for update_contact_flag)"
            },
            "recurring": {
                "type": "string",
                "enum": ["M", "T", "W", "H", "F", "Sa", "Monthly"],
                "description": "Recurring pattern (required for update_recurring)"
            },
            "project": {
                "type": "string",
                "description": "Project name - must be from allowed list (required for update_project)"
            },
            "task_title": {
                "type": "string",
                "description": "Task title text (required for update_task)"
            },
            "assigned_to": {
                "type": "string",
                "description": "Email address of assignee (required for update_assigned_to)"
            },
            "notes": {
                "type": "string",
                "description": "Notes text (required for update_notes)"
            },
            "estimated_hours": {
                "type": "string",
                "enum": [".05", ".15", ".25", ".50", ".75", "1", "2", "3", "4", "5", "6", "7", "8"],
                "description": "Estimated hours (required for update_estimated_hours)"
            },
            "reason": {
                "type": "string",
                "description": "Brief explanation of why this update is being made"
            }
        },
        "required": ["action", "reason"]
    }
}

# Tool definition for updating email drafts
EMAIL_DRAFT_UPDATE_TOOL = {
    "name": "update_email_draft",
    "description": "Update the current email draft with new content. Use this when the user asks to refine, improve, or change their email draft.",
    "input_schema": {
        "type": "object",
        "properties": {
            "subject": {
                "type": "string",
                "description": "New subject line for the email (optional - only include if changing)"
            },
            "body": {
                "type": "string", 
                "description": "New body content for the email (optional - only include if changing)"
            },
            "reason": {
                "type": "string",
                "description": "Brief explanation of what was changed"
            }
        },
        "required": ["reason"]
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
- Change task number (#)
- Toggle Contact flag (checkbox)
- Set Recurring pattern (M, T, W, H, F, Sa, Monthly)
- Change Project (must be from allowed list)
- Update Task title
- Change Assigned To (email)
- Update Notes
- Set Estimated Hours (.05, .15, .25, .50, .75, 1, 2, 3, 4, 5, 6, 7, 8)

CRITICAL INSTRUCTION: When David asks you to update ANY task field, you MUST call the update_task tool. Do NOT say "I can't do that" or "I don't have access" - YOU DO HAVE ACCESS through the update_task tool.

TASK UPDATE TRIGGERS - CALL THE TOOL IMMEDIATELY:
- "done", "finished", "complete", "close it", "mark it done" → update_task(action="mark_complete", reason="...")
- "blocked", "stuck", "waiting on..." → update_task(action="update_status", status="Blocked", reason="...")
- "push to...", "change due date" → update_task(action="update_due_date", due_date="YYYY-MM-DD", reason="...")
- "make this urgent", "lower priority" → update_task(action="update_priority", priority="...", reason="...")
- "add note:", "note that..." → update_task(action="add_comment", comment="...", reason="...")
- "change project to...", "move to Church Tasks" → update_task(action="update_project", project="...", reason="...")
- "rename task to...", "change title to..." → update_task(action="update_task", task_title="...", reason="...")
- "assign to...", "give this to..." → update_task(action="update_assigned_to", assigned_to="email@...", reason="...")
- "update notes to...", "set notes:" → update_task(action="update_notes", notes="...", reason="...")
- "set hours to...", "estimate 2 hours" → update_task(action="update_estimated_hours", estimated_hours="2", reason="...")
- "set recurring to Monday" → update_task(action="update_recurring", recurring="M", reason="...")
- "mark as contact", "flag for contact" → update_task(action="update_contact_flag", contact_flag=true, reason="...")
- "set number to 5" → update_task(action="update_number", number=5, reason="...")

PROJECT VALUES (must use exact match):
- Personal sheets: Around The House, Church Tasks, Family Time, Shopping, Sm. Projects & Tasks, Zendesk Ticket
- Work sheets: Atlassian (Jira/Confluence), Crafter Studio, Internal Application Support, Team Management, Strategic Planning, Stakeholder Relations, Process Improvement, Daily Operations, Zendesk Support, Intranet Management, Vendor Management, AI/Automation Projects, DTS Transformation, New Technology Evaluation

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
- Refine email drafts using the update_email_draft tool
- Create action plans
- Research and summarize information
- Web search for current information

EMAIL DRAFT REFINEMENT:
When the user shares an email draft and asks for improvements, use the update_email_draft tool to provide the refined version. Include only the fields you're changing (subject and/or body).

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
    subject: Optional[str] = None
    body: Optional[str] = None
    reason: str = ""


@dataclass(slots=True)
class ChatResponse:
    """Response from chat_with_tools, may include a pending action or email update."""
    message: str
    pending_action: Optional[TaskUpdateAction] = None
    email_draft_update: Optional[EmailDraftUpdate] = None


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

    # Build task context - include source for priority format guidance
    priority_format = "numbered (5-Critical, 4-Urgent, 3-Important, 2-Standard, 1-Low)" if task.source == "work" else "simple (Critical, Urgent, Important, Standard, Low)"
    task_context = f"""Current Task:
- Title: {task.title}
- Status: {task.status}
- Priority: {task.priority}
- Due: {task.due.strftime("%Y-%m-%d")}
- Project: {task.project}
- Source: {task.source} (use {priority_format} priorities)
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
            tools=[TASK_UPDATE_TOOL, WEB_SEARCH_TOOL, EMAIL_DRAFT_UPDATE_TOOL],
        )
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
            if tool_name == "update_task":
                tool_input = getattr(block, "input", {})
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
                tool_input = getattr(block, "input", {})
                email_draft_update = EmailDraftUpdate(
                    subject=tool_input.get("subject"),
                    body=tool_input.get("body"),
                    reason=tool_input.get("reason", ""),
                )

    message = "\n".join(text_content).strip()
    
    # If there's a pending action but no message, generate a confirmation message
    if pending_action and not message:
        action_desc = _describe_action(pending_action)
        message = f"I'll {action_desc}. Should I proceed?"
    
    # If there's an email draft update but no message, generate a confirmation message
    if email_draft_update and not message:
        changes = []
        if email_draft_update.subject:
            changes.append("subject")
        if email_draft_update.body:
            changes.append("body")
        message = f"I've updated the email {' and '.join(changes)}. {email_draft_update.reason}"

    return ChatResponse(message=message, pending_action=pending_action, email_draft_update=email_draft_update)


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
    elif action.action == "update_number":
        return f"change the task number to {action.number}"
    elif action.action == "update_contact_flag":
        return f"{'check' if action.contact_flag else 'uncheck'} the Contact flag"
    elif action.action == "update_recurring":
        return f"set the recurring pattern to '{action.recurring}'"
    elif action.action == "update_project":
        return f"change the project to '{action.project}'"
    elif action.action == "update_task":
        preview = (action.task_title or "")[:50]
        return f"change the task title to '{preview}...'" if len(action.task_title or "") > 50 else f"change the task title to '{action.task_title}'"
    elif action.action == "update_assigned_to":
        return f"assign this task to '{action.assigned_to}'"
    elif action.action == "update_notes":
        preview = (action.notes or "")[:50]
        return f"update the notes to '{preview}...'" if len(action.notes or "") > 50 else f"update the notes to '{action.notes}'"
    elif action.action == "update_estimated_hours":
        return f"set the estimated hours to {action.estimated_hours}"
    return f"perform action: {action.action}"


RESEARCH_SYSTEM_PROMPT = """You are DATA, researching to help David gain DEEPER UNDERSTANDING of a task topic.

PURPOSE: Surface insights, best practices, pros/cons, and approaches that help David make informed decisions and execute effectively.

RESEARCH SHOULD REVEAL:
- Pros and cons of the approach mentioned in the task
- Alternative approaches worth considering
- Best practices and common pitfalls
- How to get started or structure the work

DO NOT:
- List product/tool comparisons with pricing
- Provide generic definitions David already knows
- Include contact info unless the task requires external parties

FORMAT:

## Key Insights
- 3-5 bullets revealing UNDERSTANDING about the topic
- Focus on "why" and "how" not just "what"
- Include best practices, trade-offs, or lessons learned

## Approach Options
- 2-3 alternative approaches if relevant
- Brief pros/cons for each

## Getting Started
- 2-3 concrete first steps to begin implementation
- Focus on structure, setup, or initial actions

RULES:
- Maximum 200 words
- Skip sections not relevant to this task
- Be substantive, not generic
- If the topic is straightforward, keep it brief
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
    
    research_prompt = f"""Research this topic to help David understand it better and execute effectively:

**Task:** {task.title}
**Notes:** {task.notes or "None"}
{f"**Context:** {next_steps_text}" if next_steps_text else ""}

Research goals:
- Understand pros/cons and trade-offs of the approach
- Discover best practices and common pitfalls
- Find alternative approaches worth considering
- Identify how to structure or get started

Do NOT provide: tool/product comparisons with pricing, generic definitions, or contact info unless the task involves external parties."""

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

    # Use extract_formatted_only=True to filter out web search reasoning/thinking
    return _extract_text(response, extract_formatted_only=True)


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

