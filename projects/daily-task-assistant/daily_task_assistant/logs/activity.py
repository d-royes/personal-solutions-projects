"""Activity logging to Firestore with file fallback."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional
from datetime import datetime, timezone

from ..actions import AssistPlan
from ..firestore import get_firestore_client

DEFAULT_LOG_PATH = Path(__file__).resolve().parents[2] / "activity_log.jsonl"
ACTIVITY_COLLECTION = os.getenv("DTA_ACTIVITY_COLLECTION", "activity_log")
FORCE_FILE_FALLBACK = os.getenv("DTA_ACTIVITY_FORCE_FILE", "0") == "1"

def log_assist_event(
    *,
    plan: AssistPlan,
    account_name: Optional[str],
    message_id: Optional[str],
    anthropic_model: Optional[str],
    environment: str,
    source: str,
) -> None:
    entry: Dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "task_id": plan.task.row_id,
        "task_title": plan.task.title,
        "project": plan.task.project,
        "priority": plan.task.priority,
        "account": account_name,
        "recipient": plan.task.assigned_to,
        "message_id": message_id,
        "anthropic_model": anthropic_model or plan.generator,
        "generator": plan.generator,
        "environment": environment,
        "source": source,
        "labels": plan.labels,
        "automation_triggers": plan.automation_triggers,
    }

    if FORCE_FILE_FALLBACK:
        _write_file(entry)
        return

    try:
        client = get_firestore_client()
        client.collection(ACTIVITY_COLLECTION).add(entry)
    except Exception as exc:  # pragma: no cover - network/auth path
        _write_file(entry)
        print(
            f"[ActivityLog] Firestore write failed, wrote to local log instead: {exc}",
            file=sys.stderr,
        )


def fetch_activity_entries(limit: int = 50) -> list[Dict[str, Any]]:
    """Return recent activity entries (Firestore with file fallback)."""

    if FORCE_FILE_FALLBACK:
        return _read_file_entries(limit)

    try:
        client = get_firestore_client()
        from firebase_admin import firestore as fb_firestore  # type: ignore

        query = (
            client.collection(ACTIVITY_COLLECTION)
            .order_by("ts", direction=fb_firestore.Query.DESCENDING)
            .limit(limit)
        )
        docs = query.stream()
        return [doc.to_dict() for doc in docs]
    except Exception as exc:  # pragma: no cover - network/auth path
        print(
            f"[ActivityLog] Firestore read failed, falling back to local log: {exc}",
            file=sys.stderr,
        )
        return _read_file_entries(limit)


def _write_file(entry: Dict[str, Any]) -> None:
    path = _get_log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry))
        handle.write("\n")


def _get_log_path() -> Path:
    override = os.getenv("DTA_ACTIVITY_LOG")
    if override:
        return Path(override)
    return DEFAULT_LOG_PATH


def _read_file_entries(limit: int) -> list[Dict[str, Any]]:
    path = _get_log_path()
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    entries: list[Dict[str, Any]] = []
    for line in lines[-limit:]:
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return list(reversed(entries))