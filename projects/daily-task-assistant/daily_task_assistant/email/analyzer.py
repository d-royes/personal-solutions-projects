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
"""
from __future__ import annotations

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
    ATTENTION_PATTERNS = [
        (r"\?$", "Question asked"),
        (r"\bplease\s+\w+", "Request detected"),
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
    
    for msg in messages:
        content = (msg.subject + " " + msg.snippet).lower()
        
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

