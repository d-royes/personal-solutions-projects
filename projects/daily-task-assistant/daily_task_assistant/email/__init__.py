"""Email analysis and management package."""

from .analyzer import (
    EmailAnalyzer,
    RuleSuggestion,
    AttentionItem,
    analyze_inbox_patterns,
    suggest_label_rules,
    detect_attention_items,
)

__all__ = [
    "EmailAnalyzer",
    "RuleSuggestion",
    "AttentionItem",
    "analyze_inbox_patterns",
    "suggest_label_rules",
    "detect_attention_items",
]

