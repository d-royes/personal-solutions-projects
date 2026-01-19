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
    struck: bool = False
    struck_at: Optional[str] = None


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
    """Render a human-readable summary suitable for chat bubbles.
    
    Includes new fields from Task Planning Skill when present.
    """
    sections = [plan.summary, ""]
    
    # Add complexity indicator
    if hasattr(plan, 'complexity') and plan.complexity and plan.complexity != "simple":
        sections.append(f"**Complexity:** {plan.complexity}")
        sections.append("")
    
    # Add crux for medium/complex tasks
    if hasattr(plan, 'crux') and plan.crux:
        sections.append("**The Crux:**")
        sections.append(plan.crux)
        sections.append("")
    
    # Add approach options for complex tasks
    if hasattr(plan, 'approach_options') and plan.approach_options:
        sections.append("**Approach Options:**")
        for opt in plan.approach_options:
            opt_name = opt.get('option', 'Option')
            sections.append(f"- {opt_name}")
        sections.append("")
    
    # Add recommended path for complex tasks
    if hasattr(plan, 'recommended_path') and plan.recommended_path:
        sections.append("**Recommended Path:**")
        sections.append(plan.recommended_path)
        sections.append("")
    
    # Next steps (always present)
    next_steps = "\n".join(f"- {step}" for step in plan.next_steps)
    sections.append("**Next steps:**")
    sections.append(next_steps or "- No specific steps provided.")
    sections.append("")
    
    # Efficiency tips
    efficiency = "\n".join(f"- {tip}" for tip in plan.efficiency_tips)
    sections.append("**Efficiency tips:**")
    sections.append(efficiency or "- No efficiency tips right now.")
    sections.append("")
    
    # Open questions for complex tasks
    if hasattr(plan, 'open_questions') and plan.open_questions:
        questions = "\n".join(f"- {q}" for q in plan.open_questions)
        sections.append("**Open Questions:**")
        sections.append(questions)
        sections.append("")
    
    # Done when for medium/complex tasks
    if hasattr(plan, 'done_when') and plan.done_when:
        sections.append("**Done When:**")
        sections.append(plan.done_when)
        sections.append("")
    
    actions = ", ".join(plan.suggested_actions) if plan.suggested_actions else "none"
    sections.append(f"**Available actions:** {actions}")
    
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


def strike_message(task_id: str, message_ts: str) -> bool:
    """Mark a message as struck by its timestamp.
    
    Returns True if the message was found and struck, False otherwise.
    """
    if _force_file_fallback():
        return _strike_file_message(task_id, message_ts, strike=True)
    
    try:
        client = get_firestore_client()
        collection = (
            client.collection(_conversation_collection())
            .document(task_id)
            .collection("messages")
        )
        # Find the message by timestamp
        query = collection.where("ts", "==", message_ts).limit(1)
        docs = list(query.stream())
        if docs:
            docs[0].reference.update({
                "struck": True,
                "struck_at": _now(),
            })
            return True
        return False
    except Exception as exc:
        print(f"[Conversation] Firestore strike failed, falling back to file: {exc}")
        return _strike_file_message(task_id, message_ts, strike=True)


def unstrike_message(task_id: str, message_ts: str) -> bool:
    """Remove the struck flag from a message.
    
    Returns True if the message was found and unstruck, False otherwise.
    """
    if _force_file_fallback():
        return _strike_file_message(task_id, message_ts, strike=False)
    
    try:
        client = get_firestore_client()
        collection = (
            client.collection(_conversation_collection())
            .document(task_id)
            .collection("messages")
        )
        # Find the message by timestamp
        query = collection.where("ts", "==", message_ts).limit(1)
        docs = list(query.stream())
        if docs:
            docs[0].reference.update({
                "struck": False,
                "struck_at": None,
            })
            return True
        return False
    except Exception as exc:
        print(f"[Conversation] Firestore unstrike failed, falling back to file: {exc}")
        return _strike_file_message(task_id, message_ts, strike=False)


def fetch_conversation_for_llm(task_id: str, limit: int = 50) -> List[ConversationMessage]:
    """Return conversation history excluding struck messages (for LLM context)."""
    messages = fetch_conversation(task_id, limit=limit)
    return [msg for msg in messages if not msg.struck]


def delete_message(task_id: str, message_ts: str) -> bool:
    """Permanently delete a message by its timestamp.
    
    WARNING: This is irreversible. Use strike_message for soft-hiding.
    Returns True if the message was found and deleted, False otherwise.
    """
    if _force_file_fallback():
        return _delete_file_message(task_id, message_ts)
    
    try:
        client = get_firestore_client()
        collection = (
            client.collection(_conversation_collection())
            .document(task_id)
            .collection("messages")
        )
        docs = list(
            collection.where("ts", "==", message_ts).limit(1).stream()
        )
        if docs:
            docs[0].reference.delete()
            return True
        return False
    except Exception as exc:
        print(f"[Conversation] Firestore delete failed, falling back to file: {exc}")
        return _delete_file_message(task_id, message_ts)


def _delete_file_message(task_id: str, message_ts: str) -> bool:
    """Permanently delete a message from the local file."""
    path = _conversation_file(task_id)
    if not path.exists():
        return False
    
    lines = path.read_text().strip().split("\n")
    updated_lines = []
    found = False
    
    for line in lines:
        try:
            data = json.loads(line)
            if data.get("ts") == message_ts:
                found = True
                continue  # Skip this line (delete it)
            updated_lines.append(line)
        except json.JSONDecodeError:
            updated_lines.append(line)
    
    if found:
        path.write_text("\n".join(updated_lines) + "\n" if updated_lines else "")
    
    return found


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
    """Serialize plan for Firestore storage.
    
    Includes all fields from Task Planning Skill integration.
    """
    snapshot = {
        "summary": plan.summary,
        "next_steps": plan.next_steps,
        "efficiency_tips": plan.efficiency_tips,
        "suggested_actions": plan.suggested_actions,
        "labels": plan.labels,
        # New fields from Task Planning Skill
        "complexity": plan.complexity,
    }
    # Only include optional fields if they have values (keeps Firestore docs lean)
    if plan.crux:
        snapshot["crux"] = plan.crux
    if plan.approach_options:
        snapshot["approach_options"] = plan.approach_options
    if plan.recommended_path:
        snapshot["recommended_path"] = plan.recommended_path
    if plan.open_questions:
        snapshot["open_questions"] = plan.open_questions
    if plan.done_when:
        snapshot["done_when"] = plan.done_when
    return snapshot


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


def _strike_file_message(task_id: str, message_ts: str, strike: bool) -> bool:
    """Update the struck status of a message in the local file.
    
    Rewrites the entire file with the updated message.
    """
    path = _conversation_file(task_id)
    if not path.exists():
        return False
    
    lines = path.read_text(encoding="utf-8").splitlines()
    updated_lines = []
    found = False
    
    for line in lines:
        try:
            data = json.loads(line)
            if data.get("ts") == message_ts:
                data["struck"] = strike
                data["struck_at"] = _now() if strike else None
                found = True
            updated_lines.append(json.dumps(data))
        except json.JSONDecodeError:
            updated_lines.append(line)
    
    if found:
        path.write_text("\n".join(updated_lines) + "\n", encoding="utf-8")
    
    return found

