#!/usr/bin/env python3
"""
DATA Baseline Test Runner

Automated testing for DATA quality regression detection.
Runs fixed prompts against fixed test fixtures and captures responses.

Usage:
    python run_baseline.py --save-as level0       # Save new baseline
    python run_baseline.py --compare level0       # Compare against baseline
    python run_baseline.py --run-only             # Just run tests, print results
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional, Any
import requests


# Paths
SCRIPT_DIR = Path(__file__).parent
CONFIG_PATH = SCRIPT_DIR / "config.json"
BASELINES_DIR = SCRIPT_DIR / "baselines"
RESULTS_DIR = SCRIPT_DIR / "results"


@dataclass
class TestResult:
    """Result of a single test prompt."""
    test_id: str
    mode: str
    prompt: str
    description: str
    
    # Response data
    response_text: str = ""
    pending_action: Optional[dict] = None
    tool_used: Optional[str] = None
    action_type: Optional[str] = None
    
    # Quality checks
    response_length: int = 0
    passed_tool_check: Optional[bool] = None
    passed_length_check: Optional[bool] = None
    hallucination_flags: list = field(default_factory=list)
    verbose_flags: list = field(default_factory=list)
    
    # Timing
    response_time_ms: int = 0
    
    # Overall
    status: str = "pending"  # pending, pass, warning, fail, error
    notes: str = ""


@dataclass
class BaselineRun:
    """Complete baseline test run."""
    timestamp: str
    branch: str
    commit: str
    config_hash: str
    results: list = field(default_factory=list)
    summary: dict = field(default_factory=dict)


def load_config() -> dict:
    """Load test configuration."""
    with open(CONFIG_PATH) as f:
        return json.load(f)


def get_git_info() -> tuple[str, str]:
    """Get current git branch and commit."""
    import subprocess
    try:
        branch = subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=SCRIPT_DIR.parent,
            text=True
        ).strip()
        commit = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=SCRIPT_DIR.parent,
            text=True
        ).strip()
        return branch, commit
    except Exception:
        return "unknown", "unknown"


class BaselineRunner:
    """Runs baseline tests against DATA API."""
    
    def __init__(self, config: dict):
        self.config = config
        self.base_url = config["api_base_url"]
        self.user_email = config["user_email"]
        self.headers = {"X-User-Email": self.user_email}
        self.fixtures = config["test_fixtures"]
        self.quality_checks = config["quality_checks"]
    
    def run_all_tests(self) -> list[TestResult]:
        """Run all configured tests."""
        results = []
        
        print("\n" + "=" * 60)
        print("DATA BASELINE TEST RUNNER")
        print("=" * 60)
        
        # Task Mode Tests
        print("\n[TASK MODE TESTS]")
        print("-" * 40)
        results.extend(self._run_task_mode_tests())
        
        # Portfolio Mode Tests
        print("\n[PORTFOLIO MODE TESTS]")
        print("-" * 40)
        results.extend(self._run_portfolio_mode_tests())
        
        # Calendar Mode Tests
        print("\n[CALENDAR MODE TESTS]")
        print("-" * 40)
        results.extend(self._run_calendar_mode_tests())
        
        # Email Mode Tests
        print("\n[EMAIL MODE TESTS]")
        print("-" * 40)
        results.extend(self._run_email_mode_tests())
        
        return results
    
    def _run_task_mode_tests(self) -> list[TestResult]:
        """Run task mode tests (engaged with specific task)."""
        results = []
        task_id = self.fixtures["task"]["row_id"]
        
        # First, engage with the task
        print(f"  Engaging with task {task_id}...")
        try:
            resp = requests.post(
                f"{self.base_url}/assist/{task_id}",
                headers=self.headers,
                json={"source": "auto"},
                timeout=30
            )
            if resp.status_code != 200:
                print(f"  [WARN] Failed to engage task: {resp.status_code} - {resp.text[:100]}")
        except Exception as e:
            print(f"  [WARN] Error engaging task: {e}")
        
        # Run each prompt
        for prompt_config in self.config["prompts"]["task_mode"]:
            result = self._run_task_chat(task_id, prompt_config)
            results.append(result)
            self._print_result(result)
        
        return results
    
    def _run_task_chat(self, task_id: str, prompt_config: dict) -> TestResult:
        """Run a single task mode chat prompt."""
        result = TestResult(
            test_id=prompt_config["id"],
            mode="task",
            prompt=prompt_config["prompt"],
            description=prompt_config["description"]
        )
        
        try:
            start = datetime.now()
            resp = requests.post(
                f"{self.base_url}/assist/{task_id}/chat",
                headers=self.headers,
                json={"message": prompt_config["prompt"]},
                timeout=60
            )
            result.response_time_ms = int((datetime.now() - start).total_seconds() * 1000)
            
            if resp.status_code == 200:
                data = resp.json()
                # Task chat uses "response" not "message"
                result.response_text = data.get("response", data.get("message", ""))
                # Task chat uses "pendingAction" (camelCase) not "pending_action"
                result.pending_action = data.get("pendingAction", data.get("pending_action"))
                result.response_length = len(result.response_text)
                
                # Extract tool info from pending_action
                if result.pending_action:
                    result.tool_used = "update_task"
                    result.action_type = result.pending_action.get("action")
                
                # Quality checks
                self._check_quality(result, prompt_config)
            else:
                result.status = "error"
                result.notes = f"HTTP {resp.status_code}: {resp.text[:200]}"
                
        except Exception as e:
            result.status = "error"
            result.notes = str(e)
        
        return result
    
    def _run_portfolio_mode_tests(self) -> list[TestResult]:
        """Run portfolio mode tests (Quick Question chat)."""
        results = []
        
        for prompt_config in self.config["prompts"]["portfolio_mode"]:
            result = self._run_portfolio_chat(prompt_config)
            results.append(result)
            self._print_result(result)
        
        return results
    
    def _run_portfolio_chat(self, prompt_config: dict) -> TestResult:
        """Run a portfolio mode chat prompt."""
        result = TestResult(
            test_id=prompt_config["id"],
            mode="portfolio",
            prompt=prompt_config["prompt"],
            description=prompt_config["description"]
        )
        
        perspective = prompt_config.get("perspective", "personal")
        
        try:
            start = datetime.now()
            resp = requests.post(
                f"{self.base_url}/assist/global/chat",
                headers=self.headers,
                json={
                    "message": prompt_config["prompt"],
                    "perspective": perspective
                },
                timeout=90
            )
            result.response_time_ms = int((datetime.now() - start).total_seconds() * 1000)
            
            if resp.status_code == 200:
                data = resp.json()
                result.response_text = data.get("message", data.get("response", ""))
                result.pending_action = data.get("pending_action")
                result.response_length = len(result.response_text)
                
                # Quality checks
                self._check_quality(result, prompt_config)
                
                # Hallucination check for portfolio
                if prompt_config.get("hallucination_check"):
                    self._check_hallucination(result)
            else:
                result.status = "error"
                result.notes = f"HTTP {resp.status_code}: {resp.text[:200]}"
                
        except Exception as e:
            result.status = "error"
            result.notes = str(e)
        
        return result
    
    def _run_calendar_mode_tests(self) -> list[TestResult]:
        """Run calendar mode tests."""
        results = []
        
        for prompt_config in self.config["prompts"]["calendar_mode"]:
            result = self._run_calendar_chat(prompt_config)
            results.append(result)
            self._print_result(result)
        
        return results
    
    def _run_calendar_chat(self, prompt_config: dict) -> TestResult:
        """Run a calendar mode chat prompt."""
        result = TestResult(
            test_id=prompt_config["id"],
            mode="calendar",
            prompt=prompt_config["prompt"],
            description=prompt_config["description"]
        )
        
        domain = prompt_config.get("domain", "combined")
        
        try:
            start = datetime.now()
            resp = requests.post(
                f"{self.base_url}/calendar/{domain}/chat",
                headers=self.headers,
                json={"message": prompt_config["prompt"]},
                timeout=90
            )
            result.response_time_ms = int((datetime.now() - start).total_seconds() * 1000)
            
            if resp.status_code == 200:
                data = resp.json()
                result.response_text = data.get("message", data.get("response", ""))
                result.response_length = len(result.response_text)
                
                # Quality checks
                self._check_quality(result, prompt_config)
            else:
                result.status = "error"
                result.notes = f"HTTP {resp.status_code}: {resp.text[:200]}"
                
        except Exception as e:
            result.status = "error"
            result.notes = str(e)
        
        return result
    
    def _run_email_mode_tests(self) -> list[TestResult]:
        """Run email mode tests."""
        results = []
        
        for prompt_config in self.config["prompts"]["email_mode"]:
            result = self._run_email_chat(prompt_config)
            results.append(result)
            self._print_result(result)
        
        return results
    
    def _run_email_chat(self, prompt_config: dict) -> TestResult:
        """Run an email mode chat prompt."""
        result = TestResult(
            test_id=prompt_config["id"],
            mode="email",
            prompt=prompt_config["prompt"],
            description=prompt_config["description"]
        )
        
        account = prompt_config.get("account", "personal")
        email_fixture_key = prompt_config.get("email_fixture", "email_personal")
        email_fixture = self.fixtures.get(email_fixture_key, {})
        email_id = email_fixture.get("id", "")
        
        try:
            start = datetime.now()
            resp = requests.post(
                f"{self.base_url}/email/{account}/chat",
                headers=self.headers,
                json={
                    "message": prompt_config["prompt"],
                    "email_id": email_id
                },
                timeout=90
            )
            result.response_time_ms = int((datetime.now() - start).total_seconds() * 1000)
            
            if resp.status_code == 200:
                data = resp.json()
                result.response_text = data.get("message", data.get("response", ""))
                result.response_length = len(result.response_text)
                
                # Quality checks
                self._check_quality(result, prompt_config)
            else:
                result.status = "error"
                result.notes = f"HTTP {resp.status_code}: {resp.text[:200]}"
                
        except Exception as e:
            result.status = "error"
            result.notes = str(e)
        
        return result
    
    def _check_quality(self, result: TestResult, prompt_config: dict):
        """Run quality checks on a result."""
        # Tool check
        expected_tool = prompt_config.get("expected_tool")
        if expected_tool is not None:
            result.passed_tool_check = (result.tool_used == expected_tool)
        
        # Length check for action prompts
        if expected_tool:
            max_len = self.quality_checks["max_response_length_for_actions"]
            result.passed_length_check = result.response_length <= max_len
        
        # Verbose patterns
        for pattern in self.quality_checks["verbose_patterns"]:
            if pattern.lower() in result.response_text.lower():
                result.verbose_flags.append(pattern)
        
        # Determine status
        if result.status == "error":
            return
        
        if result.passed_tool_check is False:
            result.status = "fail"
            result.notes = f"Expected tool '{expected_tool}', got '{result.tool_used}'"
        elif result.passed_length_check is False:
            result.status = "warning"
            result.notes = f"Response too long ({result.response_length} chars)"
        elif result.verbose_flags:
            result.status = "warning"
            result.notes = f"Verbose patterns: {result.verbose_flags}"
        else:
            result.status = "pass"
    
    def _check_hallucination(self, result: TestResult):
        """Check for hallucination indicators."""
        for keyword in self.quality_checks["hallucination_keywords"]:
            if keyword.lower() in result.response_text.lower():
                result.hallucination_flags.append(keyword)
        
        if result.hallucination_flags and result.status == "pass":
            result.status = "warning"
            result.notes = f"Possible hallucination: {result.hallucination_flags}"
    
    def _print_result(self, result: TestResult):
        """Print a single result."""
        status_icons = {
            "pass": "[PASS]",
            "warning": "[WARN]",
            "fail": "[FAIL]",
            "error": "[ERR!]",
            "pending": "[....]"
        }
        icon = status_icons.get(result.status, "[????]")
        
        print(f"  {icon} {result.test_id}: {result.prompt[:40]}...")
        print(f"     Status: {result.status.upper()} | Time: {result.response_time_ms}ms | Len: {result.response_length}")
        if result.tool_used:
            print(f"     Tool: {result.tool_used} -> {result.action_type}")
        if result.notes:
            print(f"     Note: {result.notes}")


def save_baseline(run: BaselineRun, name: str):
    """Save baseline to file."""
    filepath = BASELINES_DIR / f"{name}.json"
    
    # Convert to serializable format
    data = {
        "timestamp": run.timestamp,
        "branch": run.branch,
        "commit": run.commit,
        "config_hash": run.config_hash,
        "summary": run.summary,
        "results": [asdict(r) for r in run.results]
    }
    
    with open(filepath, "w") as f:
        json.dump(data, f, indent=2, default=str)
    
    print(f"\n[SAVED] Baseline saved to: {filepath}")


def load_baseline(name: str) -> dict:
    """Load baseline from file."""
    filepath = BASELINES_DIR / f"{name}.json"
    with open(filepath) as f:
        return json.load(f)


def compare_baselines(current: BaselineRun, baseline_name: str):
    """Compare current run against saved baseline."""
    baseline = load_baseline(baseline_name)
    
    print("\n" + "=" * 60)
    print(f"COMPARISON: Current vs '{baseline_name}'")
    print("=" * 60)
    print(f"Baseline: {baseline['timestamp']} | {baseline['branch']}@{baseline['commit']}")
    print(f"Current:  {current.timestamp} | {current.branch}@{current.commit}")
    print("-" * 60)
    
    baseline_results = {r["test_id"]: r for r in baseline["results"]}
    
    regressions = []
    improvements = []
    unchanged = []
    
    for result in current.results:
        baseline_result = baseline_results.get(result.test_id)
        if not baseline_result:
            print(f"  [NEW] {result.test_id}")
            continue
        
        old_status = baseline_result["status"]
        new_status = result.status
        
        if old_status == "pass" and new_status in ("fail", "error"):
            regressions.append((result.test_id, old_status, new_status))
        elif old_status in ("fail", "error") and new_status == "pass":
            improvements.append((result.test_id, old_status, new_status))
        else:
            unchanged.append(result.test_id)
    
    print(f"\n[COMPARISON SUMMARY]")
    print(f"  Regressions:  {len(regressions)}")
    print(f"  Improvements: {len(improvements)}")
    print(f"  Unchanged:    {len(unchanged)}")
    
    if regressions:
        print(f"\n[REGRESSIONS]")
        for test_id, old, new in regressions:
            print(f"    {test_id}: {old} -> {new}")
    
    if improvements:
        print(f"\n[IMPROVEMENTS]")
        for test_id, old, new in improvements:
            print(f"    {test_id}: {old} -> {new}")
    
    return len(regressions) == 0


def generate_summary(results: list[TestResult]) -> dict:
    """Generate summary statistics."""
    total = len(results)
    passed = sum(1 for r in results if r.status == "pass")
    warnings = sum(1 for r in results if r.status == "warning")
    failed = sum(1 for r in results if r.status == "fail")
    errors = sum(1 for r in results if r.status == "error")
    
    return {
        "total": total,
        "passed": passed,
        "warnings": warnings,
        "failed": failed,
        "errors": errors,
        "pass_rate": f"{(passed / total * 100):.1f}%" if total > 0 else "N/A"
    }


def main():
    parser = argparse.ArgumentParser(description="DATA Baseline Test Runner")
    parser.add_argument("--save-as", type=str, help="Save results as named baseline")
    parser.add_argument("--compare", type=str, help="Compare against named baseline")
    parser.add_argument("--run-only", action="store_true", help="Just run tests, don't save")
    args = parser.parse_args()
    
    # Load config
    config = load_config()
    
    # Get git info
    branch, commit = get_git_info()
    
    # Create runner and run tests
    runner = BaselineRunner(config)
    results = runner.run_all_tests()
    
    # Generate summary
    summary = generate_summary(results)
    
    # Create run object
    run = BaselineRun(
        timestamp=datetime.now().isoformat(),
        branch=branch,
        commit=commit,
        config_hash="",  # Could hash config for change detection
        results=results,
        summary=summary
    )
    
    # Print summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"  Total:    {summary['total']}")
    print(f"  Passed:   {summary['passed']}")
    print(f"  Warnings: {summary['warnings']}")
    print(f"  Failed:   {summary['failed']}")
    print(f"  Errors:   {summary['errors']}")
    print(f"  Pass Rate: {summary['pass_rate']}")
    
    # Handle arguments
    if args.save_as:
        save_baseline(run, args.save_as)
    
    if args.compare:
        success = compare_baselines(run, args.compare)
        sys.exit(0 if success else 1)
    
    # Save latest results
    save_baseline(run, "latest")
    
    # Exit with appropriate code
    if summary["failed"] > 0 or summary["errors"] > 0:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
