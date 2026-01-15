"""Backfill fsid column in Smartsheet for existing synced tasks."""
from dotenv import load_dotenv
load_dotenv()

import os
import time

from daily_task_assistant.task_store import list_tasks
from daily_task_assistant.smartsheet_client import SmartsheetClient
from daily_task_assistant.config import Settings

settings = Settings(smartsheet_token=os.getenv('SMARTSHEET_API_TOKEN', ''))
client = SmartsheetClient(settings)

tasks = list_tasks('david.a.royes@gmail.com', limit=200)
synced_with_ss = [t for t in tasks if t.smartsheet_row_id and t.domain in ('personal', 'church')]

print(f'Backfilling fsid for {len(synced_with_ss)} tasks...')

count = 0
errors = 0
for task in synced_with_ss:
    try:
        client.update_row(
            task.smartsheet_row_id,
            {'fsid': task.id},
            source='personal'
        )
        count += 1
        if count % 10 == 0:
            print(f'  Updated {count} rows...')
            time.sleep(1)  # Rate limit protection
    except Exception as e:
        errors += 1
        print(f'  Error on task {task.id[:8]}...: {e}')

print(f'\nDone! Updated {count} rows, {errors} errors')
