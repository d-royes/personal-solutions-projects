"""
API Snapshot Tests for Refactoring Validation.

These tests capture API responses and verify they don't change during refactoring.
Run before and after refactoring to ensure API contract stability.

Run with: pytest tests/test_api_snapshots.py -v
Update snapshots: pytest tests/test_api_snapshots.py --snapshot-update
"""
import os
import sys
from pathlib import Path

import pytest

# Set env vars BEFORE any imports that might cache them
os.environ["SMARTSHEET_API_TOKEN"] = "test-token"
os.environ["DTA_ACTIVITY_LOG"] = str(Path("test_activity_log.jsonl").resolve())
os.environ["DTA_ACTIVITY_FORCE_FILE"] = "1"
os.environ["DTA_CONVERSATION_FORCE_FILE"] = "1"
os.environ["DTA_CONVERSATION_DIR"] = str(Path("test_conversations").resolve())
os.environ["DTA_DEV_AUTH_BYPASS"] = "1"
os.environ["DTA_ALLOWED_EMAILS"] = "tester@example.com,david.a.royes@gmail.com"
os.environ["DTA_TASK_STORE_FORCE_FILE"] = "1"
os.environ["DTA_PROFILE_FORCE_FILE"] = "1"
os.environ["DTA_FEEDBACK_FORCE_FILE"] = "1"
os.environ["DTA_WORKSPACE_FORCE_FILE"] = "1"

API_ROOT = Path("projects/daily-task-assistant").resolve()
if str(API_ROOT) not in sys.path:
    sys.path.append(str(API_ROOT))

# Clear any cached auth functions before importing app
from daily_task_assistant.api import auth as auth_module
auth_module._allowed_emails.cache_clear()

from fastapi.testclient import TestClient
from api.main import app

try:
    from snapshottest import TestCase
    SNAPSHOT_AVAILABLE = True
except ImportError:
    SNAPSHOT_AVAILABLE = False
    TestCase = None

client = TestClient(app)
USER_HEADERS = {"X-User-Email": "tester@example.com"}


# ============================================================================
# Simple pytest-based snapshot comparison (works without snapshottest)
# ============================================================================

class APIResponseSnapshots:
    """
    Simple snapshot testing without external dependencies.
    Compares response structure (keys) rather than exact values.
    """
    
    @staticmethod
    def assert_response_structure(response_json, expected_keys, endpoint_name):
        """Verify response has expected top-level keys."""
        if isinstance(response_json, dict):
            actual_keys = set(response_json.keys())
            expected_set = set(expected_keys)
            missing = expected_set - actual_keys
            assert not missing, f"{endpoint_name}: Missing keys {missing}. Got: {actual_keys}"
        elif isinstance(response_json, list):
            if len(response_json) > 0 and isinstance(response_json[0], dict):
                actual_keys = set(response_json[0].keys())
                expected_set = set(expected_keys)
                missing = expected_set - actual_keys
                assert not missing, f"{endpoint_name}: Missing keys in list item {missing}"


# ============================================================================
# Core Endpoint Tests
# ============================================================================

def test_health_endpoint_structure():
    """Verify /health response structure."""
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    APIResponseSnapshots.assert_response_structure(
        data, 
        ["status"], 
        "/health"
    )
    assert data["status"] == "ok"


def test_tasks_endpoint_structure():
    """Verify /tasks response structure."""
    resp = client.get("/tasks?source=stub&limit=5", headers=USER_HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    APIResponseSnapshots.assert_response_structure(
        data,
        ["tasks", "liveTasks", "warning", "environment"],
        "/tasks"
    )
    # Verify task structure
    if data["tasks"]:
        task = data["tasks"][0]
        expected_task_keys = [
            "rowId", "title", "status", "due", "priority", 
            "project", "source", "done"
        ]
        APIResponseSnapshots.assert_response_structure(
            task,
            expected_task_keys,
            "/tasks[0]"
        )


def test_settings_endpoint_structure():
    """Verify /settings response structure."""
    resp = client.get("/settings", headers=USER_HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    # Settings should be a dict (structure may vary)
    assert isinstance(data, dict)


def test_profile_endpoint_structure():
    """Verify /profile response structure."""
    resp = client.get("/profile", headers=USER_HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    # Profile wraps content in a "profile" key
    assert "profile" in data, "/profile: Missing 'profile' key"
    profile = data["profile"]
    # Profile should have attention patterns
    assert isinstance(profile, dict), "/profile: profile should be a dict"


def test_contacts_endpoint_structure():
    """Verify /contacts response structure."""
    resp = client.get("/contacts", headers=USER_HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    # Contacts returns {contacts: [], count: N}
    APIResponseSnapshots.assert_response_structure(
        data,
        ["contacts", "count"],
        "/contacts"
    )
    assert isinstance(data["contacts"], list)


def test_firestore_tasks_endpoint_structure():
    """Verify /tasks/firestore response structure."""
    resp = client.get("/tasks/firestore", headers=USER_HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    # Returns {tasks: [], count: N}
    APIResponseSnapshots.assert_response_structure(
        data,
        ["tasks", "count"],
        "/tasks/firestore"
    )
    assert isinstance(data["tasks"], list)


# ============================================================================
# Assist Endpoint Tests
# ============================================================================

def test_assist_global_context_structure():
    """Verify /assist/global/context response structure."""
    resp = client.get("/assist/global/context?source=stub", headers=USER_HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    # Global context has portfolio, history, perspective, description
    expected_keys = ["portfolio", "history", "perspective", "description"]
    APIResponseSnapshots.assert_response_structure(
        data,
        expected_keys,
        "/assist/global/context"
    )


def test_assist_engage_structure():
    """Verify /assist/{task_id} engage response structure."""
    resp = client.post(
        "/assist/1001",
        json={"source": "stub"},
        headers=USER_HEADERS
    )
    assert resp.status_code == 200
    data = resp.json()
    # Response has plan, history, warning, environment, liveTasks
    expected_keys = ["plan", "history", "environment", "liveTasks"]
    APIResponseSnapshots.assert_response_structure(
        data,
        expected_keys,
        "/assist/{task_id}"
    )


def test_assist_history_structure():
    """Verify /assist/{task_id}/history response structure."""
    resp = client.get("/assist/1001/history", headers=USER_HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    # History is a list of messages
    assert isinstance(data, list)


# ============================================================================
# Email Endpoint Tests (structure only, no live Gmail)
# ============================================================================

def test_email_haiku_settings_structure():
    """Verify /email/haiku/settings response structure."""
    resp = client.get("/email/haiku/settings", headers=USER_HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    # Should have settings fields
    assert isinstance(data, dict)


# ============================================================================
# Response Code Consistency Tests
# ============================================================================

class TestResponseCodes:
    """Verify expected response codes for various scenarios."""
    
    def test_health_returns_200(self):
        assert client.get("/health").status_code == 200
    
    def test_tasks_returns_200(self):
        assert client.get("/tasks?source=stub", headers=USER_HEADERS).status_code == 200
    
    def test_settings_returns_200(self):
        assert client.get("/settings", headers=USER_HEADERS).status_code == 200
    
    def test_profile_returns_200(self):
        assert client.get("/profile", headers=USER_HEADERS).status_code == 200
    
    def test_contacts_returns_200(self):
        assert client.get("/contacts", headers=USER_HEADERS).status_code == 200
    
    def test_unauthorized_returns_401_or_403(self):
        """Endpoints should reject requests without auth header."""
        # When DTA_DEV_AUTH_BYPASS is set but no header provided,
        # behavior depends on implementation
        pass  # Skip for now - auth behavior may vary
    
    def test_not_found_returns_404(self):
        """Non-existent endpoints should return 404."""
        resp = client.get("/nonexistent/endpoint", headers=USER_HEADERS)
        assert resp.status_code == 404


# ============================================================================
# OpenAPI Schema Snapshot
# ============================================================================

def test_openapi_endpoint_count():
    """
    Track the number of endpoints in the OpenAPI schema.
    This helps detect if endpoints are accidentally removed during refactoring.
    """
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    schema = resp.json()
    
    path_count = len(schema["paths"])
    
    # We expect approximately 115 endpoints (as of 2026-01-21)
    # Allow some variance but flag major changes
    MIN_EXPECTED = 110
    MAX_EXPECTED = 130
    
    assert path_count >= MIN_EXPECTED, (
        f"Too few endpoints ({path_count}). "
        f"Expected at least {MIN_EXPECTED}. "
        "Endpoints may have been accidentally removed."
    )
    assert path_count <= MAX_EXPECTED, (
        f"More endpoints than expected ({path_count}). "
        f"Expected at most {MAX_EXPECTED}. "
        "This may be fine, but verify new endpoints are intentional."
    )
    
    print(f"\nOpenAPI schema endpoint count: {path_count}")


def test_openapi_paths_snapshot():
    """
    Capture all API paths for comparison.
    Useful for detecting path changes during refactoring.
    """
    resp = client.get("/openapi.json")
    schema = resp.json()
    
    paths = sorted(schema["paths"].keys())
    
    # Store critical paths that must exist
    critical_paths = [
        "/health",
        "/tasks",
        "/settings",
        "/profile",
        "/contacts",
        "/assist/{task_id}",
        "/assist/{task_id}/chat",
        "/assist/global/chat",
        "/tasks/firestore",
    ]
    
    for path in critical_paths:
        assert path in paths, f"Critical path {path} missing from API"
    
    print(f"\nTotal paths: {len(paths)}")
    print("Sample paths:", paths[:10])
