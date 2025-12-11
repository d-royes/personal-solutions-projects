#!/usr/bin/env python3
"""Test that update_status handles Done checkbox correctly."""
import requests
import json

BASE_URL = "http://localhost:8000"
HEADERS = {"X-User-Email": "david.a.royes@gmail.com", "Content-Type": "application/json"}
task_id = "3275614679142276"  # Test task #1

# Test 1: update_status to 'Scheduled' (non-terminal - should NOT touch Done)
url = f"{BASE_URL}/assist/{task_id}/update"
payload = {"action": "update_status", "status": "Scheduled", "confirmed": True}
resp = requests.post(url, headers=HEADERS, json=payload)
print("Test 1: update_status to Scheduled (non-terminal)")
print(f"  HTTP Status: {resp.status_code}")
result = resp.json()
changes = result.get("changes", {})
print(f"  Changes: {changes}")
print(f"  Done in changes: {'done' in changes}")
test1_pass = "done" not in changes
print(f"  RESULT: {'✅ PASS' if test1_pass else '❌ FAIL'}")

print()

# Test 2: update_status to 'Cancelled' (terminal - SHOULD set Done=True)
payload = {"action": "update_status", "status": "Cancelled", "confirmed": True}
resp = requests.post(url, headers=HEADERS, json=payload)
print("Test 2: update_status to Cancelled (terminal)")
print(f"  HTTP Status: {resp.status_code}")
result = resp.json()
changes = result.get("changes", {})
print(f"  Changes: {changes}")
print(f"  Done set to True: {changes.get('done') == True}")
test2_pass = changes.get("done") == True
print(f"  RESULT: {'✅ PASS' if test2_pass else '❌ FAIL'}")

print()

# Reset to Scheduled for further testing
payload = {"action": "update_status", "status": "Scheduled", "confirmed": True}
resp = requests.post(url, headers=HEADERS, json=payload)
print("Reset: status back to Scheduled")
print(f"  Done: {resp.status_code == 200}")

print()
print("=" * 50)
print(f"SUMMARY: {'ALL TESTS PASSED' if test1_pass and test2_pass else 'SOME TESTS FAILED'}")

