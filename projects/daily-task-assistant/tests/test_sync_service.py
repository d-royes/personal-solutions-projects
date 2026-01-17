"""Tests for the SyncService - Smartsheet <-> Firestore bidirectional sync.

These tests use mocking for Smartsheet API calls and file-based storage
for Firestore to ensure reproducibility without live API calls.

Test Categories:
1. FSID Duplicate Prevention
2. Bidirectional Sync (SS->FS and FS->SS)
3. Orphan Detection and Tagging
4. Field Translation (status, priority, estimated_hours)
5. Sync Status Transitions
"""
from __future__ import annotations

import os
import pytest
import tempfile
import shutil
from datetime import datetime, date
from unittest.mock import MagicMock, patch
from typing import Dict, Any, List

# Set up file-based storage before imports
os.environ["DTA_TASK_STORE_FORCE_FILE"] = "1"

from daily_task_assistant.sync.service import (
    SyncService,
    SyncDirection,
    SyncResult,
    STATUS_MAP,
    REVERSE_STATUS_MAP,
    translate_smartsheet_to_firestore,
    translate_firestore_to_smartsheet,
    _translate_priority,
    _translate_estimated_hours,
    _normalize_priority,
)
from daily_task_assistant.task_store.store import (
    FirestoreTask,
    TaskStatus,
    SyncStatus,
    TaskPriority,
    TaskSource,
    create_task,
    get_task,
    update_task,
    delete_task,
    list_tasks,
)
from daily_task_assistant.tasks import TaskDetail
from daily_task_assistant.config import Settings


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def temp_task_dir(tmp_path):
    """Create a temporary directory for task storage."""
    task_dir = tmp_path / "task_store"
    task_dir.mkdir()
    old_dir = os.environ.get("DTA_TASK_STORE_DIR")
    os.environ["DTA_TASK_STORE_DIR"] = str(task_dir)
    yield task_dir
    if old_dir:
        os.environ["DTA_TASK_STORE_DIR"] = old_dir
    else:
        os.environ.pop("DTA_TASK_STORE_DIR", None)


@pytest.fixture
def mock_settings():
    """Create mock settings for SyncService."""
    return Settings(smartsheet_token="test-token")


@pytest.fixture
def mock_smartsheet_client():
    """Create a mock SmartsheetClient."""
    client = MagicMock()
    client.list_tasks.return_value = []
    client.find_by_fsid.return_value = None
    client.create_row.return_value = {"result": [{"id": "new-row-123"}]}
    client.update_row.return_value = {"result": [{"id": "updated"}]}
    return client


@pytest.fixture
def sync_service(mock_settings, mock_smartsheet_client):
    """Create a SyncService with mocked dependencies."""
    service = SyncService(mock_settings, user_email="test@example.com")
    service.smartsheet = mock_smartsheet_client
    return service


@pytest.fixture
def sample_smartsheet_task() -> TaskDetail:
    """Create a sample TaskDetail from Smartsheet."""
    return TaskDetail(
        row_id="12345",
        title="Test Task from Smartsheet",
        status="Scheduled",
        due=datetime(2026, 1, 20),
        priority="Standard",
        project="Sm. Projects & Tasks",
        assigned_to="test@example.com",
        estimated_hours=1.0,
        notes="Test notes",
        next_step=None,
        automation_hint="Standard task",
        source="personal",
        done=False,
        number=1.0,
        deadline=None,
        contact_flag=False,
        completed_on=None,
        recurring_pattern=None,
    )


@pytest.fixture
def sample_firestore_task(temp_task_dir) -> FirestoreTask:
    """Create a sample FirestoreTask in storage."""
    task = create_task(
        user_id="test@example.com",
        title="Test Task from Firestore",
        status=TaskStatus.SCHEDULED.value,
        priority="Standard",
        domain="personal",
        planned_date=date(2026, 1, 20),
        project="Sm. Projects & Tasks",
        notes="Test notes",
        estimated_hours=1.0,
        sync_status=SyncStatus.LOCAL_ONLY.value,
    )
    return task


# =============================================================================
# Field Translation Tests
# =============================================================================

class TestFieldTranslation:
    """Tests for field translation between Smartsheet and Firestore formats."""
    
    def test_status_map_covers_all_smartsheet_statuses(self):
        """Verify STATUS_MAP includes all expected Smartsheet status values."""
        expected_statuses = [
            "Scheduled", "Recurring", "On Hold", "In Progress", "Follow-up",
            "Awaiting Reply", "Delivered", "Create ZD Ticket", "Ticket Created",
            "Validation", "Needs Approval", "Cancelled", "Delegated", "Completed"
        ]
        for status in expected_statuses:
            assert status in STATUS_MAP, f"Missing status: {status}"
    
    def test_translate_priority_personal_domain(self):
        """Personal domain should use plain text priorities."""
        assert _translate_priority("Critical", "personal") == "Critical"
        assert _translate_priority("Standard", "personal") == "Standard"
        assert _translate_priority(None, "personal") == "Standard"
    
    def test_translate_priority_work_domain(self):
        """Work domain should use numbered priorities."""
        assert _translate_priority("Critical", "work") == "5-Critical"
        assert _translate_priority("Standard", "work") == "2-Standard"
        assert _translate_priority(None, "work") == "2-Standard"
    
    def test_translate_priority_work_format_passthrough(self):
        """Work format should pass through unchanged for work domain."""
        assert _translate_priority("5-Critical", "work") == "5-Critical"
        assert _translate_priority("2-Standard", "work") == "2-Standard"
    
    def test_translate_priority_work_to_personal(self):
        """Work format should convert to personal format for personal domain."""
        assert _translate_priority("5-Critical", "personal") == "Critical"
        assert _translate_priority("2-Standard", "personal") == "Standard"
    
    def test_normalize_priority_from_work_format(self):
        """Work format priorities should normalize to plain text."""
        assert _normalize_priority("5-Critical") == "Critical"
        assert _normalize_priority("4-Urgent") == "Urgent"
        assert _normalize_priority("3-Important") == "Important"
        assert _normalize_priority("2-Standard") == "Standard"
        assert _normalize_priority("1-Low") == "Low"
    
    def test_normalize_priority_personal_format_unchanged(self):
        """Personal format priorities should remain unchanged."""
        assert _normalize_priority("Critical") == "Critical"
        assert _normalize_priority("Standard") == "Standard"
    
    def test_normalize_priority_default(self):
        """Unknown or empty priority should default to Standard."""
        assert _normalize_priority(None) == "Standard"
        assert _normalize_priority("") == "Standard"
        assert _normalize_priority("Unknown") == "Standard"
    
    def test_translate_estimated_hours_fractions(self):
        """Fractional hours should translate correctly."""
        assert _translate_estimated_hours(0.05) == ".05"
        assert _translate_estimated_hours(0.25) == ".25"
        assert _translate_estimated_hours(0.5) == ".50"
        assert _translate_estimated_hours(0.75) == ".75"
    
    def test_translate_estimated_hours_whole_numbers(self):
        """Whole number hours should translate correctly."""
        assert _translate_estimated_hours(1.0) == "1"
        assert _translate_estimated_hours(2.0) == "2"
        assert _translate_estimated_hours(8.0) == "8"
    
    def test_translate_estimated_hours_caps_at_8(self):
        """Hours above 8 should cap at 8."""
        assert _translate_estimated_hours(10.0) == "8"
        assert _translate_estimated_hours(100.0) == "8"
    
    def test_translate_estimated_hours_default(self):
        """None or zero hours should return None (preserve existing Smartsheet value)."""
        assert _translate_estimated_hours(None) is None
        assert _translate_estimated_hours(0) is None


class TestTranslateSmartsheetToFirestore:
    """Tests for translate_smartsheet_to_firestore function."""
    
    def test_basic_translation(self, sample_smartsheet_task):
        """Basic fields should translate correctly."""
        result = translate_smartsheet_to_firestore(sample_smartsheet_task)
        
        assert result["title"] == "Test Task from Smartsheet"
        assert result["status"] == TaskStatus.SCHEDULED.value
        assert result["priority"] == "Standard"
        assert result["domain"] == "personal"
        assert result["project"] == "Sm. Projects & Tasks"
        assert result["smartsheet_row_id"] == "12345"
    
    def test_church_domain_derivation(self, sample_smartsheet_task):
        """Tasks with 'Church Tasks' project should get church domain."""
        sample_smartsheet_task.project = "Church Tasks"
        result = translate_smartsheet_to_firestore(sample_smartsheet_task)
        assert result["domain"] == "church"
    
    def test_work_priority_normalization(self, sample_smartsheet_task):
        """Work-format priorities should normalize to plain text."""
        sample_smartsheet_task.priority = "5-Critical"
        result = translate_smartsheet_to_firestore(sample_smartsheet_task)
        assert result["priority"] == "Critical"


class TestTranslateFirestoreToSmartsheet:
    """Tests for translate_firestore_to_smartsheet function."""
    
    def test_basic_translation(self, sample_firestore_task):
        """Basic fields should translate correctly."""
        result = translate_firestore_to_smartsheet(sample_firestore_task)
        
        assert result["task"] == "Test Task from Firestore"
        assert result["status"] == "Scheduled"
        assert result["priority"] == "Standard"
        assert result["project"] == "Sm. Projects & Tasks"
    
    def test_work_domain_priority_translation(self, temp_task_dir):
        """Work domain should translate to numbered priorities."""
        task = create_task(
            user_id="test@example.com",
            title="Work Task",
            domain="work",
            priority="Critical",
            planned_date=date(2026, 1, 20),
            project="Daily Operations",
        )
        result = translate_firestore_to_smartsheet(task)
        assert result["priority"] == "5-Critical"


# =============================================================================
# FSID Duplicate Prevention Tests
# =============================================================================

class TestFSIDDuplicatePrevention:
    """Tests for FSID-based duplicate prevention logic."""
    
    def test_find_by_fsid_returns_row_id_when_exists(self, sync_service):
        """find_by_fsid should return row_id when fsid exists in Smartsheet."""
        sync_service.smartsheet.find_by_fsid.return_value = "existing-row-456"
        
        row_id = sync_service.smartsheet.find_by_fsid("fs-task-123", source="personal")
        
        assert row_id == "existing-row-456"
        sync_service.smartsheet.find_by_fsid.assert_called_once_with("fs-task-123", source="personal")
    
    def test_find_by_fsid_returns_none_when_not_exists(self, sync_service):
        """find_by_fsid should return None when fsid doesn't exist."""
        sync_service.smartsheet.find_by_fsid.return_value = None
        
        row_id = sync_service.smartsheet.find_by_fsid("nonexistent-id", source="personal")
        
        assert row_id is None
    
    def test_create_smartsheet_prevents_duplicate_when_fsid_exists(
        self, sync_service, sample_firestore_task, temp_task_dir
    ):
        """When fsid already exists in Smartsheet, should link instead of create."""
        # Setup: fsid already exists in Smartsheet
        sync_service.smartsheet.find_by_fsid.return_value = "existing-row-789"
        sync_service.user_email = "test@example.com"
        
        # Act: Try to create in Smartsheet
        sync_service._create_smartsheet_from_firestore(sample_firestore_task)
        
        # Assert: Should NOT call create_row
        sync_service.smartsheet.create_row.assert_not_called()
        
        # Assert: Firestore task should be linked to existing row
        updated_task = get_task("test@example.com", sample_firestore_task.id)
        assert updated_task.smartsheet_row_id == "existing-row-789"
        assert updated_task.sync_status == SyncStatus.SYNCED.value
    
    def test_create_smartsheet_creates_new_when_fsid_not_exists(
        self, sync_service, sample_firestore_task, temp_task_dir
    ):
        """When fsid doesn't exist, should create new row with fsid."""
        # Setup: fsid doesn't exist
        sync_service.smartsheet.find_by_fsid.return_value = None
        sync_service.user_email = "test@example.com"
        
        # Act: Create in Smartsheet
        sync_service._create_smartsheet_from_firestore(sample_firestore_task)
        
        # Assert: Should call create_row with fsid
        sync_service.smartsheet.create_row.assert_called_once()
        call_args = sync_service.smartsheet.create_row.call_args
        task_data = call_args[0][0]  # First positional argument
        assert "fsid" in task_data
        assert task_data["fsid"] == sample_firestore_task.id


# =============================================================================
# Orphan Detection Tests
# =============================================================================

class TestOrphanDetection:
    """Tests for orphan detection and tagging logic."""
    
    def test_detect_orphans_tags_missing_tasks(self, sync_service, temp_task_dir):
        """Tasks with SS row_ids not in SS should be tagged as orphaned."""
        # Setup: Create a task that appears to be synced
        task = create_task(
            user_id="test@example.com",
            title="Orphaned Task",
            domain="personal",
            smartsheet_row_id="deleted-row-999",
            sync_status=SyncStatus.SYNCED.value,
        )
        
        sync_service.user_email = "test@example.com"
        
        # Act: Detect orphans with empty SS row set (simulating deleted rows)
        ss_row_ids = set()  # Row was deleted from Smartsheet
        orphaned_count = sync_service._detect_and_tag_orphans(ss_row_ids, ["personal"])
        
        # Assert: Task should be tagged as orphaned
        assert orphaned_count == 1
        updated_task = get_task("test@example.com", task.id)
        assert updated_task.sync_status == SyncStatus.ORPHANED.value
        assert updated_task.attention_reason is not None
        assert "deleted" in updated_task.attention_reason.lower()
    
    def test_detect_orphans_preserves_valid_tasks(self, sync_service, temp_task_dir):
        """Tasks with valid SS row_ids should not be tagged."""
        # Setup: Create a task with a valid SS row_id
        task = create_task(
            user_id="test@example.com",
            title="Valid Task",
            domain="personal",
            smartsheet_row_id="valid-row-123",
            sync_status=SyncStatus.SYNCED.value,
        )
        
        sync_service.user_email = "test@example.com"
        
        # Act: Detect orphans with the valid row_id present
        ss_row_ids = {"valid-row-123"}
        orphaned_count = sync_service._detect_and_tag_orphans(ss_row_ids, ["personal"])
        
        # Assert: Task should NOT be tagged
        assert orphaned_count == 0
        updated_task = get_task("test@example.com", task.id)
        assert updated_task.sync_status == SyncStatus.SYNCED.value
    
    def test_detect_orphans_skips_already_orphaned(self, sync_service, temp_task_dir):
        """Already orphaned tasks should not be re-tagged."""
        # Setup: Create an already-orphaned task
        task = create_task(
            user_id="test@example.com",
            title="Already Orphaned",
            domain="personal",
            smartsheet_row_id="deleted-row-888",
            sync_status=SyncStatus.ORPHANED.value,
        )
        
        sync_service.user_email = "test@example.com"
        
        # Act: Detect orphans
        ss_row_ids = set()
        orphaned_count = sync_service._detect_and_tag_orphans(ss_row_ids, ["personal"])
        
        # Assert: Should not count as newly orphaned
        assert orphaned_count == 0
    
    def test_detect_orphans_skips_local_only_tasks(self, sync_service, temp_task_dir):
        """Local-only tasks (no SS row_id) should not be affected."""
        # Setup: Create a local-only task
        task = create_task(
            user_id="test@example.com",
            title="Local Only Task",
            domain="personal",
            sync_status=SyncStatus.LOCAL_ONLY.value,
        )
        
        sync_service.user_email = "test@example.com"
        
        # Act: Detect orphans
        ss_row_ids = set()
        orphaned_count = sync_service._detect_and_tag_orphans(ss_row_ids, ["personal"])
        
        # Assert: Should not be touched
        assert orphaned_count == 0
        updated_task = get_task("test@example.com", task.id)
        assert updated_task.sync_status == SyncStatus.LOCAL_ONLY.value


# =============================================================================
# Sync Status Transition Tests
# =============================================================================

class TestSyncStatusTransitions:
    """Tests for sync status state transitions."""
    
    def test_update_task_sets_pending_status(self, temp_task_dir):
        """Updating a synced task should set sync_status to pending."""
        # Setup: Create a synced task
        task = create_task(
            user_id="test@example.com",
            title="Synced Task",
            domain="personal",
            smartsheet_row_id="row-123",
            sync_status=SyncStatus.SYNCED.value,
        )
        
        # Act: Update the task
        updated = update_task(
            "test@example.com",
            task.id,
            {"title": "Updated Title"}
        )
        
        # Assert: sync_status should change to pending
        assert updated.sync_status == SyncStatus.PENDING.value
    
    def test_update_task_preserves_explicit_sync_status(self, temp_task_dir):
        """Explicit sync_status in updates should not be overridden."""
        # Setup: Create a synced task
        task = create_task(
            user_id="test@example.com",
            title="Synced Task",
            domain="personal",
            smartsheet_row_id="row-123",
            sync_status=SyncStatus.SYNCED.value,
        )
        
        # Act: Update with explicit sync_status
        updated = update_task(
            "test@example.com",
            task.id,
            {
                "title": "Updated Title",
                "sync_status": SyncStatus.SYNCED.value,  # Explicit
            }
        )
        
        # Assert: sync_status should remain as explicitly set
        assert updated.sync_status == SyncStatus.SYNCED.value
    
    def test_local_only_task_not_auto_pending(self, temp_task_dir):
        """Local-only tasks should not auto-transition to pending."""
        # Setup: Create a local-only task
        task = create_task(
            user_id="test@example.com",
            title="Local Task",
            domain="personal",
            sync_status=SyncStatus.LOCAL_ONLY.value,
        )
        
        # Act: Update the task
        updated = update_task(
            "test@example.com",
            task.id,
            {"title": "Updated Title"}
        )
        
        # Assert: sync_status should remain local_only
        assert updated.sync_status == SyncStatus.LOCAL_ONLY.value


# =============================================================================
# Bidirectional Sync Tests
# =============================================================================

class TestBidirectionalSync:
    """Tests for bidirectional sync operations."""
    
    def test_sync_smartsheet_to_firestore_creates_new_task(
        self, sync_service, sample_smartsheet_task, temp_task_dir
    ):
        """New SS task should create new FS task with correct mapping."""
        sync_service.smartsheet.list_tasks.return_value = [sample_smartsheet_task]
        sync_service.user_email = "test@example.com"
        
        # Act
        result = sync_service.sync_from_smartsheet(sources=["personal"])
        
        # Assert
        assert result.created == 1
        assert result.success
        
        # Verify task was created in Firestore
        tasks = list_tasks("test@example.com")
        assert len(tasks) == 1
        assert tasks[0].smartsheet_row_id == "12345"
        assert tasks[0].sync_status == SyncStatus.SYNCED.value
    
    def test_sync_smartsheet_to_firestore_updates_existing(
        self, sync_service, sample_smartsheet_task, temp_task_dir
    ):
        """Existing FS task should be updated from SS changes."""
        # Setup: Create existing task linked to SS
        existing = create_task(
            user_id="test@example.com",
            title="Old Title",
            domain="personal",
            smartsheet_row_id="12345",
            sync_status=SyncStatus.SYNCED.value,
        )
        
        # SS has updated title
        sample_smartsheet_task.title = "New Title from SS"
        sync_service.smartsheet.list_tasks.return_value = [sample_smartsheet_task]
        sync_service.user_email = "test@example.com"
        
        # Act
        result = sync_service.sync_from_smartsheet(sources=["personal"])
        
        # Assert
        assert result.updated == 1
        updated = get_task("test@example.com", existing.id)
        assert updated.title == "New Title from SS"
    
    def test_sync_firestore_to_smartsheet_creates_new_row(
        self, sync_service, sample_firestore_task, temp_task_dir
    ):
        """Local-only FS task should create new SS row."""
        sync_service.user_email = "test@example.com"
        sync_service.smartsheet.find_by_fsid.return_value = None
        
        # Act
        result = sync_service.sync_to_smartsheet()
        
        # Assert
        assert result.created == 1
        sync_service.smartsheet.create_row.assert_called_once()
    
    def test_sync_firestore_to_smartsheet_updates_existing_row(
        self, sync_service, temp_task_dir
    ):
        """Pending FS task should update existing SS row."""
        # Setup: Create a pending task with SS link
        task = create_task(
            user_id="test@example.com",
            title="Updated in Firestore",
            domain="personal",
            smartsheet_row_id="existing-row-123",
            sync_status=SyncStatus.PENDING.value,
        )
        
        sync_service.user_email = "test@example.com"
        
        # Act
        result = sync_service.sync_to_smartsheet()
        
        # Assert
        assert result.updated == 1
        sync_service.smartsheet.update_row.assert_called_once()


# =============================================================================
# Sync Status Summary Tests
# =============================================================================

class TestSyncStatusSummary:
    """Tests for get_sync_status method."""
    
    def test_get_sync_status_counts_all_statuses(self, sync_service, temp_task_dir):
        """get_sync_status should return counts for all sync statuses."""
        sync_service.user_email = "test@example.com"
        
        # Create tasks with various statuses
        create_task("test@example.com", "Synced 1", sync_status=SyncStatus.SYNCED.value)
        create_task("test@example.com", "Synced 2", sync_status=SyncStatus.SYNCED.value)
        create_task("test@example.com", "Pending", sync_status=SyncStatus.PENDING.value)
        create_task("test@example.com", "Local", sync_status=SyncStatus.LOCAL_ONLY.value)
        create_task("test@example.com", "Orphaned", sync_status=SyncStatus.ORPHANED.value)
        
        # Act
        status = sync_service.get_sync_status()
        
        # Assert
        assert status["total_tasks"] == 5
        assert status["synced"] == 2
        assert status["pending"] == 1
        assert status["local_only"] == 1
        assert status["orphaned"] == 1
        assert status["conflicts"] == 0
