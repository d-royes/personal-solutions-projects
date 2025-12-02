"""Contact search functionality using entity extraction and web search."""
from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Any

from ..smartsheet_client import TaskDetail


@dataclass
class ContactCard:
    """A structured contact card with confidence level."""
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    title: Optional[str] = None
    organization: Optional[str] = None
    location: Optional[str] = None
    source: str = "unknown"  # "task", "web_search", "validation"
    confidence: str = "low"  # "high", "medium", "low"
    source_url: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    def to_markdown(self) -> str:
        """Format contact as markdown for workspace."""
        lines = [f"📇 **{self.name}**"]
        if self.email:
            lines.append(f"📧 {self.email}")
        if self.phone:
            lines.append(f"📱 {self.phone}")
        if self.title and self.organization:
            lines.append(f"🏢 {self.organization} - {self.title}")
        elif self.organization:
            lines.append(f"🏢 {self.organization}")
        elif self.title:
            lines.append(f"💼 {self.title}")
        if self.location:
            lines.append(f"📍 {self.location}")
        
        source_text = f"Source: {self.source}"
        if self.source_url:
            source_text = f"Source: [{self.source}]({self.source_url})"
        lines.append(f"🔗 {source_text} | Confidence: {self.confidence.capitalize()}")
        
        return "\n".join(lines)


@dataclass
class ExtractedEntity:
    """An entity extracted from task text."""
    name: str
    entity_type: str  # "person", "organization", "email", "phone"
    context: Optional[str] = None  # surrounding text for context
    

@dataclass
class ContactSearchResult:
    """Result of a contact search operation."""
    entities_found: List[ExtractedEntity] = field(default_factory=list)
    contacts: List[ContactCard] = field(default_factory=list)
    needs_confirmation: bool = False
    confirmation_message: Optional[str] = None
    search_performed: bool = False
    message: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "entitiesFound": [asdict(e) for e in self.entities_found],
            "contacts": [c.to_dict() for c in self.contacts],
            "needsConfirmation": self.needs_confirmation,
            "confirmationMessage": self.confirmation_message,
            "searchPerformed": self.search_performed,
            "message": self.message,
        }


# Common email pattern
EMAIL_PATTERN = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')

# Phone patterns (US-centric but flexible)
PHONE_PATTERN = re.compile(
    r'(?:\+?1[-.\s]?)?\(?[0-9]{3}\)?[-.\s]?[0-9]{3}[-.\s]?[0-9]{4}'
)


def extract_entities(task: TaskDetail, use_ai: bool = True) -> List[ExtractedEntity]:
    """Extract potential contact entities from task details.
    
    Looks for:
    - Email addresses
    - Phone numbers
    - Names (from "From:", "To:", common patterns)
    - Organizations
    - AI-powered extraction for names/orgs in prose text (when use_ai=True)
    
    Args:
        task: The task to extract entities from
        use_ai: Whether to use AI for enhanced entity extraction (default True)
    """
    entities: List[ExtractedEntity] = []
    seen_values: set = set()
    
    # Combine all text sources
    text_sources = [
        task.title or "",
        task.notes or "",
    ]
    full_text = "\n".join(text_sources)
    
    # Extract emails
    for match in EMAIL_PATTERN.finditer(full_text):
        email = match.group().lower()
        if email not in seen_values:
            seen_values.add(email)
            # Try to find associated name
            context = _get_context(full_text, match.start(), match.end())
            entities.append(ExtractedEntity(
                name=email,
                entity_type="email",
                context=context,
            ))
    
    # Extract phone numbers
    for match in PHONE_PATTERN.finditer(full_text):
        phone = match.group()
        normalized = re.sub(r'[^\d]', '', phone)
        if normalized not in seen_values and len(normalized) >= 10:
            seen_values.add(normalized)
            context = _get_context(full_text, match.start(), match.end())
            entities.append(ExtractedEntity(
                name=phone,
                entity_type="phone",
                context=context,
            ))
    
    # Extract names from common email patterns
    # "From: Name <email>" or "From: Name"
    from_pattern = re.compile(r'From:\s*([^<\n]+?)(?:\s*<|\s*\n|$)', re.IGNORECASE)
    for match in from_pattern.finditer(full_text):
        name = match.group(1).strip()
        # Clean up common artifacts
        name = re.sub(r'[\[\]"\'<>]', '', name).strip()
        if name and len(name) > 2 and name.lower() not in seen_values:
            # Skip if it looks like an email
            if '@' not in name and not name.startswith('http'):
                seen_values.add(name.lower())
                entities.append(ExtractedEntity(
                    name=name,
                    entity_type="person",
                    context=_get_context(full_text, match.start(), match.end()),
                ))
    
    # "To: Name" pattern
    to_pattern = re.compile(r'To:\s*([^<\n]+?)(?:\s*<|\s*\n|$)', re.IGNORECASE)
    for match in to_pattern.finditer(full_text):
        name = match.group(1).strip()
        name = re.sub(r'[\[\]"\'<>]', '', name).strip()
        if name and len(name) > 2 and name.lower() not in seen_values:
            if '@' not in name and not name.startswith('http'):
                seen_values.add(name.lower())
                entities.append(ExtractedEntity(
                    name=name,
                    entity_type="person",
                    context=_get_context(full_text, match.start(), match.end()),
                ))
    
    # Extract organization names from email domains
    for entity in list(entities):
        if entity.entity_type == "email":
            domain = entity.name.split('@')[1] if '@' in entity.name else None
            if domain and domain not in seen_values:
                # Skip common personal email domains
                personal_domains = {'gmail.com', 'yahoo.com', 'hotmail.com', 'outlook.com', 'icloud.com', 'aol.com'}
                if domain.lower() not in personal_domains:
                    seen_values.add(domain)
                    # Convert domain to org name guess
                    org_name = domain.split('.')[0].replace('-', ' ').title()
                    entities.append(ExtractedEntity(
                        name=org_name,
                        entity_type="organization",
                        context=f"Extracted from email domain: {domain}",
                    ))
    
    # If no person/org entities found and we have meaningful text, try AI extraction
    person_org_entities = [e for e in entities if e.entity_type in ("person", "organization")]
    if use_ai and not person_org_entities and len(full_text.strip()) > 20:
        ai_entities = _extract_entities_with_ai(full_text, seen_values)
        entities.extend(ai_entities)
    
    return entities


def _extract_entities_with_ai(text: str, seen_values: set) -> List[ExtractedEntity]:
    """Use AI to extract person and organization names from text.
    
    This is used as a fallback when regex-based extraction doesn't find anything.
    """
    import json
    
    try:
        from ..llm.anthropic_client import build_anthropic_client, resolve_config
        
        client = build_anthropic_client()
        config = resolve_config()
        
        system_prompt = """You are a named entity recognition system. Extract person names and organization names from the given text.

Return ONLY a JSON array with objects containing:
- "name": The full name of the person or organization
- "type": Either "person" or "organization"
- "context": A brief phrase showing where this name appears

Rules:
- Only extract actual names, not generic terms like "attorney" or "lawyer"
- Include law firms, companies, and organizations
- For people, use their full name as mentioned
- If no names are found, return an empty array: []

Example output:
[
  {"name": "Phil Revah", "type": "person", "context": "Phil Revah, who is well-regarded in real estate law"},
  {"name": "Lampert Law Firm", "type": "organization", "context": "the Lampert Law Firm come highly recommended"}
]"""

        response = client.messages.create(
            model=config.model,
            max_tokens=500,
            temperature=0,
            system=system_prompt,
            messages=[{
                "role": "user",
                "content": f"Extract person and organization names from this text:\n\n{text[:2000]}"  # Limit text length
            }],
        )
        
        # Extract text from response
        result_text = ""
        for block in response.content:
            if hasattr(block, 'text'):
                result_text += block.text
        
        if not result_text.strip():
            return []
        
        # Parse JSON response - find array in response
        json_match = re.search(r'\[[\s\S]*\]', result_text)
        if json_match:
            data = json.loads(json_match.group())
            entities = []
            for item in data:
                name = item.get("name", "").strip()
                entity_type = item.get("type", "").lower()
                context = item.get("context", "")
                
                if name and entity_type in ("person", "organization"):
                    if name.lower() not in seen_values:
                        seen_values.add(name.lower())
                        entities.append(ExtractedEntity(
                            name=name,
                            entity_type=entity_type,
                            context=context,
                        ))
            return entities
        
        return []
        
    except Exception as e:
        print(f"[Contact Search] AI entity extraction failed: {e}")
        return []


def _get_context(text: str, start: int, end: int, window: int = 50) -> str:
    """Get surrounding context for a match."""
    ctx_start = max(0, start - window)
    ctx_end = min(len(text), end + window)
    context = text[ctx_start:ctx_end].strip()
    # Clean up newlines
    context = re.sub(r'\s+', ' ', context)
    return context


def _build_contact_from_task_entities(
    entities: List[ExtractedEntity],
) -> List[ContactCard]:
    """Build contact cards from entities found in task (high confidence)."""
    contacts: List[ContactCard] = []
    
    # Group entities by likely association
    # For now, simple approach: if we have email + name from same context, combine them
    emails = [e for e in entities if e.entity_type == "email"]
    persons = [e for e in entities if e.entity_type == "person"]
    phones = [e for e in entities if e.entity_type == "phone"]
    orgs = [e for e in entities if e.entity_type == "organization"]
    
    # Try to match emails with names
    used_emails = set()
    used_names = set()
    
    for person in persons:
        # Look for email that might belong to this person
        matching_email = None
        for email_entity in emails:
            if email_entity.name in used_emails:
                continue
            # Check if name appears in email or context overlap
            name_parts = person.name.lower().split()
            email_lower = email_entity.name.lower()
            if any(part in email_lower for part in name_parts if len(part) > 2):
                matching_email = email_entity.name
                used_emails.add(email_entity.name)
                break
        
        # Find org from email domain if we have matching email
        org_name = None
        if matching_email:
            domain = matching_email.split('@')[1] if '@' in matching_email else None
            if domain:
                for org in orgs:
                    if domain.split('.')[0].lower() in org.name.lower():
                        org_name = org.name
                        break
        
        contact = ContactCard(
            name=person.name,
            email=matching_email,
            organization=org_name,
            source="task",
            confidence="high" if matching_email else "medium",
        )
        contacts.append(contact)
        used_names.add(person.name.lower())
    
    # Add remaining emails as contacts
    for email_entity in emails:
        if email_entity.name not in used_emails:
            # Try to extract name from email
            local_part = email_entity.name.split('@')[0]
            # Convert john.doe to John Doe
            name_guess = local_part.replace('.', ' ').replace('_', ' ').replace('-', ' ').title()
            
            # Get org from domain
            domain = email_entity.name.split('@')[1]
            org_name = None
            for org in orgs:
                if domain.split('.')[0].lower() in org.name.lower():
                    org_name = org.name
                    break
            
            contact = ContactCard(
                name=name_guess,
                email=email_entity.name,
                organization=org_name,
                source="task",
                confidence="high",  # Email directly from task
            )
            contacts.append(contact)
    
    return contacts


def search_contacts(
    task: TaskDetail,
    *,
    client: Optional[Any] = None,
    config: Optional[Any] = None,
) -> ContactSearchResult:
    """Search for contact information based on task details.
    
    1. Extract entities from task
    2. Build contacts from task data (high confidence)
    3. If needed, perform web search for additional info
    4. Return structured results
    
    Args:
        task: The task to search contacts for
        client: Optional Anthropic client for web search
        config: Optional Anthropic config
        
    Returns:
        ContactSearchResult with found contacts
    """
    from ..llm.anthropic_client import (
        build_anthropic_client,
        resolve_config,
        AnthropicError,
    )
    
    # Step 1: Extract entities
    entities = extract_entities(task)
    
    if not entities:
        return ContactSearchResult(
            entities_found=[],
            contacts=[],
            search_performed=False,
            message="No contact entities found in task details.",
        )
    
    # Check if we need confirmation (>3 entities)
    person_entities = [e for e in entities if e.entity_type == "person"]
    org_entities = [e for e in entities if e.entity_type == "organization"]
    searchable_entities = person_entities + org_entities
    
    if len(searchable_entities) > 10:
        entity_names = [e.name for e in searchable_entities[:6]]  # Show first 6
        return ContactSearchResult(
            entities_found=entities,
            contacts=[],
            needs_confirmation=True,
            confirmation_message=f"I found {len(searchable_entities)} potential contacts: {', '.join(entity_names)}{'...' if len(searchable_entities) > 6 else ''}. Should I search for all of them?",
            search_performed=False,
            message="Confirmation needed before searching.",
        )
    
    # Step 2: Build contacts from task entities (high confidence)
    task_contacts = _build_contact_from_task_entities(entities)
    
    # Step 3: Determine if web search is needed
    # Web search if we have persons/orgs without full contact info
    needs_web_search = False
    search_queries = []
    
    for contact in task_contacts:
        if not contact.email and not contact.phone:
            needs_web_search = True
            query = contact.name
            if contact.organization:
                query += f" {contact.organization}"
            query += " contact email"
            search_queries.append((contact, query))
    
    # Also search for orgs that aren't associated with a person
    for org in org_entities:
        org_has_contact = any(
            c.organization and org.name.lower() in c.organization.lower() 
            for c in task_contacts
        )
        if not org_has_contact:
            needs_web_search = True
            search_queries.append((None, f"{org.name} contact information"))
    
    # Step 4: Perform web search if needed
    if needs_web_search and search_queries:
        client = client or build_anthropic_client()
        config = config or resolve_config()
        
        for contact_or_none, query in search_queries[:5]:  # Limit to 5 searches
            try:
                web_results = _web_search_contact(query, client, config)
                if web_results and contact_or_none:
                    # Update existing contact with web results
                    if web_results.email and not contact_or_none.email:
                        contact_or_none.email = web_results.email
                        contact_or_none.source = "task + web_search"
                        contact_or_none.confidence = "medium"
                    if web_results.phone and not contact_or_none.phone:
                        contact_or_none.phone = web_results.phone
                    if web_results.title and not contact_or_none.title:
                        contact_or_none.title = web_results.title
                    if web_results.location and not contact_or_none.location:
                        contact_or_none.location = web_results.location
                    if web_results.source_url:
                        contact_or_none.source_url = web_results.source_url
                elif web_results:
                    # Add as new contact
                    web_results.confidence = "medium"
                    task_contacts.append(web_results)
            except Exception as e:
                print(f"[Contact Search] Web search failed for '{query}': {e}")
    
    # Build message
    entity_names = [e.name for e in entities if e.entity_type in ("person", "organization")]
    if entity_names:
        message = f"Found contacts for: {', '.join(entity_names[:5])}"
        if len(entity_names) > 5:
            message += f" (+{len(entity_names) - 5} more)"
    else:
        message = "Extracted contact information from task."
    
    return ContactSearchResult(
        entities_found=entities,
        contacts=task_contacts,
        search_performed=needs_web_search,
        message=message,
    )


def _web_search_contact(
    query: str,
    client: Any,
    config: Any,
) -> Optional[ContactCard]:
    """Perform web search for contact information."""
    from anthropic import APIStatusError
    
    system_prompt = """You are a contact information extractor. Given web search results, extract contact details.

Return ONLY a JSON object with these fields (use null for missing info):
{
    "name": "Full Name",
    "email": "email@example.com",
    "phone": "+1-555-123-4567",
    "title": "Job Title",
    "organization": "Company Name",
    "location": "City, State",
    "source_url": "https://source.url"
}

If no contact information is found, return: {"name": null}
Do not include any other text, just the JSON."""

    try:
        response = client.messages.create(
            model=config.model,
            max_tokens=500,
            temperature=0,
            system=system_prompt,
            tools=[{
                "type": "web_search_20250305",
                "name": "web_search",
                "max_uses": 1,
            }],
            messages=[{
                "role": "user",
                "content": f"Search for contact information: {query}"
            }],
        )
        
        # Extract text from response
        result_text = ""
        for block in response.content:
            if hasattr(block, 'text'):
                result_text += block.text
        
        if not result_text.strip():
            return None
        
        # Parse JSON response
        import json
        # Find JSON in response
        json_match = re.search(r'\{[^{}]*\}', result_text, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group())
            if data.get("name"):
                return ContactCard(
                    name=data["name"],
                    email=data.get("email"),
                    phone=data.get("phone"),
                    title=data.get("title"),
                    organization=data.get("organization"),
                    location=data.get("location"),
                    source="web_search",
                    source_url=data.get("source_url"),
                    confidence="medium",
                )
        
        return None
        
    except APIStatusError as e:
        print(f"[Contact Search] API error: {e}")
        return None
    except Exception as e:
        print(f"[Contact Search] Error parsing response: {e}")
        return None

