"""Anthropic client wrappers for Daily Task Assistant."""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
from typing import Dict, List, Optional

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

DEFAULT_MODEL = "claude-3-opus-20240229"
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
4. email_draft: short email or message the assistant could send.

Rules:
- JSON only. Keys: summary, next_steps, efficiency_tips, email_draft.
- Steps and tips must be strings without numbering prefixes.
- Reference provided context; do not invent data.
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
    email_draft: str
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
        email_draft=_coerce_string(data.get("email_draft")),
        raw=text,
    )


def _extract_text(response) -> str:
    chunks = []
    for block in getattr(response, "content", []):
        if getattr(block, "type", None) == "text":
            chunks.append(getattr(block, "text", ""))
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

