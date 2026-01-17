"""Migrate tasks from users/{email}/tasks/ to global/david/tasks/.

This script consolidates tasks from both email accounts into the new
global user path so tasks are accessible regardless of which Google
account David logs in with.

Run with:
    cd projects/daily-task-assistant
    $env:PYTHONPATH = "."
    python scripts/migrate_tasks_to_global.py
"""
from dotenv import load_dotenv
load_dotenv()

import firebase_admin
from firebase_admin import firestore

# Initialize Firebase
if not firebase_admin._apps:
    firebase_admin.initialize_app()

db = firestore.client()

# Source paths (old per-email structure)
SOURCE_EMAILS = [
    "david.a.royes@gmail.com",
    "davidroyes@southpointsda.org",
]

# Target path (new global structure)
TARGET_USER_ID = "david"


def migrate_tasks():
    """Migrate tasks from old per-email paths to global path."""
    
    target_collection = db.collection("global").document(TARGET_USER_ID).collection("tasks")
    
    # Track what we've migrated to avoid duplicates
    existing_ids = set()
    for doc in target_collection.stream():
        existing_ids.add(doc.id)
    
    print(f"Found {len(existing_ids)} existing tasks in global/{TARGET_USER_ID}/tasks/")
    print()
    
    total_migrated = 0
    total_skipped = 0
    total_duplicates = 0
    
    for email in SOURCE_EMAILS:
        print(f"Processing {email}...")
        source_collection = db.collection("users").document(email).collection("tasks")
        
        migrated = 0
        skipped = 0
        
        for doc in source_collection.stream():
            task_id = doc.id
            task_data = doc.to_dict()
            
            if task_id in existing_ids:
                # Already exists in target - skip
                skipped += 1
                total_duplicates += 1
                continue
            
            # Migrate to new location
            target_collection.document(task_id).set(task_data)
            existing_ids.add(task_id)
            migrated += 1
        
        print(f"  Migrated: {migrated}")
        print(f"  Skipped (already exists): {skipped}")
        total_migrated += migrated
        total_skipped += skipped
    
    print()
    print("=" * 50)
    print(f"Migration complete!")
    print(f"  Total migrated: {total_migrated}")
    print(f"  Total skipped (duplicates): {total_duplicates}")
    print(f"  Total in global/{TARGET_USER_ID}/tasks/: {len(existing_ids)}")
    
    return total_migrated, total_skipped


def verify_migration():
    """Verify the migration by counting tasks in the new location."""
    target_collection = db.collection("global").document(TARGET_USER_ID).collection("tasks")
    
    count = 0
    for _ in target_collection.stream():
        count += 1
    
    print(f"\nVerification: {count} tasks in global/{TARGET_USER_ID}/tasks/")
    return count


if __name__ == "__main__":
    print("Task Migration: users/{email}/tasks/ -> global/david/tasks/")
    print("=" * 50)
    print()
    
    migrated, skipped = migrate_tasks()
    verify_migration()
    
    print()
    print("Note: Old data at users/{email}/tasks/ is preserved.")
    print("You can manually delete it after verifying the migration.")
