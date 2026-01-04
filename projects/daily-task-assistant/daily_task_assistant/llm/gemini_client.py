"""Gemini LLM client for DATA.

Provides access to Google's Gemini models for fast classification and general queries.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

# Load environment variables
load_dotenv()


@dataclass(slots=True)
class GeminiConfig:
    """Configuration for Gemini API."""
    api_key: str
    model: str = "gemini-2.5-pro"  # High quality for thoughtful responses
    
# Available Gemini models:
# - gemini-2.5-pro: Best quality, complex reasoning (recommended for chat)
# - gemini-2.5-flash: Balanced speed/quality
# - gemini-2.5-flash-lite: Fastest, lowest cost
# - gemini-2.0-flash: Previous gen, still good
    

class GeminiError(Exception):
    """Raised when Gemini API call fails."""
    pass


def get_gemini_api_key() -> str:
    """Get Gemini API key from environment."""
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        raise GeminiError("GEMINI_API_KEY not found in environment")
    return key


def build_gemini_client():
    """Build and return a configured Gemini client."""
    try:
        import google.generativeai as genai
    except ImportError:
        raise GeminiError("google-generativeai package not installed")
    
    api_key = get_gemini_api_key()
    genai.configure(api_key=api_key)
    return genai


def chat_with_gemini(
    messages: List[Dict[str, Any]],
    system_prompt: str = "",
    model: str = "gemini-2.0-flash",
    max_tokens: int = 800,
    temperature: float = 0.5,
) -> str:
    """Send a chat request to Gemini.
    
    Args:
        messages: List of message dicts with 'role' and 'content'
        system_prompt: System instructions (Gemini uses system_instruction)
        model: Model name to use
        max_tokens: Maximum output tokens
        temperature: Sampling temperature
    
    Returns:
        Response text from Gemini
    """
    try:
        import google.generativeai as genai
    except ImportError:
        raise GeminiError("google-generativeai package not installed")
    
    api_key = get_gemini_api_key()
    genai.configure(api_key=api_key)
    
    # Configure the model
    generation_config = {
        "temperature": temperature,
        "max_output_tokens": max_tokens,
    }
    
    # Create model with system instruction
    gemini_model = genai.GenerativeModel(
        model_name=model,
        generation_config=generation_config,
        system_instruction=system_prompt if system_prompt else None,
    )
    
    # Convert messages to Gemini format
    # Gemini uses 'user' and 'model' roles, not 'user' and 'assistant'
    gemini_messages = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        
        # Handle content that might be a list (Claude format) or string
        if isinstance(content, list):
            # Extract text from content blocks
            text_parts = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    text_parts.append(block.get("text", ""))
                elif isinstance(block, str):
                    text_parts.append(block)
            content = "\n".join(text_parts)
        
        # Map roles
        gemini_role = "model" if role == "assistant" else "user"
        gemini_messages.append({"role": gemini_role, "parts": [content]})
    
    try:
        # Start chat and send all messages
        chat = gemini_model.start_chat(history=gemini_messages[:-1] if len(gemini_messages) > 1 else [])
        
        # Get the last user message to send
        if gemini_messages:
            last_msg = gemini_messages[-1]
            if last_msg["role"] == "user":
                response = chat.send_message(last_msg["parts"][0])
                return response.text
        
        # If no user message, just return empty
        return ""
        
    except Exception as exc:
        raise GeminiError(f"Gemini API error: {exc}") from exc


def classify_with_gemini(
    message: str,
    task_title: str,
    has_images: bool = False,
    has_workspace: bool = False,
) -> Dict[str, Any]:
    """Use Gemini Flash for fast intent classification.
    
    Uses Flash for classification (speed matters here), Pro for actual responses.
    
    Returns a dict with intent classification results.
    """
    prompt = f"""Classify this user message for a task assistant. Return JSON only.

User message: "{message}"
Task: {task_title}
Has images selected: {"yes" if has_images else "no"}
Has workspace content: {"yes" if has_workspace else "no"}

Classify into ONE intent:
- "action": Update task (mark done, change status/priority/due date)
- "visual": Analyze images/attachments
- "conversational": Discussion, questions, clarification
- "research": Find information, look up, search
- "email": Draft, refine, or send email
- "planning": Planning, organizing, strategizing

Return: {{"intent": "<type>", "confidence": <0.0-1.0>, "reasoning": "<brief>"}}"""

    try:
        response = chat_with_gemini(
            messages=[{"role": "user", "content": prompt}],
            model="gemini-2.5-flash",  # Flash for classification (speed), Pro for responses (quality)
            max_tokens=150,
            temperature=0.0,
        )
        
        # Parse JSON response
        import json
        # Clean up response - extract JSON
        text = response.strip()
        if "```" in text:
            start = text.find("{")
            end = text.rfind("}") + 1
            text = text[start:end]
        
        return json.loads(text)
        
    except Exception as exc:
        # Return default on error
        return {
            "intent": "conversational",
            "confidence": 0.5,
            "reasoning": f"Classification failed: {exc}",
        }


def is_gemini_available() -> bool:
    """Check if Gemini API is available and configured."""
    try:
        get_gemini_api_key()
        import google.generativeai  # noqa
        return True
    except (GeminiError, ImportError):
        return False

