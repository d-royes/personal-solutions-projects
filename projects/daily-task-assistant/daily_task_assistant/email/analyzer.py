"""Email pattern analysis and rule suggestion engine.

This module provides intelligence for email management by:
1. Analyzing inbox patterns to identify recurring senders
2. Suggesting filter rules based on email characteristics
3. Detecting attention items that require David's action
4. Identifying candidates for deletion/archival

The analyzer follows the "Better Tool" philosophy:
- Suggests, doesn't act
- Requires explicit approval
- Learns from patterns

Haiku Intelligence Layer (v1.0):
- Uses Claude 3.5 Haiku for semantic email understanding
- Runs in parallel with profile/regex analysis
- Includes usage tracking with daily/weekly limits
- Falls back to regex when limits reached
"""
from __future__ import annotations

import logging
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import List, Dict, Optional, Set, Tuple

from ..mailer.inbox import EmailMessage
from ..sheets.filter_rules import (
    FilterRule,
    FilterCategory,
    FilterField,
    FilterOperator,
)
from .haiku_analyzer import (
    HaikuAnalysisResult,
    analyze_email_with_haiku,
)
from .haiku_usage import (
    can_use_haiku,
    increment_usage as increment_haiku_usage,
    get_usage_summary as get_haiku_usage_summary,
)
from ..llm.anthropic_client import AnthropicError

logger = logging.getLogger(__name__)


class SuggestionType(str, Enum):
    """Types of rule suggestions."""
    
    NEW_LABEL = "new_label"  # Suggest adding a label rule
    DELETION = "deletion"  # Suggest deletion/trash rule
    ATTENTION = "attention"  # Requires user attention


class ConfidenceLevel(str, Enum):
    """Confidence levels for suggestions."""
    
    HIGH = "high"  # Very confident, seen multiple times
    MEDIUM = "medium"  # Somewhat confident
    LOW = "low"  # Uncertain, needs review


@dataclass(slots=True)
class RuleSuggestion:
    """A suggested filter rule."""
    
    type: SuggestionType
    suggested_rule: FilterRule
    confidence: ConfidenceLevel
    reason: str  # Why this rule is suggested
    examples: List[str] = field(default_factory=list)  # Sample subjects/senders
    email_count: int = 1  # How many emails matched this pattern
    
    def to_dict(self) -> dict:
        """Convert to API-friendly dict (camelCase for JavaScript)."""
        return {
            "type": self.type.value,
            "suggestedRule": {
                "emailAccount": self.suggested_rule.email_account,
                "order": self.suggested_rule.order,
                "category": self.suggested_rule.category,
                "field": self.suggested_rule.field,
                "operator": self.suggested_rule.operator,
                "value": self.suggested_rule.value,
                "action": self.suggested_rule.action,
            },
            "confidence": self.confidence.value,
            "reason": self.reason,
            "examples": self.examples[:5],  # Limit examples
            "emailCount": self.email_count,
        }


@dataclass(slots=True)
class AttentionItem:
    """An email requiring David's attention."""

    email: EmailMessage
    reason: str  # Why attention is needed
    urgency: str  # high, medium, low
    suggested_action: Optional[str] = None  # e.g., "Create task", "Reply needed"
    extracted_deadline: Optional[datetime] = None
    extracted_task: Optional[str] = None  # Suggested task title
    matched_role: Optional[str] = None  # Role/context that triggered this item
    confidence: float = 0.5  # Confidence score 0.0-1.0
    analysis_method: str = "regex"  # "regex" | "profile" | "vip"

    def to_dict(self) -> dict:
        """Convert to API-friendly dict (camelCase for JavaScript)."""
        return {
            "emailId": self.email.id,
            "subject": self.email.subject,
            "fromAddress": self.email.from_address,
            "fromName": self.email.from_name,
            "date": self.email.date.isoformat(),
            "reason": self.reason,
            "urgency": self.urgency,
            "suggestedAction": self.suggested_action,
            "extractedDeadline": (
                self.extracted_deadline.isoformat()
                if self.extracted_deadline else None
            ),
            "extractedTask": self.extracted_task,
            "labels": self.email.labels,
            "matchedRole": self.matched_role,
            "confidence": self.confidence,
            "analysisMethod": self.analysis_method,
        }


class EmailActionType(str, Enum):
    """Types of email actions DATA can suggest."""
    
    LABEL = "label"  # Apply a custom label
    ARCHIVE = "archive"  # Archive the email
    DELETE = "delete"  # Move to trash
    STAR = "star"  # Star the email
    MARK_IMPORTANT = "mark_important"  # Mark as important
    CREATE_TASK = "create_task"  # Create a task from email
    REPLY = "reply"  # Suggest replying


@dataclass(slots=True)
class EmailActionSuggestion:
    """A suggested action for a specific email.
    
    This is different from RuleSuggestion - this is about taking action
    on individual emails, not creating filter rules.
    """
    
    number: int  # Display number (#1, #2, etc.) for chat reference
    email: EmailMessage  # The email this suggestion is for
    action: EmailActionType  # What action is suggested
    rationale: str  # Why DATA suggests this action
    label_id: Optional[str] = None  # For LABEL action
    label_name: Optional[str] = None  # For LABEL action
    task_title: Optional[str] = None  # For CREATE_TASK action
    confidence: ConfidenceLevel = ConfidenceLevel.MEDIUM
    
    def to_dict(self) -> dict:
        """Convert to API-friendly dict (camelCase for JavaScript)."""
        return {
            "number": self.number,
            "emailId": self.email.id,
            "from": self.email.from_address,
            "fromName": self.email.from_name,
            "to": self.email.to_address,
            "subject": self.email.subject,
            "snippet": self.email.snippet,
            "date": self.email.date.isoformat(),
            "isUnread": self.email.is_unread,
            "isImportant": self.email.is_important,
            "isStarred": self.email.is_starred,
            "action": self.action.value,
            "rationale": self.rationale,
            "labelId": self.label_id,
            "labelName": self.label_name,
            "taskTitle": self.task_title,
            "confidence": self.confidence.value,
        }


class EmailAnalyzer:
    """Analyzes email patterns and suggests filter rules.
    
    This is the core intelligence engine for email management.
    It observes patterns and suggests rules, but never acts autonomously.
    """
    
    # Patterns that indicate promotional/newsletter content
    PROMOTIONAL_PATTERNS = [
        r"unsubscribe",
        r"view in browser",
        r"email preferences",
        r"opt.?out",
        r"newsletter",
        r"weekly digest",
        r"special offer",
        r"limited time",
        r"% off",
        r"sale ends",
        r"don't miss",
        r"exclusive deal",
    ]
    
    # Patterns that indicate transactional emails
    TRANSACTIONAL_PATTERNS = [
        r"receipt",
        r"invoice",
        r"order confirm",
        r"shipping",
        r"delivered",
        r"payment",
        r"statement",
        r"bill is ready",
        r"autopay",
        r"subscription renewal",
    ]
    
    # Patterns that indicate attention needed
    # Note: Soft exclusions (prayer requests, newsletters, etc.) are handled by
    # NOT including them as triggers - they can still appear if other patterns match.
    ATTENTION_PATTERNS = [
        (r"\?$", "Question asked"),
        # Specific action requests (not generic "please add" which catches prayer requests)
        (r"\bplease\s+(review|approve|confirm|check|update|submit)\b", "Action requested"),
        (r"\basap\b", "Urgent - ASAP mentioned"),
        (r"\burgent\b", "Urgent flag"),
        (r"\bdeadline\b", "Deadline mentioned"),
        (r"\bby\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", "Day deadline"),
        (r"\bby\s+\d{1,2}[\/\-]\d{1,2}", "Date deadline"),
        (r"\bcan you\b", "Request - can you"),
        (r"\bwould you\b", "Request - would you"),
        (r"\bneed\s+(your|you to)\b", "Action needed from you"),
        (r"\bwaiting\s+(for|on)\s+your\b", "Waiting for response"),
        (r"\bfollow\s*up\b", "Follow-up required"),
        # Additional patterns for action items
        (r"\bpast\s*due\b", "Past due - requires action"),
        (r"\boverdue\b", "Overdue item"),
        (r"\bneed(s)?\s+attention\b", "Needs attention"),
        (r"\baction\s+(required|needed)\b", "Action required"),
        (r"\bpending\s+(request|purchase|approval|action|review|delivery)\b", "Pending item"),
        (r"\brequires?\s+(your\s+)?(attention|action|review|approval)\b", "Requires attention"),
        (r"\breminder\b", "Reminder"),
        (r"\bimportant:\b", "Flagged as important"),
        (r"\bfyi\b", "FYI - for your information"),
        # Patterns from inbox analysis (David approved 2024-12-12)
        (r"\bawaiting\s+(delivery|approval|response|review)\b", "Awaiting action"),
        (r"\bapproval\s+status\b", "Approval status - needs review"),
        (r"^fwd?:", "Forwarded - may need action"),
        (r"\binvoice\b", "Invoice - track for payment"),
    ]
    
    # Known junk patterns
    JUNK_PATTERNS = [
        r"congratulations",
        r"you've been selected",
        r"claim now",
        r"act fast",
        r"limited time offer",
        r"people noticed you",
        r"rate your transaction",
    ]
    
    def __init__(
        self,
        email_account: str,
        existing_rules: Optional[List[FilterRule]] = None,
    ):
        """Initialize the analyzer.
        
        Args:
            email_account: Email account being analyzed.
            existing_rules: Current filter rules for this account.
        """
        self.email_account = email_account
        self.existing_rules = existing_rules or []
        
        # Build a set of already-covered patterns
        self._covered_patterns: Set[str] = set()
        for rule in self.existing_rules:
            self._covered_patterns.add(rule.value.lower())
    
    def analyze_messages(
        self,
        messages: List[EmailMessage],
    ) -> Tuple[List[RuleSuggestion], List[AttentionItem]]:
        """Analyze a batch of messages.
        
        Args:
            messages: Messages to analyze.
            
        Returns:
            Tuple of (rule suggestions, attention items).
        """
        suggestions = []
        attention_items = []
        
        # Analyze sender patterns
        sender_suggestions = self._analyze_sender_patterns(messages)
        suggestions.extend(sender_suggestions)
        
        # Analyze content patterns
        content_suggestions = self._analyze_content_patterns(messages)
        suggestions.extend(content_suggestions)
        
        # Detect attention items
        for msg in messages:
            attention = self._check_attention_needed(msg)
            if attention:
                attention_items.append(attention)
        
        # Deduplicate suggestions
        suggestions = self._deduplicate_suggestions(suggestions)
        
        return suggestions, attention_items
    
    def _analyze_sender_patterns(
        self,
        messages: List[EmailMessage],
    ) -> List[RuleSuggestion]:
        """Analyze sender patterns to suggest label rules."""
        suggestions = []
        
        # Group by sender domain
        domain_counts: Dict[str, List[EmailMessage]] = defaultdict(list)
        for msg in messages:
            domain = self._extract_domain(msg.from_address)
            if domain:
                domain_counts[domain].append(msg)
        
        # Group by sender address
        address_counts: Dict[str, List[EmailMessage]] = defaultdict(list)
        for msg in messages:
            address_counts[msg.from_address.lower()].append(msg)
        
        # Suggest rules for frequent senders not already covered
        for domain, msgs in domain_counts.items():
            if len(msgs) >= 2 and domain not in self._covered_patterns:
                suggestion = self._suggest_domain_rule(domain, msgs)
                if suggestion:
                    suggestions.append(suggestion)
        
        for address, msgs in address_counts.items():
            if len(msgs) >= 2 and address not in self._covered_patterns:
                suggestion = self._suggest_address_rule(address, msgs)
                if suggestion:
                    suggestions.append(suggestion)
        
        return suggestions
    
    def _analyze_content_patterns(
        self,
        messages: List[EmailMessage],
    ) -> List[RuleSuggestion]:
        """Analyze email content to suggest rules."""
        suggestions = []
        
        for msg in messages:
            content = f"{msg.subject} {msg.snippet}".lower()
            
            # Check for promotional patterns
            if self._matches_patterns(content, self.PROMOTIONAL_PATTERNS):
                if msg.from_address.lower() not in self._covered_patterns:
                    suggestions.append(self._create_promotional_suggestion(msg))
            
            # Check for transactional patterns
            elif self._matches_patterns(content, self.TRANSACTIONAL_PATTERNS):
                if msg.from_address.lower() not in self._covered_patterns:
                    suggestions.append(self._create_transactional_suggestion(msg))
            
            # Check for junk patterns
            if self._matches_patterns(content, self.JUNK_PATTERNS):
                suggestions.append(self._create_junk_suggestion(msg))
        
        return suggestions
    
    def _check_attention_needed(
        self,
        msg: EmailMessage,
    ) -> Optional[AttentionItem]:
        """Check if an email needs David's attention."""
        content = f"{msg.subject} {msg.snippet}".lower()
        
        # Check if addressed to David (not CC'd on mass email)
        to_lower = msg.to_address.lower()
        is_addressed_to_david = (
            "david" in to_lower or 
            self.email_account.lower() in to_lower
        )
        
        if not is_addressed_to_david:
            return None
        
        # Check attention patterns
        for pattern, reason in self.ATTENTION_PATTERNS:
            if re.search(pattern, content, re.IGNORECASE):
                urgency = self._determine_urgency(msg, pattern, content)
                action = self._suggest_action(msg, content)
                
                return AttentionItem(
                    email=msg,
                    reason=reason,
                    urgency=urgency,
                    suggested_action=action,
                    extracted_deadline=self._extract_deadline(content),
                    extracted_task=self._extract_task(msg),
                )
        
        # Check if it's a direct question (ends with ?)
        if msg.subject.strip().endswith("?"):
            return AttentionItem(
                email=msg,
                reason="Question in subject line",
                urgency="medium",
                suggested_action="Reply needed",
            )
        
        return None
    
    def _suggest_domain_rule(
        self,
        domain: str,
        messages: List[EmailMessage],
    ) -> Optional[RuleSuggestion]:
        """Suggest a rule based on domain pattern."""
        # Determine likely category based on content
        category = self._infer_category(messages)
        
        return RuleSuggestion(
            type=SuggestionType.NEW_LABEL,
            suggested_rule=FilterRule(
                email_account=self.email_account,
                order=self._get_category_order(category),
                category=category,
                field=FilterField.SENDER_EMAIL.value,
                operator=FilterOperator.CONTAINS.value,
                value=domain,
                action="Add",
            ),
            confidence=ConfidenceLevel.HIGH if len(messages) >= 3 else ConfidenceLevel.MEDIUM,
            reason=f"Received {len(messages)} emails from this domain",
            examples=[m.subject[:50] for m in messages[:3]],
            email_count=len(messages),
        )
    
    def _suggest_address_rule(
        self,
        address: str,
        messages: List[EmailMessage],
    ) -> Optional[RuleSuggestion]:
        """Suggest a rule based on specific address."""
        category = self._infer_category(messages)
        
        return RuleSuggestion(
            type=SuggestionType.NEW_LABEL,
            suggested_rule=FilterRule(
                email_account=self.email_account,
                order=self._get_category_order(category),
                category=category,
                field=FilterField.SENDER_EMAIL.value,
                operator=FilterOperator.EQUALS.value,
                value=address,
                action="Add",
            ),
            confidence=ConfidenceLevel.MEDIUM,
            reason=f"Received {len(messages)} emails from this sender",
            examples=[m.subject[:50] for m in messages[:3]],
            email_count=len(messages),
        )
    
    def _create_promotional_suggestion(
        self,
        msg: EmailMessage,
    ) -> RuleSuggestion:
        """Create a promotional category suggestion."""
        return RuleSuggestion(
            type=SuggestionType.NEW_LABEL,
            suggested_rule=FilterRule(
                email_account=self.email_account,
                order=5,  # Promotional is order 5
                category=FilterCategory.PROMOTIONAL.value,
                field=FilterField.SENDER_EMAIL.value,
                operator=FilterOperator.CONTAINS.value,
                value=self._extract_domain(msg.from_address) or msg.from_address,
                action="Add",
            ),
            confidence=ConfidenceLevel.MEDIUM,
            reason="Contains promotional content patterns",
            examples=[msg.subject[:50]],
            email_count=1,
        )
    
    def _create_transactional_suggestion(
        self,
        msg: EmailMessage,
    ) -> RuleSuggestion:
        """Create a transactional category suggestion."""
        return RuleSuggestion(
            type=SuggestionType.NEW_LABEL,
            suggested_rule=FilterRule(
                email_account=self.email_account,
                order=4,  # Transactional is order 4
                category=FilterCategory.TRANSACTIONAL.value,
                field=FilterField.SENDER_EMAIL.value,
                operator=FilterOperator.CONTAINS.value,
                value=self._extract_domain(msg.from_address) or msg.from_address,
                action="Add",
            ),
            confidence=ConfidenceLevel.MEDIUM,
            reason="Contains transactional content patterns",
            examples=[msg.subject[:50]],
            email_count=1,
        )
    
    def _create_junk_suggestion(
        self,
        msg: EmailMessage,
    ) -> RuleSuggestion:
        """Create a junk category suggestion."""
        return RuleSuggestion(
            type=SuggestionType.DELETION,
            suggested_rule=FilterRule(
                email_account=self.email_account,
                order=6,  # Junk is order 6
                category=FilterCategory.JUNK.value,
                field=FilterField.SENDER_EMAIL.value,
                operator=FilterOperator.CONTAINS.value,
                value=self._extract_domain(msg.from_address) or msg.from_address,
                action="Add",
            ),
            confidence=ConfidenceLevel.LOW,
            reason="Contains junk/spam patterns - review carefully",
            examples=[msg.subject[:50]],
            email_count=1,
        )
    
    def _infer_category(
        self,
        messages: List[EmailMessage],
    ) -> str:
        """Infer the most likely category for a set of messages."""
        # Combine all content for analysis
        all_content = " ".join(
            f"{m.subject} {m.snippet}" for m in messages
        ).lower()
        
        # Check patterns in order of priority
        if self._matches_patterns(all_content, self.JUNK_PATTERNS):
            return FilterCategory.JUNK.value
        
        if self._matches_patterns(all_content, self.PROMOTIONAL_PATTERNS):
            return FilterCategory.PROMOTIONAL.value
        
        if self._matches_patterns(all_content, self.TRANSACTIONAL_PATTERNS):
            return FilterCategory.TRANSACTIONAL.value
        
        # Default to 1 Week Hold for unknown patterns
        return FilterCategory.ONE_WEEK_HOLD.value
    
    def _get_category_order(self, category: str) -> int:
        """Get the order number for a category."""
        order_map = {
            FilterCategory.ONE_WEEK_HOLD.value: 1,
            FilterCategory.PERSONAL.value: 2,
            FilterCategory.ADMIN.value: 3,
            FilterCategory.TRANSACTIONAL.value: 4,
            FilterCategory.PROMOTIONAL.value: 5,
            FilterCategory.JUNK.value: 6,
            FilterCategory.TRASH.value: 7,
        }
        return order_map.get(category, 1)
    
    def _determine_urgency(
        self,
        msg: EmailMessage,
        pattern: str,
        content: str,
    ) -> str:
        """Determine urgency level of an attention item."""
        # High urgency indicators
        if any(word in content for word in ["asap", "urgent", "immediately"]):
            return "high"
        
        # Check message age - older unread = higher urgency
        if msg.is_unread and msg.age_hours() > 48:
            return "high"
        
        # Questions and requests are medium urgency
        if "?" in content or any(word in content for word in ["please", "can you", "would you"]):
            return "medium"
        
        return "low"
    
    def _suggest_action(
        self,
        msg: EmailMessage,
        content: str,
    ) -> str:
        """Suggest an action for an attention item."""
        if any(word in content for word in ["deadline", "due", "by"]):
            return "Create task"
        
        if "?" in msg.subject or "question" in content:
            return "Reply needed"
        
        if any(word in content for word in ["please", "can you", "would you", "need"]):
            return "Action requested"
        
        return "Review needed"
    
    def _extract_deadline(self, content: str) -> Optional[datetime]:
        """Try to extract a deadline from content."""
        # Simple date extraction - could be enhanced
        date_patterns = [
            r"by\s+(\d{1,2})[\/\-](\d{1,2})",  # by 12/15
            r"due\s+(\d{1,2})[\/\-](\d{1,2})",  # due 12/15
        ]
        
        for pattern in date_patterns:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                try:
                    month, day = int(match.group(1)), int(match.group(2))
                    year = datetime.now().year
                    return datetime(year, month, day, tzinfo=timezone.utc)
                except ValueError:
                    continue
        
        return None
    
    def _extract_task(self, msg: EmailMessage) -> Optional[str]:
        """Extract a potential task title from the email."""
        # Use subject line, cleaned up
        task = msg.subject.strip()
        
        # Remove common prefixes
        prefixes = ["re:", "fwd:", "fw:"]
        for prefix in prefixes:
            if task.lower().startswith(prefix):
                task = task[len(prefix):].strip()
        
        # Limit length
        if len(task) > 60:
            task = task[:57] + "..."
        
        return task if task else None
    
    def _extract_domain(self, email_address: str) -> Optional[str]:
        """Extract domain from email address."""
        if "@" in email_address:
            return email_address.split("@")[1].lower()
        return None
    
    def _matches_patterns(
        self,
        content: str,
        patterns: List[str],
    ) -> bool:
        """Check if content matches any of the patterns."""
        for pattern in patterns:
            if re.search(pattern, content, re.IGNORECASE):
                return True
        return False
    
    def _deduplicate_suggestions(
        self,
        suggestions: List[RuleSuggestion],
    ) -> List[RuleSuggestion]:
        """Remove duplicate suggestions, keeping highest confidence."""
        seen: Dict[str, RuleSuggestion] = {}
        
        for suggestion in suggestions:
            key = suggestion.suggested_rule.value.lower()
            
            if key not in seen:
                seen[key] = suggestion
            elif suggestion.email_count > seen[key].email_count:
                # Keep the one with more examples
                seen[key] = suggestion
        
        return list(seen.values())


# Convenience functions

def analyze_inbox_patterns(
    messages: List[EmailMessage],
    email_account: str,
    existing_rules: Optional[List[FilterRule]] = None,
) -> Tuple[List[RuleSuggestion], List[AttentionItem]]:
    """Analyze inbox messages and return suggestions.
    
    Args:
        messages: Messages to analyze.
        email_account: Email account being analyzed.
        existing_rules: Current filter rules.
        
    Returns:
        Tuple of (rule suggestions, attention items).
    """
    analyzer = EmailAnalyzer(email_account, existing_rules)
    return analyzer.analyze_messages(messages)


def suggest_label_rules(
    messages: List[EmailMessage],
    email_account: str,
    existing_rules: Optional[List[FilterRule]] = None,
) -> List[RuleSuggestion]:
    """Get only label rule suggestions.
    
    Args:
        messages: Messages to analyze.
        email_account: Email account being analyzed.
        existing_rules: Current filter rules.
        
    Returns:
        List of rule suggestions.
    """
    analyzer = EmailAnalyzer(email_account, existing_rules)
    suggestions, _ = analyzer.analyze_messages(messages)
    return [s for s in suggestions if s.type == SuggestionType.NEW_LABEL]


def detect_attention_items(
    messages: List[EmailMessage],
    email_account: str,
) -> List[AttentionItem]:
    """Get emails requiring attention.
    
    Args:
        messages: Messages to analyze.
        email_account: Email account being analyzed.
        
    Returns:
        List of attention items.
    """
    analyzer = EmailAnalyzer(email_account)
    _, attention_items = analyzer.analyze_messages(messages)
    return attention_items


def generate_action_suggestions(
    messages: List[EmailMessage],
    email_account: str,
    available_labels: Optional[List[Dict[str, str]]] = None,
) -> List[EmailActionSuggestion]:
    """Generate action suggestions for a list of emails.
    
    This analyzes recent emails and suggests actions like:
    - Applying labels
    - Archiving
    - Starring
    - Creating tasks
    
    Args:
        messages: Messages to analyze.
        email_account: Email account being analyzed.
        available_labels: List of user's custom labels (id, name, color).
        
    Returns:
        List of numbered EmailActionSuggestion objects.
    """
    suggestions = []
    number = 1
    
    # Build a set of available label names for matching
    label_lookup = {}
    if available_labels:
        for label in available_labels:
            label_lookup[label["name"].lower()] = label
    
    analyzer = EmailAnalyzer(email_account)
    
    # System labels to ignore when checking for user labels
    SYSTEM_LABELS = {
        "INBOX", "UNREAD", "STARRED", "IMPORTANT", "SENT", "DRAFT", 
        "SPAM", "TRASH", "CATEGORY_PERSONAL", "CATEGORY_SOCIAL",
        "CATEGORY_PROMOTIONS", "CATEGORY_UPDATES", "CATEGORY_FORUMS"
    }
    
    def has_user_label(email_labels: List[str]) -> bool:
        """Check if email has any user-defined label."""
        for lbl in email_labels:
            # User labels start with "Label_" or aren't in system labels
            if lbl.startswith("Label_") or lbl not in SYSTEM_LABELS:
                return True
        return False
    
    for msg in messages:
        content = (msg.subject + " " + msg.snippet).lower()
        
        # Skip emails that already have user-defined labels (already categorized)
        if has_user_label(msg.labels):
            continue
        
        # Check for emails that should be archived (old promotional)
        age_hours = msg.age_hours()
        if age_hours > 72:  # Over 3 days old
            if analyzer._matches_patterns(content, analyzer.PROMOTIONAL_PATTERNS):
                suggestions.append(EmailActionSuggestion(
                    number=number,
                    email=msg,
                    action=EmailActionType.ARCHIVE,
                    rationale=f"Promotional email over {int(age_hours / 24)} days old",
                    confidence=ConfidenceLevel.HIGH,
                ))
                number += 1
                continue
        
        # Check for transactional emails - suggest labeling
        if analyzer._matches_patterns(content, analyzer.TRANSACTIONAL_PATTERNS):
            label_info = label_lookup.get("transactional")
            if label_info:
                suggestions.append(EmailActionSuggestion(
                    number=number,
                    email=msg,
                    action=EmailActionType.LABEL,
                    rationale="Appears to be a receipt/invoice/shipping notification",
                    label_id=label_info.get("id"),
                    label_name="Transactional",
                    confidence=ConfidenceLevel.HIGH,
                ))
                number += 1
                continue
        
        # Check for attention-worthy emails - suggest star/important
        attention = analyzer._check_attention_needed(msg)
        if attention and attention.urgency == "high":
            if not msg.is_starred:
                suggestions.append(EmailActionSuggestion(
                    number=number,
                    email=msg,
                    action=EmailActionType.STAR,
                    rationale=attention.reason,
                    confidence=ConfidenceLevel.MEDIUM,
                ))
                number += 1
            
            # Also suggest task creation if deadline detected
            if attention.extracted_task:
                suggestions.append(EmailActionSuggestion(
                    number=number,
                    email=msg,
                    action=EmailActionType.CREATE_TASK,
                    rationale=attention.reason,
                    task_title=attention.extracted_task,
                    confidence=ConfidenceLevel.MEDIUM,
                ))
                number += 1
        
        # Check for junk patterns - suggest delete
        if analyzer._matches_patterns(content, analyzer.JUNK_PATTERNS):
            suggestions.append(EmailActionSuggestion(
                number=number,
                email=msg,
                action=EmailActionType.DELETE,
                rationale="Appears to be junk/spam email",
                confidence=ConfidenceLevel.MEDIUM,
            ))
            number += 1
            continue
        
        # Limit suggestions to prevent overwhelming the user
        if number > 20:
            break

    return suggestions


# Profile-aware analysis functions

def is_vip_sender(
    email: EmailMessage,
    vip_patterns: List[str],
) -> bool:
    """Check if an email is from a VIP sender.

    VIP senders are always high priority regardless of content.
    Matching is case-insensitive and checks both address and name.

    Args:
        email: The email message to check.
        vip_patterns: List of VIP sender patterns (names, domains, etc.)

    Returns:
        True if sender matches any VIP pattern.
    """
    from_lower = email.from_address.lower()
    from_name_lower = (email.from_name or "").lower()

    for pattern in vip_patterns:
        pattern_lower = pattern.lower()
        if pattern_lower in from_lower or pattern_lower in from_name_lower:
            return True

    return False


def matches_not_actionable(
    email: EmailMessage,
    not_actionable_patterns: List[str],
) -> bool:
    """Check if an email matches not-actionable patterns.

    These are patterns that should be skipped during attention detection
    because they're known to be not actionable (e.g., prayer requests,
    automated notifications, marketing).

    Args:
        email: The email message to check.
        not_actionable_patterns: List of patterns to skip.

    Returns:
        True if email matches any not-actionable pattern.
    """
    content = f"{email.from_address} {email.from_name or ''} {email.subject} {email.snippet}".lower()

    for pattern in not_actionable_patterns:
        if pattern.lower() in content:
            return True

    return False


def _determine_profile_urgency(
    email_account: str,
    role: str,
    pattern: str,
) -> str:
    """Determine urgency based on account, role, and matched pattern.

    Args:
        email_account: "church" or "personal"
        role: The matched role (e.g., "Treasurer", "Parent")
        pattern: The pattern that matched

    Returns:
        Urgency level: "high", "medium", or "low"
    """
    pattern_lower = pattern.lower()

    # High urgency patterns
    high_urgency_keywords = [
        "past due", "urgent", "deadline", "fraud alert",
        "overdue", "immediately", "asap", "payment due",
    ]
    if any(kw in pattern_lower for kw in high_urgency_keywords):
        return "high"

    # Medium urgency roles (financial/leadership)
    medium_urgency_roles = [
        "Treasurer", "Head Elder", "Financial", "Parent",
        "Procurement Lead",
    ]
    if role in medium_urgency_roles:
        return "medium"

    return "low"


def analyze_with_profile(
    email: EmailMessage,
    email_account: str,
    church_roles: List[str],
    personal_contexts: List[str],
    vip_senders: Dict[str, List[str]],
    church_attention_patterns: Dict[str, List[str]],
    personal_attention_patterns: Dict[str, List[str]],
    not_actionable_patterns: Dict[str, List[str]],
) -> Optional[AttentionItem]:
    """Role-aware attention detection using profile data.

    This function checks emails against the user's profile to determine
    if attention is needed. It's more intelligent than regex because it
    understands David's roles and contexts.

    Processing order:
    1. Check not-actionable patterns (skip these)
    2. Check VIP senders (always high priority)
    3. Check role/context-specific patterns
    4. Fall back to regex patterns if nothing matches

    Args:
        email: The email message to analyze.
        email_account: "church" or "personal"
        church_roles: List of church roles (e.g., ["Treasurer", "IT Lead"])
        personal_contexts: List of personal contexts (e.g., ["Parent", "Homeowner"])
        vip_senders: Dict mapping account to VIP sender patterns
        church_attention_patterns: Dict mapping role to attention keywords
        personal_attention_patterns: Dict mapping context to attention keywords
        not_actionable_patterns: Dict mapping account to skip patterns

    Returns:
        AttentionItem if attention needed, None otherwise.
    """
    # Get account-specific patterns
    account_vips = vip_senders.get(email_account, [])
    account_not_actionable = not_actionable_patterns.get(email_account, [])

    # 1. Check not-actionable patterns first (skip these)
    if matches_not_actionable(email, account_not_actionable):
        return None

    # 2. Check VIP senders (always high priority)
    if is_vip_sender(email, account_vips):
        # Find which VIP pattern matched for the reason
        from_lower = email.from_address.lower()
        from_name_lower = (email.from_name or "").lower()
        matched_vip = "VIP sender"
        for pattern in account_vips:
            if pattern.lower() in from_lower or pattern.lower() in from_name_lower:
                matched_vip = pattern
                break

        return AttentionItem(
            email=email,
            reason=f"VIP: {matched_vip}",
            urgency="high",
            suggested_action="Review immediately",
            extracted_task=_extract_task_from_email(email),
            matched_role="VIP",
            confidence=0.95,
            analysis_method="vip",
        )

    # 3. Check role/context-specific patterns
    content = f"{email.subject} {email.snippet}".lower()

    # Route to appropriate patterns based on account
    if email_account == "church":
        roles = church_roles
        patterns_by_role = church_attention_patterns
    else:  # personal
        roles = personal_contexts
        patterns_by_role = personal_attention_patterns

    # Check each role's patterns
    for role in roles:
        patterns = patterns_by_role.get(role, [])
        for pattern in patterns:
            if pattern.lower() in content:
                urgency = _determine_profile_urgency(email_account, role, pattern)
                return AttentionItem(
                    email=email,
                    reason=f"{role}: {pattern}",
                    urgency=urgency,
                    suggested_action=_suggest_action_for_role(role, pattern),
                    extracted_task=_extract_task_from_email(email),
                    matched_role=role,
                    confidence=0.85,
                    analysis_method="profile",
                )

    # 4. No profile match - return None (let regex analysis handle it)
    return None


def _extract_task_from_email(email: EmailMessage) -> Optional[str]:
    """Extract a potential task title from the email subject.

    Args:
        email: The email message.

    Returns:
        Cleaned subject line suitable for a task title, or None.
    """
    task = email.subject.strip()

    # Remove common prefixes
    prefixes = ["re:", "fwd:", "fw:"]
    for prefix in prefixes:
        if task.lower().startswith(prefix):
            task = task[len(prefix):].strip()

    # Limit length
    if len(task) > 60:
        task = task[:57] + "..."

    return task if task else None


def _suggest_action_for_role(role: str, pattern: str) -> str:
    """Suggest an action based on the matched role and pattern.

    Args:
        role: The matched role (e.g., "Treasurer", "Parent")
        pattern: The pattern that matched

    Returns:
        Suggested action string
    """
    pattern_lower = pattern.lower()

    # Financial patterns -> Create task for tracking
    if any(kw in pattern_lower for kw in ["invoice", "payment", "bill", "deposit", "check request"]):
        return "Create task to track payment"

    # Deadline patterns -> Create task
    if any(kw in pattern_lower for kw in ["deadline", "due", "pending", "awaiting"]):
        return "Create task"

    # Meeting patterns -> Review
    if any(kw in pattern_lower for kw in ["meeting", "appointment"]):
        return "Review and calendar"

    # Family patterns -> Reply or action needed
    if role in ["Parent", "Family Coordinator"]:
        return "Action needed"

    # Default -> Review
    return "Review needed"


def detect_attention_with_profile(
    messages: List[EmailMessage],
    email_account: str,
    church_roles: List[str],
    personal_contexts: List[str],
    vip_senders: Dict[str, List[str]],
    church_attention_patterns: Dict[str, List[str]],
    personal_attention_patterns: Dict[str, List[str]],
    not_actionable_patterns: Dict[str, List[str]],
    fallback_to_regex: bool = True,
) -> List[AttentionItem]:
    """Detect attention items using profile-aware analysis.

    This is the main entry point for profile-aware attention detection.
    It processes each email with profile analysis first, then optionally
    falls back to regex for emails that don't match profile patterns.

    Args:
        messages: List of emails to analyze.
        email_account: "church" or "personal"
        church_roles: List of church roles
        personal_contexts: List of personal contexts
        vip_senders: Dict mapping account to VIP sender patterns
        church_attention_patterns: Dict mapping role to attention keywords
        personal_attention_patterns: Dict mapping context to attention keywords
        not_actionable_patterns: Dict mapping account to skip patterns
        fallback_to_regex: If True, use regex analysis for non-profile matches

    Returns:
        List of AttentionItem objects requiring attention.
    """
    attention_items = []
    processed_ids = set()

    # First pass: Profile-aware analysis
    for msg in messages:
        item = analyze_with_profile(
            email=msg,
            email_account=email_account,
            church_roles=church_roles,
            personal_contexts=personal_contexts,
            vip_senders=vip_senders,
            church_attention_patterns=church_attention_patterns,
            personal_attention_patterns=personal_attention_patterns,
            not_actionable_patterns=not_actionable_patterns,
        )
        if item:
            attention_items.append(item)
            processed_ids.add(msg.id)

    # Second pass: Regex fallback for emails not caught by profile
    if fallback_to_regex:
        analyzer = EmailAnalyzer(email_account)
        for msg in messages:
            if msg.id not in processed_ids:
                # Check not-actionable first
                account_not_actionable = not_actionable_patterns.get(email_account, [])
                if matches_not_actionable(msg, account_not_actionable):
                    continue

                # Use regex analysis
                item = analyzer._check_attention_needed(msg)
                if item:
                    # Add profile fields with defaults
                    item.matched_role = None
                    item.confidence = 0.7
                    item.analysis_method = "regex"
                    attention_items.append(item)

    return attention_items


# =============================================================================
# Haiku Intelligence Layer Integration
# =============================================================================

def _haiku_result_to_attention_item(
    email: EmailMessage,
    result: HaikuAnalysisResult,
) -> Optional[AttentionItem]:
    """Convert HaikuAnalysisResult to AttentionItem.

    Args:
        email: The analyzed email message.
        result: The Haiku analysis result.

    Returns:
        AttentionItem if attention needed, None otherwise.
    """
    attention = result.attention

    if not attention.needs_attention:
        return None

    return AttentionItem(
        email=email,
        reason=attention.reason,
        urgency=attention.urgency,
        suggested_action=attention.suggested_action,
        extracted_deadline=None,  # Haiku doesn't extract deadlines yet
        extracted_task=attention.extracted_task,
        matched_role=attention.matched_role,
        confidence=attention.confidence,
        analysis_method="haiku",
    )


def analyze_email_with_haiku_safe(
    email: EmailMessage,
    user_id: str,
    roles_context: Optional[str] = None,
    available_labels: Optional[str] = None,
) -> Optional[HaikuAnalysisResult]:
    """Safely analyze an email with Haiku, handling errors gracefully.

    Args:
        email: The email to analyze.
        user_id: User identifier for usage tracking.
        roles_context: Optional custom roles context.
        available_labels: Optional custom labels list.

    Returns:
        HaikuAnalysisResult if successful, None if error or skipped.
    """
    try:
        # For short snippets (< 250 chars), include body if available
        # This handles emails where snippet is just a signature
        body_to_send = None
        snippet_len = len(email.snippet) if email.snippet else 0
        if snippet_len < 250 and email.body:
            # Use body for short snippets (likely signature-only previews)
            body_to_send = email.body

        result = analyze_email_with_haiku(
            sender_email=email.from_address,
            sender_name=email.from_name or "",
            subject=email.subject,
            snippet=email.snippet,
            date=email.date.isoformat() if email.date else "",
            body=body_to_send,
            roles_context=roles_context,
            available_labels=available_labels,
        )

        # Increment usage only on successful analysis (GLOBAL - no user param)
        if result.analysis_method == "haiku":
            increment_haiku_usage()

        return result

    except AnthropicError as exc:
        logger.warning(f"Haiku analysis failed for email {email.id}: {exc}")
        return None
    except Exception as exc:
        logger.error(f"Unexpected error in Haiku analysis: {exc}")
        return None


def detect_attention_with_haiku(
    messages: List[EmailMessage],
    email_account: str,
    user_id: str,
    church_roles: List[str],
    personal_contexts: List[str],
    vip_senders: Dict[str, List[str]],
    church_attention_patterns: Dict[str, List[str]],
    personal_attention_patterns: Dict[str, List[str]],
    not_actionable_patterns: Dict[str, List[str]],
    roles_context: Optional[str] = None,
    available_labels: Optional[str] = None,
    already_analyzed_ids: Optional[Set[str]] = None,
) -> Tuple[List[AttentionItem], Dict[str, HaikuAnalysisResult]]:
    """Detect attention items with Haiku Intelligence Layer.

    This is the enhanced entry point for attention detection that uses
    Claude 3.5 Haiku for semantic email understanding. Analysis flow:

    1. Check not-actionable patterns (skip these entirely)
    2. Check VIP senders (always high priority, no Haiku needed)
    3. Check if already analyzed by Haiku (skip to avoid duplicates)
    4. If Haiku enabled and under limits: run Haiku analysis
    5. Fall back to profile/regex for remaining emails

    Args:
        messages: List of emails to analyze.
        email_account: "church" or "personal"
        user_id: User identifier for usage tracking.
        church_roles: List of church roles
        personal_contexts: List of personal contexts
        vip_senders: Dict mapping account to VIP sender patterns
        church_attention_patterns: Dict mapping role to attention keywords
        personal_attention_patterns: Dict mapping context to attention keywords
        not_actionable_patterns: Dict mapping account to skip patterns
        roles_context: Optional custom roles context for Haiku.
        available_labels: Optional custom labels list for Haiku.
        already_analyzed_ids: Set of email IDs already analyzed by Haiku.

    Returns:
        Tuple of (attention_items, haiku_results)
        - attention_items: List of AttentionItem objects requiring attention
        - haiku_results: Dict mapping email_id to HaikuAnalysisResult for later use
    """
    attention_items: List[AttentionItem] = []
    haiku_results: Dict[str, HaikuAnalysisResult] = {}
    processed_ids: Set[str] = set()
    already_analyzed = already_analyzed_ids or set()

    # Get account-specific patterns
    account_vips = vip_senders.get(email_account, [])
    account_not_actionable = not_actionable_patterns.get(email_account, [])

    # Check if Haiku is available (GLOBAL - not per-user)
    haiku_available = can_use_haiku()
    if not haiku_available:
        logger.info("Haiku not available, using profile/regex only")

    for msg in messages:
        # Skip already processed in this batch
        if msg.id in processed_ids:
            continue

        # 1. Check not-actionable patterns (skip entirely)
        if matches_not_actionable(msg, account_not_actionable):
            processed_ids.add(msg.id)
            continue

        # 2. Check VIP senders (always high priority, no Haiku needed)
        if is_vip_sender(msg, account_vips):
            # Find which VIP pattern matched
            from_lower = msg.from_address.lower()
            from_name_lower = (msg.from_name or "").lower()
            matched_vip = "VIP sender"
            for pattern in account_vips:
                if pattern.lower() in from_lower or pattern.lower() in from_name_lower:
                    matched_vip = pattern
                    break

            attention_items.append(AttentionItem(
                email=msg,
                reason=f"VIP: {matched_vip}",
                urgency="high",
                suggested_action="Review immediately",
                extracted_task=_extract_task_from_email(msg),
                matched_role="VIP",
                confidence=0.95,
                analysis_method="vip",
            ))
            processed_ids.add(msg.id)
            continue

        # 3. Skip if already analyzed by Haiku (avoid re-analysis)
        if msg.id in already_analyzed:
            processed_ids.add(msg.id)
            continue

        # 4. Try Haiku analysis if available
        if haiku_available:
            # Re-check availability (may have hit limit during batch)
            if can_use_haiku():
                haiku_result = analyze_email_with_haiku_safe(
                    email=msg,
                    user_id=user_id,
                    roles_context=roles_context,
                    available_labels=available_labels,
                )

                if haiku_result and haiku_result.analysis_method == "haiku":
                    # Store result for later use (action/rule suggestions)
                    haiku_results[msg.id] = haiku_result

                    # Convert to attention item if needed
                    item = _haiku_result_to_attention_item(msg, haiku_result)
                    if item:
                        attention_items.append(item)
                    processed_ids.add(msg.id)
                    continue
                elif haiku_result and haiku_result.skipped_reason:
                    # Haiku skipped due to privacy (sensitive domain)
                    logger.debug(f"Haiku skipped {msg.id}: {haiku_result.skipped_reason}")
                    # Fall through to profile/regex

    # 5. Fallback to profile/regex for remaining emails
    analyzer = EmailAnalyzer(email_account)
    for msg in messages:
        if msg.id in processed_ids:
            continue

        # Check not-actionable again (shouldn't happen but safety check)
        if matches_not_actionable(msg, account_not_actionable):
            continue

        # Try profile analysis first
        item = analyze_with_profile(
            email=msg,
            email_account=email_account,
            church_roles=church_roles,
            personal_contexts=personal_contexts,
            vip_senders=vip_senders,
            church_attention_patterns=church_attention_patterns,
            personal_attention_patterns=personal_attention_patterns,
            not_actionable_patterns=not_actionable_patterns,
        )

        if item:
            attention_items.append(item)
        else:
            # Last resort: regex analysis
            regex_item = analyzer._check_attention_needed(msg)
            if regex_item:
                regex_item.matched_role = None
                regex_item.confidence = 0.7
                regex_item.analysis_method = "regex"
                attention_items.append(regex_item)

    return attention_items, haiku_results


def get_haiku_usage_for_user() -> Dict:
    """Get GLOBAL Haiku usage summary.

    Convenience function for API endpoints.
    Usage is shared across all login identities.

    Returns:
        Dict with usage stats (dailyCount, weeklyCount, limits, etc.)
    """
    return get_haiku_usage_summary()


def _haiku_action_to_suggestion(
    email: EmailMessage,
    result: HaikuAnalysisResult,
    number: int,
    label_lookup: Dict[str, Dict[str, str]],
) -> Optional[EmailActionSuggestion]:
    """Convert HaikuActionResult to EmailActionSuggestion.

    Args:
        email: The analyzed email message.
        result: The Haiku analysis result.
        number: Suggestion number for ordering.
        label_lookup: Dict mapping label names to label info.

    Returns:
        EmailActionSuggestion if action is actionable, None otherwise.
    """
    action_result = result.action

    # Map Haiku action to EmailActionType
    action_map = {
        "archive": EmailActionType.ARCHIVE,
        "label": EmailActionType.LABEL,
        "star": EmailActionType.STAR,
        "delete": EmailActionType.DELETE,
        "keep": None,  # No action needed
    }

    action_type = action_map.get(action_result.action)
    if action_type is None:
        return None

    # Map confidence
    confidence = ConfidenceLevel.HIGH if result.confidence >= 0.8 else (
        ConfidenceLevel.MEDIUM if result.confidence >= 0.6 else ConfidenceLevel.LOW
    )

    # Build suggestion
    suggestion = EmailActionSuggestion(
        number=number,
        email=email,
        action=action_type,
        rationale=action_result.reason or "Suggested by AI analysis",
        confidence=confidence,
    )

    # Add label info if labeling
    if action_type == EmailActionType.LABEL and action_result.label_name:
        label_name_lower = action_result.label_name.lower()
        if label_name_lower in label_lookup:
            label_info = label_lookup[label_name_lower]
            suggestion.label_id = label_info.get("id")
            suggestion.label_name = label_info.get("name", action_result.label_name)
        else:
            suggestion.label_name = action_result.label_name

    return suggestion


def generate_action_suggestions_with_haiku(
    messages: List[EmailMessage],
    email_account: str,
    haiku_results: Dict[str, HaikuAnalysisResult],
    available_labels: Optional[List[Dict[str, str]]] = None,
) -> List[EmailActionSuggestion]:
    """Generate action suggestions using pre-computed Haiku results.

    This function uses Haiku analysis results from detect_attention_with_haiku()
    to generate intelligent action suggestions. For emails without Haiku results,
    it falls back to regex-based analysis.

    Args:
        messages: Messages to generate suggestions for.
        email_account: Email account being analyzed.
        haiku_results: Dict mapping email_id to HaikuAnalysisResult (from attention).
        available_labels: List of user's custom labels (id, name, color).

    Returns:
        List of numbered EmailActionSuggestion objects.
    """
    suggestions = []
    number = 1

    # Build label lookup
    label_lookup = {}
    if available_labels:
        for label in available_labels:
            label_lookup[label["name"].lower()] = label

    # System labels to ignore when checking for user labels
    SYSTEM_LABELS = {
        "INBOX", "UNREAD", "STARRED", "IMPORTANT", "SENT", "DRAFT",
        "SPAM", "TRASH", "CATEGORY_PERSONAL", "CATEGORY_SOCIAL",
        "CATEGORY_PROMOTIONS", "CATEGORY_UPDATES", "CATEGORY_FORUMS"
    }

    def has_user_label(email_labels: List[str]) -> bool:
        """Check if email has any user-defined label."""
        for lbl in email_labels:
            if lbl.startswith("Label_") or lbl not in SYSTEM_LABELS:
                return True
        return False

    analyzer = EmailAnalyzer(email_account)

    for msg in messages:
        # Skip emails that already have user-defined labels
        if has_user_label(msg.labels):
            continue

        # Try Haiku results first
        if msg.id in haiku_results:
            haiku_result = haiku_results[msg.id]
            suggestion = _haiku_action_to_suggestion(
                email=msg,
                result=haiku_result,
                number=number,
                label_lookup=label_lookup,
            )
            if suggestion:
                suggestions.append(suggestion)
                number += 1

            # Also check attention for task creation
            attention = haiku_result.attention
            if attention.needs_attention and attention.extracted_task:
                suggestions.append(EmailActionSuggestion(
                    number=number,
                    email=msg,
                    action=EmailActionType.CREATE_TASK,
                    rationale=attention.reason,
                    task_title=attention.extracted_task,
                    confidence=ConfidenceLevel.MEDIUM if attention.confidence >= 0.7 else ConfidenceLevel.LOW,
                ))
                number += 1

            continue  # Skip regex fallback for Haiku-analyzed emails

        # Fallback: Regex-based analysis (existing logic)
        content = (msg.subject + " " + msg.snippet).lower()

        # Check for old promotional emails - suggest archive
        age_hours = msg.age_hours()
        if age_hours > 72:  # Over 3 days old
            if analyzer._matches_patterns(content, analyzer.PROMOTIONAL_PATTERNS):
                suggestions.append(EmailActionSuggestion(
                    number=number,
                    email=msg,
                    action=EmailActionType.ARCHIVE,
                    rationale=f"Promotional email over {int(age_hours / 24)} days old",
                    confidence=ConfidenceLevel.HIGH,
                ))
                number += 1
                continue

        # Check for transactional emails - suggest labeling
        if analyzer._matches_patterns(content, analyzer.TRANSACTIONAL_PATTERNS):
            label_info = label_lookup.get("transactional")
            if label_info:
                suggestions.append(EmailActionSuggestion(
                    number=number,
                    email=msg,
                    action=EmailActionType.LABEL,
                    rationale="Appears to be a receipt/invoice/shipping notification",
                    label_id=label_info.get("id"),
                    label_name="Transactional",
                    confidence=ConfidenceLevel.HIGH,
                ))
                number += 1
                continue

        # Check for attention-worthy emails - suggest star
        attention = analyzer._check_attention_needed(msg)
        if attention and attention.urgency == "high":
            if not msg.is_starred:
                suggestions.append(EmailActionSuggestion(
                    number=number,
                    email=msg,
                    action=EmailActionType.STAR,
                    rationale=attention.reason,
                    confidence=ConfidenceLevel.MEDIUM,
                ))
                number += 1

            # Also suggest task creation if deadline detected
            if attention.extracted_task:
                suggestions.append(EmailActionSuggestion(
                    number=number,
                    email=msg,
                    action=EmailActionType.CREATE_TASK,
                    rationale=attention.reason,
                    task_title=attention.extracted_task,
                    confidence=ConfidenceLevel.MEDIUM,
                ))
                number += 1

        # Check for junk patterns - suggest delete
        if analyzer._matches_patterns(content, analyzer.JUNK_PATTERNS):
            suggestions.append(EmailActionSuggestion(
                number=number,
                email=msg,
                action=EmailActionType.DELETE,
                rationale="Appears to be junk/spam email",
                confidence=ConfidenceLevel.MEDIUM,
            ))
            number += 1
            continue

        # Limit suggestions
        if number > 20:
            break

    return suggestions


def _haiku_rule_to_suggestion(
    email: EmailMessage,
    result: HaikuAnalysisResult,
    email_account: str,
    available_labels: Optional[Set[str]] = None,
) -> Optional[RuleSuggestion]:
    """Convert HaikuRuleResult to RuleSuggestion.

    Args:
        email: The analyzed email message.
        result: The Haiku analysis result.
        email_account: Email account for the rule.
        available_labels: Set of label names available in this Gmail account.
            If provided, only suggests rules with labels that exist.

    Returns:
        RuleSuggestion if Haiku suggests a rule, None otherwise.
    """
    rule_result = result.rule

    if not rule_result.should_suggest:
        return None

    # Map pattern_type to FilterField
    field_map = {
        "sender": FilterField.SENDER_EMAIL.value,
        "subject": FilterField.EMAIL_SUBJECT.value,
        "content": FilterField.EMAIL_SUBJECT.value,  # Map content to subject for now
    }

    field = field_map.get(rule_result.pattern_type, FilterField.SENDER_EMAIL.value)

    # Determine operator based on pattern type
    operator = FilterOperator.CONTAINS.value

    # Determine category and action
    action_map = {
        "label": "Add",
        "archive": "Add",
        "star": "Add",
    }

    # Default to 1 Week Hold category if label action
    category = FilterCategory.ONE_WEEK_HOLD.value
    if rule_result.action == "label" and rule_result.label_name:
        # Try to map label to category
        label_to_category = {
            "promotional": FilterCategory.PROMOTIONAL.value,
            "transactional": FilterCategory.TRANSACTIONAL.value,
            "junk": FilterCategory.JUNK.value,
            "personal": FilterCategory.PERSONAL.value,
            "admin": FilterCategory.ADMIN.value,
        }
        category = label_to_category.get(
            rule_result.label_name.lower(),
            FilterCategory.ONE_WEEK_HOLD.value
        )

    # Validate category exists in available labels for this account
    if available_labels:
        if category not in available_labels:
            # Category/label doesn't exist in this account, skip suggestion
            return None

    # Map confidence to ConfidenceLevel
    confidence = ConfidenceLevel.HIGH if result.confidence >= 0.8 else (
        ConfidenceLevel.MEDIUM if result.confidence >= 0.6 else ConfidenceLevel.LOW
    )

    return RuleSuggestion(
        type=SuggestionType.NEW_LABEL,
        suggested_rule=FilterRule(
            email_account=email_account,
            order=1,  # Default order
            category=category,
            field=field,
            operator=operator,
            value=rule_result.pattern or email.from_address,
            action=action_map.get(rule_result.action, "Add"),
        ),
        confidence=confidence,
        reason=rule_result.reason or "Suggested by AI analysis",
        examples=[email.subject[:50]],
        email_count=1,
    )


def generate_rule_suggestions_with_haiku(
    messages: List[EmailMessage],
    email_account: str,
    haiku_results: Dict[str, HaikuAnalysisResult],
    existing_rules: Optional[List[FilterRule]] = None,
    available_labels: Optional[Set[str]] = None,
) -> List[RuleSuggestion]:
    """Generate filter rule suggestions using pre-computed Haiku results.

    This function uses Haiku analysis results from detect_attention_with_haiku()
    to generate intelligent rule suggestions. For emails without Haiku results,
    it falls back to pattern-based analysis.

    Args:
        messages: Messages to analyze for rule patterns.
        email_account: Email account being analyzed.
        haiku_results: Dict mapping email_id to HaikuAnalysisResult (from attention).
        existing_rules: Current filter rules to avoid duplicates.
        available_labels: Set of label names available in this Gmail account.
            If provided, only suggests rules with labels that exist.

    Returns:
        List of RuleSuggestion objects.
    """
    suggestions: List[RuleSuggestion] = []
    seen_patterns: Set[str] = set()

    # Build set of existing patterns
    if existing_rules:
        for rule in existing_rules:
            seen_patterns.add(rule.value.lower())

    # Process Haiku results first
    for msg in messages:
        if msg.id in haiku_results:
            haiku_result = haiku_results[msg.id]
            suggestion = _haiku_rule_to_suggestion(
                email=msg,
                result=haiku_result,
                email_account=email_account,
                available_labels=available_labels,
            )
            if suggestion:
                pattern = suggestion.suggested_rule.value.lower()
                if pattern not in seen_patterns:
                    suggestions.append(suggestion)
                    seen_patterns.add(pattern)

    # Fallback: Use EmailAnalyzer for pattern-based analysis
    analyzer = EmailAnalyzer(email_account, existing_rules)

    # Filter messages that weren't analyzed by Haiku
    non_haiku_messages = [m for m in messages if m.id not in haiku_results]

    if non_haiku_messages:
        regex_suggestions, _ = analyzer.analyze_messages(non_haiku_messages)

        # Add regex suggestions that aren't duplicates
        # Also validate category against available labels
        for suggestion in regex_suggestions:
            pattern = suggestion.suggested_rule.value.lower()
            if pattern not in seen_patterns:
                # Validate category if available_labels provided
                if available_labels:
                    if suggestion.suggested_rule.category not in available_labels:
                        continue  # Skip if label doesn't exist
                suggestions.append(suggestion)
                seen_patterns.add(pattern)

    # Deduplicate and limit
    return suggestions[:20]  # Limit to 20 suggestions
