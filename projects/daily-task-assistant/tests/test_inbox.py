"""Tests for inbox reading functionality.

This module tests the inbox module without requiring live Gmail credentials
by mocking the Gmail API responses.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from daily_task_assistant.mailer.inbox import (
    EmailMessage,
    InboxSummary,
    _parse_email_address,
    _parse_email_date,
    _parse_message,
    get_inbox_summary,
    get_message,
    get_unread_messages,
    list_messages,
    search_messages,
)
from daily_task_assistant.mailer.gmail import GmailAccountConfig, GmailError


# Test fixtures

@pytest.fixture
def mock_account():
    """Create a mock Gmail account config."""
    return GmailAccountConfig(
        name="test",
        client_id="test-client-id",
        client_secret="test-client-secret",
        refresh_token="test-refresh-token",
        from_address="test@example.com",
    )


@pytest.fixture
def sample_message_data():
    """Sample Gmail API message response."""
    return {
        "id": "msg123",
        "threadId": "thread123",
        "labelIds": ["INBOX", "UNREAD", "IMPORTANT"],
        "snippet": "This is a preview of the email content...",
        "payload": {
            "headers": [
                {"name": "From", "value": "John Doe <john@example.com>"},
                {"name": "To", "value": "test@example.com"},
                {"name": "Subject", "value": "Test Subject Line"},
                {"name": "Date", "value": "Mon, 11 Dec 2025 10:30:00 -0500"},
            ]
        }
    }


@pytest.fixture
def sample_message_list():
    """Sample Gmail API messages list response."""
    return {
        "messages": [
            {"id": "msg1", "threadId": "thread1"},
            {"id": "msg2", "threadId": "thread2"},
            {"id": "msg3", "threadId": "thread3"},
        ]
    }


# Unit tests for parsing functions

class TestParseEmailAddress:
    """Tests for _parse_email_address function."""
    
    def test_parse_with_name_and_brackets(self):
        name, email = _parse_email_address("John Doe <john@example.com>")
        assert name == "John Doe"
        assert email == "john@example.com"
    
    def test_parse_with_quoted_name(self):
        name, email = _parse_email_address('"John Doe" <john@example.com>')
        assert name == "John Doe"
        assert email == "john@example.com"
    
    def test_parse_email_only(self):
        name, email = _parse_email_address("john@example.com")
        assert name == ""
        assert email == "john@example.com"
    
    def test_parse_empty_string(self):
        name, email = _parse_email_address("")
        assert name == ""
        assert email == ""


class TestParseEmailDate:
    """Tests for _parse_email_date function."""
    
    def test_parse_standard_format(self):
        date_str = "Mon, 11 Dec 2025 10:30:00 -0500"
        result = _parse_email_date(date_str)
        assert result.year == 2025
        assert result.month == 12
        assert result.day == 11
    
    def test_parse_iso_format(self):
        date_str = "2025-12-11T10:30:00+00:00"
        result = _parse_email_date(date_str)
        assert result.year == 2025
    
    def test_parse_invalid_returns_now(self):
        result = _parse_email_date("invalid date")
        # Should return a datetime close to now
        assert isinstance(result, datetime)


class TestParseMessage:
    """Tests for _parse_message function."""
    
    def test_parse_full_message(self, sample_message_data):
        msg = _parse_message(sample_message_data)
        
        assert msg.id == "msg123"
        assert msg.thread_id == "thread123"
        assert msg.from_address == "john@example.com"
        assert msg.from_name == "John Doe"
        assert msg.to_address == "test@example.com"
        assert msg.subject == "Test Subject Line"
        assert msg.snippet == "This is a preview of the email content..."
        assert msg.is_unread is True
        assert "IMPORTANT" in msg.labels
    
    def test_parse_minimal_message(self):
        data = {
            "id": "msg456",
            "payload": {"headers": []}
        }
        msg = _parse_message(data)
        
        assert msg.id == "msg456"
        assert msg.thread_id == "msg456"  # Falls back to id
        assert msg.from_address == ""
        assert msg.subject == ""


class TestEmailMessage:
    """Tests for EmailMessage dataclass."""
    
    def test_is_important_property(self):
        msg = EmailMessage(
            id="1",
            thread_id="1",
            from_address="test@example.com",
            from_name="Test",
            to_address="me@example.com",
            subject="Test",
            snippet="Test",
            date=datetime.now(timezone.utc),
            is_unread=False,
            labels=["INBOX", "IMPORTANT"],
        )
        assert msg.is_important is True
    
    def test_is_starred_property(self):
        msg = EmailMessage(
            id="1",
            thread_id="1",
            from_address="test@example.com",
            from_name="Test",
            to_address="me@example.com",
            subject="Test",
            snippet="Test",
            date=datetime.now(timezone.utc),
            is_unread=False,
            labels=["INBOX", "STARRED"],
        )
        assert msg.is_starred is True
    
    def test_age_hours(self):
        # Create a message from 2 hours ago
        from datetime import timedelta
        two_hours_ago = datetime.now(timezone.utc) - timedelta(hours=2)
        
        msg = EmailMessage(
            id="1",
            thread_id="1",
            from_address="test@example.com",
            from_name="Test",
            to_address="me@example.com",
            subject="Test",
            snippet="Test",
            date=two_hours_ago,
            is_unread=False,
            labels=[],
        )
        
        age = msg.age_hours()
        assert 1.9 < age < 2.1  # Allow small variance


# Integration tests with mocked API

class TestListMessages:
    """Tests for list_messages function."""
    
    @patch("daily_task_assistant.mailer.inbox._fetch_access_token")
    @patch("daily_task_assistant.mailer.inbox.urlrequest.urlopen")
    def test_list_messages_basic(
        self, mock_urlopen, mock_fetch_token, mock_account, sample_message_list
    ):
        mock_fetch_token.return_value = "mock-access-token"
        
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(sample_message_list).encode()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response
        
        result = list_messages(mock_account, max_results=10)
        
        assert len(result) == 3
        assert result[0]["id"] == "msg1"
    
    @patch("daily_task_assistant.mailer.inbox._fetch_access_token")
    @patch("daily_task_assistant.mailer.inbox.urlrequest.urlopen")
    def test_list_messages_with_query(
        self, mock_urlopen, mock_fetch_token, mock_account
    ):
        mock_fetch_token.return_value = "mock-access-token"
        
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({"messages": []}).encode()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response
        
        result = list_messages(mock_account, query="is:unread from:boss@company.com")
        
        # Verify URL contains the query
        call_args = mock_urlopen.call_args
        url = call_args[0][0].full_url
        assert "q=" in url
        assert "is%3Aunread" in url  # URL encoded
    
    @patch("daily_task_assistant.mailer.inbox._fetch_access_token")
    @patch("daily_task_assistant.mailer.inbox.urlrequest.urlopen")
    def test_list_messages_with_labels(
        self, mock_urlopen, mock_fetch_token, mock_account
    ):
        mock_fetch_token.return_value = "mock-access-token"
        
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({"messages": []}).encode()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response
        
        result = list_messages(mock_account, label_ids=["INBOX", "UNREAD"])
        
        call_args = mock_urlopen.call_args
        url = call_args[0][0].full_url
        assert "labelIds=INBOX" in url
        assert "labelIds=UNREAD" in url


class TestGetMessage:
    """Tests for get_message function."""
    
    @patch("daily_task_assistant.mailer.inbox._fetch_access_token")
    @patch("daily_task_assistant.mailer.inbox.urlrequest.urlopen")
    def test_get_message_returns_email_message(
        self, mock_urlopen, mock_fetch_token, mock_account, sample_message_data
    ):
        mock_fetch_token.return_value = "mock-access-token"
        
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(sample_message_data).encode()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response
        
        result = get_message(mock_account, "msg123")
        
        assert isinstance(result, EmailMessage)
        assert result.id == "msg123"
        assert result.subject == "Test Subject Line"


class TestGetInboxSummary:
    """Tests for get_inbox_summary function."""
    
    @patch("daily_task_assistant.mailer.inbox.get_message")
    @patch("daily_task_assistant.mailer.inbox.list_messages")
    def test_inbox_summary_structure(
        self, mock_list, mock_get, mock_account
    ):
        # Mock list_messages to return message refs
        mock_list.side_effect = [
            [{"id": "1"}, {"id": "2"}],  # unread
            [{"id": "1"}],  # important
            [{"id": "1"}, {"id": "2"}],  # recent
        ]
        
        # Mock get_message to return EmailMessage
        mock_msg = EmailMessage(
            id="1",
            thread_id="1",
            from_address="test@example.com",
            from_name="Test",
            to_address="me@example.com",
            subject="Test",
            snippet="Test",
            date=datetime.now(timezone.utc),
            is_unread=True,
            labels=["INBOX", "UNREAD"],
        )
        mock_get.return_value = mock_msg
        
        result = get_inbox_summary(mock_account)
        
        assert isinstance(result, InboxSummary)
        assert result.total_unread == 2
        assert result.unread_important == 1
    
    @patch("daily_task_assistant.mailer.inbox.get_message")
    @patch("daily_task_assistant.mailer.inbox.list_messages")
    def test_inbox_summary_with_vips(
        self, mock_list, mock_get, mock_account
    ):
        mock_list.return_value = [{"id": "1"}]
        
        mock_msg = EmailMessage(
            id="1",
            thread_id="1",
            from_address="boss@company.com",
            from_name="Boss",
            to_address="me@example.com",
            subject="Important",
            snippet="Test",
            date=datetime.now(timezone.utc),
            is_unread=True,
            labels=["INBOX", "UNREAD"],
        )
        mock_get.return_value = mock_msg
        
        result = get_inbox_summary(
            mock_account,
            vip_senders=["@company.com"],
        )
        
        assert result.unread_from_vips == 1
        assert len(result.vip_messages) == 1


class TestSearchMessages:
    """Tests for search_messages function."""
    
    @patch("daily_task_assistant.mailer.inbox.get_message")
    @patch("daily_task_assistant.mailer.inbox.list_messages")
    def test_search_returns_messages(
        self, mock_list, mock_get, mock_account
    ):
        mock_list.return_value = [{"id": "1"}, {"id": "2"}]
        
        mock_msg = EmailMessage(
            id="1",
            thread_id="1",
            from_address="test@example.com",
            from_name="Test",
            to_address="me@example.com",
            subject="Test",
            snippet="Test",
            date=datetime.now(timezone.utc),
            is_unread=False,
            labels=[],
        )
        mock_get.return_value = mock_msg
        
        result = search_messages(mock_account, "subject:urgent")
        
        assert len(result) == 2
        mock_list.assert_called_once_with(
            mock_account, max_results=20, query="subject:urgent"
        )


class TestGetUnreadMessages:
    """Tests for get_unread_messages function."""
    
    @patch("daily_task_assistant.mailer.inbox.get_message")
    @patch("daily_task_assistant.mailer.inbox.list_messages")
    def test_get_unread_builds_correct_query(
        self, mock_list, mock_get, mock_account
    ):
        mock_list.return_value = []
        
        get_unread_messages(mock_account, from_filter="@company.com")
        
        mock_list.assert_called_once()
        call_kwargs = mock_list.call_args[1]
        assert "is:unread" in call_kwargs["query"]
        assert "from:@company.com" in call_kwargs["query"]

