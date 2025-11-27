#!/usr/bin/env python3
"""Daily Task Assistant CLI stub."""
from __future__ import annotations

import argparse
import sys

from daily_task_assistant.config import ConfigError, load_settings
from daily_task_assistant.tasks import fetch_stubbed_tasks, format_task_rows


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="daily-task-assistant",
        description=(
            "Prototype companion that syncs Smartsheet tasks and suggests assists."
        ),
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser(
        "list",
        help="List high-priority tasks (stubbed data for now).",
    )
    list_parser.add_argument(
        "--limit",
        type=int,
        default=3,
        help="Maximum number of tasks to show.",
    )

    subparsers.add_parser(
        "check-token",
        help="Validate that the Smartsheet token is available in the environment.",
    )

    return parser


def _cmd_list(limit: int) -> int:
    settings = load_settings()
    tasks = fetch_stubbed_tasks(limit=limit)
    print(format_task_rows(tasks))
    print()
    print(
        "Environment:",
        settings.environment,
        "| Token loaded:",
        "yes" if bool(settings.smartsheet_token) else "no",
    )
    return 0


def _cmd_check_token() -> int:
    try:
        settings = load_settings()
    except ConfigError as exc:
        print(f"Token check failed: {exc}", file=sys.stderr)
        return 1

    token_preview = settings.smartsheet_token[:4] + "..."
    print(
        "Smartsheet token is configured",
        f"(preview {token_preview})",
        f"environment={settings.environment}",
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "list":
        return _cmd_list(limit=args.limit)
    if args.command == "check-token":
        return _cmd_check_token()

    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
