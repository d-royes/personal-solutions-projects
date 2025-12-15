"""Haiku Intelligence Layer for email analysis.

Provides AI-powered email analysis using Claude 3.5 Haiku for:
- Attention detection (needs David's action?)
- Action suggestions (archive, label, star)
- Rule suggestions (filter patterns)

Includes privacy safeguards: domain blocklist and content masking.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

try:
    from anthropic import Anthropic, APIStatusError
except ModuleNotFoundError:
    Anthropic = None  # type: ignore
    APIStatusError = Exception  # type: ignore

from ..llm.anthropic_client import build_anthropic_client, AnthropicError


# =============================================================================
# Constants
# =============================================================================

HAIKU_MODEL = "claude-3-5-haiku-20241022"

# Domains that should NEVER be sent to Haiku (financial, government, healthcare)
SENSITIVE_DOMAINS = frozenset([
    # Banking
    "bankofamerica.com", "chase.com", "wellsfargo.com", "citibank.com",
    "usbank.com", "pnc.com", "capitalone.com", "ally.com", "discover.com",
    "americanexpress.com", "amex.com", "citi.com", "barclays.com",
    # Credit Unions
    "navyfederal.org", "usaa.com", "becu.org",
    # Investments
    "fidelity.com", "schwab.com", "vanguard.com", "etrade.com",
    "tdameritrade.com", "robinhood.com", "merrilledge.com", "edwardjones.com",
    # Payments
    "paypal.com", "venmo.com", "stripe.com", "square.com", "zelle.com",
    "cashapp.com", "wise.com", "remitly.com",
    # Government
    "irs.gov", "ssa.gov", "treasury.gov", "medicare.gov", "va.gov",
    "usa.gov", "state.gov", "dhs.gov",
    # Healthcare portals
    "mychart.com", "healthvault.com", "followmyhealth.com",
    "patient-portal.com", "myuhc.com", "anthem.com", "cigna.com",
    "aetna.com", "humana.com", "bluecrossma.com", "bcbs.com",
])

# Patterns to mask before sending content to Haiku
# IMPORTANT: Order matters! More specific patterns (with keywords) should come first.
CONTENT_MASK_PATTERNS: List[Tuple[re.Pattern, str]] = [
    # Credit card numbers (with/without spaces/dashes) - 16 digits
    (re.compile(r'\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b'), '[CARD-XXXX]'),
    # Routing numbers (explicitly labeled) - must come before SSN/account patterns
    (re.compile(r'(?i)routing[:\s#]*\d{9}'), '[ROUTING-XXXX]'),
    # Bank account references (explicitly labeled) - must come before generic account pattern
    (re.compile(r'(?i)account[:\s#]*\d{6,}'), '[ACCOUNT-XXXX]'),
    # SSN patterns (XXX-XX-XXXX with optional dashes)
    (re.compile(r'\b\d{3}[- ]?\d{2}[- ]?\d{4}\b'), '[SSN-XXXX]'),
    # Account numbers (9-12 consecutive digits) - generic fallback
    (re.compile(r'\b\d{9,12}\b'), '[ACCT-XXXX]'),
    # Passwords in plaintext
    (re.compile(r'(?i)password[:\s]*\S+'), '[PASSWORD-REDACTED]'),
    # API keys / tokens (common patterns - 20+ alphanumeric chars)
    (re.compile(r'(?i)(api[_-]?key|token|secret|bearer)[:\s]*[A-Za-z0-9_-]{20,}'), '[API-KEY-REDACTED]'),
    # AWS-style keys
    (re.compile(r'(?i)AKIA[A-Z0-9]{16}'), '[AWS-KEY-REDACTED]'),
]


# =============================================================================
# Response Dataclasses
# =============================================================================

@dataclass(slots=True)
class HaikuAttentionResult:
    """Result from Haiku attention analysis."""
    needs_attention: bool
    urgency: str  # "high" | "medium" | "low"
    reason: str
    suggested_action: str  # "Create task" | "Reply needed" | "Review" | "Archive"
    extracted_task: Optional[str] = None
    matched_role: Optional[str] = None
    confidence: float = 0.5


@dataclass(slots=True)
class HaikuActionResult:
    """Result from Haiku action suggestion."""
    action: str  # "archive" | "label" | "star" | "delete" | "keep"
    label_name: Optional[str] = None
    reason: str = ""
    confidence: float = 0.5


@dataclass(slots=True)
class HaikuRuleResult:
    """Result from Haiku rule suggestion."""
    should_suggest: bool
    pattern_type: Optional[str] = None  # "sender" | "subject" | "content"
    pattern: Optional[str] = None
    action: Optional[str] = None  # "label" | "archive" | "star"
    label_name: Optional[str] = None
    reason: str = ""
    confidence: float = 0.5


@dataclass(slots=True)
class HaikuAnalysisResult:
    """Combined result from unified Haiku analysis."""
    attention: HaikuAttentionResult
    action: HaikuActionResult
    rule: HaikuRuleResult
    confidence: float = 0.5
    analysis_method: str = "haiku"
    skipped_reason: Optional[str] = None  # Set if analysis was skipped


@dataclass(slots=True)
class PrivacySanitizeResult:
    """Result from privacy sanitization."""
    sanitized_content: str
    was_modified: bool
    masked_patterns: List[str] = field(default_factory=list)


# =============================================================================
# Privacy Safeguards
# =============================================================================

def is_sensitive_domain(email_address: str) -> bool:
    """Check if an email address belongs to a sensitive domain.

    Args:
        email_address: The sender's email address

    Returns:
        True if the domain is in the sensitive blocklist
    """
    if not email_address or "@" not in email_address:
        return False

    domain = email_address.lower().split("@")[-1]

    # Direct match
    if domain in SENSITIVE_DOMAINS:
        return True

    # Check for subdomains (e.g., mail.chase.com)
    for sensitive in SENSITIVE_DOMAINS:
        if domain.endswith(f".{sensitive}"):
            return True

    return False


def sanitize_content(content: str) -> PrivacySanitizeResult:
    """Sanitize email content by masking sensitive patterns.

    Args:
        content: The raw email content (subject, snippet, body)

    Returns:
        PrivacySanitizeResult with sanitized content and metadata
    """
    if not content:
        return PrivacySanitizeResult(
            sanitized_content="",
            was_modified=False,
            masked_patterns=[]
        )

    sanitized = content
    masked_patterns = []

    for pattern, replacement in CONTENT_MASK_PATTERNS:
        matches = pattern.findall(sanitized)
        if matches:
            # Track what we masked (without the actual values)
            masked_patterns.append(replacement.strip("[]"))
            sanitized = pattern.sub(replacement, sanitized)

    return PrivacySanitizeResult(
        sanitized_content=sanitized,
        was_modified=len(masked_patterns) > 0,
        masked_patterns=masked_patterns
    )


def prepare_email_for_haiku(
    sender: str,
    subject: str,
    snippet: str,
    body: Optional[str] = None
) -> Tuple[Optional[str], Optional[str]]:
    """Prepare email content for Haiku analysis with privacy safeguards.

    Args:
        sender: Sender email address
        subject: Email subject
        snippet: Email preview/snippet
        body: Full email body (optional)

    Returns:
        Tuple of (sanitized_content, skip_reason)
        If skip_reason is set, the email should not be sent to Haiku
    """
    # Check domain blocklist first (fast path)
    if is_sensitive_domain(sender):
        return None, f"Sensitive domain: {sender.split('@')[-1]}"

    # Sanitize content
    content_parts = []

    subject_result = sanitize_content(subject)
    content_parts.append(f"Subject: {subject_result.sanitized_content}")

    snippet_result = sanitize_content(snippet)
    content_parts.append(f"Preview: {snippet_result.sanitized_content}")

    if body:
        # Only use first 1000 chars of body to limit token usage
        body_result = sanitize_content(body[:1000])
        content_parts.append(f"Body excerpt: {body_result.sanitized_content}")

    return "\n".join(content_parts), None


# =============================================================================
# Haiku Prompt Templates
# =============================================================================

HAIKU_UNIFIED_PROMPT = """Analyze this email for David Royes and return a JSON object with your analysis.

DAVID'S ROLES AND RESPONSIBILITIES:
{roles_context}

AVAILABLE LABELS FOR ORGANIZATION:
{available_labels}

EMAIL TO ANALYZE:
From: {sender_name} <{sender_email}>
Date: {date}
{email_content}

Return ONLY a JSON object (no markdown, no explanation) with this exact structure:
{{
    "attention": {{
        "needs_attention": true or false,
        "urgency": "high" or "medium" or "low",
        "reason": "brief explanation",
        "suggested_action": "Create task" or "Reply needed" or "Review" or "Archive",
        "extracted_task": "suggested task title" or null,
        "matched_role": "which role this relates to" or null
    }},
    "action": {{
        "recommended": "archive" or "label" or "star" or "keep",
        "label_name": "suggested label" or null,
        "reason": "brief explanation"
    }},
    "rule": {{
        "should_suggest": true or false,
        "pattern_type": "sender" or "subject" or null,
        "pattern": "the pattern to match" or null,
        "reason": "why this rule would help" or null
    }},
    "confidence": 0.0 to 1.0
}}

GUIDELINES:
- needs_attention=true ONLY if David must personally act on this email
- High urgency: deadlines within 48h, urgent requests from VIPs, time-sensitive items
- Medium urgency: questions requiring response, action items with flexibility
- Low urgency: FYI items, newsletters worth reading, non-urgent updates
- Suggest archive for: newsletters already read, confirmations, receipts, FYI items
- Suggest label for: emails that fit a category/project but need to stay visible
- Suggest star for: important items David should revisit
- Only suggest rules for recurring patterns (would apply to future similar emails)
"""

DEFAULT_ROLES_CONTEXT = """
WORK (PGA TOUR):
- Business Solutions Team lead for Custom Dev, SaaS, CRM, BI projects
- Manages stakeholder relationships and vendor communications
- Handles Zendesk tickets and internal application support

CHURCH (Jacksonville Southpoint SDA):
- Elder and Lead Elder responsibilities
- Treasurer handling financial matters
- IT Lead, Procurement Lead, Maintenance Lead

PERSONAL:
- Family matters (wife Esther, sons Elijah & Daniel)
- Personal projects and household tasks
"""

DEFAULT_LABELS = """
Work: Atlassian, Zendesk, Stakeholder, Vendor, Team
Church: Treasury, Elder, IT, Maintenance, Events
Personal: Family, Shopping, Projects, Subscriptions
Categories: Transactional, Promotional, Newsletter, Important
"""


# =============================================================================
# Main Analysis Function
# =============================================================================

def analyze_email_with_haiku(
    sender_email: str,
    sender_name: str,
    subject: str,
    snippet: str,
    date: str,
    body: Optional[str] = None,
    roles_context: Optional[str] = None,
    available_labels: Optional[str] = None,
    *,
    client: Optional[Anthropic] = None,
) -> HaikuAnalysisResult:
    """Analyze an email using Claude 3.5 Haiku.

    Performs unified analysis returning attention, action, and rule suggestions
    in a single API call for efficiency.

    Args:
        sender_email: Sender's email address
        sender_name: Sender's display name
        subject: Email subject line
        snippet: Email preview text
        date: Email date string
        body: Optional full email body
        roles_context: Optional custom roles context (defaults to David's roles)
        available_labels: Optional custom labels list
        client: Optional pre-built Anthropic client

    Returns:
        HaikuAnalysisResult with attention, action, and rule analysis

    Raises:
        AnthropicError: If the API call fails
    """
    # Privacy check - prepare content or get skip reason
    sanitized_content, skip_reason = prepare_email_for_haiku(
        sender_email, subject, snippet, body
    )

    if skip_reason:
        # Return fallback result for sensitive emails
        return _create_fallback_result(skip_reason)

    # Build the prompt
    prompt = HAIKU_UNIFIED_PROMPT.format(
        roles_context=roles_context or DEFAULT_ROLES_CONTEXT,
        available_labels=available_labels or DEFAULT_LABELS,
        sender_name=sender_name or "Unknown",
        sender_email=sender_email,
        date=date or "Unknown",
        email_content=sanitized_content,
    )

    # Get or create client
    if client is None:
        client = build_anthropic_client()

    try:
        response = client.messages.create(
            model=HAIKU_MODEL,
            max_tokens=500,
            temperature=0.2,  # Low temperature for consistent analysis
            system="You are an email triage assistant. Respond with JSON only, no markdown fences.",
            messages=[{"role": "user", "content": prompt}],
        )
    except APIStatusError as exc:
        raise AnthropicError(f"Haiku API error: {exc}") from exc
    except Exception as exc:
        raise AnthropicError(f"Haiku request failed: {exc}") from exc

    # Extract and parse response
    text = _extract_response_text(response)
    data = _parse_haiku_response(text)

    return _build_analysis_result(data)


def _extract_response_text(response) -> str:
    """Extract text content from Anthropic response."""
    for block in getattr(response, "content", []):
        if getattr(block, "type", None) == "text":
            return getattr(block, "text", "").strip()
    raise AnthropicError("Haiku response did not contain text content.")


def _parse_haiku_response(text: str) -> Dict[str, Any]:
    """Parse JSON response from Haiku, handling markdown fences."""
    import json

    cleaned = text.strip()

    # Strip markdown code fences if present
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        # Remove first line (```json or ```) and last line (```)
        if len(lines) >= 2:
            cleaned = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as exc:
        # Log the error and return empty dict for fallback handling
        print(f"[WARN] Failed to parse Haiku response: {text[:200]}")
        raise AnthropicError(f"Invalid JSON from Haiku: {exc}") from exc


def _build_analysis_result(data: Dict[str, Any]) -> HaikuAnalysisResult:
    """Build HaikuAnalysisResult from parsed response data."""
    attention_data = data.get("attention", {})
    action_data = data.get("action", {})
    rule_data = data.get("rule", {})

    return HaikuAnalysisResult(
        attention=HaikuAttentionResult(
            needs_attention=bool(attention_data.get("needs_attention", False)),
            urgency=str(attention_data.get("urgency", "low")),
            reason=str(attention_data.get("reason", "")),
            suggested_action=str(attention_data.get("suggested_action", "Archive")),
            extracted_task=attention_data.get("extracted_task"),
            matched_role=attention_data.get("matched_role"),
            confidence=float(data.get("confidence", 0.5)),
        ),
        action=HaikuActionResult(
            action=str(action_data.get("recommended", "keep")),
            label_name=action_data.get("label_name"),
            reason=str(action_data.get("reason", "")),
            confidence=float(data.get("confidence", 0.5)),
        ),
        rule=HaikuRuleResult(
            should_suggest=bool(rule_data.get("should_suggest", False)),
            pattern_type=rule_data.get("pattern_type"),
            pattern=rule_data.get("pattern"),
            action=rule_data.get("action"),
            label_name=rule_data.get("label_name"),
            reason=str(rule_data.get("reason", "")),
            confidence=float(data.get("confidence", 0.5)),
        ),
        confidence=float(data.get("confidence", 0.5)),
        analysis_method="haiku",
    )


def _create_fallback_result(skip_reason: str) -> HaikuAnalysisResult:
    """Create a fallback result when Haiku analysis is skipped."""
    return HaikuAnalysisResult(
        attention=HaikuAttentionResult(
            needs_attention=False,
            urgency="low",
            reason="Analysis skipped - using profile/regex fallback",
            suggested_action="Review",
            confidence=0.0,
        ),
        action=HaikuActionResult(
            action="keep",
            reason="Analysis skipped - manual review recommended",
            confidence=0.0,
        ),
        rule=HaikuRuleResult(
            should_suggest=False,
            reason="Analysis skipped",
            confidence=0.0,
        ),
        confidence=0.0,
        analysis_method="skipped",
        skipped_reason=skip_reason,
    )
