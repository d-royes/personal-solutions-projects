"""Smartsheet connector scaffolding for the Daily Task Assistant."""
from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple
from urllib import error as urlerror
from urllib import parse as urlparse
from urllib import request as urlrequest

from .config import Settings
from .tasks import TaskDetail, fetch_stubbed_tasks

try:  # Optional dependency
    import yaml
except ModuleNotFoundError as exc:  # pragma: no cover - handled at runtime
    yaml = None
    _yaml_import_error = exc
else:
    _yaml_import_error = None


class SchemaError(RuntimeError):
    """Raised when the schema config file is missing or invalid."""


class SmartsheetAPIError(RuntimeError):
    """Raised when Smartsheet returns an error response."""


@dataclass(slots=True)
class ColumnDefinition:
    field: str
    column_id: str
    col_type: str = "text"  # text, picklist, checkbox, date, contact, etc.
    optional: bool = False
    allowed_values: Optional[List[str]] = None


@dataclass(slots=True)
class SheetSchema:
    sheet_id: str
    name: str
    source_key: str  # "personal" or "work"
    include_in_all: bool
    columns: Dict[str, ColumnDefinition]
    required_fields: List[str]
    priority_values: List[str]
    project_values: List[str]

    @property
    def ready_for_live(self) -> bool:
        return all(
            not col.column_id.startswith("TODO") for col in self.columns.values()
        )


@dataclass
class MultiSheetConfig:
    """Configuration for multiple Smartsheets."""
    sheets: Dict[str, SheetSchema] = field(default_factory=dict)
    required_fields: List[str] = field(default_factory=list)
    priority_values: List[str] = field(default_factory=list)
    project_values: List[str] = field(default_factory=list)

    def get_all_sources(self) -> List[str]:
        """Return all available source keys."""
        return list(self.sheets.keys())

    def get_sources_for_all_filter(self) -> List[str]:
        """Return source keys that should be included in 'ALL' filter."""
        return [key for key, schema in self.sheets.items() if schema.include_in_all]

    @property
    def primary_sheet(self) -> Optional[SheetSchema]:
        """Return the primary (personal) sheet for backwards compatibility."""
        return self.sheets.get("personal")


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_SCHEMA_PATH = PROJECT_ROOT.parent / "config" / "smartsheet.yml"


def _load_yaml(path: Path) -> Dict[str, Any]:
    if yaml is None:
        raise SchemaError(
            "PyYAML is required to load config/smartsheet.yml. Install it with "
            "'pip install pyyaml' or convert the config to JSON."
        ) from _yaml_import_error

    if not path.exists():
        raise SchemaError(f"Schema file not found at {path}")

    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def load_multi_sheet_config(path: Optional[Path] = None) -> MultiSheetConfig:
    """Load multi-sheet configuration from YAML."""
    path = path or DEFAULT_SCHEMA_PATH
    data = _load_yaml(path)

    required_fields = data.get("required_fields") or []
    priority_values = data.get("priority_values", {}).get("ordered", [])
    project_values = data.get("project_values", [])

    sheets_data = data.get("sheets") or {}
    sheets: Dict[str, SheetSchema] = {}

    for source_key, sheet_cfg in sheets_data.items():
        sheet_id = str(sheet_cfg.get("id", "")).strip()
        if not sheet_id:
            continue  # Skip sheets without ID

        columns_data = sheet_cfg.get("columns") or {}
        columns: Dict[str, ColumnDefinition] = {}
        for field_name, column_cfg in columns_data.items():
            column_id = str(column_cfg.get("column_id", ""))
            columns[field_name] = ColumnDefinition(
                field=field_name,
                column_id=column_id,
                col_type=str(column_cfg.get("type", "text")),
                optional=bool(column_cfg.get("optional", False)),
                allowed_values=list(column_cfg.get("allowed_values", []) or []),
            )

        sheets[source_key] = SheetSchema(
            sheet_id=sheet_id,
            name=sheet_cfg.get("name", source_key),
            source_key=source_key,
            include_in_all=bool(sheet_cfg.get("include_in_all", True)),
            columns=columns,
            required_fields=list(required_fields),
            priority_values=list(priority_values),
            project_values=list(project_values),
        )

    return MultiSheetConfig(
        sheets=sheets,
        required_fields=list(required_fields),
        priority_values=list(priority_values),
        project_values=list(project_values),
    )


def load_schema(path: Optional[Path] = None) -> SheetSchema:
    """Load the Smartsheet schema metadata from YAML (legacy single-sheet)."""
    config = load_multi_sheet_config(path)
    if config.primary_sheet:
        return config.primary_sheet

    # Fallback to legacy format if no multi-sheet config
    path = path or DEFAULT_SCHEMA_PATH
    data = _load_yaml(path)

    sheet = data.get("sheet") or {}
    columns_data = data.get("columns") or {}
    required_fields = data.get("required_fields") or []
    priority_values = data.get("priority_values", {}).get("ordered", [])
    project_values = data.get("project_values", [])

    columns: Dict[str, ColumnDefinition] = {}
    for field_name, column_cfg in columns_data.items():
        column_id = str(column_cfg.get("column_id", ""))
        columns[field_name] = ColumnDefinition(
            field=field_name,
            column_id=column_id,
            col_type=str(column_cfg.get("type", "text")),
            optional=bool(column_cfg.get("optional", False)),
            allowed_values=list(column_cfg.get("allowed_values", []) or []),
        )

    sheet_id = str(sheet.get("id", "")).strip()
    if not sheet_id:
        raise SchemaError("Sheet ID missing from smartsheet.yml")

    return SheetSchema(
        sheet_id=sheet_id,
        name=sheet.get("name", "Unknown"),
        source_key="personal",
        include_in_all=True,
        columns=columns,
        required_fields=list(required_fields),
        priority_values=list(priority_values),
        project_values=list(project_values),
    )


class SmartsheetClient:
    """Very small Smartsheet REST wrapper for sheet reads."""

    base_url = "https://api.smartsheet.com/2.0"

    def __init__(
        self,
        settings: Settings,
        *,
        schema_path: Optional[Path] = None,
        timeout_seconds: int = 15,
    ) -> None:
        self.settings = settings
        self.multi_config = load_multi_sheet_config(schema_path)
        self.schema = self.multi_config.primary_sheet or load_schema(schema_path)
        self.timeout_seconds = timeout_seconds
        self._last_fetch_used_live = False
        self._row_errors: List[str] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def list_tasks(
        self,
        *,
        limit: Optional[int] = None,
        fallback_to_stub: bool = True,
        sources: Optional[List[str]] = None,
        include_work_in_all: bool = False,
    ) -> List[TaskDetail]:
        """Return TaskDetail rows, pulling live data when schema is ready.

        Args:
            limit: Maximum number of tasks to return (per sheet).
            fallback_to_stub: If True, fall back to stubbed data on API errors.
            sources: List of source keys to fetch from (e.g., ["personal", "work"]).
                     If None, fetches from sources included in 'ALL' filter.
            include_work_in_all: If True, include work tasks even when sources is None.
        """
        self._last_fetch_used_live = False
        self._row_errors = []

        # Determine which sheets to fetch from
        if sources is not None:
            target_sources = sources
        elif include_work_in_all:
            target_sources = self.multi_config.get_all_sources()
        else:
            target_sources = self.multi_config.get_sources_for_all_filter()

        all_tasks: List[TaskDetail] = []
        all_errors: List[str] = []
        any_live = False

        for source_key in target_sources:
            schema = self.multi_config.sheets.get(source_key)
            if not schema:
                continue

            if not schema.ready_for_live:
                if fallback_to_stub and source_key == "personal":
                    all_tasks.extend(fetch_stubbed_tasks(limit=limit))
                continue

            try:
                payload = self._request(
                    "GET",
                    f"/sheets/{schema.sheet_id}",
                    params={"include": "objectValue,rowNumbers,childIds"},
                )
                any_live = True
            except SmartsheetAPIError:
                if fallback_to_stub and source_key == "personal":
                    all_tasks.extend(fetch_stubbed_tasks(limit=limit))
                continue

            details, errors = self._rows_to_details(
                payload.get("rows", []),
                limit=limit,
                schema=schema,
                source_key=source_key,
            )
            all_tasks.extend(details)
            all_errors.extend(errors)

        self._last_fetch_used_live = any_live
        self._row_errors = all_errors
        return all_tasks

    def get_available_sources(self) -> List[str]:
        """Return list of available source keys."""
        return self.multi_config.get_all_sources()

    def get_work_tasks_count(self) -> Dict[str, int]:
        """Return counts of work tasks by urgency for the badge indicator.

        Returns dict with:
            - urgent: count of Critical/Urgent priority tasks
            - due_soon: count of tasks due within 3 days
            - overdue: count of overdue tasks
            - total: total work tasks
        """
        work_schema = self.multi_config.sheets.get("work")
        if not work_schema or not work_schema.ready_for_live:
            return {"urgent": 0, "due_soon": 0, "overdue": 0, "total": 0}

        try:
            payload = self._request(
                "GET",
                f"/sheets/{work_schema.sheet_id}",
                params={"include": "objectValue,rowNumbers,childIds"},
            )
        except SmartsheetAPIError:
            return {"urgent": 0, "due_soon": 0, "overdue": 0, "total": 0}

        details, _ = self._rows_to_details(
            payload.get("rows", []),
            limit=None,
            schema=work_schema,
            source_key="work",
        )

        # Filter out completed/cancelled tasks
        active_tasks = [
            t for t in details
            if t.status.lower() not in ("completed", "cancelled")
        ]

        from datetime import datetime, timedelta
        now = datetime.utcnow()
        three_days = now + timedelta(days=3)

        urgent = sum(1 for t in active_tasks if t.priority in ("Critical", "Urgent"))
        due_soon = sum(1 for t in active_tasks if now <= t.due <= three_days)
        overdue = sum(1 for t in active_tasks if t.due < now)

        return {
            "urgent": urgent,
            "due_soon": due_soon,
            "overdue": overdue,
            "total": len(active_tasks),
        }

    def _get_schema_for_source(self, source: str = "personal") -> SheetSchema:
        """Get the schema for a given source key."""
        schema = self.multi_config.sheets.get(source)
        if not schema:
            # Fall back to primary schema
            return self.schema
        return schema

    def post_comment(self, row_id: str, text: str, *, source: str = "personal") -> None:
        """Create a discussion comment on a row.

        Args:
            row_id: The Smartsheet row ID
            text: Comment text
            source: Source key ("personal" or "work") to determine which sheet
        """
        schema = self._get_schema_for_source(source)
        payload = {
            "comment": {"text": text},
        }
        try:
            self._request(
                "POST",
                f"/sheets/{schema.sheet_id}/rows/{row_id}/discussions",
                body=payload,
            )
        except SmartsheetAPIError as exc:
            raise SmartsheetAPIError(f"Failed to post comment: {exc}") from exc

    def update_row(
        self, row_id: str, updates: Dict[str, Any], *, source: str = "personal"
    ) -> Dict[str, Any]:
        """Update one or more cells in a row.
        
        Args:
            row_id: The Smartsheet row ID to update
            updates: Dict mapping field names to new values. Supported fields:
                     status, priority, due_date, notes, done, project, etc.
            source: Source key ("personal" or "work") to determine which sheet
        
        Returns:
            The API response containing the updated row data.
        
        Raises:
            SmartsheetAPIError: If the API call fails
            ValueError: If a field value fails validation
        """
        if not updates:
            raise ValueError("No updates provided")

        schema = self._get_schema_for_source(source)
        cells = []
        for field_name, value in updates.items():
            column = schema.columns.get(field_name)
            if not column:
                raise ValueError(f"Unknown field: {field_name}")

            # Validate against allowed values if defined
            if column.allowed_values and value not in column.allowed_values:
                raise ValueError(
                    f"Invalid value '{value}' for field '{field_name}'. "
                    f"Allowed: {column.allowed_values}"
                )

            # Checkbox columns expect boolean values (True/False), not integers
            cell_value = value
            if column.col_type == "checkbox":
                # Ensure boolean type for checkbox
                cell_value = bool(value)

            # Handle special column types that require objectValue format
            if field_name == "recurring_pattern":
                # MULTI_PICKLIST requires objectValue with values array
                cells.append({
                    "columnId": int(column.column_id),
                    "objectValue": {
                        "objectType": "MULTI_PICKLIST",
                        "values": [cell_value] if cell_value else []
                    },
                })
            elif column.col_type == "contact" and cell_value:
                # Contact columns require objectValue with email
                cells.append({
                    "columnId": int(column.column_id),
                    "objectValue": {
                        "objectType": "MULTI_CONTACT",
                        "values": [{
                            "objectType": "CONTACT",
                            "email": str(cell_value)
                        }]
                    },
                })
            else:
                cells.append({
                    "columnId": int(column.column_id),
                    "value": cell_value,
                })

        payload = [{"id": int(row_id), "cells": cells}]

        try:
            response = self._request(
                "PUT",
                f"/sheets/{schema.sheet_id}/rows",
                body=payload,
            )
            return response
        except SmartsheetAPIError as exc:
            raise SmartsheetAPIError(f"Failed to update row {row_id}: {exc}") from exc

    def mark_complete(self, row_id: str, *, source: str = "personal") -> Dict[str, Any]:
        """Mark a task as complete by setting Status='Completed' and Done=true.
        
        Args:
            row_id: The Smartsheet row ID to mark complete
            source: Source key ("personal" or "work") to determine which sheet
            
        Returns:
            The API response containing the updated row data.
        """
        return self.update_row(row_id, {
            "status": "Completed",
            "done": True,
        }, source=source)

    @property
    def last_fetch_used_live(self) -> bool:
        return self._last_fetch_used_live

    @property
    def row_errors(self) -> List[str]:
        return self._row_errors

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _rows_to_details(
        self,
        rows: Iterable[Dict[str, Any]],
        *,
        limit: Optional[int],
        schema: Optional[SheetSchema] = None,
        source_key: str = "personal",
    ) -> Tuple[List[TaskDetail], List[str]]:
        schema = schema or self.schema
        summaries: List[TaskDetail] = []
        errors: List[str] = []
        for row in rows:
            if self._is_parent_row(row):
                continue
            cell_map = self._cells_by_column(row.get("cells", []))
            try:
                # Parse done checkbox - convert to boolean
                done_value = self._cell_value(cell_map, "done", allow_optional=True, schema=schema)
                is_done = bool(done_value) if done_value is not None else False
                
                summary = TaskDetail(
                    row_id=str(row.get("id")),
                    title=self._cell_value(cell_map, "task", schema=schema),
                    status=self._cell_value(cell_map, "status", schema=schema),
                    due=self._parse_due_date(self._cell_value(cell_map, "due_date", schema=schema)),
                    priority=self._cell_value(cell_map, "priority", schema=schema),
                    project=self._cell_value(cell_map, "project", schema=schema),
                    assigned_to=self._cell_value(
                        cell_map, "assigned_to", allow_optional=True, schema=schema
                    ),
                    estimated_hours=self._coerce_estimated_hours(
                        self._cell_value(cell_map, "estimated_hours", allow_optional=True, schema=schema)
                    ),
                    notes=self._cell_value(cell_map, "notes", allow_optional=True, schema=schema),
                    next_step=self._cell_value(
                        cell_map, "notes", allow_optional=True, schema=schema
                    )
                    or "Review notes",
                    automation_hint=self._derive_hint(cell_map, schema=schema),
                    source=source_key,
                    done=is_done,
                )
            except (KeyError, ValueError) as exc:
                errors.append(self._format_row_error(row, exc))
                continue

            summaries.append(summary)
            if limit is not None and len(summaries) >= limit:
                break

        return summaries, errors

    def _is_parent_row(self, row: Dict[str, Any]) -> bool:
        child_ids = row.get("childIds") or []
        return bool(child_ids)

    def _format_row_error(self, row: Dict[str, Any], exc: Exception) -> str:
        row_number = row.get("rowNumber")
        row_id = row.get("id")
        if row_number:
            label = f"Row {row_number}"
        else:
            label = f"Row ID {row_id}"
        return f"{label}: {exc}. Check schema and sheet data."

    def _cells_by_column(self, cells: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
        lookup: Dict[str, Any] = {}
        for cell in cells:
            column_id = str(cell.get("columnId"))
            lookup[column_id] = cell.get("displayValue") or cell.get("value")
        return lookup

    def _cell_value(
        self,
        cell_map: Dict[str, Any],
        field_name: str,
        *,
        allow_optional: bool = False,
        schema: Optional[SheetSchema] = None,
    ) -> Any:
        """Extract a cell value from the row data.
        
        Note: This method does NOT validate against allowed_values when reading.
        Validation only happens in update_row() when writing changes.
        This allows existing Smartsheet data to be read even if it doesn't
        match the current picklist configuration.
        """
        schema = schema or self.schema
        column = schema.columns.get(field_name)
        if not column:
            raise SchemaError(f"Field '{field_name}' missing from schema config.")

        value = cell_map.get(column.column_id)
        if value in (None, ""):
            if column.optional or allow_optional:
                return None
            raise KeyError(f"Required field '{field_name}' missing in sheet row.")

        # No validation on read - only validate on write (in update_row)
        return value

    def _parse_due_date(self, value: Any):
        from datetime import datetime

        if isinstance(value, datetime):
            return value
        if isinstance(value, (int, float)):
            # Smartsheet may provide timestamps (milliseconds since epoch)
            return datetime.utcfromtimestamp(value / 1000)
        if isinstance(value, str):
            for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y-%m-%dT%H:%M:%S%z"):
                try:
                    return datetime.strptime(value, fmt)
                except ValueError:
                    continue
        raise ValueError(f"Unable to parse due date value: {value}")

    def _derive_hint(
        self, cell_map: Dict[str, Any], *, schema: Optional[SheetSchema] = None
    ) -> str:
        schema = schema or self.schema
        priority = self._cell_value(cell_map, "priority", schema=schema)
        status = self._cell_value(cell_map, "status", schema=schema)
        project = self._cell_value(cell_map, "project", schema=schema)
        return f"{priority} {project} task currently {status.lower()}"

    def _coerce_estimated_hours(self, value: Any) -> Optional[float]:
        if value in (None, ""):
            return None
        if isinstance(value, (int, float)):
            return float(value)
        text = str(value).strip()
        if not text:
            return None
        # Handle ranges like "1-2" by averaging.
        if "-" in text:
            bounds = [b for b in text.split("-") if b.strip()]
            numbers = []
            for bound in bounds:
                try:
                    numbers.append(float(bound))
                except ValueError:
                    continue
            if numbers:
                return sum(numbers) / len(numbers)
        # Handle "<1" or "0.5+" styles
        digits = "".join(ch for ch in text if (ch.isdigit() or ch == "." or ch == ","))
        digits = digits.replace(",", "")
        try:
            return float(digits)
        except ValueError:
            return None

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        body: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        url = f"{self.base_url}{path}"
        if params:
            query = urlparse.urlencode(params)
            url = f"{url}?{query}"

        data: Optional[bytes] = None
        headers = {
            "Authorization": f"Bearer {self.settings.smartsheet_token}",
            "Accept": "application/json",
        }

        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"

        req = urlrequest.Request(url, data=data, method=method, headers=headers)

        try:
            with urlrequest.urlopen(req, timeout=self.timeout_seconds) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw)
        except urlerror.HTTPError as exc:  # pragma: no cover - network path
            detail = exc.read().decode("utf-8", errors="ignore")
            raise SmartsheetAPIError(
                f"Smartsheet API {method} {path} failed with status {exc.code}: {detail}"
            ) from exc
        except urlerror.URLError as exc:  # pragma: no cover - network path
            raise SmartsheetAPIError(f"Network error calling Smartsheet: {exc}") from exc