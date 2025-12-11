#!/usr/bin/env python
"""Live integration tests for email functionality.

This script tests the email functionality with real Gmail credentials.
It's meant to be run manually during development to validate the integration.

Usage:
    # Test with personal account
    python scripts/test_email_integration.py --account personal
    
    # Test with church account
    python scripts/test_email_integration.py --account church
    
    # Test all functionality
    python scripts/test_email_integration.py --account personal --all
    
    # Run specific test
    python scripts/test_email_integration.py --account personal --test inbox
    
Environment Variables Required:
    PERSONAL_GMAIL_CLIENT_ID
    PERSONAL_GMAIL_CLIENT_SECRET
    PERSONAL_GMAIL_REFRESH_TOKEN
    PERSONAL_GMAIL_ADDRESS
    
    (or CHURCH_* variants for church account)
"""
from __future__ import annotations

import argparse
import sys
import os
from datetime import datetime, timezone
from typing import Optional

# Add parent directory to path for imports
script_dir = os.path.dirname(os.path.abspath(__file__))
project_dir = os.path.dirname(script_dir)
sys.path.insert(0, project_dir)

# Load .env file from project directory
from dotenv import load_dotenv
env_path = os.path.join(project_dir, ".env")
load_dotenv(env_path)

# Configure stdout for Unicode
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')


class TestResult:
    """Track test results."""
    
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.skipped = 0
        self.errors = []
    
    def record_pass(self, name: str):
        self.passed += 1
        print(f"  ✅ {name}")
    
    def record_fail(self, name: str, error: str):
        self.failed += 1
        self.errors.append((name, error))
        print(f"  ❌ {name}: {error}")
    
    def record_skip(self, name: str, reason: str):
        self.skipped += 1
        print(f"  ⏭️ {name}: {reason}")
    
    def summary(self):
        total = self.passed + self.failed + self.skipped
        print(f"\n{'='*50}")
        print(f"Results: {self.passed}/{total} passed, {self.failed} failed, {self.skipped} skipped")
        if self.errors:
            print(f"\nErrors:")
            for name, error in self.errors:
                print(f"  - {name}: {error}")
        return self.failed == 0


def test_account_loading(account_prefix: str, results: TestResult) -> Optional[object]:
    """Test loading Gmail account from environment."""
    print(f"\n📧 Testing account loading for {account_prefix}...")
    
    try:
        from daily_task_assistant.mailer import load_account_from_env
        
        account = load_account_from_env(account_prefix)
        results.record_pass(f"Loaded {account_prefix} account: {account.from_address}")
        return account
    except Exception as e:
        results.record_fail(f"Load {account_prefix} account", str(e))
        return None


def test_inbox_list(account, results: TestResult):
    """Test listing messages from inbox."""
    print(f"\n📬 Testing inbox listing...")
    
    try:
        from daily_task_assistant.mailer import list_messages
        
        # Test basic list
        messages = list_messages(account, max_results=5)
        results.record_pass(f"Listed {len(messages)} messages from inbox")
        
        # Test with query
        unread = list_messages(account, max_results=5, query="is:unread")
        results.record_pass(f"Listed {len(unread)} unread messages")
        
        # Test with label filter
        inbox_only = list_messages(account, max_results=5, label_ids=["INBOX"])
        results.record_pass(f"Listed {len(inbox_only)} inbox messages")
        
        return messages
    except Exception as e:
        results.record_fail("List messages", str(e))
        return []


def test_get_message(account, message_refs: list, results: TestResult):
    """Test getting individual message details."""
    print(f"\n📨 Testing message retrieval...")
    
    if not message_refs:
        results.record_skip("Get message details", "No messages available")
        return []
    
    try:
        from daily_task_assistant.mailer import get_message
        
        messages = []
        for i, ref in enumerate(message_refs[:3]):  # Test first 3 messages
            msg = get_message(account, ref["id"])
            messages.append(msg)
            
            print(f"    Message {i+1}:")
            print(f"      From: {msg.from_name} <{msg.from_address}>")
            print(f"      Subject: {msg.subject[:50]}...")
            print(f"      Date: {msg.date}")
            print(f"      Unread: {msg.is_unread}")
        
        results.record_pass(f"Retrieved {len(messages)} message details")
        return messages
    except Exception as e:
        results.record_fail("Get message details", str(e))
        return []


def test_inbox_summary(account, results: TestResult):
    """Test getting inbox summary."""
    print(f"\n📊 Testing inbox summary...")
    
    try:
        from daily_task_assistant.mailer import get_inbox_summary
        
        summary = get_inbox_summary(
            account,
            vip_senders=["@gmail.com"],  # Test VIP detection
            max_recent=5,
        )
        
        print(f"    Total unread: {summary.total_unread}")
        print(f"    Unread important: {summary.unread_important}")
        print(f"    Recent messages: {len(summary.recent_messages)}")
        
        results.record_pass(f"Got inbox summary (unread: {summary.total_unread})")
        return summary
    except Exception as e:
        results.record_fail("Get inbox summary", str(e))
        return None


def test_search_messages(account, results: TestResult):
    """Test searching messages."""
    print(f"\n🔍 Testing message search...")
    
    try:
        from daily_task_assistant.mailer import search_messages
        
        # Test various search queries
        queries = [
            "is:unread",
            "is:important",
            "newer_than:7d",
        ]
        
        for query in queries:
            try:
                messages = search_messages(account, query, max_results=3)
                results.record_pass(f"Search '{query}': {len(messages)} results")
            except Exception as e:
                results.record_fail(f"Search '{query}'", str(e))
    except Exception as e:
        results.record_fail("Search messages", str(e))


def test_filter_rules(account_prefix: str, results: TestResult):
    """Test filter rules from Google Sheets."""
    print(f"\n📋 Testing filter rules management...")
    
    try:
        from daily_task_assistant.sheets.filter_rules import FilterRulesManager
        
        manager = FilterRulesManager.from_env(account_prefix)
        
        # Test getting all rules
        rules = manager.get_all_rules()
        results.record_pass(f"Retrieved {len(rules)} filter rules from sheet")
        
        if rules:
            print(f"    Sample rules:")
            for rule in rules[:3]:
                print(f"      - {rule.category}: {rule.field} {rule.operator} '{rule.value}'")
        
        # Test filtering by account
        email_address = os.getenv(f"{account_prefix.upper()}_GMAIL_ADDRESS")
        if email_address:
            account_rules = manager.get_rules_for_account(email_address)
            results.record_pass(f"Filtered rules for {email_address}: {len(account_rules)}")
        
        return rules
    except Exception as e:
        results.record_fail("Filter rules", str(e))
        return []


def test_email_analyzer(account, messages: list, rules: list, results: TestResult):
    """Test email pattern analyzer."""
    print(f"\n🧠 Testing email analyzer...")
    
    if not messages:
        results.record_skip("Email analyzer", "No messages to analyze")
        return
    
    try:
        from daily_task_assistant.email.analyzer import (
            analyze_inbox_patterns,
            suggest_label_rules,
            detect_attention_items,
        )
        
        email_account = account.from_address
        
        # Test full analysis
        suggestions, attention = analyze_inbox_patterns(messages, email_account, rules)
        results.record_pass(f"Analyzed patterns: {len(suggestions)} suggestions, {len(attention)} attention items")
        
        if suggestions:
            print(f"    Top suggestions:")
            for s in suggestions[:3]:
                print(f"      - {s.type.value}: {s.suggested_rule.value} ({s.confidence.value})")
        
        if attention:
            print(f"    Attention items:")
            for a in attention[:3]:
                print(f"      - [{a.urgency}] {a.email.subject[:40]}... ({a.reason})")
        
        # Test label suggestions only
        label_suggestions = suggest_label_rules(messages, email_account)
        results.record_pass(f"Generated {len(label_suggestions)} label suggestions")
        
        # Test attention detection only
        attention_items = detect_attention_items(messages, email_account)
        results.record_pass(f"Detected {len(attention_items)} attention items")
        
    except Exception as e:
        results.record_fail("Email analyzer", str(e))


def test_api_endpoints(account_prefix: str, results: TestResult):
    """Test API endpoints for email functionality."""
    print(f"\n🌐 Testing API endpoints...")
    
    import json
    from urllib import request as urlrequest
    from urllib import error as urlerror
    
    base_url = "http://localhost:8000"
    email = os.getenv(f"{account_prefix.upper()}_GMAIL_ADDRESS")
    headers = {
        "X-User-Email": email or "test@example.com",
        "Content-Type": "application/json",
    }
    
    endpoints = [
        ("GET", f"/inbox/{account_prefix}/summary", "Inbox summary"),
        ("GET", f"/email/rules/{account_prefix}", "Email rules"),
    ]
    
    for method, path, name in endpoints:
        try:
            url = f"{base_url}{path}"
            req = urlrequest.Request(url, headers=headers, method=method)
            
            with urlrequest.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                results.record_pass(f"API {name}: {resp.status}")
        except urlerror.HTTPError as e:
            if e.code == 400:
                # Config error - expected if credentials not set
                body = e.read().decode("utf-8", errors="ignore")
                results.record_skip(f"API {name}", f"Config error: {body[:50]}")
            else:
                results.record_fail(f"API {name}", f"HTTP {e.code}")
        except urlerror.URLError as e:
            results.record_skip(f"API {name}", f"Server not running: {e}")
        except Exception as e:
            results.record_fail(f"API {name}", str(e))


def run_all_tests(account_prefix: str, include_api: bool = False):
    """Run all tests for a given account."""
    results = TestResult()
    
    print(f"\n{'='*50}")
    print(f"🧪 Email Integration Tests - {account_prefix.upper()} Account")
    print(f"{'='*50}")
    
    # Test 1: Account loading
    account = test_account_loading(account_prefix, results)
    if not account:
        print("\n⚠️ Cannot proceed without valid account credentials")
        return results
    
    # Test 2: Inbox listing
    message_refs = test_inbox_list(account, results)
    
    # Test 3: Get message details
    messages = test_get_message(account, message_refs, results)
    
    # Test 4: Inbox summary
    test_inbox_summary(account, results)
    
    # Test 5: Search messages
    test_search_messages(account, results)
    
    # Test 6: Filter rules (Google Sheets)
    rules = test_filter_rules(account_prefix, results)
    
    # Test 7: Email analyzer
    test_email_analyzer(account, messages, rules, results)
    
    # Test 8: API endpoints (optional)
    if include_api:
        test_api_endpoints(account_prefix, results)
    
    return results


def run_specific_test(account_prefix: str, test_name: str):
    """Run a specific test."""
    results = TestResult()
    
    # Load account first
    account = test_account_loading(account_prefix, results)
    if not account:
        return results
    
    test_map = {
        "inbox": lambda: test_inbox_list(account, results),
        "summary": lambda: test_inbox_summary(account, results),
        "search": lambda: test_search_messages(account, results),
        "rules": lambda: test_filter_rules(account_prefix, results),
        "analyzer": lambda: test_email_analyzer(
            account, 
            test_get_message(account, test_inbox_list(account, results)[:5], results),
            test_filter_rules(account_prefix, results),
            results
        ),
        "api": lambda: test_api_endpoints(account_prefix, results),
    }
    
    if test_name not in test_map:
        print(f"Unknown test: {test_name}")
        print(f"Available tests: {', '.join(test_map.keys())}")
        return results
    
    test_map[test_name]()
    return results


def main():
    parser = argparse.ArgumentParser(description="Test email integration")
    parser.add_argument(
        "--account", 
        required=True, 
        choices=["personal", "church"],
        help="Account to test (personal or church)"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Run all tests including API endpoints"
    )
    parser.add_argument(
        "--test",
        type=str,
        help="Run specific test (inbox, summary, search, rules, analyzer, api)"
    )
    
    args = parser.parse_args()
    
    if args.test:
        results = run_specific_test(args.account, args.test)
    else:
        results = run_all_tests(args.account, include_api=args.all)
    
    success = results.summary()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

