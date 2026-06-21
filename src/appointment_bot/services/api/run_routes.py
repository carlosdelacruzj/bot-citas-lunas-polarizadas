from __future__ import annotations

from dataclasses import asdict
from http import HTTPStatus
from typing import Any
from urllib.parse import unquote

from appointment_bot.services.api.http import error_payload
from appointment_bot.services.postgres_database import get_run, list_runs


def list_runs_payload(query: dict[str, list[str]]) -> dict[str, Any]:
    limit = query_int(query, "limit", default=50, minimum=1, maximum=200)
    offset = query_int(query, "offset", default=0, minimum=0, maximum=10_000)
    order_id = query_text(query, "order_id")
    status = query_text(query, "status")
    return {
        "runs": [_public_run(run) for run in list_runs(
            limit=limit,
            offset=offset,
            order_id=order_id,
            status=status,
        )],
        "limit": limit,
        "offset": offset,
    }


def get_run_payload(path: str) -> tuple[HTTPStatus, dict[str, Any]]:
    run_id = unquote(path.removeprefix("/api/v1/runs/")).strip()
    run = get_run(run_id) if run_id else None
    if run is None:
        return HTTPStatus.NOT_FOUND, error_payload("not_found", "Run not found.")
    return HTTPStatus.OK, _public_run(run)


def _public_run(run: Any) -> dict[str, Any]:
    return asdict(run)


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
