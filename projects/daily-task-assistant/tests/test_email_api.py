"""Tests for email API endpoints.

This module tests the email-related API endpoints with mocked
Gmail and Sheets integrations.

Note: The email endpoints in main.py use lazy imports inside the functions,
so we need to mock the actual modules (daily_task_assistant.mailer, etc.)
rather than api.main attributes.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api.main import app
from daily_task_assistant.mailer.inbox import EmailMessage, InboxSummary
from daily_task_assistant.sheets.filter_rules import FilterRule


@pytest.fixture
def client():
    """Create test client with auth bypass."""
    with patch.dict("os.environ", {"DTA_DEV_AUTH_BYPASS": "1"}):
        yield TestClient(app)


@pytest.fixture
def auth_headers():
    """Headers for authenticated requests."""
    return {"X-User-Email": "david.a.royes@gmail.com"}


@pytest.fixture
def sample_email_message():
    """Create a sample EmailMessage for testing."""
    return EmailMessage(
        id="msg123",
        thread_id="thread123",
        from_address="sender@example.com",
        from_name="Sender Name",
        to_address="david.a.royes@gmail.com",
        subject="Test Subject",
        snippet="This is a test email...",
        date=datetime(2025, 12, 11, 10, 0, 0, tzinfo=timezone.utc),
        is_unread=True,
        labels=["INBOX", "UNREAD"],
    )


@pytest.fixture
def sample_inbox_summary(sample_email_message):
    """Create a sample InboxSummary for testing."""
    return InboxSummary(
        total_unread=5,
        unread_important=2,
        unread_from_vips=1,
        recent_messages=[sample_email_message],
        vip_messages=[],
    )


@pytest.fixture
def sample_filter_rules():
    """Create sample filter rules for testing."""
    return [
        FilterRule(
            email_account="david.a.royes@gmail.com",
            order=1,
            category="Personal",
            field="Sender Email Address",
            operator="Contains",
            value="@friend.com",
            action="",
            row_number=2,
        ),
        FilterRule(
            email_account="david.a.royes@gmail.com",
            order=5,
            category="Promotional",
            field="Sender Email Address",
            operator="Contains",
            value="@marketing.com",
            action="",
            row_number=3,
        ),
    ]


class TestInboxEndpoint:
    """Tests for GET /inbox/{account} endpoint."""
    
    @patch("daily_task_assistant.mailer.load_account_from_env")
    @patch("daily_task_assistant.mailer.get_inbox_summary")
    def test_inbox_summary_success(
        self, mock_get_summary, mock_load_account, client, auth_headers, sample_inbox_summary
    ):
        mock_account = MagicMock()
        mock_account.from_address = "david.a.royes@gmail.com"
        mock_load_account.return_value = mock_account
        mock_get_summary.return_value = sample_inbox_summary
        
        response = client.get("/inbox/personal", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data["total_unread"] == 5
        assert data["unread_important"] == 2
    
    @patch("daily_task_assistant.mailer.load_account_from_env")
    def test_inbox_missing_config(
        self, mock_load_account, client, auth_headers
    ):
        from daily_task_assistant.mailer import GmailError
        mock_load_account.side_effect = GmailError("Missing credentials")
        
        response = client.get("/inbox/personal", headers=auth_headers)
        
        assert response.status_code == 400
        assert "Gmail config error" in response.json()["detail"]


class TestUnreadEndpoint:
    """Tests for GET /inbox/{account}/unread endpoint."""
    
    @patch("daily_task_assistant.mailer.load_account_from_env")
    @patch("daily_task_assistant.mailer.get_unread_messages")
    def test_unread_messages_success(
        self,
        mock_get_unread,
        mock_load_account,
        client,
        auth_headers,
        sample_email_message,
    ):
        mock_account = MagicMock()
        mock_account.from_address = "david.a.royes@gmail.com"
        mock_load_account.return_value = mock_account
        mock_get_unread.return_value = [sample_email_message]
        
        response = client.get("/inbox/personal/unread", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["messages"]) == 1


class TestSearchEndpoint:
    """Tests for GET /inbox/{account}/search endpoint."""
    
    @patch("daily_task_assistant.mailer.load_account_from_env")
    @patch("daily_task_assistant.mailer.search_messages")
    def test_search_messages_success(
        self,
        mock_search,
        mock_load_account,
        client,
        auth_headers,
        sample_email_message,
    ):
        mock_account = MagicMock()
        mock_account.from_address = "david.a.royes@gmail.com"
        mock_load_account.return_value = mock_account
        mock_search.return_value = [sample_email_message]
        
        response = client.get(
            "/inbox/personal/search?query=is:unread",
            headers=auth_headers,
        )
        
        assert response.status_code == 200


class TestEmailRulesEndpoint:
    """Tests for /email/rules/{account} endpoints."""
    
    @patch("daily_task_assistant.sheets.FilterRulesManager.from_env")
    @patch("daily_task_assistant.mailer.load_account_from_env")
    def test_get_rules_success(
        self, mock_load_account, mock_from_env, client, auth_headers, sample_filter_rules
    ):
        mock_account = MagicMock()
        mock_account.from_address = "david.a.royes@gmail.com"
        mock_load_account.return_value = mock_account
        
        mock_manager = MagicMock()
        mock_manager.get_all_rules.return_value = sample_filter_rules
        mock_from_env.return_value = mock_manager
        
        response = client.get("/email/rules/personal", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert "rules" in data
    
    @patch("daily_task_assistant.sheets.FilterRulesManager.from_env")
    @patch("daily_task_assistant.mailer.load_account_from_env")
    def test_add_rule_success(
        self, mock_load_account, mock_from_env, client, auth_headers
    ):
        mock_account = MagicMock()
        mock_account.from_address = "david.a.royes@gmail.com"
        mock_load_account.return_value = mock_account
        
        mock_manager = MagicMock()
        mock_manager.add_rule.return_value = FilterRule(
            email_account="david.a.royes@gmail.com",
            order=5,
            category="Promotional",
            field="Sender Email Address",
            operator="Contains",
            value="@newmarketing.com",
            action="Add",
            row_number=10,
        )
        mock_from_env.return_value = mock_manager
        
        rule_data = {
            "order": 5,
            "category": "Promotional",
            "field": "Sender Email Address",
            "operator": "Contains",
            "value": "@newmarketing.com",
        }
        
        response = client.post(
            "/email/rules/personal",
            headers=auth_headers,
            json=rule_data,
        )
        
        assert response.status_code == 200
    
    @patch("daily_task_assistant.sheets.FilterRulesManager.from_env")
    def test_delete_rule_success(
        self, mock_from_env, client, auth_headers
    ):
        mock_manager = MagicMock()
        mock_from_env.return_value = mock_manager
        
        response = client.delete(
            "/email/rules/personal/5",
            headers=auth_headers,
        )
        
        assert response.status_code == 200


class TestAnalyzeEndpoint:
    """Tests for GET /email/analyze/{account} endpoint."""
    
    @patch("daily_task_assistant.email.EmailAnalyzer")
    @patch("daily_task_assistant.sheets.FilterRulesManager.from_env")
    @patch("daily_task_assistant.mailer.get_unread_messages")
    @patch("daily_task_assistant.mailer.load_account_from_env")
    def test_analyze_inbox_success(
        self,
        mock_load_account,
        mock_get_unread,
        mock_manager_from_env,
        mock_analyzer_class,
        client,
        auth_headers,
        sample_email_message,
    ):
        # Setup mocks
        mock_account = MagicMock()
        mock_account.from_address = "david.a.royes@gmail.com"
        mock_load_account.return_value = mock_account
        
        mock_get_unread.return_value = [sample_email_message]
        
        mock_manager = MagicMock()
        mock_manager.get_rules_for_account.return_value = []
        mock_manager_from_env.return_value = mock_manager
        
        mock_analyzer = MagicMock()
        mock_analyzer.analyze_messages.return_value = ([], [])
        mock_analyzer_class.return_value = mock_analyzer
        
        response = client.get("/email/analyze/personal", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert "suggestions" in data
        assert "attention_items" in data


class TestAuthRequirement:
    """Tests that endpoints require authentication."""
    
    def test_inbox_requires_auth(self, client):
        # No auth headers
        response = client.get("/inbox/personal")
        assert response.status_code == 401
    
    def test_email_rules_requires_auth(self, client):
        response = client.get("/email/rules/personal")
        assert response.status_code == 401
    
    def test_analyze_requires_auth(self, client):
        response = client.get("/email/analyze/personal")
        assert response.status_code == 401


class TestInvalidAccount:
    """Tests for invalid account handling."""
    
    @patch("daily_task_assistant.mailer.load_account_from_env")
    def test_invalid_account_returns_error(self, mock_load_account, client, auth_headers):
        from daily_task_assistant.mailer import GmailError
        mock_load_account.side_effect = GmailError("Missing env vars for 'invalid'")
        
        response = client.get("/inbox/invalid", headers=auth_headers)
        
        # Should return 400 with config error
        assert response.status_code == 400
