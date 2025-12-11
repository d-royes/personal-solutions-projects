"""Trust event tracking for earned autonomy.

Records user responses to DATA's suggestions to track the trust gradient
and inform future autonomy expansion.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# File-based storage for development
TRUST_LOG_DIR = Path(__file__).parent.parent.parent / "trust_log"


@dataclass(slots=True)
class TrustEvent:
    """A single trust-related interaction."""
    
    timestamp: str
    scope: str  # "task" or "portfolio"
    perspective: str  # Which domain context
    suggestion_type: str  # "insight", "action", "priority", etc.
    suggestion: str
    response: Optional[str] = None  # "accepted", "rejected", "modified", None
    user: str = ""


def log_trust_event(
    scope: str,
    perspective: str,
    suggestion_type: str,
    suggestion: str,
    response: Optional[str] = None,
    user: str = "",
) -> TrustEvent:
    """Log a trust event for later analysis.
    
    Args:
        scope: "task" or "portfolio"
        perspective: The domain context (personal, church, work, holistic)
        suggestion_type: Category of suggestion (insight, action, priority, etc.)
        suggestion: The actual suggestion made
        response: User's response (accepted, rejected, modified, or None if pending)
        user: User email if available
    
    Returns:
        The created TrustEvent
    """
    event = TrustEvent(
        timestamp=datetime.now(timezone.utc).isoformat(),
        scope=scope,
        perspective=perspective,
        suggestion_type=suggestion_type,
        suggestion=suggestion,
        response=response,
        user=user,
    )
    
    # Only persist if file-based storage is enabled (development mode)
    if os.getenv("DTA_TRUST_FORCE_FILE", "").strip():
        _persist_event(event)
    
    return event


def get_trust_summary(perspective: Optional[str] = None, days: int = 30) -> Dict[str, Any]:
    """Get aggregated trust statistics.
    
    Args:
        perspective: Filter to specific perspective (or None for all)
        days: Number of days to include in summary
    
    Returns:
        Dict with acceptance rates, common rejections, etc.
    """
    events = _load_recent_events(days)
    
    if perspective:
        events = [e for e in events if e.perspective == perspective]
    
    if not events:
        return {
            "total": 0,
            "accepted": 0,
            "rejected": 0,
            "acceptance_rate": None,
            "by_type": {},
        }
    
    accepted = sum(1 for e in events if e.response == "accepted")
    rejected = sum(1 for e in events if e.response == "rejected")
    total_with_response = accepted + rejected
    
    # Group by suggestion type
    by_type: Dict[str, Dict[str, int]] = {}
    for event in events:
        if event.suggestion_type not in by_type:
            by_type[event.suggestion_type] = {"accepted": 0, "rejected": 0, "pending": 0}
        if event.response == "accepted":
            by_type[event.suggestion_type]["accepted"] += 1
        elif event.response == "rejected":
            by_type[event.suggestion_type]["rejected"] += 1
        else:
            by_type[event.suggestion_type]["pending"] += 1
    
    return {
        "total": len(events),
        "accepted": accepted,
        "rejected": rejected,
        "acceptance_rate": accepted / total_with_response if total_with_response > 0 else None,
        "by_type": by_type,
    }


def _persist_event(event: TrustEvent) -> None:
    """Persist event to file-based storage."""
    TRUST_LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_file = TRUST_LOG_DIR / "events.jsonl"
    
    with log_file.open("a", encoding="utf-8") as f:
        f.write(json.dumps(asdict(event)) + "\n")


def _load_recent_events(days: int = 30) -> List[TrustEvent]:
    """Load recent events from file storage."""
    log_file = TRUST_LOG_DIR / "events.jsonl"
    
    if not log_file.exists():
        return []
    
    events: List[TrustEvent] = []
    cutoff = datetime.now(timezone.utc).timestamp() - (days * 24 * 60 * 60)
    
    with log_file.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                # Check timestamp
                ts = datetime.fromisoformat(data["timestamp"].replace("Z", "+00:00"))
                if ts.timestamp() >= cutoff:
                    events.append(TrustEvent(**data))
            except (json.JSONDecodeError, KeyError, ValueError):
                continue
    
    return events
