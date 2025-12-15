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
    # Haiku-enhanced analysis
    detect_attention_with_haiku,
    analyze_email_with_haiku_safe,
    get_haiku_usage_for_user,
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

from .haiku_analyzer import (
    # Result dataclasses
    HaikuAnalysisResult,
    HaikuAttentionResult,
    HaikuActionResult,
    HaikuRuleResult,
    PrivacySanitizeResult,
    # Privacy functions
    is_sensitive_domain,
    sanitize_content,
    prepare_email_for_haiku,
    # Main analysis
    analyze_email_with_haiku,
)

from .haiku_usage import (
    # Dataclasses
    HaikuSettings,
    HaikuUsage,
    # Settings operations
    get_settings as get_haiku_settings,
    save_settings as save_haiku_settings,
    # Usage operations
    get_usage as get_haiku_usage,
    save_usage as save_haiku_usage,
    increment_usage as increment_haiku_usage,
    # Combined operations
    can_use_haiku,
    get_usage_summary as get_haiku_usage_summary,
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
    # Haiku-enhanced analysis
    "detect_attention_with_haiku",
    "analyze_email_with_haiku_safe",
    "get_haiku_usage_for_user",
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
    # Haiku Analyzer
    "HaikuAnalysisResult",
    "HaikuAttentionResult",
    "HaikuActionResult",
    "HaikuRuleResult",
    "PrivacySanitizeResult",
    "is_sensitive_domain",
    "sanitize_content",
    "prepare_email_for_haiku",
    "analyze_email_with_haiku",
    # Haiku Usage
    "HaikuSettings",
    "HaikuUsage",
    "get_haiku_settings",
    "save_haiku_settings",
    "get_haiku_usage",
    "save_haiku_usage",
    "increment_haiku_usage",
    "can_use_haiku",
    "get_haiku_usage_summary",
]

