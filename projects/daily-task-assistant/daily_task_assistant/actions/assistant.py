"""High-level assistant actions built on top of task details."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..analysis.prioritizer import detect_automation_triggers, score_task
from ..llm import (
    AnthropicError,
    AnthropicNotConfigured,
    AnthropicSuggestion,
    generate_assist_suggestion,
)
from ..tasks import TaskDetail

PROMPT_DIR = Path(__file__).resolve().parents[2] / "prompts"


@dataclass(slots=True)
class AssistPlan:
    """Bundle of AI-generated suggestions for a task."""

    task: TaskDetail
    summary: str
    score: float
    labels: List[str]
    automation_triggers: List[str]
    reasons: List[str]
    next_steps: List[str]
    efficiency_tips: List[str]
    suggested_actions: List[str]
    generator: str = "templates"
    generator_notes: List[str] = field(default_factory=list)
    # New fields from Task Planning Skill
    complexity: str = "simple"  # simple | medium | complex
    crux: Optional[str] = None
    approach_options: Optional[List[Dict[str, Any]]] = None
    recommended_path: Optional[str] = None
    open_questions: Optional[List[str]] = None
    done_when: Optional[str] = None


def plan_assist(
    task: TaskDetail,
    *,
    model_override: str | None = None,
    history: list[dict[str, str]] | None = None,
    workspace_context: str | None = None,
) -> AssistPlan:
    """Generate draft actions (next steps, efficiency tips, suggested actions)."""

    ranked = score_task(task)
    next_steps = suggest_next_steps(task)
    efficiency = efficiency_tips(task)
    suggested_actions = _default_actions(task)
    summary = (
        f"{task.priority} task for {task.project}; "
        f"status {task.status.lower()} with due {task.due:%Y-%m-%d}."
    )

    triggers = detect_automation_triggers(task)
    generator = "templates"
    generator_notes: List[str] = []

    # Initialize new fields with defaults
    complexity = "simple"
    crux: Optional[str] = None
    approach_options: Optional[List[Dict[str, Any]]] = None
    recommended_path: Optional[str] = None
    open_questions: Optional[List[str]] = None
    done_when: Optional[str] = None

    llm_suggestion = _maybe_call_llm(
        task,
        generator_notes,
        model_override=model_override,
        history=history,
        workspace_context=workspace_context,
    )
    if llm_suggestion:
        generator = "anthropic"
        summary = llm_suggestion.summary or summary
        if llm_suggestion.next_steps:
            next_steps = llm_suggestion.next_steps
        if llm_suggestion.efficiency_tips:
            efficiency = llm_suggestion.efficiency_tips
        if llm_suggestion.suggested_actions:
            suggested_actions = llm_suggestion.suggested_actions
        # Copy new fields from Task Planning Skill
        complexity = llm_suggestion.complexity or "simple"
        crux = llm_suggestion.crux
        approach_options = llm_suggestion.approach_options
        recommended_path = llm_suggestion.recommended_path
        open_questions = llm_suggestion.open_questions
        done_when = llm_suggestion.done_when

    return AssistPlan(
        task=task,
        summary=summary,
        score=ranked.score,
        labels=list(ranked.labels),
        automation_triggers=list(triggers),
        reasons=list(ranked.reasons),
        next_steps=next_steps,
        efficiency_tips=efficiency,
        suggested_actions=suggested_actions,
        generator=generator,
        generator_notes=generator_notes,
        # New fields from Task Planning Skill
        complexity=complexity,
        crux=crux,
        approach_options=approach_options,
        recommended_path=recommended_path,
        open_questions=open_questions,
        done_when=done_when,
    )


def _default_actions(task: TaskDetail) -> List[str]:
    """Determine default suggested actions based on task context."""
    actions = ["research", "review"]
    
    # Only suggest email if there's a clear external contact in the notes
    notes_lower = (task.notes or "").lower()
    if any(indicator in notes_lower for indicator in ["@", "email", "contact", "reply", "respond"]):
        actions.append("draft_email")
    
    return actions


def _maybe_call_llm(
    task: TaskDetail,
    notes: List[str],
    *,
    model_override: str | None = None,
    history: list[dict[str, str]] | None = None,
    workspace_context: str | None = None,
) -> AnthropicSuggestion | None:
    try:
        return generate_assist_suggestion(
            task,
            model_override=model_override,
            history=history,
            workspace_context=workspace_context,
        )
    except AnthropicNotConfigured as exc:
        notes.append(str(exc))
    except AnthropicError as exc:
        notes.append(str(exc))
    except Exception as exc:  # pragma: no cover - safety
        notes.append(f"Unexpected LLM error: {exc}")
    return None


def draft_email(task: TaskDetail) -> str:
    template = _load_template("email.txt")
    recipient = task.assigned_to or "team"
    context = {
        "title": task.title,
        "due": task.due.strftime("%Y-%m-%d"),
        "next_step": task.next_step,
        "project": task.project,
        "priority": task.priority.lower(),
        "recipient": recipient,
    }
    return template.format(**context)


def suggest_next_steps(task: TaskDetail) -> List[str]:
    template = _load_template("next_steps.txt")
    base = template.format(
        title=task.title,
        next_step=task.next_step,
        project=task.project,
        status=task.status.lower(),
    ).strip()

    steps = [line.strip("- ").strip() for line in base.splitlines() if line.strip()]
    return steps


def efficiency_tips(task: TaskDetail) -> List[str]:
    template = _load_template("efficiency.txt")
    notes = task.notes or "No notes provided"
    payload = template.format(
        project=task.project,
        notes=notes,
        estimated_hours=_format_hours(task.estimated_hours),
    )
    tips = [line.strip("- ").strip() for line in payload.splitlines() if line.strip()]
    return tips


def _format_hours(value: float | None) -> str:
    if value is None:
        return "unknown"
    if value.is_integer():
        return f"{int(value)}h"
    return f"{value:.1f}h"


def _load_template(name: str) -> str:
    path = PROMPT_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"Prompt template '{name}' not found at {path}")
    return path.read_text(encoding="utf-8")


