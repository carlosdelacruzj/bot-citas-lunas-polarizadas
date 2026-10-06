from __future__ import annotations

from dataclasses import asdict
from http import HTTPStatus
from typing import Any
from urllib.parse import unquote

from appointment_bot.core.statuses import sanitize_details
from appointment_bot.db.runs import get_run, list_runs
from appointment_bot.services.api.http import error_payload

PUBLIC_RUN_FIELDS = (
    "run_id",
    "order_id",
    "status",
    "message",
    "exit_code",
    "started_at",
    "finished_at",
    "duration_seconds",
    "reservation_attempted",
    "reservation_confirmed",
    "screenshot_path",
    "screenshot_count",
    "created_at",
)

PUBLIC_RUN_DETAIL_FIELDS = PUBLIC_RUN_FIELDS + ("screenshot_paths",)


def list_runs_payload(query: dict[str, list[str]]) -> dict[str, Any]:
    limit = query_int(query, "limit", default=50, minimum=1, maximum=200)
    offset = query_int(query, "offset", default=0, minimum=0, maximum=10_000)
    order_id = query_text(query, "order_id")
    status = query_text(query, "status")
    return {
        "runs": [
            _public_run(run)
            for run in list_runs(
                limit=limit,
                offset=offset,
                order_id=order_id,
                status=status,
            )
        ],
        "limit": limit,
        "offset": offset,
    }


def get_run_payload(path: str, query: dict[str, list[str]]) -> tuple[HTTPStatus, dict[str, Any]]:
    run_id = unquote(path.removeprefix("/api/v1/runs/")).strip()
    run = get_run(run_id) if run_id else None
    if run is None:
        return HTTPStatus.NOT_FOUND, error_payload("not_found", "Run not found.")
    include_details = query_bool(query, "include_details", default=False)
    return HTTPStatus.OK, _public_run_detail(run, include_details=include_details)


def _public_run(run: Any) -> dict[str, Any]:
    payload = asdict(run)
    return {field: payload.get(field) for field in PUBLIC_RUN_FIELDS}


def _public_run_detail(run: Any, *, include_details: bool) -> dict[str, Any]:
    payload = asdict(run)
    public_payload = {field: payload.get(field) for field in PUBLIC_RUN_DETAIL_FIELDS}
    if include_details:
        details = payload.get("details")
        public_payload["details"] = sanitize_details(details) if isinstance(details, dict) else None
    return public_payload


def query_int(
    query: dict[str, list[str]],
    name: str,
    *,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    raw = query.get(name, [str(default)])[0]
    try:
        value = int(raw)
    except ValueError:
        value = default
    return min(max(value, minimum), maximum)


def query_text(query: dict[str, list[str]], name: str) -> str | None:
    value = query.get(name, [""])[0].strip()
    return value or None


def query_bool(query: dict[str, list[str]], name: str, *, default: bool) -> bool:
    value = query.get(name, [""])[0].strip().lower()
    if not value:
        return default
    return value in {"1", "true", "yes", "y", "on"}
