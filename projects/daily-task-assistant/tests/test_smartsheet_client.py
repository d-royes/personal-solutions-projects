"""Tests for SmartsheetClient write operations."""

from unittest.mock import MagicMock, patch
import pytest

from daily_task_assistant.smartsheet_client import (
    SmartsheetClient,
    SmartsheetAPIError,
)
from daily_task_assistant.config import Settings


@pytest.fixture
def mock_settings():
    """Create mock Settings for testing."""
    return Settings(smartsheet_token="test_token_123", environment="test")


@pytest.fixture
def mock_client(mock_settings):
    """Create a SmartsheetClient with mocked HTTP requests."""
    with patch.object(SmartsheetClient, "_request") as mock_request:
        client = SmartsheetClient(mock_settings)
        client._mock_request = mock_request
        yield client


class TestUpdateRow:
    """Tests for SmartsheetClient.update_row()"""

    def test_update_row_single_field(self, mock_client):
        """Test updating a single field."""
        mock_client._mock_request.return_value = {
            "result": [{"id": "123", "cells": []}]
        }

        result = mock_client.update_row("123", {"status": "Completed"})

        assert result == {"result": [{"id": "123", "cells": []}]}
        mock_client._mock_request.assert_called_once()
        call_args = mock_client._mock_request.call_args
        assert call_args[0][0] == "PUT"
        assert "/rows" in call_args[0][1]
        payload = call_args[1]["body"]
        assert payload[0]["id"] == 123
        assert any(c["value"] == "Completed" for c in payload[0]["cells"])

    def test_update_row_multiple_fields(self, mock_client):
        """Test updating multiple fields at once."""
        mock_client._mock_request.return_value = {"result": [{"id": "123"}]}

        result = mock_client.update_row("123", {
            "status": "Completed",
            "done": True,
            "priority": "Urgent",
        })

        call_args = mock_client._mock_request.call_args
        payload = call_args[1]["body"]
        cells = payload[0]["cells"]
        assert len(cells) == 3

    def test_update_row_empty_updates_raises(self, mock_client):
        """Test that empty updates dict raises ValueError."""
        with pytest.raises(ValueError, match="No updates provided"):
            mock_client.update_row("123", {})

    def test_update_row_unknown_field_raises(self, mock_client):
        """Test that unknown field name raises ValueError."""
        with pytest.raises(ValueError, match="Unknown field"):
            mock_client.update_row("123", {"nonexistent_field": "value"})

    def test_update_row_invalid_status_raises(self, mock_client):
        """Test that invalid status value raises ValueError."""
        with pytest.raises(ValueError, match="Invalid value"):
            mock_client.update_row("123", {"status": "InvalidStatus"})

    def test_update_row_invalid_priority_raises(self, mock_client):
        """Test that invalid priority value raises ValueError."""
        with pytest.raises(ValueError, match="Invalid value"):
            mock_client.update_row("123", {"priority": "Super Urgent"})

    def test_update_row_api_error(self, mock_client):
        """Test that API errors are wrapped in SmartsheetAPIError."""
        mock_client._mock_request.side_effect = SmartsheetAPIError("API failed")

        with pytest.raises(SmartsheetAPIError, match="Failed to update row"):
            mock_client.update_row("123", {"status": "Completed"})


class TestMarkComplete:
    """Tests for SmartsheetClient.mark_complete()"""

    def test_mark_complete_sets_status_and_done(self, mock_client):
        """Test that mark_complete sets both Status and Done."""
        mock_client._mock_request.return_value = {"result": [{"id": "456"}]}

        result = mock_client.mark_complete("456")

        call_args = mock_client._mock_request.call_args
        payload = call_args[1]["body"]
        cells = payload[0]["cells"]

        # Should have exactly 2 cells: status and done
        assert len(cells) == 2

        # Find status and done cells
        status_cell = next((c for c in cells if c["value"] == "Completed"), None)
        done_cell = next((c for c in cells if c["value"] is True), None)

        assert status_cell is not None, "Status cell not found"
        assert done_cell is not None, "Done cell not found"

    def test_mark_complete_returns_response(self, mock_client):
        """Test that mark_complete returns the API response."""
        expected = {"result": [{"id": "789", "cells": []}]}
        mock_client._mock_request.return_value = expected

        result = mock_client.mark_complete("789")

        assert result == expected


class TestPostComment:
    """Tests for SmartsheetClient.post_comment()"""

    def test_post_comment_success(self, mock_client):
        """Test posting a comment to a row."""
        mock_client._mock_request.return_value = {"result": {"id": "comment123"}}

        # Should not raise
        mock_client.post_comment("123", "Test comment text")

        mock_client._mock_request.assert_called_once()
        call_args = mock_client._mock_request.call_args
        assert call_args[0][0] == "POST"
        assert "/discussions" in call_args[0][1]
        assert "123" in call_args[0][1]

    def test_post_comment_api_error(self, mock_client):
        """Test that API errors are wrapped properly."""
        mock_client._mock_request.side_effect = SmartsheetAPIError("API failed")

        with pytest.raises(SmartsheetAPIError, match="Failed to post comment"):
            mock_client.post_comment("123", "Test")

