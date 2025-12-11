"""Tests for Gmail filter rules management via Google Sheets.

This module tests the filter_rules module without requiring live Google Sheets
credentials by mocking the Sheets API responses.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from daily_task_assistant.sheets.filter_rules import (
    FilterRule,
    FilterCategory,
    FilterField,
    FilterOperator,
    FilterAction,
    FilterRulesManager,
    SheetsError,
    get_filter_rules,
    add_filter_rule,
)


# Test fixtures

@pytest.fixture
def sample_rule():
    """Create a sample filter rule."""
    return FilterRule(
        email_account="david.a.royes@gmail.com",
        order=5,
        category=FilterCategory.PROMOTIONAL.value,
        field=FilterField.SENDER_EMAIL.value,
        operator=FilterOperator.CONTAINS.value,
        value="@newsletter.com",
        action="Add",
        row_number=None,
    )


@pytest.fixture
def sample_sheet_data():
    """Sample Google Sheets API response with filter rules."""
    return {
        "values": [
            # Header row
            ["Email Account", "Order", "Filter Category", "Filter Field", "Operator", "Value", "Action"],
            # Data rows
            ["david.a.royes@gmail.com", "1", "1 Week Hold", "Sender Email Address", "Contains", "@bank.com", ""],
            ["david.a.royes@gmail.com", "2", "Personal", "Sender Email Address", "Equals", "friend@example.com", ""],
            ["david.a.royes@gmail.com", "5", "Promotional", "Sender Email Address", "Contains", "@marketing.com", ""],
            ["davidroyes@southpointsda.org", "1", "Admin", "Sender Email Address", "Contains", "@church.org", ""],
        ]
    }


@pytest.fixture
def mock_manager():
    """Create a FilterRulesManager with mocked credentials."""
    return FilterRulesManager(
        client_id="test-client-id",
        client_secret="test-client-secret",
        refresh_token="test-refresh-token",
    )


# Unit tests for FilterRule dataclass

class TestFilterRule:
    """Tests for FilterRule dataclass."""
    
    def test_to_row(self, sample_rule):
        row = sample_rule.to_row()
        
        assert row[0] == "david.a.royes@gmail.com"
        assert row[1] == "5"
        assert row[2] == "Promotional"
        assert row[3] == "Sender Email Address"
        assert row[4] == "Contains"
        assert row[5] == "@newsletter.com"
        assert row[6] == "Add"
    
    def test_from_row(self):
        row = ["david.a.royes@gmail.com", "3", "Admin", "Email Subject", "Contains", "URGENT", "Edit"]
        
        rule = FilterRule.from_row(row, row_number=5)
        
        assert rule.email_account == "david.a.royes@gmail.com"
        assert rule.order == 3
        assert rule.category == "Admin"
        assert rule.field == "Email Subject"
        assert rule.operator == "Contains"
        assert rule.value == "URGENT"
        assert rule.action == "Edit"
        assert rule.row_number == 5
    
    def test_from_row_handles_short_row(self):
        row = ["david@example.com", "1", "Personal"]  # Missing columns
        
        rule = FilterRule.from_row(row, row_number=10)
        
        assert rule.email_account == "david@example.com"
        assert rule.order == 1
        assert rule.category == "Personal"
        assert rule.field == ""
        assert rule.value == ""
    
    def test_from_row_handles_invalid_order(self):
        row = ["david@example.com", "invalid", "Personal", "", "", "", ""]
        
        rule = FilterRule.from_row(row, row_number=10)
        
        assert rule.order == 1  # Default to 1
    
    def test_matches_email_contains(self):
        rule = FilterRule(
            email_account="test@example.com",
            order=1,
            category="Personal",
            field="Sender Email Address",
            operator="Contains",
            value="@company.com",
        )
        
        assert rule.matches_email("john@company.com", "John", "Hello") is True
        assert rule.matches_email("john@other.com", "John", "Hello") is False
    
    def test_matches_email_equals(self):
        rule = FilterRule(
            email_account="test@example.com",
            order=1,
            category="Personal",
            field="Sender Email Address",
            operator="Equals",
            value="john@company.com",
        )
        
        assert rule.matches_email("john@company.com", "John", "Hello") is True
        assert rule.matches_email("jane@company.com", "Jane", "Hello") is False
    
    def test_matches_email_subject(self):
        rule = FilterRule(
            email_account="test@example.com",
            order=1,
            category="Admin",
            field="Email Subject",
            operator="Contains",
            value="urgent",
        )
        
        assert rule.matches_email("john@company.com", "John", "URGENT: Please respond") is True
        assert rule.matches_email("john@company.com", "John", "Hello") is False
    
    def test_matches_email_sender_name(self):
        rule = FilterRule(
            email_account="test@example.com",
            order=1,
            category="Personal",
            field="Sender Email Name",
            operator="Contains",
            value="john",
        )
        
        assert rule.matches_email("john@company.com", "John Doe", "Hello") is True
        assert rule.matches_email("jane@company.com", "Jane Doe", "Hello") is False
    
    def test_matches_email_case_insensitive(self):
        rule = FilterRule(
            email_account="test@example.com",
            order=1,
            category="Personal",
            field="Sender Email Address",
            operator="Contains",
            value="@Company.COM",
        )
        
        assert rule.matches_email("JOHN@COMPANY.COM", "John", "Hello") is True


class TestFilterCategory:
    """Tests for FilterCategory enum."""
    
    def test_category_values(self):
        assert FilterCategory.ONE_WEEK_HOLD.value == "1 Week Hold"
        assert FilterCategory.PERSONAL.value == "Personal"
        assert FilterCategory.ADMIN.value == "Admin"
        assert FilterCategory.TRANSACTIONAL.value == "Transactional"
        assert FilterCategory.PROMOTIONAL.value == "Promotional"
        assert FilterCategory.JUNK.value == "Junk"
        assert FilterCategory.TRASH.value == "Trash"


class TestFilterField:
    """Tests for FilterField enum."""
    
    def test_field_values(self):
        assert FilterField.SENDER_EMAIL.value == "Sender Email Address"
        assert FilterField.EMAIL_SUBJECT.value == "Email Subject"
        assert FilterField.SENDER_NAME.value == "Sender Email Name"


class TestFilterOperator:
    """Tests for FilterOperator enum."""
    
    def test_operator_values(self):
        assert FilterOperator.CONTAINS.value == "Contains"
        assert FilterOperator.EQUALS.value == "Equals"


# Tests for FilterRulesManager

class TestFilterRulesManager:
    """Tests for FilterRulesManager class."""
    
    @patch.object(FilterRulesManager, "_get_access_token")
    @patch.object(FilterRulesManager, "_request")
    def test_get_all_rules(self, mock_request, mock_token, mock_manager, sample_sheet_data):
        mock_token.return_value = "mock-token"
        mock_request.return_value = sample_sheet_data
        
        rules = mock_manager.get_all_rules()
        
        assert len(rules) == 4
        assert rules[0].category == "1 Week Hold"
        assert rules[1].category == "Personal"
        assert rules[2].category == "Promotional"
        assert rules[3].category == "Admin"
    
    @patch.object(FilterRulesManager, "_get_access_token")
    @patch.object(FilterRulesManager, "_request")
    def test_get_rules_for_account(self, mock_request, mock_token, mock_manager, sample_sheet_data):
        mock_token.return_value = "mock-token"
        mock_request.return_value = sample_sheet_data
        
        rules = mock_manager.get_rules_for_account("david.a.royes@gmail.com")
        
        assert len(rules) == 3
        assert all(r.email_account == "david.a.royes@gmail.com" for r in rules)
    
    @patch.object(FilterRulesManager, "_get_access_token")
    @patch.object(FilterRulesManager, "_request")
    def test_get_rules_by_category(self, mock_request, mock_token, mock_manager, sample_sheet_data):
        mock_token.return_value = "mock-token"
        mock_request.return_value = sample_sheet_data
        
        rules = mock_manager.get_rules_by_category("Personal")
        
        assert len(rules) == 1
        assert rules[0].value == "friend@example.com"
    
    @patch.object(FilterRulesManager, "_get_access_token")
    @patch.object(FilterRulesManager, "_request")
    def test_add_rule(self, mock_request, mock_token, mock_manager, sample_rule):
        mock_token.return_value = "mock-token"
        mock_request.return_value = {
            "updates": {
                "updatedRange": "Sheet1!A10:G10"
            }
        }
        
        result = mock_manager.add_rule(sample_rule)
        
        assert result.row_number == 10
        mock_request.assert_called_once()
    
    @patch.object(FilterRulesManager, "_get_access_token")
    @patch.object(FilterRulesManager, "_request")
    def test_update_rule(self, mock_request, mock_token, mock_manager, sample_rule):
        mock_token.return_value = "mock-token"
        mock_request.return_value = {}
        
        sample_rule.row_number = 5
        result = mock_manager.update_rule(sample_rule)
        
        assert result.row_number == 5
        mock_request.assert_called_once()
        call_args = mock_request.call_args
        assert "A5:G5" in call_args[0][1]
    
    @patch.object(FilterRulesManager, "_get_access_token")
    @patch.object(FilterRulesManager, "_request")
    def test_update_rule_without_row_number_raises(self, mock_request, mock_token, mock_manager, sample_rule):
        mock_token.return_value = "mock-token"
        
        # sample_rule has no row_number
        with pytest.raises(SheetsError):
            mock_manager.update_rule(sample_rule)
    
    @patch.object(FilterRulesManager, "_get_access_token")
    @patch.object(FilterRulesManager, "_request")
    def test_delete_rule(self, mock_request, mock_token, mock_manager):
        mock_token.return_value = "mock-token"
        mock_request.return_value = {}
        
        mock_manager.delete_rule(5)
        
        mock_request.assert_called_once()
        call_args = mock_request.call_args
        assert "A5:G5:clear" in call_args[0][1]
    
    @patch.object(FilterRulesManager, "_get_access_token")
    @patch.object(FilterRulesManager, "_request")
    def test_find_matching_rules(self, mock_request, mock_token, mock_manager, sample_sheet_data):
        mock_token.return_value = "mock-token"
        mock_request.return_value = sample_sheet_data
        
        rules = mock_manager.find_matching_rules(
            sender_address="news@marketing.com",
            sender_name="Marketing News",
            subject="Special Offer!",
        )
        
        assert len(rules) == 1
        assert rules[0].category == "Promotional"
    
    def test_from_env_raises_on_missing_credentials(self, monkeypatch):
        # Clear any existing env vars
        for key in ["PERSONAL_GMAIL_CLIENT_ID", "PERSONAL_GMAIL_CLIENT_SECRET", "PERSONAL_GMAIL_REFRESH_TOKEN"]:
            monkeypatch.delenv(key, raising=False)
        
        with pytest.raises(SheetsError):
            FilterRulesManager.from_env("PERSONAL")
    
    def test_from_env_success(self, monkeypatch):
        monkeypatch.setenv("PERSONAL_GMAIL_CLIENT_ID", "test-id")
        monkeypatch.setenv("PERSONAL_GMAIL_CLIENT_SECRET", "test-secret")
        monkeypatch.setenv("PERSONAL_GMAIL_REFRESH_TOKEN", "test-token")
        
        manager = FilterRulesManager.from_env("PERSONAL")
        
        assert manager._client_id == "test-id"
        assert manager._client_secret == "test-secret"
        assert manager._refresh_token == "test-token"


# Tests for convenience functions

class TestConvenienceFunctions:
    """Tests for module-level convenience functions."""
    
    @patch("daily_task_assistant.sheets.filter_rules.FilterRulesManager.from_env")
    def test_get_filter_rules(self, mock_from_env):
        mock_manager = MagicMock()
        mock_manager.get_all_rules.return_value = []
        mock_from_env.return_value = mock_manager
        
        result = get_filter_rules()
        
        mock_manager.get_all_rules.assert_called_once()
    
    @patch("daily_task_assistant.sheets.filter_rules.FilterRulesManager.from_env")
    def test_get_filter_rules_for_account(self, mock_from_env):
        mock_manager = MagicMock()
        mock_manager.get_rules_for_account.return_value = []
        mock_from_env.return_value = mock_manager
        
        result = get_filter_rules(email_account="test@example.com")
        
        mock_manager.get_rules_for_account.assert_called_once_with("test@example.com")
    
    @patch("daily_task_assistant.sheets.filter_rules.FilterRulesManager.from_env")
    def test_add_filter_rule(self, mock_from_env, sample_rule):
        mock_manager = MagicMock()
        mock_manager.add_rule.return_value = sample_rule
        mock_from_env.return_value = mock_manager
        
        result = add_filter_rule(sample_rule)
        
        mock_manager.add_rule.assert_called_once_with(sample_rule)

