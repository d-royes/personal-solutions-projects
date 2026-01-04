#!/usr/bin/env python3
"""Test mark_complete action."""
import requests
import json

BASE_URL = "http://localhost:8000"
HEADERS = {"X-User-Email": "david.a.royes@gmail.com", "Content-Type": "application/json"}
task_id = "5594123924868996"  # Test task #3

# Test mark_complete
url = f"{BASE_URL}/assist/{task_id}/update"
payload = {"action": "mark_complete", "confirmed": True}
resp = requests.post(url, headers=HEADERS, json=payload)
print(f"Status: {resp.status_code}")
print(f"Response: {json.dumps(resp.json(), indent=2)}")

