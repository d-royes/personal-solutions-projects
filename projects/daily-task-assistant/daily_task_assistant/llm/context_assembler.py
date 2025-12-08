"""Context assembler for DATA chat.

Orchestrates building the minimal effective context for each LLM call
based on classified intent.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from urllib import request as urlrequest

from ..tasks import AttachmentDetail, TaskDetail
from .intent_classifier import ClassifiedIntent
from .prompts import assemble_system_prompt, get_tools_for_intent


@dataclass(slots=True)
class ContextBundle:
    """Bundle of assembled context for an LLM call.
    
    Attributes:
        system_prompt: The assembled system prompt
        messages: The message history to send
        tools: Tool definitions to include
        estimated_tokens: Rough estimate of input tokens
    """
    system_prompt: str
    messages: List[Dict[str, Any]]
    tools: List[dict]
    estimated_tokens: int = 0


def assemble_context(
    intent: ClassifiedIntent,
    task: TaskDetail,
    user_message: str,
    history: Optional[List[Dict[str, str]]] = None,
    selected_images: Optional[List[AttachmentDetail]] = None,
    workspace_content: Optional[str] = None,
) -> ContextBundle:
    """Assemble the minimal effective context for a chat request.
    
    Args:
        intent: Classified intent with context requirements
        task: The current task
        user_message: The user's message
        history: Conversation history (may be filtered/summarized)
        selected_images: Images the user selected to include
        workspace_content: Checked workspace content to include
    
    Returns:
        ContextBundle ready for LLM call
    """
    # 1. Build system prompt based on intent
    system_prompt = assemble_system_prompt(
        intent=intent.intent,
        include_task_updates=(intent.intent == "action"),
        include_vision=(intent.intent == "visual" and intent.include_images),
        include_email=(intent.intent == "email"),
        include_research=(intent.intent == "research"),
        include_conversational=(intent.intent == "conversational"),
    )
    
    # 2. Get tools for this intent
    tools = get_tools_for_intent(intent.intent, intent.tools_needed)
    
    # 3. Build task context
    priority_format = "numbered (5-Critical, etc.)" if task.source == "work" else "simple (Critical, etc.)"
    task_context = f"""Current Task:
- Title: {task.title}
- Status: {task.status}
- Priority: {task.priority}
- Due: {task.due.strftime("%Y-%m-%d")}
- Project: {task.project}
- Source: {task.source} (use {priority_format} priorities)
- Notes: {task.notes or "None"}"""

    # 4. Build messages
    messages: List[Dict[str, Any]] = []
    
    # Build initial context content
    context_parts: List[Dict[str, Any]] = []
    
    # Add images first if visual intent with selected images
    if intent.include_images and selected_images:
        for att in selected_images:
            image_data = _download_and_encode_image(att.download_url)
            if image_data:
                context_parts.append({
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": att.mime_type,
                        "data": image_data,
                    }
                })
    
    # Add task context
    context_parts.append({"type": "text", "text": task_context})
    
    # Add workspace content if included
    if intent.include_workspace and workspace_content:
        context_parts.append({
            "type": "text", 
            "text": f"\n---\nWorkspace Notes:\n{workspace_content}"
        })
    
    # Task context as priming
    messages.append({"role": "user", "content": context_parts})
    messages.append({
        "role": "assistant",
        "content": [{"type": "text", "text": "Ready to help. What would you like to do?"}]
    })
    
    # 5. Add history based on intent
    if intent.include_history and history:
        processed_history = _prepare_history(history, intent)
        for msg in processed_history:
            messages.append({
                "role": msg["role"],
                "content": [{"type": "text", "text": msg["content"]}]
            })
    
    # 6. Add current user message
    messages.append({
        "role": "user",
        "content": [{"type": "text", "text": user_message}]
    })
    
    # 7. Estimate tokens (rough)
    estimated_tokens = _estimate_tokens(system_prompt, messages)
    
    return ContextBundle(
        system_prompt=system_prompt,
        messages=messages,
        tools=tools,
        estimated_tokens=estimated_tokens,
    )


def _prepare_history(
    history: List[Dict[str, str]],
    intent: ClassifiedIntent,
) -> List[Dict[str, str]]:
    """Prepare conversation history, potentially summarizing older turns.
    
    Args:
        history: Full conversation history
        intent: Classified intent (affects how much history to include)
    
    Returns:
        Processed history list
    """
    if not history:
        return []
    
    # For action intents, minimal history needed
    if intent.intent == "action":
        # Just the last 2 turns for context
        return history[-2:] if len(history) > 2 else history
    
    # For other intents, keep recent history full
    max_full_turns = 6
    
    if len(history) <= max_full_turns:
        return history
    
    # Summarize older history
    older = history[:-max_full_turns]
    recent = history[-max_full_turns:]
    
    # Create a summary of older turns
    summary = _summarize_history(older)
    
    # Prepend summary as a system-like message
    return [{"role": "user", "content": f"[Previous context: {summary}]"}] + recent


def _summarize_history(history: List[Dict[str, str]]) -> str:
    """Create a brief summary of conversation history.
    
    This is a simple extractive summary - for production, could use LLM.
    """
    if not history:
        return "No prior context."
    
    topics = []
    for msg in history:
        content = msg.get("content", "")[:100]  # First 100 chars
        if msg["role"] == "user":
            topics.append(f"User asked about: {content}...")
        else:
            topics.append(f"DATA discussed: {content}...")
    
    # Limit to last few topics
    topics = topics[-4:]
    return " ".join(topics)


def _download_and_encode_image(url: str, max_size_bytes: int = 3_500_000) -> Optional[str]:
    """Download and base64 encode an image.
    
    Resizes if too large for Claude's limits.
    Note: max_size_bytes is for RAW data. Base64 adds ~33% overhead,
    so 3.5MB raw becomes ~4.7MB encoded (under 5MB limit).
    """
    try:
        with urlrequest.urlopen(url, timeout=15) as response:
            data = response.read()
            
            if len(data) > max_size_bytes:
                data = _resize_image(data, max_size_bytes)
                if data is None:
                    return None
            
            return base64.standard_b64encode(data).decode('utf-8')
    except Exception:
        return None


def _resize_image(image_data: bytes, max_size_bytes: int) -> Optional[bytes]:
    """Resize image to fit within size limit."""
    try:
        from PIL import Image
        import io
        
        img = Image.open(io.BytesIO(image_data))
        
        if img.mode in ('RGBA', 'P'):
            img = img.convert('RGB')
        
        quality = 85
        scale = 1.0
        
        for _ in range(10):
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
            
            if quality > 50:
                quality -= 10
            else:
                scale *= 0.8
        
        return None
    except ImportError:
        return None
    except Exception:
        return None


def _estimate_tokens(system_prompt: str, messages: List[Dict[str, Any]]) -> int:
    """Rough token estimation (4 chars per token average)."""
    total_chars = len(system_prompt)
    
    for msg in messages:
        content = msg.get("content", [])
        if isinstance(content, str):
            total_chars += len(content)
        elif isinstance(content, list):
            for part in content:
                if part.get("type") == "text":
                    total_chars += len(part.get("text", ""))
                elif part.get("type") == "image":
                    # Images are ~1000 tokens base + size
                    total_chars += 4000
    
    return total_chars // 4

