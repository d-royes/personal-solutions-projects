#!/usr/bin/env python3
"""Test all 13 update_task actions against test tasks in Smartsheet.

Test tasks: "This is a test task for validating DATA's Smartsheet capabilities. #1-10"
"""
import requests
import json
from datetime import datetime, timedelta

BASE_URL = "http://localhost:8000"
HEADERS = {"X-User-Email": "david.a.royes@gmail.com", "Content-Type": "application/json"}

# Test task row IDs (from find_test_tasks.py output)
TEST_TASKS = {
    1: "3275614679142276",
    2: "4016883084758916", 
    3: "5594123924868996",
    4: "3250558913679236",
    5: "2917096579075972",
    6: "5361250798079876",
    7: "2712256703827844",
    8: "404656675032964",
    9: "4235350891237252",
    10: "2573586168483716",
}

def test_action(task_num: int, action: str, payload: dict, description: str):
    """Test an action on a specific task."""
    task_id = TEST_TASKS[task_num]
    url = f"{BASE_URL}/assist/{task_id}/update"
    
    # First call without confirmation (preview)
    preview_payload = {**payload, "confirmed": False}
    print(f"\n{'='*60}")
    print(f"TEST: {description}")
    print(f"Task: #{task_num} (ID: {task_id})")
    print(f"Action: {action}")
    print(f"Payload: {json.dumps(payload, indent=2)}")
    
    # Get preview
    resp = requests.post(url, headers=HEADERS, json=preview_payload)
    if resp.status_code != 200:
        print(f"❌ PREVIEW FAILED: {resp.status_code} - {resp.text}")
        return False
    
    preview = resp.json()
    print(f"Preview: {preview.get('preview', {}).get('description', 'N/A')}")
    
    if preview.get("status") != "pending_confirmation":
        print(f"❌ Expected pending_confirmation, got: {preview.get('status')}")
        return False
    
    # Now confirm
    confirm_payload = {**payload, "confirmed": True}
    resp = requests.post(url, headers=HEADERS, json=confirm_payload)
    if resp.status_code != 200:
        print(f"❌ EXECUTE FAILED: {resp.status_code} - {resp.text}")
        return False
    
    result = resp.json()
    if result.get("status") == "success":
        print(f"✅ SUCCESS: {result.get('message')}")
        return True
    else:
        print(f"❌ FAILED: {result}")
        return False


def run_all_tests():
    """Run all 13 action tests."""
    results = {}
    
    # 1. update_status (Task #1)
    results["update_status"] = test_action(
        1, "update_status",
        {"action": "update_status", "status": "In Progress"},
        "Update status to 'In Progress'"
    )
    
    # 2. update_priority (Task #2)
    results["update_priority"] = test_action(
        2, "update_priority",
        {"action": "update_priority", "priority": "Urgent"},
        "Update priority to 'Urgent'"
    )
    
    # 3. update_due_date (Task #3)
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    results["update_due_date"] = test_action(
        3, "update_due_date",
        {"action": "update_due_date", "due_date": tomorrow},
        f"Update due date to '{tomorrow}'"
    )
    
    # 4. add_comment (Task #4)
    results["add_comment"] = test_action(
        4, "add_comment",
        {"action": "add_comment", "comment": "Test comment from validation script"},
        "Add a test comment"
    )
    
    # 5. update_notes (Task #5)
    results["update_notes"] = test_action(
        5, "update_notes",
        {"action": "update_notes", "notes": "Test notes added by validation script"},
        "Update notes field"
    )
    
    # 6. update_number (Task #6)
    results["update_number"] = test_action(
        6, "update_number",
        {"action": "update_number", "number": 99},
        "Update task number to 99"
    )
    
    # 7. update_project (Task #7)
    results["update_project"] = test_action(
        7, "update_project",
        {"action": "update_project", "project": "Around The House"},
        "Move task to 'Around The House' project"
    )
    
    # 8. update_contact_flag (Task #8)
    results["update_contact_flag"] = test_action(
        8, "update_contact_flag",
        {"action": "update_contact_flag", "contact_flag": True},
        "Set contact flag to checked"
    )
    
    # 9. update_recurring (Task #9)
    results["update_recurring"] = test_action(
        9, "update_recurring",
        {"action": "update_recurring", "recurring": "M"},
        "Set recurring pattern to Monday"
    )
    
    # 10. update_task (title) (Task #10)
    results["update_task"] = test_action(
        10, "update_task",
        {"action": "update_task", "task_title": "RENAMED: Test task #10 - title updated by validation"},
        "Rename task title"
    )
    
    # 11. update_estimated_hours (Task #1 - reuse)
    results["update_estimated_hours"] = test_action(
        1, "update_estimated_hours",
        {"action": "update_estimated_hours", "estimated_hours": "2"},
        "Set estimated hours to 2"
    )
    
    # 12. update_assigned_to (Task #2 - reuse)
    results["update_assigned_to"] = test_action(
        2, "update_assigned_to",
        {"action": "update_assigned_to", "assigned_to": "david.a.royes@gmail.com"},
        "Assign task to david.a.royes@gmail.com"
    )
    
    # 13. mark_complete (Task #3 - last, since it removes from active list)
    # Skipping mark_complete to keep tasks available for more testing
    # results["mark_complete"] = test_action(
    #     3, "mark_complete",
    #     {"action": "mark_complete"},
    #     "Mark task as complete"
    # )
    print(f"\n{'='*60}")
    print("SKIPPING mark_complete to preserve test tasks")
    results["mark_complete"] = "SKIPPED"
    
    # Summary
    print(f"\n{'='*60}")
    print("TEST SUMMARY")
    print(f"{'='*60}")
    passed = sum(1 for v in results.values() if v is True)
    failed = sum(1 for v in results.values() if v is False)
    skipped = sum(1 for v in results.values() if v == "SKIPPED")
    
    for action, result in results.items():
        status = "✅ PASS" if result is True else ("⏭️ SKIP" if result == "SKIPPED" else "❌ FAIL")
        print(f"  {action}: {status}")
    
    print(f"\nTotal: {passed} passed, {failed} failed, {skipped} skipped")
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    exit(0 if success else 1)

