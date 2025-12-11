"""Gmail filter rules management via Google Sheets.

This module provides integration with the Gmail_Filter_Index Google Sheet
that controls Gmail App Script filter rules. DATA manages this sheet to
delegate email labeling work to App Script.

Sheet Structure:
- Email Account: Which Gmail account the rule applies to
- Order: Priority (1-7, lower = higher priority)
- Filter Category: The label/category to apply (1 Week Hold, Personal, etc.)
- Filter Field: What to match (Sender Email Address, Email Subject, Sender Email Name)
- Operator: How to match (Contains, Equals)
- Value: The pattern to match
- Action: Add, Remove, Edit, or blank (for existing rules)
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, asdict
from enum import Enum
from typing import List, Optional, Literal
from urllib import request as urlrequest
from urllib import error as urlerror
from urllib import parse as urlparse


# Gmail_Filter_Index sheet ID
FILTER_SHEET_ID = "1TcNDnFgdWk3GLf4Ponrim5YkWKbBVg9avcvPBmYXo9A"

# Google Sheets API endpoints
SHEETS_API_BASE = "https://sheets.googleapis.com/v4/spreadsheets"
TOKEN_URL = "https://oauth2.googleapis.com/token"


class SheetsError(RuntimeError):
    """Raised when Google Sheets operations fail."""


class FilterCategory(str, Enum):
    """Available filter categories matching Gmail labels."""
    
    ONE_WEEK_HOLD = "1 Week Hold"
    PERSONAL = "Personal"
    ADMIN = "Admin"
    TRANSACTIONAL = "Transactional"
    PROMOTIONAL = "Promotional"
    JUNK = "Junk"
    TRASH = "Trash"


class FilterField(str, Enum):
    """Fields that can be matched in filter rules."""
    
    SENDER_EMAIL = "Sender Email Address"
    EMAIL_SUBJECT = "Email Subject"
    SENDER_NAME = "Sender Email Name"


class FilterOperator(str, Enum):
    """Match operators for filter rules."""
    
    CONTAINS = "Contains"
    EQUALS = "Equals"


class FilterAction(str, Enum):
    """Actions for filter rules."""
    
    ADD = "Add"
    REMOVE = "Remove"
    EDIT = "Edit"
    NONE = ""  # Existing rule, no change


@dataclass(slots=True)
class FilterRule:
    """Represents a single email filter rule."""
    
    email_account: str
    order: int  # 1-7, priority
    category: str  # FilterCategory value
    field: str  # FilterField value
    operator: str  # FilterOperator value
    value: str  # The pattern to match
    action: str = ""  # FilterAction value, empty for existing rules
    row_number: Optional[int] = None  # Sheet row number (for updates)
    
    def to_row(self) -> List[str]:
        """Convert to sheet row values."""
        return [
            self.email_account,
            str(self.order),
            self.category,
            self.field,
            self.operator,
            self.value,
            self.action,
        ]
    
    @classmethod
    def from_row(cls, row: List[str], row_number: int) -> "FilterRule":
        """Create FilterRule from sheet row."""
        # Pad row to ensure we have all columns
        while len(row) < 7:
            row.append("")
        
        return cls(
            email_account=row[0].strip(),
            order=int(row[1]) if row[1].strip().isdigit() else 1,
            category=row[2].strip(),
            field=row[3].strip(),
            operator=row[4].strip(),
            value=row[5].strip(),
            action=row[6].strip() if len(row) > 6 else "",
            row_number=row_number,
        )
    
    def matches_email(
        self,
        sender_address: str,
        sender_name: str,
        subject: str,
    ) -> bool:
        """Check if this rule matches an email."""
        if self.field == FilterField.SENDER_EMAIL.value:
            target = sender_address.lower()
        elif self.field == FilterField.SENDER_NAME.value:
            target = sender_name.lower()
        elif self.field == FilterField.EMAIL_SUBJECT.value:
            target = subject.lower()
        else:
            return False
        
        pattern = self.value.lower()
        
        if self.operator == FilterOperator.CONTAINS.value:
            return pattern in target
        elif self.operator == FilterOperator.EQUALS.value:
            return pattern == target
        
        return False


class FilterRulesManager:
    """Manages filter rules via Google Sheets API.
    
    Uses the same OAuth credentials as Gmail for authentication.
    """
    
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        refresh_token: str,
        sheet_id: str = FILTER_SHEET_ID,
    ):
        """Initialize the manager.
        
        Args:
            client_id: OAuth client ID.
            client_secret: OAuth client secret.
            refresh_token: OAuth refresh token.
            sheet_id: Google Sheet ID (defaults to Gmail_Filter_Index).
        """
        self._client_id = client_id
        self._client_secret = client_secret
        self._refresh_token = refresh_token
        self._sheet_id = sheet_id
        self._access_token: Optional[str] = None
    
    @classmethod
    def from_env(cls, account_prefix: str = "PERSONAL") -> "FilterRulesManager":
        """Create manager from environment variables.
        
        Uses the Gmail OAuth credentials for the specified account.
        
        Args:
            account_prefix: Environment variable prefix (PERSONAL or CHURCH).
        """
        prefix = account_prefix.upper()
        client_id = os.getenv(f"{prefix}_GMAIL_CLIENT_ID")
        client_secret = os.getenv(f"{prefix}_GMAIL_CLIENT_SECRET")
        refresh_token = os.getenv(f"{prefix}_GMAIL_REFRESH_TOKEN")
        
        if not all([client_id, client_secret, refresh_token]):
            raise SheetsError(
                f"Missing OAuth credentials for {prefix}. "
                "Ensure GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET, and "
                "GMAIL_REFRESH_TOKEN environment variables are set."
            )
        
        return cls(
            client_id=client_id,
            client_secret=client_secret,
            refresh_token=refresh_token,
        )
    
    def _get_access_token(self) -> str:
        """Fetch a fresh access token using the refresh token."""
        payload = urlparse.urlencode({
            "client_id": self._client_id,
            "client_secret": self._client_secret,
            "refresh_token": self._refresh_token,
            "grant_type": "refresh_token",
        }).encode("utf-8")
        
        req = urlrequest.Request(
            TOKEN_URL,
            data=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        
        try:
            with urlrequest.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urlerror.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise SheetsError(f"Token request failed ({exc.code}): {detail}") from exc
        except urlerror.URLError as exc:
            raise SheetsError(f"Network error: {exc}") from exc
        
        token = data.get("access_token")
        if not token:
            raise SheetsError("Token response missing access_token.")
        
        self._access_token = token
        return token
    
    def _request(
        self,
        method: str,
        endpoint: str,
        body: Optional[dict] = None,
    ) -> dict:
        """Make an authenticated request to the Sheets API."""
        token = self._get_access_token()
        
        url = f"{SHEETS_API_BASE}/{self._sheet_id}/{endpoint}"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        
        data = json.dumps(body).encode("utf-8") if body else None
        req = urlrequest.Request(url, data=data, headers=headers, method=method)
        
        try:
            with urlrequest.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urlerror.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise SheetsError(f"Sheets API error ({exc.code}): {detail}") from exc
        except urlerror.URLError as exc:
            raise SheetsError(f"Network error: {exc}") from exc
    
    def get_all_rules(self) -> List[FilterRule]:
        """Get all filter rules from the sheet.
        
        Returns:
            List of FilterRule objects.
        """
        # Read all data from the sheet (assuming Sheet1 is the main sheet)
        endpoint = "values/Sheet1!A:G"
        result = self._request("GET", endpoint)
        
        values = result.get("values", [])
        if not values:
            return []
        
        rules = []
        # Skip header row (row 1)
        for i, row in enumerate(values[1:], start=2):
            if row and row[0].strip():  # Skip empty rows
                try:
                    rule = FilterRule.from_row(row, row_number=i)
                    rules.append(rule)
                except (ValueError, IndexError):
                    # Skip malformed rows
                    continue
        
        return rules
    
    def get_rules_for_account(self, email_account: str) -> List[FilterRule]:
        """Get filter rules for a specific email account.
        
        Args:
            email_account: Email address to filter by.
            
        Returns:
            List of FilterRule objects for that account.
        """
        all_rules = self.get_all_rules()
        return [
            rule for rule in all_rules
            if rule.email_account.lower() == email_account.lower()
        ]
    
    def get_rules_by_category(
        self,
        category: str,
        email_account: Optional[str] = None,
    ) -> List[FilterRule]:
        """Get rules for a specific category.
        
        Args:
            category: Category to filter by.
            email_account: Optional account filter.
            
        Returns:
            List of matching FilterRule objects.
        """
        rules = self.get_all_rules()
        
        if email_account:
            rules = [r for r in rules if r.email_account.lower() == email_account.lower()]
        
        return [r for r in rules if r.category.lower() == category.lower()]
    
    def add_rule(self, rule: FilterRule) -> FilterRule:
        """Add a new filter rule to the sheet.
        
        Args:
            rule: FilterRule to add.
            
        Returns:
            The added rule with row_number set.
        """
        endpoint = "values/Sheet1!A:G:append?valueInputOption=USER_ENTERED"
        body = {
            "values": [rule.to_row()]
        }
        
        result = self._request("POST", endpoint, body)
        
        # Extract the row number from the updated range
        updated_range = result.get("updates", {}).get("updatedRange", "")
        # Parse "Sheet1!A123:G123" to get row 123
        if "!" in updated_range and ":" in updated_range:
            row_part = updated_range.split("!")[1].split(":")[0]
            row_num = int("".join(c for c in row_part if c.isdigit()))
            rule.row_number = row_num
        
        return rule
    
    def update_rule(self, rule: FilterRule) -> FilterRule:
        """Update an existing filter rule.
        
        Args:
            rule: FilterRule with row_number set.
            
        Returns:
            The updated rule.
            
        Raises:
            SheetsError: If row_number is not set.
        """
        if not rule.row_number:
            raise SheetsError("Cannot update rule without row_number.")
        
        endpoint = f"values/Sheet1!A{rule.row_number}:G{rule.row_number}?valueInputOption=USER_ENTERED"
        body = {
            "values": [rule.to_row()]
        }
        
        self._request("PUT", endpoint, body)
        return rule
    
    def delete_rule(self, row_number: int) -> None:
        """Delete a filter rule by row number.
        
        Note: This clears the row content rather than deleting the row
        to avoid shifting row numbers for other rules.
        
        Args:
            row_number: Sheet row number to clear.
        """
        endpoint = f"values/Sheet1!A{row_number}:G{row_number}:clear"
        self._request("POST", endpoint)
    
    def sync_rules(self, rules: List[FilterRule], email_account: str) -> int:
        """Sync a list of rules for an account.
        
        This replaces all rules for the account with the provided list.
        
        Args:
            rules: New rules to sync.
            email_account: Account to sync rules for.
            
        Returns:
            Number of rules synced.
        """
        # Get current rules for this account
        current_rules = self.get_rules_for_account(email_account)
        current_row_numbers = {r.row_number for r in current_rules if r.row_number}
        
        # Clear existing rules for this account
        for row_num in current_row_numbers:
            self.delete_rule(row_num)
        
        # Add new rules
        for rule in rules:
            rule.email_account = email_account
            self.add_rule(rule)
        
        return len(rules)
    
    def find_matching_rules(
        self,
        sender_address: str,
        sender_name: str,
        subject: str,
        email_account: Optional[str] = None,
    ) -> List[FilterRule]:
        """Find all rules that match an email.
        
        Args:
            sender_address: Email sender address.
            sender_name: Email sender name.
            subject: Email subject.
            email_account: Optional account filter.
            
        Returns:
            List of matching rules sorted by priority (order).
        """
        if email_account:
            rules = self.get_rules_for_account(email_account)
        else:
            rules = self.get_all_rules()
        
        matching = [
            rule for rule in rules
            if rule.matches_email(sender_address, sender_name, subject)
        ]
        
        # Sort by order (priority)
        matching.sort(key=lambda r: r.order)
        return matching


# Convenience functions for simple operations

def get_filter_rules(
    email_account: Optional[str] = None,
    account_prefix: str = "PERSONAL",
) -> List[FilterRule]:
    """Get filter rules from the sheet.
    
    Args:
        email_account: Optional account to filter by.
        account_prefix: OAuth credentials prefix (PERSONAL or CHURCH).
        
    Returns:
        List of FilterRule objects.
    """
    manager = FilterRulesManager.from_env(account_prefix)
    
    if email_account:
        return manager.get_rules_for_account(email_account)
    return manager.get_all_rules()


def add_filter_rule(
    rule: FilterRule,
    account_prefix: str = "PERSONAL",
) -> FilterRule:
    """Add a new filter rule.
    
    Args:
        rule: FilterRule to add.
        account_prefix: OAuth credentials prefix.
        
    Returns:
        Added rule with row_number.
    """
    manager = FilterRulesManager.from_env(account_prefix)
    return manager.add_rule(rule)


def update_filter_rule(
    rule: FilterRule,
    account_prefix: str = "PERSONAL",
) -> FilterRule:
    """Update an existing filter rule.
    
    Args:
        rule: FilterRule with row_number set.
        account_prefix: OAuth credentials prefix.
        
    Returns:
        Updated rule.
    """
    manager = FilterRulesManager.from_env(account_prefix)
    return manager.update_rule(rule)


def delete_filter_rule(
    row_number: int,
    account_prefix: str = "PERSONAL",
) -> None:
    """Delete a filter rule by row number.
    
    Args:
        row_number: Sheet row to clear.
        account_prefix: OAuth credentials prefix.
    """
    manager = FilterRulesManager.from_env(account_prefix)
    manager.delete_rule(row_number)


def sync_rules_to_sheet(
    rules: List[FilterRule],
    email_account: str,
    account_prefix: str = "PERSONAL",
) -> int:
    """Sync rules to the sheet for an account.
    
    Args:
        rules: Rules to sync.
        email_account: Account to sync for.
        account_prefix: OAuth credentials prefix.
        
    Returns:
        Number of rules synced.
    """
    manager = FilterRulesManager.from_env(account_prefix)
    return manager.sync_rules(rules, email_account)

