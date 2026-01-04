"""LLM prompts for global DATA engagement.

Contains system prompts and message builders for portfolio analysis.
"""
from __future__ import annotations

from typing import Any, Dict, List

from ..portfolio_context import PortfolioContext


GLOBAL_CHAT_SYSTEM_PROMPT = """You are DATA, David's AI chief of staff. You're analyzing his task portfolio to provide actionable insights.

Your role in portfolio mode:
1. Surface actionable insights specific to the current domain
2. Identify risks and bottlenecks
3. Suggest priorities based on urgency and importance
4. In holistic mode: flag cross-domain conflicts and competing demands
5. Be concise but insightful - David values efficiency

Communication style:
- Direct and actionable
- Use bullet points for clarity
- Highlight urgent items first
- Suggest specific next actions when appropriate

Remember: You're building toward earned autonomy. Provide value through insight, not just information regurgitation."""


PERSPECTIVE_CONTEXT = {
    "personal": "Home, family, and personal projects (Around The House, Family Time, etc.)",
    "church": "Ministry and church leadership responsibilities (Church Tasks)",
    "work": "Professional responsibilities from work Smartsheet",
    "holistic": "Complete view across all life domains - watch for conflicts",
}


def build_global_chat_messages(
    portfolio: PortfolioContext,
    user_message: str,
    history: List[Dict[str, str]],
) -> List[Dict[str, str]]:
    """Build messages array for global portfolio chat.
    
    Args:
        portfolio: Aggregated portfolio statistics
        user_message: The user's current message
        history: Previous conversation history (role/content dicts)
    
    Returns:
        List of messages ready for Anthropic API
    """
    # Build portfolio summary for context
    portfolio_summary = _format_portfolio_summary(portfolio)
    
    # Start with portfolio context as first user message (if no history)
    messages: List[Dict[str, str]] = []
    
    if not history:
        # First message includes portfolio context
        messages.append({
            "role": "user",
            "content": f"""[Portfolio Context - {portfolio.perspective.title()}]
{portfolio_summary}

{user_message}"""
        })
    else:
        # Add history
        messages.extend(history)
        
        # Add new message with updated portfolio context
        messages.append({
            "role": "user",
            "content": f"""[Updated Portfolio: {portfolio.total_open} open, {portfolio.overdue} overdue, {portfolio.due_today} due today]

{user_message}"""
        })
    
    return messages


def _format_portfolio_summary(portfolio: PortfolioContext) -> str:
    """Format portfolio stats as readable text for LLM context."""
    perspective_desc = PERSPECTIVE_CONTEXT.get(
        portfolio.perspective,
        "Tasks from selected perspective"
    )
    
    # Include today's date so the LLM knows the reference point
    from datetime import datetime
    from zoneinfo import ZoneInfo
    today = datetime.now(ZoneInfo("America/New_York"))
    today_str = today.strftime("%A, %B %d, %Y")  # e.g., "Thursday, December 11, 2025"
    
    lines = [
        f"**Today's Date: {today_str}**",
        "",
        f"Perspective: {portfolio.perspective.title()} - {perspective_desc}",
        "",
        "## Current Snapshot",
        f"- Total Open Tasks: {portfolio.total_open}",
        f"- Overdue: {portfolio.overdue}",
        f"- Due Today: {portfolio.due_today}",
        f"- Due This Week: {portfolio.due_this_week}",
    ]
    
    # Priority distribution
    if portfolio.by_priority:
        lines.append("")
        lines.append("## By Priority")
        for priority, count in sorted(
            portfolio.by_priority.items(),
            key=lambda x: _priority_sort_key(x[0])
        ):
            lines.append(f"- {priority}: {count}")
    
    # Project distribution (top 5)
    if portfolio.by_project:
        lines.append("")
        lines.append("## By Project (Top 5)")
        sorted_projects = sorted(
            portfolio.by_project.items(),
            key=lambda x: x[1],
            reverse=True
        )[:5]
        for project, count in sorted_projects:
            lines.append(f"- {project}: {count}")
    
    # Due date distribution (for workload management suggestions)
    if portfolio.by_due_date:
        lines.append("")
        lines.append("## By Due Date")
        due_date_labels = {
            "overdue": "⚠️ Overdue",
            "today": "📅 Due Today",
            "this_week": "📆 This Week",
            "later": "📋 Later",
        }
        for bucket in ["overdue", "today", "this_week", "later"]:
            count = portfolio.by_due_date.get(bucket, 0)
            if count > 0:
                lines.append(f"- {due_date_labels.get(bucket, bucket)}: {count}")
    
    # Domain breakdown (for holistic)
    if portfolio.perspective == "holistic" and portfolio.domain_breakdown:
        lines.append("")
        lines.append("## Domain Breakdown")
        for domain, count in portfolio.domain_breakdown.items():
            if count > 0:
                lines.append(f"- {domain}: {count}")
    
    # Conflicts
    if portfolio.conflicts:
        lines.append("")
        lines.append("## ⚠️ Potential Conflicts")
        for conflict in portfolio.conflicts:
            lines.append(f"- {conflict}")
    
    # Task summaries (limited)
    if portfolio.task_summaries:
        lines.append("")
        lines.append("## Task Details (Sample)")
        for task in portfolio.task_summaries[:10]:
            priority_marker = "🔴" if task["priority"] in ("Critical", "Urgent") else "⚪"
            lines.append(
                f"- {priority_marker} [{task['priority']}] {task['title'][:50]} "
                f"(due: {task['due'][:10]})"
            )
        if len(portfolio.task_summaries) > 10:
            lines.append(f"  ... and {len(portfolio.task_summaries) - 10} more")
    
    return "\n".join(lines)


def _priority_sort_key(priority: str) -> int:
    """Sort key for priorities (highest first)."""
    order = {
        "Critical": 0,
        "Urgent": 1,
        "Important": 2,
        "Standard": 3,
        "Low": 4,
        "Unknown": 5,
    }
    return order.get(priority, 99)
