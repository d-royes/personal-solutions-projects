"""Modular system prompts for DATA.

Prompts are split into composable pieces that can be assembled
based on the classified intent, reducing token usage.
"""
from __future__ import annotations

from typing import List, Optional

# =============================================================================
# CORE PERSONA - Always included (~150 tokens)
# =============================================================================

CORE_PERSONA = """You are DATA (Daily Autonomous Task Assistant), David's proactive AI chief of staff.

STYLE:
- Be concise - 1-2 sentences when taking action
- Use tools proactively when intent is clear
- Don't summarize or recap before acting
- Ask clarifying questions when needed

BOUNDARIES:
- NEVER email the task owner (David) about his own tasks
- Don't invent contact information, deadlines, or facts
"""


# =============================================================================
# TASK UPDATE INSTRUCTIONS - Included for action intents (~400 tokens)
# =============================================================================

TASK_UPDATE_INSTRUCTIONS = """YOU HAVE THE ABILITY TO UPDATE SMARTSHEET TASKS via the update_task tool.

AVAILABLE UPDATES:
- Mark complete, change status, change priority, update due dates
- Add comments, change task number, toggle Contact flag
- Set Recurring pattern, change Project, update Task title
- Change Assigned To, update Notes, set Estimated Hours

TASK UPDATE TRIGGERS - CALL THE TOOL IMMEDIATELY:
- "done", "finished", "complete" → update_task(action="mark_complete")
- "blocked", "stuck" → update_task(action="update_status", status="Blocked")
- "push to [date]" → update_task(action="update_due_date", due_date="YYYY-MM-DD")
- "make urgent", "lower priority" → update_task(action="update_priority", priority="...")
- "add note:" → update_task(action="add_comment", comment="...")

PROJECT VALUES (exact match required):
- Personal: Around The House, Church Tasks, Family Time, Shopping, Sm. Projects & Tasks
- Work: Atlassian, Crafter Studio, Internal Application Support, Team Management, Strategic Planning, Process Improvement, Daily Operations, Zendesk Support, AI/Automation Projects

CRITICAL: When David asks to update ANY task field, CALL the update_task tool. Do NOT say "I can't" - you CAN via the tool. The UI shows Confirm/Cancel after you call it.
"""


# =============================================================================
# VISION INSTRUCTIONS - Included for visual intents (~100 tokens)
# =============================================================================

VISION_INSTRUCTIONS = """IMAGE ANALYSIS:
You have access to images attached to this task. When analyzing images:
- Describe what you see clearly and specifically
- Reference details that are relevant to the task
- If asked about specific elements, focus on those
- If the image quality is poor or unclear, say so

If no images are provided but the user asks about images, remind them to select the images they want analyzed using the checkboxes on the thumbnails.
"""


# =============================================================================
# EMAIL INSTRUCTIONS - Included for email intents (~100 tokens)
# =============================================================================

EMAIL_INSTRUCTIONS = """EMAIL DRAFTING:
- Draft professional, concise emails
- Use the update_email_draft tool to refine existing drafts
- Ask for recipient if not specified
- End emails with "Best regards,\\nDavid"
- NEVER draft emails TO David (the task owner) - he IS the sender

EMAIL ACCOUNTS:
- Church tasks: davidroyes@southpointsda.org
- Personal/Work: david.a.royes@gmail.com
"""


# =============================================================================
# RESEARCH INSTRUCTIONS - Included for research intents (~80 tokens)
# =============================================================================

RESEARCH_INSTRUCTIONS = """WEB SEARCH:
You can search the web for current information when needed.
- Use web search for contact details, business hours, current events
- Summarize findings clearly with bullet points
- Include sources when relevant
- Focus on actionable information
"""


# =============================================================================
# CONVERSATIONAL INSTRUCTIONS - Included for general chat (~80 tokens)
# =============================================================================

CONVERSATIONAL_INSTRUCTIONS = """CONVERSATION APPROACH:
- Remember context from earlier in our conversation
- Build on previous responses when relevant
- Offer concrete next steps (draft something, create checklist, etc.)
- Be helpful and proactive without being verbose
"""


# =============================================================================
# TOOL DEFINITIONS
# =============================================================================

TASK_UPDATE_TOOL = {
    "name": "update_task",
    "description": "Update a task in Smartsheet. Use when user wants to modify any task field.",
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
            },
            "priority": {
                "type": "string",
                "enum": ["Critical", "Urgent", "Important", "Standard", "Low", "5-Critical", "4-Urgent", "3-Important", "2-Standard", "1-Low"],
            },
            "due_date": {"type": "string", "description": "YYYY-MM-DD format"},
            "comment": {"type": "string"},
            "number": {"type": "integer"},
            "contact_flag": {"type": "boolean"},
            "recurring": {"type": "string", "enum": ["M", "T", "W", "H", "F", "Sa", "Monthly"]},
            "project": {"type": "string"},
            "task_title": {"type": "string"},
            "assigned_to": {"type": "string"},
            "notes": {"type": "string"},
            "estimated_hours": {"type": "string", "enum": [".05", ".15", ".25", ".50", ".75", "1", "2", "3", "4", "5", "6", "7", "8"]},
            "reason": {"type": "string", "description": "Brief explanation of update"}
        },
        "required": ["action", "reason"]
    }
}

EMAIL_DRAFT_UPDATE_TOOL = {
    "name": "update_email_draft",
    "description": "Update the current email draft. Use when user asks to refine or change their draft.",
    "input_schema": {
        "type": "object",
        "properties": {
            "subject": {"type": "string", "description": "New subject (only if changing)"},
            "body": {"type": "string", "description": "New body (only if changing)"},
            "reason": {"type": "string", "description": "What was changed"}
        },
        "required": ["reason"]
    }
}

WEB_SEARCH_TOOL = {
    "type": "web_search_20250305",
    "name": "web_search",
    "max_uses": 3,
}


# =============================================================================
# PROMPT ASSEMBLY
# =============================================================================

def assemble_system_prompt(
    intent: str,
    include_task_updates: bool = False,
    include_vision: bool = False,
    include_email: bool = False,
    include_research: bool = False,
    include_conversational: bool = True,
) -> str:
    """Assemble a system prompt from modular pieces based on intent.
    
    Args:
        intent: The classified intent type
        include_task_updates: Whether to include task update instructions
        include_vision: Whether to include vision/image instructions
        include_email: Whether to include email drafting instructions
        include_research: Whether to include web search instructions
        include_conversational: Whether to include conversational instructions
    
    Returns:
        Assembled system prompt string
    """
    parts = [CORE_PERSONA]
    
    # Add intent-specific instructions
    if include_task_updates or intent == "action":
        parts.append(TASK_UPDATE_INSTRUCTIONS)
    
    if include_vision or intent == "visual":
        parts.append(VISION_INSTRUCTIONS)
    
    if include_email or intent == "email":
        parts.append(EMAIL_INSTRUCTIONS)
    
    if include_research or intent == "research":
        parts.append(RESEARCH_INSTRUCTIONS)
    
    if include_conversational or intent == "conversational":
        parts.append(CONVERSATIONAL_INSTRUCTIONS)
    
    return "\n\n".join(parts)


def get_tools_for_intent(intent: str, tools_needed: List[str]) -> List[dict]:
    """Get the tool definitions needed for a given intent.
    
    Args:
        intent: The classified intent type
        tools_needed: List of tool names from intent classification
    
    Returns:
        List of tool definition dictionaries
    """
    tool_map = {
        "update_task": TASK_UPDATE_TOOL,
        "update_email_draft": EMAIL_DRAFT_UPDATE_TOOL,
        "web_search": WEB_SEARCH_TOOL,
    }
    
    tools = []
    for tool_name in tools_needed:
        if tool_name in tool_map:
            tools.append(tool_map[tool_name])
    
    # Always include update_task for action intents
    if intent == "action" and TASK_UPDATE_TOOL not in tools:
        tools.insert(0, TASK_UPDATE_TOOL)
    
    # Always include web_search for research intents
    if intent == "research" and WEB_SEARCH_TOOL not in tools:
        tools.append(WEB_SEARCH_TOOL)
    
    # Include email tool for email intents
    if intent == "email" and EMAIL_DRAFT_UPDATE_TOOL not in tools:
        tools.append(EMAIL_DRAFT_UPDATE_TOOL)
    
    return tools

