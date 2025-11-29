#!/usr/bin/env python3
"""Daily Task Assistant CLI."""
from __future__ import annotations

import argparse
import sys

from daily_task_assistant.actions import AssistPlan, plan_assist
from daily_task_assistant.analysis import rank_tasks
from daily_task_assistant.config import ConfigError, Settings, load_settings
from daily_task_assistant.dataset import fetch_tasks as fetch_task_dataset
from daily_task_assistant.services import execute_assist
from daily_task_assistant.smartsheet_client import (
    SchemaError,
    SmartsheetAPIError,
    SmartsheetClient,
)
from daily_task_assistant.tasks import format_task_rows


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

    assist_parser = subparsers.add_parser(
        "assist",
        help="Generate AI assistance for a specific task ID.",
    )
    assist_parser.add_argument("task_id", help="Smartsheet row ID or stub ID.")
    assist_parser.add_argument(
        "--source",
        choices=("auto", "live", "stub"),
        default="auto",
        help="Where to load tasks from before generating assists.",
    )
    assist_parser.add_argument(
        "--anthropic-model",
        help="Override Anthropic model for AI assists (otherwise env/default is used).",
    )
    assist_parser.add_argument(
        "--send-email",
        help="Send the drafted email via the specified Gmail account (e.g., 'church').",
    )

    recommend_parser = subparsers.add_parser(
        "recommend",
        help="Show top tasks with suggested AI actions.",
    )
    recommend_parser.add_argument(
        "--limit",
        type=int,
        default=3,
        help="How many tasks to summarize.",
    )
    recommend_parser.add_argument(
        "--source",
        choices=("auto", "live", "stub"),
        default="auto",
        help="Where to load tasks from.",
    )
    recommend_parser.add_argument(
        "--anthropic-model",
        help="Override Anthropic model for AI assists (otherwise env/default is used).",
    )

    return parser


def _cmd_list(limit: int, source: str) -> int:
    try:
        tasks, live_tasks, settings, warning = fetch_task_dataset(
            limit=limit, source=source
        )
    except RuntimeError as exc:
        print(exc, file=sys.stderr)
        return 1

    if warning:
        print(warning)

    ranked_tasks = rank_tasks(tasks)
    print(format_task_rows(rt.task for rt in ranked_tasks))
    print("\nHighlights:")
    for ranked in ranked_tasks:
        labels = ", ".join(ranked.labels) if ranked.labels else "General"
        automations = ", ".join(ranked.automation_triggers) if ranked.automation_triggers else "None"
        print(
            f"- {ranked.task.row_id}: score {ranked.score:.1f} | {labels} | Next: {ranked.task.next_step}"
        )
        if automations != "None":
            print(f"    Automation ideas: {automations}")
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


def _cmd_assist(
    task_id: str,
    source: str,
    anthropic_model: str | None,
    send_email_account: str | None,
) -> int:
    try:
        tasks, live_tasks, settings, warning = fetch_task_dataset(
            limit=50, source=source
        )
    except RuntimeError as exc:
        print(f"Assist failed: {exc}", file=sys.stderr)
        return 1

    if warning:
        print(warning)

    target = next((task for task in tasks if task.row_id == task_id), None)
    if not target:
        print(f"Task {task_id} not found in the current dataset.", file=sys.stderr)
        return 1

    result = execute_assist(
        task=target,
        settings=settings,
        source=source,
        anthropic_model=anthropic_model,
        send_email_account=send_email_account,
        live_tasks=live_tasks,
    )
    _print_assist_plan(
        result.plan,
        environment=settings.environment,
        token_present=bool(settings.smartsheet_token),
        live_tasks=live_tasks,
    )
    if result.comment_posted:
        print("📝 Smartsheet comment recorded.")
    if result.message_id:
        print(f"Message ID: {result.message_id}")
    if result.warnings:
        print("\nWarnings:")
        for warning in result.warnings:
            print(f" - {warning}")

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
    if args.command == "assist":
        return _cmd_assist(
            task_id=args.task_id,
            source=args.source,
            anthropic_model=getattr(args, "anthropic_model", None),
            send_email_account=getattr(args, "send_email", None),
        )
    if args.command == "recommend":
        return _cmd_recommend(
            limit=args.limit,
            source=args.source,
            anthropic_model=getattr(args, "anthropic_model", None),
        )

    parser.error(f"Unknown command: {args.command}")
    return 2


def _build_client(settings: Settings) -> SmartsheetClient:
    return SmartsheetClient(settings=settings)


def _print_assist_plan(
    plan: AssistPlan,
    *,
    environment: str,
    token_present: bool,
    live_tasks: bool,
) -> None:
    print(
        f"Assist plan for {plan.task.row_id} — {plan.task.title} "
        f"(score {plan.score:.1f})"
    )
    if plan.labels:
        print("Labels:", ", ".join(plan.labels))

    if plan.automation_triggers:
        print("Automation:", ", ".join(plan.automation_triggers))

    print("\nSummary:", plan.summary)

    print("\nRecommended next steps:")
    for step in plan.next_steps:
        print(f" - {step}")

    print("\nEfficiency tips:")
    for tip in plan.efficiency_tips:
        print(f" - {tip}")

    print("\nEmail draft:\n")
    print(plan.email_draft)

    print("\nEnvironment:", environment, "| Token loaded:", "yes" if token_present else "no")
    print("Source:", "live" if live_tasks else "stub")


def _cmd_recommend(limit: int, source: str, anthropic_model: str | None) -> int:
    try:
        tasks, live_tasks, settings, warning = fetch_task_dataset(
            limit=limit * 2, source=source
        )
    except RuntimeError as exc:
        print(f"Recommend failed: {exc}", file=sys.stderr)
        return 1

    if warning:
        print(warning)

    ranked = rank_tasks(tasks)[:limit]
    if not ranked:
        print("No tasks available.")
        return 0

    print(f"Top {len(ranked)} tasks with recommended assists:\n")
    for idx, ranked_task in enumerate(ranked, 1):
        plan = plan_assist(ranked_task.task, model_override=anthropic_model)
        print(
            f"{idx}. {ranked_task.task.title} (score {ranked_task.score:.1f}, due {ranked_task.task.due:%Y-%m-%d})"
        )
        print(f"   Summary: {plan.summary}")
        if plan.next_steps:
            print(f"   Next: {plan.next_steps[0]}")
        if plan.automation_triggers:
            print("   Automation:", ", ".join(plan.automation_triggers))
        print(f"   Email preview: {plan.email_draft.splitlines()[0]}")
        print()

    print("Environment:", settings.environment, "| Token loaded:", "yes" if bool(settings.smartsheet_token) else "no")
    print("Source:", "live" if live_tasks else "stub")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
