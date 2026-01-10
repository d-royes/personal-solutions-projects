"""Calendar data types."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Literal, Optional, List


CalendarAttentionType = Literal[
    "vip_meeting",
    "prep_needed",
    "task_conflict",
    "overcommitment",
]
CalendarAttentionStatus = Literal["active", "dismissed", "acted", "expired"]
CalendarActionType = Literal["viewed", "dismissed", "task_linked", "prep_started"]


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(slots=True)
class CalendarInfo:
    id: str
    summary: str
    description: Optional[str] = None
    color_id: Optional[str] = None
    background_color: Optional[str] = None
    foreground_color: Optional[str] = None
    is_primary: bool = False
    access_role: str = "reader"

    @property
    def is_writable(self) -> bool:
        return self.access_role in ("owner", "writer")
