"""Backfill fsid column in Smartsheet for existing synced tasks.

Supports both personal/church and work domains.
Usage:
    python backfill_fsid.py          # Backfill personal/church (default)
    python backfill_fsid.py work     # Backfill work sheet
    python backfill_fsid.py all      # Backfill all sheets
"""
from dotenv import load_dotenv
load_dotenv()

import os
import sys
import time

from daily_task_assistant.task_store import list_tasks
from daily_task_assistant.smartsheet_client import SmartsheetClient
from daily_task_assistant.config import Settings

settings = Settings(smartsheet_token=os.getenv('SMARTSHEET_API_TOKEN', ''))
client = SmartsheetClient(settings)

# Parse command line argument for domain
arg = sys.argv[1] if len(sys.argv) > 1 else 'personal'

tasks = list_tasks('david.a.royes@gmail.com', limit=500)

if arg == 'work':
    # Work domain only
    synced_with_ss = [t for t in tasks if t.smartsheet_row_id and t.domain == 'work']
    print(f'Backfilling fsid for {len(synced_with_ss)} WORK tasks...')
elif arg == 'all':
    # All domains
    synced_with_ss = [t for t in tasks if t.smartsheet_row_id]
    print(f'Backfilling fsid for {len(synced_with_ss)} tasks (all domains)...')
else:
    # Personal/church (default)
    synced_with_ss = [t for t in tasks if t.smartsheet_row_id and t.domain in ('personal', 'church')]
    print(f'Backfilling fsid for {len(synced_with_ss)} personal/church tasks...')

count = 0
errors = 0
for task in synced_with_ss:
    # Determine source based on domain
    source = 'work' if task.domain == 'work' else 'personal'
    
    try:
        client.update_row(
            task.smartsheet_row_id,
            {'fsid': task.id},
            source=source
        )
        count += 1
        if count % 10 == 0:
            print(f'  Updated {count} rows...')
            time.sleep(1)  # Rate limit protection
    except Exception as e:
        errors += 1
        print(f'  Error on task {task.id[:8]}... (domain={task.domain}): {e}')

print(f'\nDone! Updated {count} rows, {errors} errors')
