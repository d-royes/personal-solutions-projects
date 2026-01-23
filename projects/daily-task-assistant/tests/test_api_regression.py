"""
Schemathesis-based API regression tests.

These tests automatically validate all API endpoints against the OpenAPI schema.
They catch contract violations, 500 errors, and schema mismatches.

Run with: pytest tests/test_api_regression.py -v
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

try:
    import schemathesis
    SCHEMATHESIS_AVAILABLE = True
except ImportError:
    SCHEMATHESIS_AVAILABLE = False
    schemathesis = None

if SCHEMATHESIS_AVAILABLE:
    from api.main import app
    from starlette.testclient import TestClient
    
    # Load schema from FastAPI app
    schema = schemathesis.openapi.from_asgi("/openapi.json", app)
    
    # Configure auth for all requests
    @schema.auth()
    class DevAuth:
        """Provide dev auth header for all Schemathesis requests."""
        
        def get(self, case, context):
            return "tester@example.com"
        
        def set(self, case, data, context):
            case.headers = case.headers or {}
            case.headers["X-User-Email"] = data
    
    @schema.parametrize()
    def test_api_contract(case):
        """
        Auto-generated test for each API endpoint.
        
        Schemathesis will:
        - Generate valid inputs based on the OpenAPI schema
        - Verify response status codes are expected
        - Validate response body against schema
        - Catch 500 errors and unhandled exceptions
        """
        # Skip endpoints that require live external services
        skip_patterns = [
            "/sync/now",  # Requires live Smartsheet
            "/email/analyze/",  # Requires live Gmail
            "/calendar/",  # Requires live Google Calendar (for most operations)
            "/inbox/",  # Requires live Gmail
            "/email/{account}/message",  # Requires live Gmail
            "/email/{account}/thread",  # Requires live Gmail
        ]
        
        for pattern in skip_patterns:
            if pattern in case.path:
                pytest.skip(f"Skipping {case.path} - requires live external service")
        
        # Use source=stub for task endpoints to avoid live Smartsheet calls
        if case.query:
            case.query["source"] = "stub"
        else:
            case.query = {"source": "stub"}
        
        case.call_and_validate()


@pytest.mark.skipif(not SCHEMATHESIS_AVAILABLE, reason="schemathesis not installed")
def test_schemathesis_available():
    """Verify Schemathesis is properly installed."""
    assert SCHEMATHESIS_AVAILABLE, "Install schemathesis: pip install schemathesis"


def test_openapi_schema_accessible():
    """Verify OpenAPI schema is accessible."""
    if not SCHEMATHESIS_AVAILABLE:
        pytest.skip("schemathesis not installed")
    
    from api.main import app
    from starlette.testclient import TestClient
    
    client = TestClient(app)
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    schema_data = resp.json()
    assert "paths" in schema_data
    assert "openapi" in schema_data
    # Verify we have a substantial number of endpoints
    path_count = len(schema_data["paths"])
    assert path_count >= 100, f"Expected 100+ endpoints, found {path_count}"
    print(f"OpenAPI schema has {path_count} paths")
