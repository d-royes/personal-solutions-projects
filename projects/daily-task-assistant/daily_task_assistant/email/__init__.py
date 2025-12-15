"""Email analysis and management package."""

from .analyzer import (
    EmailAnalyzer,
    RuleSuggestion,
    AttentionItem,
    EmailActionSuggestion,
    EmailActionType,
    analyze_inbox_patterns,
    suggest_label_rules,
    detect_attention_items,
    generate_action_suggestions,
    # Profile-aware analysis
    is_vip_sender,
    matches_not_actionable,
    analyze_with_profile,
    detect_attention_with_profile,
)

from .attention_store import (
    AttentionRecord,
    save_attention,
    get_attention,
    list_active_attention,
    dismiss_attention,
    snooze_attention,
    link_task,
    is_already_analyzed,
    purge_expired_records,
    get_dismissed_email_ids,
)

from .suggestion_store import (
    SuggestionRecord,
    save_suggestion,
    get_suggestion,
    list_pending_suggestions,
    record_suggestion_decision,
    create_suggestion,
    get_approval_stats,
    purge_old_suggestions,
)

from .memory import (
    CategoryPattern,
    SenderProfile,
    TimingPatterns,
    ResponseTimeRecord,
    PatternType,
    RelationshipType,
    ResponseExpectation,
    # Category operations
    record_category_approval,
    record_category_dismissal,
    get_category_pattern,
    get_category_patterns,
    suggest_category_for_email,
    # Sender operations
    get_sender_profile,
    save_sender_profile,
    list_sender_profiles,
    is_vip_sender,
    # Timing operations
    get_timing_patterns,
    save_timing_patterns,
    record_response_time,
    get_average_response_time,
    # Seed data
    seed_sender_profiles_from_memory_graph,
)

__all__ = [
    # Analyzer
    "EmailAnalyzer",
    "RuleSuggestion",
    "AttentionItem",
    "EmailActionSuggestion",
    "EmailActionType",
    "analyze_inbox_patterns",
    "suggest_label_rules",
    "detect_attention_items",
    "generate_action_suggestions",
    # Profile-aware analysis
    "is_vip_sender",
    "matches_not_actionable",
    "analyze_with_profile",
    "detect_attention_with_profile",
    # Attention Store
    "AttentionRecord",
    "save_attention",
    "get_attention",
    "list_active_attention",
    "dismiss_attention",
    "snooze_attention",
    "link_task",
    "is_already_analyzed",
    "purge_expired_records",
    "get_dismissed_email_ids",
    # Suggestion Store
    "SuggestionRecord",
    "save_suggestion",
    "get_suggestion",
    "list_pending_suggestions",
    "record_suggestion_decision",
    "create_suggestion",
    "get_approval_stats",
    "purge_old_suggestions",
    # Memory - data classes
    "CategoryPattern",
    "SenderProfile",
    "TimingPatterns",
    "ResponseTimeRecord",
    "PatternType",
    "RelationshipType",
    "ResponseExpectation",
    # Memory - category operations
    "record_category_approval",
    "record_category_dismissal",
    "get_category_pattern",
    "get_category_patterns",
    "suggest_category_for_email",
    # Memory - sender operations
    "get_sender_profile",
    "save_sender_profile",
    "list_sender_profiles",
    "is_vip_sender",
    # Memory - timing operations
    "get_timing_patterns",
    "save_timing_patterns",
    "record_response_time",
    "get_average_response_time",
    # Seed
    "seed_sender_profiles_from_memory_graph",
]

