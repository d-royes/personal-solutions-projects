#!/usr/bin/env python3
"""Find test tasks for validation."""
import requests

resp = requests.get(
    'http://localhost:8000/tasks?source=live',
    headers={'X-User-Email': 'david.a.royes@gmail.com'}
)
data = resp.json()
print(f'Total tasks: {len(data["tasks"])}')

test_tasks = []
for t in data['tasks']:
    title = t['title'].lower()
    if 'test task' in title or 'validat' in title or 'smartsheet capabil' in title:
        test_tasks.append(t)
        print(f"{t['rowId']}: {t['title'][:80]} (Status: {t['status']})")

if not test_tasks:
    print("\nNo test tasks found. Showing first 15 tasks:")
    for t in data['tasks'][:15]:
        print(f"{t['rowId']}: {t['title'][:60]}...")

