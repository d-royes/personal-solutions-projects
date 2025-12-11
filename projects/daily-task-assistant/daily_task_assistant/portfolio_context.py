"""Portfolio context builder for global DATA engagement.

This module builds aggregated portfolio statistics using the existing
multi-sheet support in SmartsheetClient.

Perspective Mapping:
- personal: sources=["personal"], exclude church projects
- church: sources=["personal"], only church projects  
- work: sources=["work"]
- holistic: sources=["personal", "work"]
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from .smartsheet_client import SmartsheetClient
from .tasks import TaskDetail


PERSPECTIVE_DESCRIPTIONS = {
    "personal": "Home, family, and personal projects",
    "church": "Ministry and church leadership responsibilities",
    "work": "Professional responsibilities from work Smartsheet",
    "holistic": "Complete view across all life domains",
}

# Explicit project filters per the plan - Personal has specific projects, 
# Church is identified by "Church Tasks" project
PERSONAL_PROJECTS = {
    "around the house",
    "family time",
    "shopping",
    "sm. projects & tasks",
}

CHURCH_PROJECTS = {
    "church tasks",
}


def get_perspective_description(perspective: str) -> str:
    """Get description for a perspective."""
    return PERSPECTIVE_DESCRIPTIONS.get(perspective, "Tasks from selected perspective")


@dataclass(slots=True)
class PortfolioContext:
    """Aggregated portfolio statistics for a perspective."""
    
    perspective: str
    total_open: int = 0
    overdue: int = 0
    due_today: int = 0
    due_this_week: int = 0
    by_priority: Dict[str, int] = field(default_factory=dict)
    by_project: Dict[str, int] = field(default_factory=dict)
    by_due_date: Dict[str, int] = field(default_factory=dict)
    domain_breakdown: Dict[str, int] = field(default_factory=dict)
    conflicts: List[str] = field(default_factory=list)
    task_summaries: List[Dict[str, Any]] = field(default_factory=list)
    
    # Phase 2 hooks - David Profile integration
    user_profile: Optional[Dict[str, Any]] = None


def build_portfolio_context(
    client: SmartsheetClient,
    perspective: str = "personal",
) -> PortfolioContext:
    """Build portfolio context using existing multi-sheet support.
    
    Args:
        client: SmartsheetClient instance (already has multi-sheet config loaded)
        perspective: One of "personal", "church", "work", "holistic"
    
    Returns:
        PortfolioContext with aggregated statistics
    """
    # Determine which sources to fetch based on perspective
    if perspective == "work":
        sources = ["work"]
    elif perspective == "holistic":
        sources = ["personal", "work"]
    else:  # personal or church - both come from personal sheet
        sources = ["personal"]
    
    # Fetch tasks using existing multi-sheet support
    # The source field on each task tells us which sheet it came from
    try:
        all_tasks = client.list_tasks(sources=sources, fallback_to_stub=False)
    except Exception:
        all_tasks = []
    
    # Filter to open tasks only
    open_tasks = [t for t in all_tasks if _is_task_open(t)]
    
    # Apply perspective-specific filtering for personal/church
    # (work and holistic don't need additional filtering)
    if perspective == "personal":
        # Use explicit project list per the plan
        open_tasks = [t for t in open_tasks if _is_personal_task(t)]
    elif perspective == "church":
        open_tasks = [t for t in open_tasks if _is_church_task(t)]
    
    # Build aggregations
    return _aggregate_portfolio(perspective, open_tasks)


def _is_task_open(task: TaskDetail) -> bool:
    """Check if task is open (not completed/cancelled/delegated)."""
    status_lower = (task.status or "").lower()
    return status_lower not in ("completed", "cancelled", "delegated")


def _is_church_task(task: TaskDetail) -> bool:
    """Check if task is a church task based on project name."""
    project = (task.project or "").lower()
    return project in CHURCH_PROJECTS or "church" in project


def _is_personal_task(task: TaskDetail) -> bool:
    """Check if task belongs to Personal perspective based on explicit project list."""
    project = (task.project or "").lower()
    return project in PERSONAL_PROJECTS


def _get_task_domain(task: TaskDetail) -> str:
    """Determine which domain a task belongs to.
    
    This matches the frontend deriveDomain() logic in TaskList.tsx.
    """
    # Work tasks from work sheet
    if task.source == "work":
        return "Work"
    
    # Church tasks from personal sheet
    if _is_church_task(task):
        return "Church"
    
    # Everything else is personal
    return "Personal"


def _aggregate_portfolio(
    perspective: str,
    tasks: List[TaskDetail],
) -> PortfolioContext:
    """Aggregate task data into portfolio statistics."""
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = now.replace(hour=23, minute=59, second=59, microsecond=999999)
    week_end = today_start + timedelta(days=7)
    
    ctx = PortfolioContext(perspective=perspective)
    ctx.total_open = len(tasks)
    
    # Track for conflict detection in holistic mode
    high_priority_by_domain: Dict[str, List[str]] = {}
    same_day_tasks: Dict[str, List[tuple]] = {}  # date -> [(domain, title)]
    
    for task in tasks:
        # Ensure due date is timezone-aware for comparison
        due = task.due
        if due.tzinfo is None:
            due = due.replace(tzinfo=timezone.utc)
        
        # Due date buckets
        if due < now:
            ctx.overdue += 1
            ctx.by_due_date["overdue"] = ctx.by_due_date.get("overdue", 0) + 1
        elif due <= today_end:
            ctx.due_today += 1
            ctx.by_due_date["today"] = ctx.by_due_date.get("today", 0) + 1
        elif due <= week_end:
            ctx.due_this_week += 1
            ctx.by_due_date["this_week"] = ctx.by_due_date.get("this_week", 0) + 1
        else:
            ctx.by_due_date["later"] = ctx.by_due_date.get("later", 0) + 1
        
        # Priority distribution (normalize priority labels)
        priority = _normalize_priority(task.priority)
        ctx.by_priority[priority] = ctx.by_priority.get(priority, 0) + 1
        
        # Project distribution
        project = task.project or "Uncategorized"
        ctx.by_project[project] = ctx.by_project.get(project, 0) + 1
        
        # Domain distribution
        domain = _get_task_domain(task)
        ctx.domain_breakdown[domain] = ctx.domain_breakdown.get(domain, 0) + 1
        
        # Track for conflict detection
        if perspective == "holistic":
            if priority in ("Critical", "Urgent"):
                if domain not in high_priority_by_domain:
                    high_priority_by_domain[domain] = []
                high_priority_by_domain[domain].append(task.title[:50])
            
            # Track same-day tasks across domains
            due_date_key = due.strftime("%Y-%m-%d")
            if due_date_key not in same_day_tasks:
                same_day_tasks[due_date_key] = []
            same_day_tasks[due_date_key].append((domain, task.title[:30]))
        
        # Task summaries (limited for LLM context)
        if len(ctx.task_summaries) < 50:
            ctx.task_summaries.append({
                "row_id": task.row_id,
                "title": task.title,
                "project": task.project,
                "priority": priority,
                "status": task.status,
                "due": due.isoformat(),
                "source": task.source,
                "domain": domain,
                "number": task.number,  # # field for sequencing
                "estimated_hours": task.estimated_hours,
            })
    
    # Detect conflicts for holistic mode
    if perspective == "holistic":
        ctx.conflicts = _detect_conflicts(high_priority_by_domain, same_day_tasks)
    
    return ctx


def _normalize_priority(priority: Optional[str]) -> str:
    """Normalize priority labels between personal and work sheets.
    
    Personal sheet: Critical, Urgent, Important, Standard, Low
    Work sheet: 5-Critical, 4-Urgent, 3-Important, 2-Standard, 1-Low
    """
    if not priority:
        return "Unknown"
    
    # Map numbered priorities to standard labels
    priority_map = {
        "5-critical": "Critical",
        "4-urgent": "Urgent",
        "3-important": "Important",
        "2-standard": "Standard",
        "1-low": "Low",
    }
    
    normalized = priority_map.get(priority.lower(), priority)
    return normalized


def _detect_conflicts(
    high_priority_by_domain: Dict[str, List[str]],
    same_day_tasks: Dict[str, List[tuple]],
) -> List[str]:
    """Detect cross-domain conflicts for holistic view."""
    conflicts = []
    
    # Check for competing high-priority items across domains
    domains_with_urgent = [d for d, tasks in high_priority_by_domain.items() if tasks]
    if len(domains_with_urgent) > 1:
        domain_list = ", ".join(domains_with_urgent)
        conflicts.append(f"Competing urgent tasks in {domain_list}")
    
    # Check for overloaded days (3+ tasks from different domains)
    for date_key, tasks in same_day_tasks.items():
        domains_on_day = set(t[0] for t in tasks)
        if len(domains_on_day) >= 2 and len(tasks) >= 3:
            conflicts.append(f"Heavy workload on {date_key} across {', '.join(domains_on_day)}")
    
    return conflicts[:5]  # Limit to top 5 conflicts
