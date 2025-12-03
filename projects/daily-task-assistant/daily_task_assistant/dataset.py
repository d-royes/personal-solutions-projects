"""Shared dataset helpers."""
from __future__ import annotations

from collections import defaultdict
import re
from typing import Optional, Tuple

from .config import Settings, load_settings
from .smartsheet_client import SchemaError, SmartsheetAPIError, SmartsheetClient
from .tasks import TaskDetail, fetch_stubbed_tasks


def fetch_tasks(
    *, limit: Optional[int], source: str
) -> Tuple[list[TaskDetail], bool, Settings, str | None]:
    """Fetch tasks from Smartsheet or fallback stub."""

    settings = load_settings()
    live_tasks = False
    warning: str | None = None
    client: SmartsheetClient | None = None

    if source != "stub":
        try:
            client = SmartsheetClient(settings=settings)
        except SchemaError as exc:
            if source == "live":
                raise RuntimeError(f"Schema error: {exc}") from exc
            warning = _merge_warning(
                warning, f"Schema not ready; falling back to stub data: {exc}"
            )

    if source == "stub" or client is None:
        return fetch_stubbed_tasks(limit=limit), live_tasks, settings, warning

    try:
        tasks = client.list_tasks(limit=limit, fallback_to_stub=(source == "auto"))
        live_tasks = client.last_fetch_used_live
        if not live_tasks and source == "auto":
            warning = _merge_warning(
                warning, "Live data unavailable, showing stubbed tasks."
            )
        if client.row_errors:
            row_warning = _summarize_row_errors(client.row_errors)
            warning = _merge_warning(warning, row_warning)
    except (SchemaError, SmartsheetAPIError) as exc:
        if source == "live":
            raise RuntimeError(f"Live list failed: {exc}") from exc
        warning = _merge_warning(
            warning, f"Live data unavailable, showing stubbed tasks: {exc}"
        )
        tasks = fetch_stubbed_tasks(limit=limit)
        live_tasks = False

    return tasks, live_tasks, settings, warning


def _merge_warning(existing: str | None, new_warning: str | None) -> str | None:
    if not new_warning:
        return existing
    if existing:
        return f"{existing}\n{new_warning}"
    return new_warning


_MISSING_FIELD_RE = re.compile(r"Required field '([^']+)' missing", re.IGNORECASE)
_INVALID_VALUE_RE = re.compile(
    r"Field '([^']+)' has invalid value", re.IGNORECASE
)
_ROW_NUMBER_RE = re.compile(r"Row\s+(\d+)")


def _summarize_row_errors(errors: list[str]) -> str:
    """Condense verbose row errors into a short dashboard-friendly summary."""

    if not errors:
        return "Skipped rows due to incomplete Smartsheet data."

    buckets = defaultdict(list)

    for err in errors:
        if match := _MISSING_FIELD_RE.search(err):
            label = f"missing {match.group(1)}"
        elif match := _INVALID_VALUE_RE.search(err):
            label = f"invalid {match.group(1)}"
        else:
            label = "other issues"

        row_label = "unknown row"
        if row_match := _ROW_NUMBER_RE.search(err):
            row_label = f"row {row_match.group(1)}"
        elif "Row ID" in err:
            row_label = err.split(":")[0]

        buckets[label].append(row_label)

    total = len(errors)
    parts = []
    for label, rows in buckets.items():
        unique_rows = []
        for row in rows:
            if row not in unique_rows:
                unique_rows.append(row)
        preview = ", ".join(unique_rows[:5])
        extra = f", +{len(unique_rows) - 5} more" if len(unique_rows) > 5 else ""
        if extra:
            parts.append(f"{label} ({preview}{extra})")
        else:
            parts.append(f"{label} ({preview})")

    summary = "; ".join(parts)
    return f"Skipped {total} row(s): {summary}. Fix Smartsheet fields and refresh."

