"""Intent classification for DATA chat messages.

Classifies user intent to determine what context is needed for each query,
enabling efficient token usage by loading only relevant context.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from anthropic import Anthropic

from .anthropic_client import build_anthropic_client, AnthropicError
from .gemini_client import classify_with_gemini, is_gemini_available


@dataclass(slots=True)
class ClassifiedIntent:
    """Result of intent classification.
    
    Attributes:
        intent: Primary intent type (action, visual, conversational, research, email, planning)
        tools_needed: List of tool names required for this intent
        include_images: Whether to include selected images in context
        include_history: Whether to include conversation history
        include_workspace: Whether to include workspace content
        confidence: Classification confidence (0.0-1.0)
        suggested_model: Recommended model for this intent type
        reasoning: Brief explanation of classification
    """
    intent: str
    tools_needed: List[str] = field(default_factory=list)
    include_images: bool = False
    include_history: bool = True
    include_workspace: bool = True
    confidence: float = 0.9
    suggested_model: str = "claude-sonnet"
    reasoning: str = ""


# Intent types and their characteristics
# Models: "claude-sonnet" for complex/tools, "gemini-flash" for fast/simple
INTENT_PROFILES = {
    "action": {
        "description": "User wants to update/modify the task (mark done, change status, etc.)",
        "tools": ["update_task"],
        "include_images": False,
        "include_history": False,  # Action intents don't need history
        "include_workspace": False,
        "model": "claude-sonnet",  # Claude for tool use
    },
    "visual": {
        "description": "User wants to analyze or discuss images/attachments",
        "tools": [],
        "include_images": True,
        "include_history": True,
        "include_workspace": True,
        "model": "claude-sonnet",  # Claude for vision
    },
    "conversational": {
        "description": "User wants to continue discussion, ask questions, or get clarification",
        "tools": [],
        "include_images": False,
        "include_history": True,
        "include_workspace": True,
        "model": "gemini-flash",  # Gemini for fast general chat
    },
    "research": {
        "description": "User wants to find information or research a topic",
        "tools": ["web_search"],
        "include_images": False,
        "include_history": False,
        "include_workspace": True,
        "model": "claude-sonnet",  # Claude has web_search tool
    },
    "email": {
        "description": "User wants to draft, refine, or send an email",
        "tools": ["update_email_draft"],
        "include_images": False,
        "include_history": True,
        "include_workspace": True,
        "model": "claude-sonnet",  # Claude for tool use
    },
    "planning": {
        "description": "User wants help planning, organizing, or strategizing",
        "tools": [],
        "include_images": False,
        "include_history": True,
        "include_workspace": True,
        "model": "gemini-flash",  # Gemini for general planning chat
    },
}


CLASSIFICATION_PROMPT = """Classify the user's intent for a task assistant. Return JSON only.

User message: "{message}"

Task context: {task_title}

Has selected images: {has_images}
Has workspace content: {has_workspace}

Classify into ONE of these intents:
- "action": User wants to update the task (mark done, change status, priority, due date, etc.)
- "visual": User wants to analyze or discuss images/attachments
- "conversational": User wants to continue discussion, ask questions, clarify
- "research": User wants to find information or research a topic
- "email": User wants to draft, refine, or work on an email
- "planning": User wants help planning, organizing, or strategizing

Return JSON: {{"intent": "<type>", "confidence": <0.0-1.0>, "reasoning": "<brief explanation>"}}

Rules:
- If user mentions "image", "picture", "attachment", "see", "look at", "photo" → likely "visual"
- If user says "done", "complete", "mark", "change status/priority", "update" → likely "action"
- If user says "research", "find", "look up", "search for" → likely "research"
- If user says "email", "draft", "send", "write to" → likely "email"
- Default to "conversational" if unclear
"""


def classify_intent(
    message: str,
    task_title: str,
    has_selected_images: bool = False,
    has_workspace_content: bool = False,
    *,
    client: Optional[Anthropic] = None,
    prefer_gemini: bool = True,
) -> ClassifiedIntent:
    """Classify user intent using a lightweight LLM call.
    
    Uses Gemini Flash (preferred) or Claude Haiku for fast, low-cost classification.
    
    Args:
        message: The user's message to classify
        task_title: Title of the current task for context
        has_selected_images: Whether user has selected images to include
        has_workspace_content: Whether there's checked workspace content
        client: Optional pre-built Anthropic client
        prefer_gemini: Whether to try Gemini first (default True)
    
    Returns:
        ClassifiedIntent with intent type and context requirements
    """
    # Quick keyword check for obvious cases (saves an API call)
    quick_result = _quick_classify(message, has_selected_images)
    if quick_result:
        return quick_result
    
    # Try Gemini Flash first (faster, cheaper)
    if prefer_gemini and is_gemini_available():
        try:
            result = classify_with_gemini(
                message=message,
                task_title=task_title,
                has_images=has_selected_images,
                has_workspace=has_workspace_content,
            )
            return _parse_classification_response(
                str(result),  # classify_with_gemini returns dict, convert to JSON string
                has_selected_images,
                has_workspace_content,
                gemini_result=result,  # Pass the dict directly
            )
        except Exception:
            pass  # Fall through to Anthropic
    
    # Fall back to Anthropic Haiku
    client = client or build_anthropic_client()
    
    prompt = CLASSIFICATION_PROMPT.format(
        message=message,
        task_title=task_title,
        has_images="yes" if has_selected_images else "no",
        has_workspace="yes" if has_workspace_content else "no",
    )
    
    try:
        response = client.messages.create(
            model="claude-3-5-haiku-20241022",  # Fast, cheap model for classification
            max_tokens=150,
            temperature=0.0,  # Deterministic classification
            messages=[{"role": "user", "content": prompt}],
        )
        
        # Parse response
        text = response.content[0].text.strip()
        return _parse_classification_response(text, has_selected_images, has_workspace_content)
        
    except Exception as exc:
        # Fallback to conversational on error
        return ClassifiedIntent(
            intent="conversational",
            tools_needed=[],
            include_images=has_selected_images,
            include_history=True,
            include_workspace=has_workspace_content,
            confidence=0.5,
            reasoning=f"Classification failed, defaulting to conversational: {exc}",
        )


def _quick_classify(message: str, has_selected_images: bool) -> Optional[ClassifiedIntent]:
    """Quick keyword-based classification for obvious cases.
    
    Returns None if classification is ambiguous and needs LLM.
    """
    msg_lower = message.lower()
    
    # Action keywords - very high confidence
    action_keywords = [
        "mark done", "mark complete", "mark it done", "close this", "finished",
        "change status", "change priority", "update status", "set status",
        "push to", "move to", "change due", "reschedule",
        "mark as blocked", "mark as complete", "mark as waiting",
    ]
    if any(kw in msg_lower for kw in action_keywords):
        profile = INTENT_PROFILES["action"]
        return ClassifiedIntent(
            intent="action",
            tools_needed=profile["tools"],
            include_images=False,
            include_history=False,
            include_workspace=False,
            confidence=0.95,
            suggested_model=profile["model"],
            reasoning="Matched action keyword",
        )
    
    # Visual keywords - requires selected images
    visual_keywords = ["image", "picture", "photo", "screenshot", "attachment", "see in", "look at", "what's in"]
    if any(kw in msg_lower for kw in visual_keywords):
        if has_selected_images:
            profile = INTENT_PROFILES["visual"]
            return ClassifiedIntent(
                intent="visual",
                tools_needed=profile["tools"],
                include_images=True,
                include_history=True,
                include_workspace=True,
                confidence=0.95,
                suggested_model=profile["model"],
                reasoning="Matched visual keyword with selected images",
            )
        else:
            # Visual intent but no images selected - still classify as visual
            # The chat handler will prompt user to select images
            return ClassifiedIntent(
                intent="visual",
                tools_needed=[],
                include_images=False,  # No images to include
                include_history=True,
                include_workspace=True,
                confidence=0.9,
                suggested_model="claude-sonnet",
                reasoning="Visual intent but no images selected",
            )
    
    # Research keywords
    research_keywords = ["research", "find out", "look up", "search for", "what is the"]
    if any(kw in msg_lower for kw in research_keywords):
        profile = INTENT_PROFILES["research"]
        return ClassifiedIntent(
            intent="research",
            tools_needed=profile["tools"],
            include_images=False,
            include_history=False,
            include_workspace=True,
            confidence=0.9,
            suggested_model=profile["model"],
            reasoning="Matched research keyword",
        )
    
    # Email keywords
    email_keywords = ["draft email", "write email", "send email", "email to", "draft a message"]
    if any(kw in msg_lower for kw in email_keywords):
        profile = INTENT_PROFILES["email"]
        return ClassifiedIntent(
            intent="email",
            tools_needed=profile["tools"],
            include_images=False,
            include_history=True,
            include_workspace=True,
            confidence=0.9,
            suggested_model=profile["model"],
            reasoning="Matched email keyword",
        )
    
    # No clear match - needs LLM classification
    return None


def _parse_classification_response(
    text: str,
    has_selected_images: bool,
    has_workspace_content: bool,
    *,
    gemini_result: Optional[dict] = None,
) -> ClassifiedIntent:
    """Parse LLM classification response into ClassifiedIntent."""
    import json
    
    # If we have a direct dict result (from Gemini), use it
    if gemini_result and isinstance(gemini_result, dict):
        intent_type = gemini_result.get("intent", "conversational")
        confidence = float(gemini_result.get("confidence", 0.8))
        reasoning = gemini_result.get("reasoning", "Classified by Gemini")
    else:
        # Parse text response (from Anthropic)
        try:
            # Handle potential markdown code blocks
            if "```" in text:
                start = text.find("{")
                end = text.rfind("}") + 1
                text = text[start:end]
            
            data = json.loads(text)
            intent_type = data.get("intent", "conversational")
            confidence = float(data.get("confidence", 0.8))
            reasoning = data.get("reasoning", "")
            
        except (json.JSONDecodeError, ValueError):
            # Fallback parsing - look for intent type in text
            intent_type = "conversational"
            confidence = 0.6
            reasoning = "Failed to parse JSON response"
            
            for intent in INTENT_PROFILES:
                if intent in text.lower():
                    intent_type = intent
                    confidence = 0.7
                    reasoning = f"Found '{intent}' in response text"
                    break
    
    # Get profile for this intent
    profile = INTENT_PROFILES.get(intent_type, INTENT_PROFILES["conversational"])
    
    # Build result, respecting user selections
    return ClassifiedIntent(
        intent=intent_type,
        tools_needed=profile["tools"],
        include_images=profile["include_images"] and has_selected_images,
        include_history=profile["include_history"],
        include_workspace=profile["include_workspace"] and has_workspace_content,
        confidence=confidence,
        suggested_model=profile["model"],
        reasoning=reasoning,
    )

