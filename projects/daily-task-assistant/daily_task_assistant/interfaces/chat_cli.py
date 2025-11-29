"""Interactive chat-style CLI for reviewing tasks with the assistant."""
from __future__ import annotations

import argparse
from ..actions import plan_assist
from ..analysis import rank_tasks
from ..dataset import fetch_tasks


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="daily-task-assistant-chat",
        description="Split-view prototype for chatting through prioritized tasks.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Maximum number of tasks to load into the queue.",
    )
    parser.add_argument(
        "--source",
        choices=("auto", "live", "stub"),
        default="auto",
        help="Where to load tasks from.",
    )
    parser.add_argument(
        "--anthropic-model",
        help="Override Anthropic model (defaults to env or built-in).",
    )
    args = parser.parse_args()

    try:
        tasks, live_tasks, settings, warning = fetch_tasks(
            limit=args.limit, source=args.source
        )
    except RuntimeError as exc:
        print(f"Unable to load tasks: {exc}")
        return 1

    if warning:
        print(warning)

    ranked = rank_tasks(tasks)
    if not ranked:
        print("No tasks available.")
        return 0

    print(
        f"\nLoaded {len(ranked)} tasks "
        f"({'live' if live_tasks else 'stub'} data) for environment {settings.environment}."
    )
    _conversation_loop(ranked, anthropic_model=args.anthropic_model)
    return 0


def _conversation_loop(ranked_tasks, anthropic_model: str | None) -> None:
    while True:
        _render_task_list(ranked_tasks)
        choice = input("\nSelect task number (enter to refresh, 'q' to quit): ").strip()
        if not choice:
            continue
        if choice.lower() in {"q", "quit", "exit"}:
            print("Goodbye!")
            return
        if not choice.isdigit():
            print("Please enter a valid number.")
            continue
        idx = int(choice) - 1
        if idx < 0 or idx >= len(ranked_tasks):
            print("Selection out of range.")
            continue
        plan = plan_assist(ranked_tasks[idx].task, model_override=anthropic_model)
        _render_plan(plan)
        action = input(
            "\n[a] Accept draft  [c] Continue discussion  [q] Quit assistant > "
        ).strip()
        if action.lower().startswith("q"):
            print("Goodbye!")
            return
        if action.lower().startswith("a"):
            print("✔ Draft accepted (placeholder action).")


def _render_task_list(ranked_tasks) -> None:
    print("\n=== Task Queue ===")
    for idx, ranked in enumerate(ranked_tasks, 1):
        labels = ", ".join(ranked.labels) if ranked.labels else "General focus"
        print(
            f"[{idx:02d}] {ranked.task.title} | score {ranked.score:.1f} | {labels} | "
            f"due {ranked.task.due:%Y-%m-%d}"
        )


def _render_plan(plan) -> None:
    print("\n--- Assistant View ---")
    print(f"{plan.task.title} (score {plan.score:.1f})")
    print(plan.summary)
    if plan.labels:
        print("Labels:", ", ".join(plan.labels))
    if plan.automation_triggers:
        print("Automation ideas:", ", ".join(plan.automation_triggers))

    print("\nSuggested next steps:")
    for step in plan.next_steps:
        print(f" - {step}")

    print("\nEfficiency tips:")
    for tip in plan.efficiency_tips:
        print(f" - {tip}")

    print("\nEmail draft:\n")
    print(plan.email_draft)


if __name__ == "__main__":
    raise SystemExit(main())

