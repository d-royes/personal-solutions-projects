"""Get the fsid column IDs from Smartsheet."""
from dotenv import load_dotenv
load_dotenv()

import os
import requests
import yaml

token = os.getenv('SMARTSHEET_API_TOKEN')
headers = {'Authorization': f'Bearer {token}'}

# Get sheet IDs from config
with open('config/smartsheet.yml', 'r') as f:
    config = yaml.safe_load(f)

personal_sheet_id = config['sheets']['personal']['id']
work_sheet_id = config['sheets']['work']['id']

print('=== Personal/Church Sheet (Task Manager) ===')
print(f'Sheet ID: {personal_sheet_id}')
resp = requests.get(f'https://api.smartsheet.com/2.0/sheets/{personal_sheet_id}/columns', headers=headers)
for col in resp.json().get('data', []):
    if 'fsid' in col['title'].lower():
        print(f"  Column: {col['title']} -> ID: {col['id']}")

print()
print('=== Work Sheet (Project Task Tracker) ===')
print(f'Sheet ID: {work_sheet_id}')
resp = requests.get(f'https://api.smartsheet.com/2.0/sheets/{work_sheet_id}/columns', headers=headers)
for col in resp.json().get('data', []):
    if 'fsid' in col['title'].lower():
        print(f"  Column: {col['title']} -> ID: {col['id']}")
