"""Anthropic client wrappers for Daily Task Assistant."""
from __future__ import annotations

import base64
from dataclasses import dataclass
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib import request as urlrequest
from urllib import error as urlerror

try:  # Optional dependency loaded via requirements.txt
    from anthropic import Anthropic, APIStatusError  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - handled at runtime
    Anthropic = None  # type: ignore
    APIStatusError = Exception  # type: ignore

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:  # pragma: no cover
    load_dotenv = None

from ..tasks import AttachmentDetail, TaskDetail


# Supported image types for Claude Vision
VISION_SUPPORTED_TYPES = {'image/jpeg', 'image/png', 'image/gif', 'image/webp'}


def download_and_encode_image(url: str, max_size_bytes: int = 4_500_000) -> Optional[str]:
    """Download an image from URL and return base64-encoded data.
    
    If the image exceeds max_size_bytes, it will be resized to fit.
    Returns None if download fails or times out.
    """
    try:
        with urlrequest.urlopen(url, timeout=15) as response:
            data = response.read()
            
            # If image is too large, try to resize it
            if len(data) > max_size_bytes:
                data = _resize_image(data, max_size_bytes)
                if data is None:
                    return None
            
            return base64.standard_b64encode(data).decode('utf-8')
    except Exception:
        # Catch any error - network issues, expired URLs, etc.
        return None


def _resize_image(image_data: bytes, max_size_bytes: int) -> Optional[bytes]:
    """Resize image to fit within max_size_bytes.
    
    Uses PIL/Pillow if available, otherwise returns None.
    """
    try:
        from PIL import Image
        import io
        
        # Open image
        img = Image.open(io.BytesIO(image_data))
        
        # Convert to RGB if necessary (for JPEG output)
        if img.mode in ('RGBA', 'P'):
            img = img.convert('RGB')
        
        # Start with current size and reduce until it fits
        quality = 85
        scale = 1.0
        
        for _ in range(10):  # Max 10 attempts
            output = io.BytesIO()
            
            if scale < 1.0:
                new_size = (int(img.width * scale), int(img.height * scale))
                resized = img.resize(new_size, Image.Resampling.LANCZOS)
            else:
                resized = img
            
            resized.save(output, format='JPEG', quality=quality, optimize=True)
            result = output.getvalue()
            
            if len(result) <= max_size_bytes:
                return result
            
            # Reduce quality first, then scale
            if quality > 50:
                quality -= 10
            else:
                scale *= 0.8
        
        return None  # Couldn't get it small enough
    except ImportError:
        # Pillow not installed
        return None
    except Exception:
        return None


def is_vision_supported(mime_type: str) -> bool:
    """Check if a MIME type is supported by Claude Vision."""
    return mime_type.lower() in VISION_SUPPORTED_TYPES


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

DEFAULT_MODEL = "claude-opus-4-20250514"
SYSTEM_PROMPT = """You are the Daily Task Assistant, a diligent chief of staff.
Produce concise, actionable guidance and respect the user's time.

CRITICAL: Your response MUST be valid JSON only. No markdown, no explanations, no text outside the JSON object.
Start your response with { and end with }. Nothing else."""

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
- RESPOND WITH JSON ONLY. No markdown. No explanations. Just the JSON object.
- Keys required: summary, next_steps, efficiency_tips, suggested_actions.
- Steps and tips must be strings without numbering prefixes.
- Reference provided context; do not invent data.
- The assignee (david.a.royes@gmail.com or davidroyes@southpointsda.org) is the OWNER, not a recipient. Never suggest emailing the owner.

Example response format:
{{"summary": "...", "next_steps": ["...", "..."], "efficiency_tips": ["..."], "suggested_actions": ["..."]}}
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
    workspace_context: Optional[str] = None,
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

    # Append workspace context if provided (user-selected workspace items)
    if workspace_context:
        prompt += f"""

---
ADDITIONAL CONTEXT (selected by user from workspace):

{workspace_context}

Use this context to make your plan more specific and actionable. Reference specific details from this context in your next steps and suggestions."""

    # Summarize conversation history to prevent format pollution
    history_summary = _summarize_history_for_planning(history) if history else ""
    if history_summary:
        prompt += f"""

---
CONVERSATION CONTEXT (summary of prior discussion):
{history_summary}

Consider this context when generating your plan, but REMEMBER: respond with JSON only."""

    try:
        messages = [
            {
                "role": "user",
                "content": [{"type": "text", "text": prompt}],
            }
        ]

        # Don't pass raw history - we've summarized it above
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


def _summarize_history_for_planning(history: List[Dict[str, str]]) -> str:
    """Reformat conversation history for planning to prevent format pollution.
    
    Converts raw messages (which may contain markdown, emojis, etc.) into
    clean plain text while preserving the substance of the conversation.
    This is reformatting, not heavy compression.
    """
    import re
    
    if not history:
        return ""
    
    def clean_text(text: str) -> str:
        """Strip formatting while preserving content."""
        # Remove emojis and special characters
        text = re.sub(r'[📋🎯💡✅❌➡️⚡✉️👍👎🔍📎📄🖼️]', '', text)
        # Remove markdown headers
        text = re.sub(r'^#{1,4}\s*', '', text, flags=re.MULTILINE)
        # Remove bold/italic markers
        text = re.sub(r'\*{1,2}([^*]+)\*{1,2}', r'\1', text)
        # Remove bullet points but keep content
        text = re.sub(r'^[\s]*[-•]\s*', '- ', text, flags=re.MULTILINE)
        # Remove code fences
        text = re.sub(r'```[\s\S]*?```', '[code block]', text)
        # Collapse multiple newlines
        text = re.sub(r'\n{3,}', '\n\n', text)
        # Clean up extra whitespace
        text = re.sub(r'[ \t]+', ' ', text)
        return text.strip()
    
    formatted_turns = []
    
    # Process recent history (last 8 turns to keep it reasonable)
    for turn in history[-8:]:
        content = (turn.get("content") or "").strip()
        if not content:
            continue
        
        role = turn.get("role", "user")
        role_label = "User" if role == "user" else "Assistant"
        
        # Clean the content
        cleaned = clean_text(content)
        
        # Truncate very long messages but keep most content
        if len(cleaned) > 500:
            cleaned = cleaned[:500] + "..."
        
        if cleaned:
            formatted_turns.append(f"{role_label}: {cleaned}")
    
    return "\n\n".join(formatted_turns)


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


# Legacy CHAT_SYSTEM_PROMPT removed - now using modular prompts in prompts.py

# Web search tool definition - now in prompts.py, kept here for backward compatibility
WEB_SEARCH_TOOL = {
    "type": "web_search_20250305",
    "name": "web_search",
    "max_uses": 3,
}

# chat_with_context function removed - superseded by intent-driven chat_with_tools


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
                "enum": ["Scheduled", "Recurring", "On Hold", "In Progress", "Follow-up", "Awaiting Reply", "Delivered", "Create ZD Ticket", "Ticket Created", "Validation", "Needs Approval", "Cancelled", "Delegated", "Completed"],
                "description": "New status value (required for update_status). Terminal statuses (Ticket Created, Cancelled, Delegated, Completed) also mark task as Done."
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
                "type": "number",
                "description": "Task number for daily ordering: 0.1-0.9 for recurring tasks (early AM), 1+ for regular tasks (required for update_number)"
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

# Tool definition for portfolio-level task updates (requires row_id)
PORTFOLIO_TASK_UPDATE_TOOL = {
    "name": "update_task",
    "description": "Update a specific task in Smartsheet from portfolio view. You MUST specify the row_id to identify which task to update.",
    "input_schema": {
        "type": "object",
        "properties": {
            "row_id": {
                "type": "string",
                "description": "The Smartsheet row ID of the task to update (REQUIRED - get from task_summaries)"
            },
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
                "enum": ["Scheduled", "Recurring", "On Hold", "In Progress", "Follow-up", "Awaiting Reply", "Delivered", "Create ZD Ticket", "Ticket Created", "Validation", "Needs Approval", "Cancelled", "Delegated", "Completed"],
                "description": "New status value (required for update_status)"
            },
            "priority": {
                "type": "string",
                "enum": ["Critical", "Urgent", "Important", "Standard", "Low", "5-Critical", "4-Urgent", "3-Important", "2-Standard", "1-Low"],
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
            "number": {
                "type": "number",
                "description": "Task number for daily ordering: 0.1-0.9 for recurring tasks (early AM), 1+ for regular tasks (required for update_number)"
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
                "description": "Project name (required for update_project)"
            },
            "task_title": {
                "type": "string",
                "description": "Task title text (required for update_task action)"
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
        "required": ["row_id", "action", "reason"]
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
- Change status (Scheduled, Recurring, On Hold, In Progress, Follow-up, Awaiting Reply, Delivered, Create ZD Ticket, Ticket Created, Validation, Needs Approval, Cancelled, Delegated, Completed)
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
- "on hold", "paused", "waiting on..." → update_task(action="update_status", status="On Hold", reason="...")
- "waiting for reply", "emailed them" → update_task(action="update_status", status="Awaiting Reply", reason="...")
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
    number: Optional[float] = None  # 0.1-0.9 for recurring, 1+ for regular
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


@dataclass(slots=True)
class PortfolioTaskUpdateAction:
    """Structured task update action for portfolio mode (includes row_id)."""
    row_id: str  # Required - identifies which task to update
    action: str
    status: Optional[str] = None
    priority: Optional[str] = None
    due_date: Optional[str] = None
    comment: Optional[str] = None
    number: Optional[float] = None  # 0.1-0.9 for recurring, 1+ for regular
    contact_flag: Optional[bool] = None
    recurring: Optional[str] = None
    project: Optional[str] = None
    task_title: Optional[str] = None
    assigned_to: Optional[str] = None
    notes: Optional[str] = None
    estimated_hours: Optional[str] = None
    reason: str = ""


@dataclass(slots=True) 
class PortfolioChatResponse:
    """Response from portfolio_chat_with_tools."""
    message: str
    pending_actions: List["PortfolioTaskUpdateAction"] = None  # Can have multiple task updates
    
    def __post_init__(self):
        if self.pending_actions is None:
            self.pending_actions = []


def chat_with_tools(
    task: TaskDetail,
    user_message: str,
    history: Optional[List[Dict[str, str]]] = None,
    *,
    attachments: Optional[List[AttachmentDetail]] = None,
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
        attachments: Optional list of task attachments (images will be included)
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
    
    # Build task context content with optional images
    context_content: List[Dict[str, Any]] = []
    
    # Add images first (Claude vision best practice)
    if attachments:
        for att in attachments:
            if is_vision_supported(att.mime_type):
                image_data = download_and_encode_image(att.download_url)
                if image_data:
                    context_content.append({
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": att.mime_type,
                            "data": image_data,
                        }
                    })
    
    # Add task context text
    context_content.append({"type": "text", "text": task_context})
    
    # Task context as priming
    messages.append({
        "role": "user",
        "content": context_content
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


# Portfolio Chat System Prompt - built dynamically to include current date
def _build_portfolio_system_prompt() -> str:
    """Build the portfolio chat system prompt with current date."""
    from datetime import datetime
    from zoneinfo import ZoneInfo
    
    today = datetime.now(ZoneInfo("America/New_York"))
    today_formatted = today.strftime("%A, %B %d, %Y")  # e.g., "Thursday, December 11, 2025"
    
    return f"""You are DATA, David's AI chief of staff, analyzing his task portfolio.

TODAY'S DATE: {today_formatted}

Use this date to determine if tasks are overdue, due today, or due in the future.
- A task with due_date before today is OVERDUE
- A task with due_date equal to today is DUE TODAY
- A task with due_date after today is UPCOMING

YOU HAVE THE ABILITY TO UPDATE TASKS IN SMARTSHEET. You have an update_task tool that lets you modify any task in the portfolio by specifying its row_id.

CRITICAL INSTRUCTION: When David asks you to update, rebalance, reschedule, or modify tasks, you MUST call the update_task tool for EACH task. Do NOT just describe what you would do - actually CALL THE TOOL.

AVAILABLE ACTIONS:
- mark_complete: Mark a task as done
- update_status: Change status
- update_priority: Change priority (Critical, Urgent, Important, Standard, Low)
- update_due_date: Change due date (YYYY-MM-DD format)
- add_comment: Add notes/comments
- update_number: Change the # field (0.1-0.9 for recurring, 1+ for regular)
- update_contact_flag: Toggle Contact checkbox
- update_recurring: Set recurring pattern (M, T, W, H, F, Sa, Monthly)
- update_project: Change project
- update_task: Rename the task
- update_assigned_to: Change assignee
- update_notes: Update notes
- update_estimated_hours: Set time estimate

WHEN TO CALL THE TOOL - DO IT IMMEDIATELY:
- "rebalance my tasks" → Call update_task for EACH task with new due_date
- "spread tasks over next week" → Call update_task for EACH task with new due_date
- "push overdue to next week" → Call update_task for EACH overdue task
- "mark X as complete" → Call update_task with action="mark_complete"
- "set priorities for today" → Call update_task for EACH task with new number

WRONG (do NOT do this):
- Describing what you WOULD do without calling the tool
- Saying "Let me update..." without actual tool calls
- Asking "Should I proceed?" for clear requests

RIGHT (do this):
- Call update_task immediately for each change
- David will see pending actions and can confirm/reject
- The UI handles the confirmation flow

EXAMPLE - "Rebalance my 5 overdue tasks across next week":
1. Call update_task(row_id="123", action="update_due_date", due_date="2025-12-15", reason="Rebalancing")
2. Call update_task(row_id="456", action="update_due_date", due_date="2025-12-16", reason="Rebalancing")
3. Call update_task(row_id="789", action="update_due_date", due_date="2025-12-17", reason="Rebalancing")
... (one call per task)

YOUR ROLE: Execute task updates efficiently. The frontend handles user confirmation."""


def portfolio_chat_with_tools(
    portfolio_context: str,
    task_summaries: List[Dict[str, Any]],
    user_message: str,
    history: Optional[List[Dict[str, str]]] = None,
    perspective: str = "holistic",
    *,
    client: Optional[Anthropic] = None,
    config: Optional[AnthropicConfig] = None,
) -> PortfolioChatResponse:
    """Chat with portfolio-level task update tool support.
    
    This enables DATA to update specific tasks from the portfolio view
    by specifying row_id in the tool call.
    
    Args:
        portfolio_context: Formatted portfolio statistics
        task_summaries: List of tasks with row_id, title, due, priority, etc.
        user_message: The user's latest message
        history: Previous conversation messages
        perspective: Current perspective (personal, church, work, holistic)
        client: Optional pre-built Anthropic client
        config: Optional configuration override
    
    Returns:
        PortfolioChatResponse with message and optional pending_actions list
    """
    client = client or build_anthropic_client()
    config = config or resolve_config()

    # Build task list for context (include row_id for targeting)
    task_list_text = "\n".join([
        f"- [{t.get('row_id')}] {t.get('title', 'Untitled')[:50]} | {t.get('priority')} | Due: {t.get('due', 'N/A')[:10]} | #: {t.get('number', '-')}"
        for t in task_summaries[:30]  # Limit for context window
    ])
    
    # Build messages
    messages: List[Dict[str, Any]] = []
    
    # Portfolio context as priming
    context_message = f"""[Portfolio View - {perspective.title()}]

{portfolio_context}

TASKS (with row_id for updates):
{task_list_text}

---
{user_message}"""

    if not history:
        messages.append({
            "role": "user",
            "content": [{"type": "text", "text": context_message}]
        })
    else:
        # Add history
        for msg in history:
            messages.append({
                "role": msg["role"],
                "content": [{"type": "text", "text": msg["content"]}]
            })
        # Add current message with brief context update
        messages.append({
            "role": "user",
            "content": [{"type": "text", "text": f"[Portfolio: {len(task_summaries)} tasks]\n\n{user_message}"}]
        })

    try:
        response = client.messages.create(
            model=config.model,
            max_tokens=4000,  # Increased for multiple tool calls
            temperature=0.5,
            system=_build_portfolio_system_prompt(),
            messages=messages,
            tools=[PORTFOLIO_TASK_UPDATE_TOOL],
        )
    except APIStatusError as exc:
        raise AnthropicError(f"Anthropic API error: {exc}") from exc
    except Exception as exc:
        raise AnthropicError(f"Anthropic request failed: {exc}") from exc

    # Extract text and tool uses from response
    text_content = []
    pending_actions = []
    
    # Debug: Log response details
    print(f"[DEBUG] Response stop_reason: {getattr(response, 'stop_reason', 'N/A')}")
    print(f"[DEBUG] Response content blocks: {len(getattr(response, 'content', []))}")
    for i, block in enumerate(getattr(response, "content", [])):
        print(f"[DEBUG] Block {i}: type={getattr(block, 'type', 'unknown')}")
    
    for block in getattr(response, "content", []):
        block_type = getattr(block, "type", None)
        if block_type == "text":
            text_content.append(getattr(block, "text", ""))
        elif block_type == "tool_use":
            tool_name = getattr(block, "name", "")
            if tool_name == "update_task":
                tool_input = getattr(block, "input", {})
                action = PortfolioTaskUpdateAction(
                    row_id=tool_input.get("row_id", ""),
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
                pending_actions.append(action)

    message = "\n".join(text_content).strip()
    
    # Generate confirmation message if actions but no text
    if pending_actions and not message:
        if len(pending_actions) == 1:
            action = pending_actions[0]
            message = f"I'll update task {action.row_id}: {_describe_portfolio_action(action)}. Proceed?"
        else:
            message = f"I have {len(pending_actions)} task updates ready. Review and confirm?"

    return PortfolioChatResponse(message=message, pending_actions=pending_actions)


def _describe_portfolio_action(action: PortfolioTaskUpdateAction) -> str:
    """Generate a human-readable description of a portfolio task action."""
    if action.action == "mark_complete":
        return "mark as complete"
    elif action.action == "update_status":
        return f"change status to '{action.status}'"
    elif action.action == "update_priority":
        return f"change priority to '{action.priority}'"
    elif action.action == "update_due_date":
        return f"change due date to {action.due_date}"
    elif action.action == "add_comment":
        return f"add comment"
    elif action.action == "update_number":
        return f"set # to {action.number}"
    elif action.action == "update_contact_flag":
        return f"{'check' if action.contact_flag else 'uncheck'} Contact flag"
    elif action.action == "update_recurring":
        return f"set recurring to '{action.recurring}'"
    elif action.action == "update_project":
        return f"change project to '{action.project}'"
    elif action.action == "update_task":
        return f"rename to '{action.task_title}'"
    elif action.action == "update_assigned_to":
        return f"assign to '{action.assigned_to}'"
    elif action.action == "update_notes":
        return f"update notes"
    elif action.action == "update_estimated_hours":
        return f"set hours to {action.estimated_hours}"
    return f"{action.action}"


# =============================================================================
# Email Chat (Phase 4)
# =============================================================================

EMAIL_CHAT_SYSTEM_PROMPT = """You are DATA, David's personal AI assistant helping manage emails.

Your role is to help David:
1. Triage and categorize emails efficiently
2. Suggest actions (archive, delete, star, flag as important)
3. Identify emails that need follow-up or tasks
4. Draft quick replies when asked
5. Summarize email threads

When David asks about an email:
- Provide concise, actionable insights
- Suggest relevant actions based on the email content
- Help identify if the email requires a response, can be archived, or should become a task

Use the email_action tool when David explicitly requests an action like:
- "Archive this"
- "Delete this"
- "Star this email"
- "Mark as important"
- "Create a task from this"
- "Draft a reply" / "Draft an email" / "Compose a response" → use draft_reply action
- "Reply all" / "Draft reply all" → use draft_reply_all action

When using draft_reply or draft_reply_all:
- Include the draft_body field with the complete email body
- Include draft_subject only if it differs from "Re: [original subject]"
- Write human-like responses: no AI-isms like "I hope this email finds you well"
- Match the tone of the original email
- Use bullet points when they help organize information (David prefers them)
- Sign off naturally as "David"

Be proactive but not presumptuous - suggest actions but wait for confirmation before executing.

Keep responses brief and focused. David values efficiency.
"""

EMAIL_ACTION_TOOL = {
    "name": "email_action",
    "description": "Perform an action on an email when the user requests it.",
    "input_schema": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["archive", "delete", "star", "unstar", "mark_important", "unmark_important", "create_task", "draft_reply", "draft_reply_all"],
                "description": "The action to perform on the email"
            },
            "reason": {
                "type": "string",
                "description": "Brief explanation of why this action is recommended"
            },
            "task_title": {
                "type": "string",
                "description": "Title for the task (only if action is create_task)"
            },
            "draft_body": {
                "type": "string",
                "description": "The email body content for the draft (only if action is draft_reply or draft_reply_all)"
            },
            "draft_subject": {
                "type": "string",
                "description": "The subject line for the draft (only if action is draft_reply or draft_reply_all)"
            },
        },
        "required": ["action", "reason"]
    }
}


@dataclass(slots=True)
class EmailAction:
    """Structured email action from chat."""
    action: str
    reason: str
    task_title: Optional[str] = None
    draft_body: Optional[str] = None
    draft_subject: Optional[str] = None


@dataclass(slots=True)
class EmailChatResponse:
    """Response from email chat, may include a pending action."""
    message: str
    pending_action: Optional[EmailAction] = None


def chat_with_email(
    email_context: str,
    user_message: str,
    history: Optional[List[Dict[str, str]]] = None,
    *,
    client: Optional[Anthropic] = None,
    config: Optional[AnthropicConfig] = None,
) -> EmailChatResponse:
    """Chat with DATA about an email with action tool support.
    
    Args:
        email_context: Formatted string with email details (from, subject, snippet, etc.)
        user_message: The user's latest message
        history: Previous conversation messages
        client: Optional pre-built Anthropic client
        config: Optional configuration override
    
    Returns:
        EmailChatResponse with message and optional pending_action
    """
    client = client or build_anthropic_client()
    config = config or resolve_config()

    # Build messages
    messages: List[Dict[str, Any]] = []
    
    # Email context as priming
    messages.append({
        "role": "user",
        "content": [{"type": "text", "text": email_context}]
    })
    messages.append({
        "role": "assistant",
        "content": [{"type": "text", "text": "I see this email. How can I help you with it?"}]
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
            system=EMAIL_CHAT_SYSTEM_PROMPT,
            messages=messages,
            tools=[EMAIL_ACTION_TOOL],
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
            if tool_name == "email_action":
                tool_input = getattr(block, "input", {})
                pending_action = EmailAction(
                    action=tool_input.get("action", ""),
                    reason=tool_input.get("reason", ""),
                    task_title=tool_input.get("task_title"),
                    draft_body=tool_input.get("draft_body"),
                    draft_subject=tool_input.get("draft_subject"),
                )

    message = "\n".join(text_content).strip()
    
    # If there's a pending action but no message, generate one
    if pending_action and not message:
        action_desc = _describe_email_action(pending_action)
        message = f"I'll {action_desc}. Should I proceed?"

    return EmailChatResponse(message=message, pending_action=pending_action)


def _describe_email_action(action: EmailAction) -> str:
    """Generate a human-readable description of an email action."""
    if action.action == "archive":
        return "archive this email"
    elif action.action == "delete":
        return "move this email to trash"
    elif action.action == "star":
        return "star this email"
    elif action.action == "unstar":
        return "remove the star from this email"
    elif action.action == "mark_important":
        return "mark this email as important"
    elif action.action == "unmark_important":
        return "remove importance from this email"
    elif action.action == "create_task":
        title = action.task_title or "from this email"
        return f"create a task: '{title}'"
    elif action.action == "draft_reply":
        return "open the reply draft panel with my suggested response"
    elif action.action == "draft_reply_all":
        return "open the reply all draft panel with my suggested response"
    return f"perform action: {action.action}"


# =============================================================================
# Task Extraction from Email (Phase B)
# =============================================================================

TASK_EXTRACTION_PROMPT = """You are DATA, David's AI assistant. Your task is to analyze an email and suggest task details.

Given the email information, suggest appropriate task details:
- title: A clear, actionable task title (not just the email subject)
- dueDate: Extract any mentioned deadline (format: YYYY-MM-DD) or null
- priority: Critical, Urgent, Important, Standard, or Low based on email urgency
- domain: "personal", "church", or "work" based on context
- project: Select from the allowed values based on domain:
  - For personal/church: "Around The House", "Church Tasks", "Family Time", "Shopping", "Sm. Projects & Tasks", or "Zendesk Ticket"
  - For work: "Atlassian (Jira/Confluence)", "Crafter Studio", "Internal Application Support", "Team Management", "Strategic Planning", "Stakeholder Relations", "Process Improvement", "Daily Operations", "Zendesk Support", "Intranet Management", "Vendor Management", "AI/Automation Projects", "DTS Transformation", "New Technology Evaluation"
- notes: Brief context from the email (1-2 sentences max)

Be concise and action-oriented. The title should describe what David needs to DO, not just what the email is about.

Respond with a JSON object only, no other text."""


def extract_task_from_email(
    from_address: str,
    from_name: str,
    subject: str,
    snippet: str,
    email_account: str,
    *,
    client: Optional[Anthropic] = None,
    config: Optional[AnthropicConfig] = None,
) -> Dict[str, Any]:
    """Extract task details from an email using DATA.
    
    Args:
        from_address: Sender's email address
        from_name: Sender's display name
        subject: Email subject
        snippet: Email preview text
        email_account: "personal" or "church"
    
    Returns:
        Dictionary with title, dueDate, priority, domain, notes
    """
    import json
    
    client = client or build_anthropic_client()
    config = config or resolve_config()
    
    email_context = f"""Email Details:
- From: {from_name} <{from_address}>
- Subject: {subject}
- Preview: {snippet}
- Account: {email_account}"""

    try:
        response = client.messages.create(
            model=config.model,
            max_tokens=500,
            temperature=0.3,
            system=TASK_EXTRACTION_PROMPT,
            messages=[{
                "role": "user",
                "content": f"Please extract task details from this email:\n\n{email_context}"
            }],
        )
    except Exception as exc:
        raise AnthropicError(f"Task extraction failed: {exc}") from exc
    
    # Parse JSON response
    text = ""
    for block in getattr(response, "content", []):
        if getattr(block, "type", None) == "text":
            text += getattr(block, "text", "")
    
    text = text.strip()
    
    # Handle markdown code blocks
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1]) if len(lines) > 2 else text
    
    try:
        result = json.loads(text)
    except json.JSONDecodeError:
        # Fallback to simple extraction
        domain = "church" if email_account == "church" else "personal"
        result = {
            "title": subject.replace("Re:", "").replace("Fwd:", "").strip(),
            "dueDate": None,
            "priority": "Standard",
            "domain": domain,
            "project": "Church Tasks" if domain == "church" else "Sm. Projects & Tasks",
            "notes": f"From: {from_name or from_address}",
        }
    
    return result


# =============================================================================
# Email Reply Draft Generation
# =============================================================================

EMAIL_REPLY_SYSTEM_PROMPT = """You are helping David compose an email reply. Your goal is to draft a natural, human-like response.

CRITICAL RULES:
1. NEVER use AI-isms like "I hope this email finds you well", "Please let me know if you have any questions", "I would be happy to assist"
2. Write in David's voice - professional but warm, direct but respectful
3. Match the tone and formality of the original email
4. Keep it concise - get to the point quickly
5. Use bullet points when they help organize information (David prefers them for clarity)
6. End naturally without clichéd sign-offs

FORMATTING:
- Use appropriate greeting based on relationship (context will indicate formality level)
- For close contacts: "Hi [Name]," or just "[Name],"
- For formal: "Hello [Name]," or "Good morning/afternoon,"
- Include relevant signature: "David" for personal, or appropriate title for work/church

STRUCTURE YOUR RESPONSE:
1. Brief acknowledgment (if replying to question/request)
2. Main content - address each point from the original email
3. Any questions or next steps needed
4. Natural closing

Remember: This should read like a human wrote it, not an AI assistant. Be conversational but efficient."""


@dataclass(slots=True)
class EmailReplyDraft:
    """Generated email reply draft."""
    subject: str
    body: str
    body_html: Optional[str] = None
    to_addresses: List[str] = None  # type: ignore
    cc_addresses: List[str] = None  # type: ignore
    
    def __post_init__(self):
        if self.to_addresses is None:
            self.to_addresses = []
        if self.cc_addresses is None:
            self.cc_addresses = []


def generate_email_reply_draft(
    original_email: Dict[str, Any],
    thread_context: Optional[str] = None,
    user_instructions: Optional[str] = None,
    reply_all: bool = False,
    *,
    client: Optional[Anthropic] = None,
    config: Optional[AnthropicConfig] = None,
) -> EmailReplyDraft:
    """Generate a human-like email reply draft.
    
    Args:
        original_email: Dict with keys: fromAddress, fromName, toAddress, ccAddress, 
                       subject, body (or snippet), date
        thread_context: Optional AI-summarized thread context for multi-message threads
        user_instructions: Optional instructions from David about what to include
        reply_all: If True, include CC recipients in the reply
        client: Optional pre-built Anthropic client
        config: Optional configuration override
    
    Returns:
        EmailReplyDraft with generated subject, body, and recipient lists
    """
    client = client or build_anthropic_client()
    config = config or resolve_config()
    
    # Build context for the AI
    sender_name = original_email.get("fromName") or original_email.get("fromAddress", "")
    sender_email = original_email.get("fromAddress", "")
    original_subject = original_email.get("subject", "")
    original_body = original_email.get("body") or original_email.get("snippet", "")
    original_cc = original_email.get("ccAddress", "")
    
    context_parts = [
        f"ORIGINAL EMAIL:",
        f"From: {sender_name} <{sender_email}>",
        f"Subject: {original_subject}",
        f"Date: {original_email.get('date', 'Unknown')}",
    ]
    
    if original_cc:
        context_parts.append(f"CC: {original_cc}")
    
    context_parts.append(f"\nBody:\n{original_body}")
    
    if thread_context:
        context_parts.insert(0, f"THREAD CONTEXT:\n{thread_context}\n\n---\n")
    
    email_context = "\n".join(context_parts)
    
    # Build the prompt
    user_prompt_parts = [
        f"Please draft a reply to this email:\n\n{email_context}"
    ]
    
    if user_instructions:
        user_prompt_parts.append(f"\nDAVID'S INSTRUCTIONS:\n{user_instructions}")
    else:
        user_prompt_parts.append("\nProvide a thoughtful, human-like response addressing the email content.")
    
    try:
        response = client.messages.create(
            model=config.model,
            max_tokens=1500,
            temperature=0.7,  # Slightly higher for more natural variation
            system=EMAIL_REPLY_SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": "\n".join(user_prompt_parts)
            }],
        )
    except Exception as exc:
        raise AnthropicError(f"Email reply generation failed: {exc}") from exc
    
    # Extract the generated reply
    body_text = ""
    for block in getattr(response, "content", []):
        if getattr(block, "type", None) == "text":
            body_text += getattr(block, "text", "")
    
    body_text = body_text.strip()
    
    # Build recipient lists
    to_addresses = [sender_email] if sender_email else []
    cc_addresses = []
    
    if reply_all and original_cc:
        # Parse CC addresses (can be comma-separated)
        cc_parts = [addr.strip() for addr in original_cc.split(",")]
        cc_addresses = [addr for addr in cc_parts if addr]
    
    # Build subject (add Re: if not already present)
    subject = original_subject
    if not subject.lower().startswith("re:"):
        subject = f"Re: {subject}"
    
    return EmailReplyDraft(
        subject=subject,
        body=body_text,
        body_html=_convert_to_simple_html(body_text),
        to_addresses=to_addresses,
        cc_addresses=cc_addresses,
    )


def _convert_to_simple_html(text: str) -> str:
    """Convert plain text to simple HTML for email.
    
    Handles:
    - Paragraphs (double newlines)
    - Line breaks
    - Bullet points (lines starting with - or *)
    """
    import html
    
    # Escape HTML entities
    text = html.escape(text)
    
    # Split into paragraphs
    paragraphs = text.split("\n\n")
    html_parts = []
    
    for para in paragraphs:
        lines = para.split("\n")
        
        # Check if this is a bullet list
        is_list = all(line.strip().startswith(("-", "*", "•")) for line in lines if line.strip())
        
        if is_list and lines:
            list_items = []
            for line in lines:
                # Remove bullet character and whitespace
                item_text = line.strip().lstrip("-*•").strip()
                if item_text:
                    list_items.append(f"<li>{item_text}</li>")
            if list_items:
                html_parts.append(f"<ul>{''.join(list_items)}</ul>")
        else:
            # Regular paragraph with line breaks
            para_html = "<br>".join(lines)
            html_parts.append(f"<p>{para_html}</p>")
    
    return "".join(html_parts)

