"""Smartsheet connector scaffolding for the Daily Task Assistant."""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from urllib import error as urlerror
from urllib import parse as urlparse
from urllib import request as urlrequest

from .config import Settings
from .tasks import TaskSummary, fetch_stubbed_tasks

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

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def list_tasks(self, *, limit: int = 50, fallback_to_stub: bool = True) -> List[TaskSummary]:
        """Return TaskSummary rows, pulling live data when schema is ready."""

        self._last_fetch_used_live = False
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
                params={"include": "objectValue"},
            )
            self._last_fetch_used_live = True
        except SmartsheetAPIError:
            if fallback_to_stub:
                return fetch_stubbed_tasks(limit=limit)
            raise

        return self._rows_to_summaries(payload.get("rows", []), limit=limit)

    @property
    def last_fetch_used_live(self) -> bool:
        return self._last_fetch_used_live

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _rows_to_summaries(self, rows: Iterable[Dict[str, Any]], *, limit: int) -> List[TaskSummary]:
        summaries: List[TaskSummary] = []
        for row in rows:
            cell_map = self._cells_by_column(row.get("cells", []))
            try:
                summary = TaskSummary(
                    row_id=str(row.get("id")),
                    title=self._cell_value(cell_map, "task"),
                    status=self._cell_value(cell_map, "status"),
                    due=self._parse_due_date(self._cell_value(cell_map, "due_date")),
                    next_step=self._cell_value(cell_map, "notes", allow_optional=True)
                    or "Review notes",  # fallback placeholder
                    automation_hint=self._derive_hint(cell_map),
                )
            except (KeyError, ValueError) as exc:
                raise SchemaError(
                    f"Failed to map row {row.get('id')} to TaskSummary: {exc}"
                ) from exc

            summaries.append(summary)
            if len(summaries) >= limit:
                break

        return summaries

    def _cells_by_column(self, cells: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
        lookup: Dict[str, Any] = {}
        for cell in cells:
            column_id = str(cell.get("columnId"))
            lookup[column_id] = cell.get("displayValue") or cell.get("value")
        return lookup

    def _cell_value(self, cell_map: Dict[str, Any], field_name: str, *, allow_optional: bool = False) -> Any:
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