#!/usr/bin/env python3
"""Daily Task Assistant CLI."""
from __future__ import annotations

import argparse
import sys

from daily_task_assistant.config import ConfigError, Settings, load_settings
from daily_task_assistant.smartsheet_client import (
    SchemaError,
    SmartsheetAPIError,
    SmartsheetClient,
)
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
        help="List high-priority tasks.",
    )
    list_parser.add_argument(
        "--limit",
        type=int,
        default=3,
        help="Maximum number of tasks to show.",
    )
    list_parser.add_argument(
        "--source",
        choices=("auto", "live", "stub"),
        default="auto",
        help="Data source preference: live Smartsheet, stub, or auto fallback.",
    )

    subparsers.add_parser(
        "check-token",
        help="Validate that the Smartsheet token is available in the environment.",
    )

    subparsers.add_parser(
        "schema",
        help="Show schema readiness and highlight placeholder column IDs.",
    )

    return parser


def _cmd_list(limit: int, source: str) -> int:
    settings = load_settings()
    live_tasks = False
    client: SmartsheetClient | None = None

    if source != "stub":
        try:
            client = _build_client(settings)
        except SchemaError as exc:
            if source == "live":
                print(f"Schema error: {exc}", file=sys.stderr)
                return 1
            print(f"Schema not ready; falling back to stub data: {exc}")

    if source == "stub" or client is None:
        tasks = fetch_stubbed_tasks(limit=limit)
    else:
        try:
            tasks = client.list_tasks(
                limit=limit,
                fallback_to_stub=(source == "auto"),
            )
            live_tasks = client.last_fetch_used_live
        except (SchemaError, SmartsheetAPIError) as exc:
            if source == "live":
                print(f"Live list failed: {exc}", file=sys.stderr)
                return 1
            print(f"Live data unavailable, showing stubbed tasks: {exc}")
            tasks = fetch_stubbed_tasks(limit=limit)

    print(format_task_rows(tasks))
    print()
    print(
        "Environment:",
        settings.environment,
        "| Token loaded:",
        "yes" if bool(settings.smartsheet_token) else "no",
        "| Source:",
        "live" if live_tasks else "stub",
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


def _cmd_schema() -> int:
    settings = load_settings()
    try:
        client = _build_client(settings)
    except SchemaError as exc:
        print(f"Unable to load schema: {exc}", file=sys.stderr)
        return 1
    placeholders = [
        field
        for field, column in client.schema.columns.items()
        if column.column_id.startswith("TODO")
    ]

    print(f"Sheet ID: {client.schema.sheet_id}")
    print("Required fields:", ", ".join(client.schema.required_fields))

    if placeholders:
        print("\n⚠️  Column IDs still missing for:")
        for field in placeholders:
            print(f"  - {field}")
        print(
            "\nUpdate config/smartsheet.yml with the real columnId values before running live syncs."
        )
    else:
        print("\n✅ Schema ready for live API calls.")

    return 0


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "list":
        return _cmd_list(limit=args.limit, source=args.source)
    if args.command == "check-token":
        return _cmd_check_token()
    if args.command == "schema":
        return _cmd_schema()

    parser.error(f"Unknown command: {args.command}")
    return 2


def _build_client(settings: Settings) -> SmartsheetClient:
    return SmartsheetClient(settings=settings)


if __name__ == "__main__":
    raise SystemExit(main())
