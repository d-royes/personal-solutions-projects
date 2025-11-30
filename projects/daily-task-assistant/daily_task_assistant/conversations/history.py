"""Persistent conversation history storage."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from ..actions import AssistPlan
from ..firestore import get_firestore_client

def _conversation_collection() -> str:
    return os.getenv("DTA_CONVERSATION_COLLECTION", "conversations")


def _force_file_fallback() -> bool:
    return os.getenv("DTA_CONVERSATION_FORCE_FILE", "0") == "1"


def _conversation_dir() -> Path:
    return Path(
        os.getenv(
            "DTA_CONVERSATION_DIR",
            Path(__file__).resolve().parents[2] / "conversation_log",
        )
    )


@dataclass
class ConversationMessage:
    role: Literal["user", "assistant"]
    content: str
    ts: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    plan: Optional[Dict[str, Any]] = None


def log_user_message(
    task_id: str,
    *,
    content: str,
    user_email: Optional[str],
    metadata: Optional[Dict[str, Any]] = None,
) -> ConversationMessage:
    """Persist a user-provided instruction."""

    payload = ConversationMessage(
        role="user",
        content=content.strip(),
        ts=_now(),
        metadata={"user": user_email or "unknown", **(metadata or {})},
    )
    _append_message(task_id, payload)
    return payload


def log_assistant_message(
    task_id: str,
    *,
    content: str,
    plan: Optional[AssistPlan] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> ConversationMessage:
    """Persist an assistant response, optionally including a snapshot of the plan."""

    payload = ConversationMessage(
        role="assistant",
        content=content.strip(),
        ts=_now(),
        metadata=metadata or {},
        plan=_plan_snapshot(plan) if plan else None,
    )
    _append_message(task_id, payload)
    return payload


def fetch_conversation(task_id: str, limit: int = 50) -> List[ConversationMessage]:
    """Return stored conversation history for a task, ordered oldest -> newest."""

    if _force_file_fallback():
        return _read_file_messages(task_id, limit)

    try:
        client = get_firestore_client()
        from firebase_admin import firestore as fb_firestore  # type: ignore

        query = (
            client.collection(_conversation_collection())
            .document(task_id)
            .collection("messages")
            .order_by("ts", direction=fb_firestore.Query.ASCENDING)
            .limit(limit)
        )
        docs = query.stream()
        messages = [ConversationMessage(**doc.to_dict()) for doc in docs]
        return messages
    except Exception:
        return _read_file_messages(task_id, limit)


def clear_conversation(task_id: str) -> None:
    """Delete stored conversation history for a task."""

    if _force_file_fallback():
        path = _conversation_file(task_id)
        if path.exists():
            path.unlink()
        return

    try:
        client = get_firestore_client()
        collection = (
            client.collection(_conversation_collection())
            .document(task_id)
            .collection("messages")
        )
        docs = collection.stream()
        for doc in docs:
            doc.reference.delete()
    except Exception:
        path = _conversation_file(task_id)
        if path.exists():
            path.unlink()


def build_plan_summary(plan: AssistPlan) -> str:
    """Render a human-readable summary suitable for chat bubbles."""

    next_steps = "\n".join(f"- {step}" for step in plan.next_steps)
    efficiency = "\n".join(f"- {tip}" for tip in plan.efficiency_tips)
    actions = ", ".join(plan.suggested_actions) if plan.suggested_actions else "none"
    sections = [
        plan.summary,
        "",
        "Next steps:",
        next_steps or "- No specific steps provided.",
        "",
        "Efficiency tips:",
        efficiency or "- No efficiency tips right now.",
        "",
        f"Available actions: {actions}",
    ]
    return "\n".join(section for section in sections if section is not None).strip()


def get_latest_plan(task_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve the most recent plan from conversation history.
    
    Returns the plan snapshot from the most recent assistant message that has one,
    or None if no plan has been generated yet.
    """
    messages = fetch_conversation(task_id, limit=100)
    
    # Search from newest to oldest for a message with a plan
    for msg in reversed(messages):
        if msg.role == "assistant" and msg.plan:
            # Add generation timestamp
            return {
                **msg.plan,
                "generatedAt": msg.ts,
            }
    
    return None


# Internal helpers ---------------------------------------------------------


def _append_message(task_id: str, message: ConversationMessage) -> None:
    if _force_file_fallback():
        _write_file(task_id, message)
        return

    try:
        client = get_firestore_client()
        client.collection(_conversation_collection()).document(task_id).collection(
            "messages"
        ).add(asdict(message))
    except Exception:
        _write_file(task_id, message)


def _plan_snapshot(plan: AssistPlan) -> Dict[str, Any]:
    return {
        "summary": plan.summary,
        "next_steps": plan.next_steps,
        "efficiency_tips": plan.efficiency_tips,
        "suggested_actions": plan.suggested_actions,
        "labels": plan.labels,
    }


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _conversation_file(task_id: str) -> Path:
    directory = _conversation_dir()
    directory.mkdir(parents=True, exist_ok=True)
    safe_id = task_id.replace("/", "_")
    return directory / f"{safe_id}.jsonl"


def _write_file(task_id: str, message: ConversationMessage) -> None:
    path = _conversation_file(task_id)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(asdict(message)))
        handle.write("\n")


def _read_file_messages(task_id: str, limit: int) -> List[ConversationMessage]:
    path = _conversation_file(task_id)
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    messages: List[ConversationMessage] = []
    for line in lines[-limit:]:
        try:
            data = json.loads(line)
            messages.append(ConversationMessage(**data))
        except json.JSONDecodeError:
            continue
    return messages

