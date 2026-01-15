"""Feedback storage module - Firestore with file fallback."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Literal, Optional, Any
import json
import os
import uuid


@dataclass(slots=True)
class FeedbackEntry:
    """A single feedback entry for a DATA response.

    Extended in Phase 1A (Quality Improvement Strategy) to support:
    - Email context linkage for tracking acceptance rates
    - Analysis method tracking for quality metrics
    - Confidence score capture for threshold calibration
    """

    id: str
    task_id: str
    feedback: Literal["helpful", "needs_work"]
    context: Literal["research", "plan", "chat", "email", "task_update"]
    message_content: str  # The content that was rated
    timestamp: datetime
    user_email: Optional[str] = None
    message_id: Optional[str] = None  # Links to conversation history
    metadata: Dict[str, Any] = field(default_factory=dict)

    # Phase 1A: Email context linkage (Quality Improvement Strategy)
    email_id: Optional[str] = None  # Gmail message ID for email feedback
    email_account: Optional[str] = None  # "church" or "personal"
    suggestion_id: Optional[str] = None  # AttentionRecord or SuggestionRecord ID
    analysis_method: Optional[str] = None  # "haiku", "regex", "vip", "profile_match"
    confidence: Optional[float] = None  # Confidence score at time of feedback
    action_taken: Optional[str] = None  # What user did: "dismissed", "task_created", "replied"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "id": self.id,
            "task_id": self.task_id,
            "feedback": self.feedback,
            "context": self.context,
            "message_content": self.message_content[:500],  # Truncate for storage
            "timestamp": self.timestamp.isoformat(),
            "user_email": self.user_email,
            "message_id": self.message_id,
            "metadata": self.metadata,
            # Phase 1A: Email context fields
            "email_id": self.email_id,
            "email_account": self.email_account,
            "suggestion_id": self.suggestion_id,
            "analysis_method": self.analysis_method,
            "confidence": self.confidence,
            "action_taken": self.action_taken,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FeedbackEntry":
        """Create from dictionary."""
        return cls(
            id=data["id"],
            task_id=data["task_id"],
            feedback=data["feedback"],
            context=data["context"],
            message_content=data["message_content"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            user_email=data.get("user_email"),
            message_id=data.get("message_id"),
            metadata=data.get("metadata", {}),
            # Phase 1A: Email context fields
            email_id=data.get("email_id"),
            email_account=data.get("email_account"),
            suggestion_id=data.get("suggestion_id"),
            analysis_method=data.get("analysis_method"),
            confidence=data.get("confidence"),
            action_taken=data.get("action_taken"),
        )


@dataclass(slots=True)
class FeedbackSummary:
    """Aggregated feedback statistics."""
    
    total_helpful: int
    total_needs_work: int
    by_context: Dict[str, Dict[str, int]]
    recent_issues: List[str]  # Recent "needs_work" message excerpts
    
    @property
    def helpful_rate(self) -> float:
        """Calculate the helpful feedback rate."""
        total = self.total_helpful + self.total_needs_work
        if total == 0:
            return 0.0
        return self.total_helpful / total


def _use_file_storage() -> bool:
    """Check if we should use file-based storage."""
    return os.getenv("DTA_FEEDBACK_FORCE_FILE", "").strip() == "1"


def _get_feedback_dir() -> Path:
    """Get the feedback storage directory."""
    env_dir = os.getenv("DTA_FEEDBACK_DIR", "").strip()
    if env_dir:
        return Path(env_dir)
    return Path(__file__).parent.parent.parent / "feedback_log"


def _get_firestore_client():
    """Get Firestore client, or None if not available."""
    if _use_file_storage():
        return None
    
    try:
        from ..firestore import get_firestore_client
        return get_firestore_client()
    except Exception:
        return None


def log_feedback(
    task_id: str,
    feedback: Literal["helpful", "needs_work"],
    context: Literal["research", "plan", "chat", "email", "task_update"],
    message_content: str,
    *,
    user_email: Optional[str] = None,
    message_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    # Phase 1A: Email context parameters
    email_id: Optional[str] = None,
    email_account: Optional[str] = None,
    suggestion_id: Optional[str] = None,
    analysis_method: Optional[str] = None,
    confidence: Optional[float] = None,
    action_taken: Optional[str] = None,
) -> FeedbackEntry:
    """Log feedback for a DATA response.

    Args:
        task_id: The task this feedback is associated with
        feedback: "helpful" or "needs_work"
        context: What type of output was rated
        message_content: The actual content that was rated
        user_email: Who provided the feedback
        message_id: Optional link to conversation history entry
        metadata: Additional context (e.g., action type, tool used)
        email_id: Gmail message ID (for email feedback)
        email_account: "church" or "personal"
        suggestion_id: AttentionRecord or SuggestionRecord ID
        analysis_method: "haiku", "regex", "vip", "profile_match"
        confidence: Confidence score at time of feedback (0.0-1.0)
        action_taken: What user did: "dismissed", "task_created", "replied"

    Returns:
        The created FeedbackEntry
    """
    entry = FeedbackEntry(
        id=str(uuid.uuid4()),
        task_id=task_id,
        feedback=feedback,
        context=context,
        message_content=message_content,
        timestamp=datetime.now(timezone.utc),
        user_email=user_email,
        message_id=message_id,
        metadata=metadata or {},
        # Phase 1A: Email context fields
        email_id=email_id,
        email_account=email_account,
        suggestion_id=suggestion_id,
        analysis_method=analysis_method,
        confidence=confidence,
        action_taken=action_taken,
    )
    
    db = _get_firestore_client()
    if db is not None:
        try:
            _log_to_firestore(db, entry)
        except Exception as e:
            print(f"[Feedback] Firestore write failed, falling back to local: {e}")
            _log_to_file(entry)
    else:
        _log_to_file(entry)
    
    return entry


def _log_to_firestore(db, entry: FeedbackEntry) -> None:
    """Store feedback in Firestore."""
    collection = db.collection("feedback")
    collection.document(entry.id).set(entry.to_dict())


def _log_to_file(entry: FeedbackEntry) -> None:
    """Store feedback in local JSON file."""
    feedback_dir = _get_feedback_dir()
    feedback_dir.mkdir(parents=True, exist_ok=True)
    
    # Store in a single JSONL file for simplicity
    feedback_file = feedback_dir / "feedback.jsonl"
    
    with feedback_file.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry.to_dict()) + "\n")


def fetch_feedback_for_task(
    task_id: str,
    limit: int = 50,
) -> List[FeedbackEntry]:
    """Fetch all feedback entries for a specific task."""
    db = _get_firestore_client()
    if db is not None:
        return _fetch_from_firestore_by_task(db, task_id, limit)
    return _fetch_from_file_by_task(task_id, limit)


def _fetch_from_firestore_by_task(db, task_id: str, limit: int) -> List[FeedbackEntry]:
    """Fetch feedback from Firestore for a task."""
    collection = db.collection("feedback")
    query = (
        collection
        .where("task_id", "==", task_id)
        .order_by("timestamp", direction="DESCENDING")
        .limit(limit)
    )
    
    entries = []
    for doc in query.stream():
        try:
            entries.append(FeedbackEntry.from_dict(doc.to_dict()))
        except Exception:
            continue
    
    return entries


def _fetch_from_file_by_task(task_id: str, limit: int) -> List[FeedbackEntry]:
    """Fetch feedback from file for a task."""
    feedback_file = _get_feedback_dir() / "feedback.jsonl"
    if not feedback_file.exists():
        return []
    
    entries = []
    with feedback_file.open("r", encoding="utf-8") as f:
        for line in f:
            try:
                data = json.loads(line.strip())
                if data.get("task_id") == task_id:
                    entries.append(FeedbackEntry.from_dict(data))
            except Exception:
                continue
    
    # Sort by timestamp descending and limit
    entries.sort(key=lambda e: e.timestamp, reverse=True)
    return entries[:limit]


def fetch_recent_feedback(limit: int = 100) -> List[FeedbackEntry]:
    """Fetch recent feedback across all tasks."""
    db = _get_firestore_client()
    if db is not None:
        return _fetch_recent_from_firestore(db, limit)
    return _fetch_recent_from_file(limit)


def _fetch_recent_from_firestore(db, limit: int) -> List[FeedbackEntry]:
    """Fetch recent feedback from Firestore."""
    collection = db.collection("feedback")
    query = (
        collection
        .order_by("timestamp", direction="DESCENDING")
        .limit(limit)
    )
    
    entries = []
    for doc in query.stream():
        try:
            entries.append(FeedbackEntry.from_dict(doc.to_dict()))
        except Exception:
            continue
    
    return entries


def _fetch_recent_from_file(limit: int) -> List[FeedbackEntry]:
    """Fetch recent feedback from file."""
    feedback_file = _get_feedback_dir() / "feedback.jsonl"
    if not feedback_file.exists():
        return []
    
    entries = []
    with feedback_file.open("r", encoding="utf-8") as f:
        for line in f:
            try:
                data = json.loads(line.strip())
                entries.append(FeedbackEntry.from_dict(data))
            except Exception:
                continue
    
    # Sort by timestamp descending and limit
    entries.sort(key=lambda e: e.timestamp, reverse=True)
    return entries[:limit]


def fetch_feedback_summary(days: int = 30) -> FeedbackSummary:
    """Get aggregated feedback statistics.
    
    Args:
        days: Number of days to include in summary
    
    Returns:
        FeedbackSummary with counts and patterns
    """
    from datetime import timedelta
    
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    recent = fetch_recent_feedback(limit=500)
    
    # Filter to date range
    filtered = [e for e in recent if e.timestamp >= cutoff]
    
    # Aggregate
    total_helpful = sum(1 for e in filtered if e.feedback == "helpful")
    total_needs_work = sum(1 for e in filtered if e.feedback == "needs_work")
    
    # By context
    by_context: Dict[str, Dict[str, int]] = {}
    for entry in filtered:
        if entry.context not in by_context:
            by_context[entry.context] = {"helpful": 0, "needs_work": 0}
        by_context[entry.context][entry.feedback] += 1
    
    # Recent issues (needs_work excerpts)
    recent_issues = [
        e.message_content[:100] + "..." if len(e.message_content) > 100 else e.message_content
        for e in filtered
        if e.feedback == "needs_work"
    ][:10]
    
    return FeedbackSummary(
        total_helpful=total_helpful,
        total_needs_work=total_needs_work,
        by_context=by_context,
        recent_issues=recent_issues,
    )

