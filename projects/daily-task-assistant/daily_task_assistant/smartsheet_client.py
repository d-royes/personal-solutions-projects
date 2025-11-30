"""Smartsheet connector scaffolding for the Daily Task Assistant."""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
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
    optional: bool = False
    allowed_values: Optional[List[str]] = None


@dataclass(slots=True)
class SheetSchema:
    sheet_id: str
    columns: Dict[str, ColumnDefinition]
    required_fields: List[str]
    priority_values: List[str]
    project_values: List[str]

    @property
    def ready_for_live(self) -> bool:
        return all(
            not col.column_id.startswith("TODO") for col in self.columns.values()
        )


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


def load_schema(path: Optional[Path] = None) -> SheetSchema:
    """Load the Smartsheet schema metadata from YAML."""

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
            optional=bool(column_cfg.get("optional", False)),
            allowed_values=list(column_cfg.get("allowed_values", []) or []),
        )

    sheet_id = str(sheet.get("id", "")).strip()
    if not sheet_id:
        raise SchemaError("Sheet ID missing from smartsheet.yml")

    return SheetSchema(
        sheet_id=sheet_id,
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
        self.schema = load_schema(schema_path)
        self.timeout_seconds = timeout_seconds
        self._last_fetch_used_live = False
        self._row_errors: List[str] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def list_tasks(
        self, *, limit: Optional[int] = None, fallback_to_stub: bool = True
    ) -> List[TaskDetail]:
        """Return TaskDetail rows, pulling live data when schema is ready."""

        self._last_fetch_used_live = False
        self._row_errors = []
        if not self.schema.ready_for_live:
            if fallback_to_stub:
                return fetch_stubbed_tasks(limit=limit)
            raise SchemaError(
                "Column IDs still use placeholder values. Update config/smartsheet.yml "
                "with real columnId entries before attempting live reads."
            )

        try:
            payload = self._request(
                "GET",
                f"/sheets/{self.schema.sheet_id}",
                params={"include": "objectValue,rowNumbers,childIds"},
            )
            self._last_fetch_used_live = True
        except SmartsheetAPIError:
            if fallback_to_stub:
                self._row_errors = []
                return fetch_stubbed_tasks(limit=limit)
            raise

        details, errors = self._rows_to_details(payload.get("rows", []), limit=limit)
        self._row_errors = errors
        return details

    def post_comment(self, row_id: str, text: str) -> None:
        """Create a discussion comment on a row."""

        payload = {
            "comment": {"text": text},
        }
        try:
            self._request(
                "POST",
                f"/sheets/{self.schema.sheet_id}/rows/{row_id}/discussions",
                body=payload,
            )
        except SmartsheetAPIError as exc:
            raise SmartsheetAPIError(f"Failed to post comment: {exc}") from exc

    def update_row(self, row_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """Update one or more cells in a row.
        
        Args:
            row_id: The Smartsheet row ID to update
            updates: Dict mapping field names to new values. Supported fields:
                     status, priority, due_date, notes, done, project, etc.
        
        Returns:
            The API response containing the updated row data.
        
        Raises:
            SmartsheetAPIError: If the API call fails
            ValueError: If a field value fails validation
        """
        if not updates:
            raise ValueError("No updates provided")

        cells = []
        for field_name, value in updates.items():
            column = self.schema.columns.get(field_name)
            if not column:
                raise ValueError(f"Unknown field: {field_name}")

            # Validate against allowed values if defined
            if column.allowed_values and value not in column.allowed_values:
                raise ValueError(
                    f"Invalid value '{value}' for field '{field_name}'. "
                    f"Allowed: {column.allowed_values}"
                )

            cells.append({
                "columnId": int(column.column_id),
                "value": value,
            })

        payload = [{"id": int(row_id), "cells": cells}]

        try:
            response = self._request(
                "PUT",
                f"/sheets/{self.schema.sheet_id}/rows",
                body=payload,
            )
            return response
        except SmartsheetAPIError as exc:
            raise SmartsheetAPIError(f"Failed to update row {row_id}: {exc}") from exc

    def mark_complete(self, row_id: str) -> Dict[str, Any]:
        """Mark a task as complete by setting Status='Complete' and Done=true.
        
        Args:
            row_id: The Smartsheet row ID to mark complete
            
        Returns:
            The API response containing the updated row data.
        """
        return self.update_row(row_id, {
            "status": "Complete",
            "done": True,
        })

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
        self, rows: Iterable[Dict[str, Any]], *, limit: Optional[int]
    ) -> Tuple[List[TaskDetail], List[str]]:
        summaries: List[TaskDetail] = []
        errors: List[str] = []
        for row in rows:
            if self._is_parent_row(row):
                continue
            cell_map = self._cells_by_column(row.get("cells", []))
            try:
                summary = TaskDetail(
                    row_id=str(row.get("id")),
                    title=self._cell_value(cell_map, "task"),
                    status=self._cell_value(cell_map, "status"),
                    due=self._parse_due_date(self._cell_value(cell_map, "due_date")),
                    priority=self._cell_value(cell_map, "priority"),
                    project=self._cell_value(cell_map, "project"),
                    assigned_to=self._cell_value(
                        cell_map, "assigned_to", allow_optional=True
                    ),
                    estimated_hours=self._coerce_estimated_hours(
                        self._cell_value(cell_map, "estimated_hours", allow_optional=True)
                    ),
                    notes=self._cell_value(cell_map, "notes", allow_optional=True),
                    next_step=self._cell_value(
                        cell_map, "notes", allow_optional=True
                    )
                    or "Review notes",
                    automation_hint=self._derive_hint(cell_map),
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
        self, cell_map: Dict[str, Any], field_name: str, *, allow_optional: bool = False
    ) -> Any:
        column = self.schema.columns.get(field_name)
        if not column:
            raise SchemaError(f"Field '{field_name}' missing from schema config.")

        value = cell_map.get(column.column_id)
        if value in (None, ""):
            if column.optional or allow_optional:
                return None
            raise KeyError(f"Required field '{field_name}' missing in sheet row.")

        if column.allowed_values and value not in column.allowed_values:
            raise ValueError(
                f"Field '{field_name}' has invalid value '{value}'. Expected one of {column.allowed_values}."
            )

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

    def _derive_hint(self, cell_map: Dict[str, Any]) -> str:
        priority = self._cell_value(cell_map, "priority")
        status = self._cell_value(cell_map, "status")
        project = self._cell_value(cell_map, "project")
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