#!/usr/bin/env python3
"""Test script to check if Gmail OAuth has read permissions."""

import json
import os
import sys
from urllib import request as urlrequest
from urllib import error as urlerror

# Add parent to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from daily_task_assistant.mailer.gmail import load_account_from_env, _fetch_access_token


def test_inbox_read(account_name: str = "church"):
    """Test if we can read the inbox with existing OAuth credentials."""
    
    print(f"\n[EMAIL] Testing Gmail READ access for: {account_name}")
    print("=" * 50)
    
    # Load account config
    try:
        account = load_account_from_env(account_name)
        print(f"[OK] Loaded credentials for: {account.from_address}")
    except Exception as e:
        print(f"[FAIL] Failed to load credentials: {e}")
        return False
    
    # Get access token
    try:
        access_token = _fetch_access_token(account)
        print(f"[OK] Got access token: {access_token[:20]}...")
    except Exception as e:
        print(f"[FAIL] Failed to get access token: {e}")
        return False
    
    # Try to list messages (just get 5 recent ones)
    list_url = "https://gmail.googleapis.com/gmail/v1/users/me/messages?maxResults=5"
    headers = {
        "Authorization": f"Bearer {access_token}",
    }
    
    req = urlrequest.Request(list_url, headers=headers, method="GET")
    
    try:
        with urlrequest.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            messages = data.get("messages", [])
            print(f"[OK] Successfully listed {len(messages)} messages!")
            print(f"   Result size estimate: {data.get('resultSizeEstimate', 'N/A')}")
            
            # Try to read the first message
            if messages:
                msg_id = messages[0]["id"]
                print(f"\n[MSG] Fetching first message (ID: {msg_id})...")
                
                msg_url = f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{msg_id}?format=metadata&metadataHeaders=Subject&metadataHeaders=From&metadataHeaders=Date"
                msg_req = urlrequest.Request(msg_url, headers=headers, method="GET")
                
                with urlrequest.urlopen(msg_req, timeout=15) as msg_resp:
                    msg_data = json.loads(msg_resp.read().decode("utf-8"))
                    
                    # Extract headers
                    headers_list = msg_data.get("payload", {}).get("headers", [])
                    subject = next((h["value"] for h in headers_list if h["name"] == "Subject"), "N/A")
                    from_addr = next((h["value"] for h in headers_list if h["name"] == "From"), "N/A")
                    date = next((h["value"] for h in headers_list if h["name"] == "Date"), "N/A")
                    
                    print(f"   [OK] Successfully read message!")
                    print(f"   From: {from_addr}")
                    print(f"   Subject: {subject}")
                    print(f"   Date: {date}")
            
            return True
            
    except urlerror.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="ignore")
        print(f"[FAIL] HTTP Error {e.code}: {e.reason}")
        print(f"   Response: {error_body[:500]}")
        
        if e.code == 403:
            print("\n[WARN] 403 Forbidden - OAuth token likely lacks 'gmail.readonly' scope")
            print("   You may need to re-authorize with additional scopes.")
        return False
        
    except urlerror.URLError as e:
        print(f"[FAIL] Network error: {e}")
        return False


if __name__ == "__main__":
    account = sys.argv[1] if len(sys.argv) > 1 else "church"
    success = test_inbox_read(account)
    print("\n" + "=" * 50)
    print(f"Result: {'[OK] READ ACCESS CONFIRMED' if success else '[FAIL] READ ACCESS DENIED'}")
    sys.exit(0 if success else 1)

